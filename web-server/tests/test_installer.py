import grp
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_BLOCKS = re.findall(
    r"<<'PY'\n(.*?)\nPY", (ROOT / "pi-server/deploy/install.sh").read_text(), re.S
)


class TestInstallerSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sdv_installer_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.group = grp.getgrgid(os.getgid()).gr_name

    def _prepare_directories(self):
        args = ["installer", str(self.root / "config"), str(self.root / "install"),
                str(self.root / "data"), str(self.root / "logs"), self.user, self.group]
        with patch.object(sys, "argv", args), patch("os.fchown") as ownership:
            exec(compile(INSTALLER_BLOCKS[0], "installer directories", "exec"), {})
        return ownership

    def test_data_parent_is_root_owned_before_staging_is_opened(self):
        ownership = self._prepare_directories()
        self.assertEqual(ownership.call_args_list[2].args[1:], (0, 0))
        self.assertEqual(ownership.call_args_list[3].args[1:], (os.getuid(), os.getgid()))
        self.assertEqual(stat.S_IMODE((self.root / "data").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.root / "data/staging").stat().st_mode), 0o750)

    def test_staging_symlink_is_rejected_without_changing_target(self):
        (self.root / "data").mkdir()
        target = self.root / "unrelated"
        target.mkdir(mode=0o700)
        (self.root / "data/staging").symlink_to(target)
        with self.assertRaises(OSError):
            self._prepare_directories()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)

    def test_config_is_group_readable_even_with_restrictive_umask(self):
        self._prepare_directories()
        args = ["installer", str(self.root / "config"),
                str(ROOT / "pi-server/config.example.json"), self.user, self.group,
                str(self.root), str(self.root / "apps"), str(self.root / "data"),
                str(self.root / "logs")]
        previous_umask = os.umask(0o077)
        try:
            with patch.object(sys, "argv", args), patch("os.fchown"):
                exec(compile(INSTALLER_BLOCKS[1], "installer config", "exec"), {})
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE((self.root / "config/config.json").stat().st_mode), 0o640)
        apps_dir = self.root / "apps"
        self.assertEqual(stat.S_IMODE(apps_dir.stat().st_mode), 0o750)
        self.assertEqual(apps_dir.stat().st_uid, os.getuid())
        self.assertEqual(apps_dir.stat().st_gid, os.getgid())

    def test_apps_dir_symlink_is_rejected_before_config_publish(self):
        self._prepare_directories()
        target = self.root / "outside"
        target.mkdir()
        (self.root / "apps").symlink_to(target)
        args = ["installer", str(self.root / "config"),
                str(ROOT / "pi-server/config.example.json"), self.user, self.group,
                str(self.root), str(self.root / "apps"), str(self.root / "data"),
                str(self.root / "logs")]
        with patch.object(sys, "argv", args), patch("os.fchown"):
            with self.assertRaises(OSError):
                exec(compile(INSTALLER_BLOCKS[1], "installer config", "exec"), {})
        self.assertFalse((self.root / "config/config.json").exists())

    def test_nested_apps_dir_parents_are_traversable_under_restrictive_umask(self):
        self._prepare_directories()
        nested_apps = self.root / "data/custom/apps"
        config = json.loads((ROOT / "pi-server/config.example.json").read_text())
        config["apps_dir"] = str(nested_apps)
        (self.root / "config/config.json").write_text(json.dumps(config))
        args = ["installer", str(self.root / "config"),
                str(ROOT / "pi-server/config.example.json"), self.user, self.group,
                str(self.root), str(self.root / "apps"), str(self.root / "data"),
                str(self.root / "logs")]
        previous_umask = os.umask(0o077)
        try:
            with patch.object(sys, "argv", args), patch("os.fchown"):
                exec(compile(INSTALLER_BLOCKS[1], "installer config", "exec"), {})
        finally:
            os.umask(previous_umask)

        self.assertEqual(stat.S_IMODE((self.root / "data/custom").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(nested_apps.stat().st_mode), 0o750)
        self.assertTrue(os.access(self.root / "data/custom/apps", os.X_OK))

    def test_remote_copy_install_and_cleanup_use_the_same_private_directory(self):
        commands = self.root / "commands"
        commands.mkdir()
        log = self.root / "remote-calls.jsonl"
        for name in ("bash", "ssh", "scp"):
            executable = commands / name
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "with open(os.environ['REMOTE_CALL_LOG'], 'a') as output:\n"
                "    output.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')\n"
                "if 'uname' in sys.argv and '-m' in sys.argv:\n"
                "    print('aarch64')\n"
                "elif any('mktemp -d' in arg for arg in sys.argv):\n"
                "    print('/tmp/sdv-deployer.Abc1234567')\n",
                encoding="utf-8"
            )
            executable.chmod(0o755)
        environment = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}",
                           REMOTE_CALL_LOG=str(log))
        result = subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/install_on_pi.sh"), "pi@example"],
            env=environment, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        copy = next(call for call in calls if call[0] == "scp")
        install = next(call for call in calls if call[0] == "ssh" and "-t" in call)
        cleanup = calls[-1]
        for call in (copy, install, cleanup):
            self.assertIn("/tmp/sdv-deployer.Abc1234567", " ".join(call))
        self.assertIn("rm -rf -- '/tmp/sdv-deployer.Abc1234567'", cleanup[-1])


if __name__ == "__main__":
    unittest.main()
