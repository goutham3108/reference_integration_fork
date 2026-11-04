import importlib.util
import io
import json
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("legacy_deployment_server", SERVER_PATH)
legacy_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy_server)


class TestLegacyServerReviewFixes(unittest.TestCase):
    def setUp(self):
        systemctl_which = legacy_server.shutil.which
        self.systemctl_patch = patch.object(
            legacy_server.shutil,
            "which",
            side_effect=lambda executable: None if executable == "systemctl"
            else systemctl_which(executable)
        )
        self.systemctl_patch.start()
        self.addCleanup(self.systemctl_patch.stop)
        self.root = Path(tempfile.mkdtemp(prefix="legacy_deployer_test_"))
        self.config = legacy_server.DeploymentConfig()
        self.config.apps_dir = str(self.root / "apps")
        self.config.staging_dir = str(self.root / "staging")
        self.config.logs_dir = str(self.root / "logs")
        self.config.data_dir = str(self.root / "data")
        self.config.smoke_test_seconds = 1
        self.app_manager = legacy_server.ApplicationManager(self.config)

    def tearDown(self):
        for app_id in list(self.app_manager.processes):
            self.app_manager.stop_application(app_id)
        shutil.rmtree(self.root, ignore_errors=True)

    def _archive(self, members):
        archive = self.root / "bundle.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name, payload in members:
                info = tarfile.TarInfo(name)
                if payload is None:
                    info.type = tarfile.FIFOTYPE
                    tar.addfile(info)
                else:
                    info.size = len(payload)
                    tar.addfile(info, io.BytesIO(payload))
        return archive

    def test_archive_rejects_special_files_and_limits_expansion(self):
        validator = legacy_server.BenchmarkValidator(self.config)
        archive = self._archive([("pipe", None)])
        result = validator.validate_package(archive, self.root / "fifo")
        self.assertFalse(result["passed"])
        self.assertIn("Unsupported archive member type", result["errors"][0])

        self.config.max_expanded_size_mb = 0
        archive = self._archive([("payload", b"x")])
        result = validator.validate_package(archive, self.root / "oversized")
        self.assertFalse(result["passed"])
        self.assertIn("expanded size limit", result["errors"][0])

    def test_manifest_paths_and_arguments_are_validated(self):
        validator = legacy_server.BenchmarkValidator(self.config)
        self._archive([("manifest.json", json.dumps({
            "app_id": "sample", "version": "../escape", "runtime": "python",
            "entrypoint": "app.py", "args": []
        }).encode())])
        result = validator.validate_package(self.root / "bundle.tar.gz", self.root / "extract")
        self.assertFalse(result["passed"])
        self.assertTrue(any("safe single path component" in error for error in result["errors"]))

        self.assertIsNone(validator._resolve_bundle_file(self.root, "../outside"))
        self.assertIsNone(validator._resolve_bundle_file(self.root, "/etc/passwd"))
        self.assertIsNone(legacy_server.DeploymentRequestHandler._app_route(
            "/api/v1/apps/sample/extra/delete"
        ))

    def test_validation_marks_later_stages_not_run(self):
        validator = legacy_server.BenchmarkValidator(self.config)
        archive = self._archive([("payload.txt", b"no manifest")])
        result = validator.validate_package(archive, self.root / "no-manifest")
        stages = result["stages"]
        self.assertEqual(stages["stage1_archive_safety"]["status"], "passed")
        self.assertEqual(stages["stage2_manifest_checksum"]["status"], "failed")
        for key in ("stage3_compatibility", "stage4_security_permissions", "stage5_startup_smoke"):
            self.assertEqual(stages[key]["status"], "not_run")
            self.assertEqual(stages[key]["details"], [])

    def _make_version(self, version, script, args):
        staging = self.root / f"staging-{version}"
        staging.mkdir()
        (staging / "app.py").write_text(script, encoding="utf-8")
        (staging / "manifest.json").write_text(json.dumps({
            "app_id": "sample", "version": version, "runtime": "python",
            "entrypoint": "app.py", "args": args
        }), encoding="utf-8")
        return staging, json.loads((staging / "manifest.json").read_text())

    def test_install_args_process_groups_and_rollback_metadata(self):
        first_script = "import sys, time; print(sys.argv[1], flush=True); time.sleep(30)\n"
        first_staging, first_manifest = self._make_version("1.0", first_script, ["first-arg"])
        self.app_manager.install_and_activate("sample", "1.0", first_staging, first_manifest)
        log_file = Path(self.config.logs_dir) / "sample.log"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and "first-arg" not in log_file.read_text():
            time.sleep(0.05)
        self.assertIn("first-arg", log_file.read_text())
        first_record = self.app_manager._read_process_record("sample")
        self.assertTrue(self.app_manager._process_group_members(first_record))

        second_staging, second_manifest = self._make_version("2.0", first_script, ["second-arg"])
        original_start = self.app_manager.start_application
        calls = 0

        def fail_activation(app_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("activation failed")
            return original_start(app_id)

        with patch.object(self.app_manager, "start_application", side_effect=fail_activation):
            with self.assertRaisesRegex(RuntimeError, "activation failed"):
                self.app_manager.install_and_activate("sample", "2.0", second_staging, second_manifest)
        metadata = self.app_manager.get_application("sample")
        self.assertEqual(metadata["active_version"], "1.0")
        self.assertEqual(metadata["args"], ["first-arg"])

        with self.assertRaisesRegex(ValueError, "already installed"):
            self.app_manager.install_and_activate("sample", "1.0", self.root, first_manifest)
        self.app_manager.stop_application("sample")


if __name__ == "__main__":
    unittest.main()
