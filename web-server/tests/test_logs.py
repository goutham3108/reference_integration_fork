import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PI_SERVER_ROOT = Path(__file__).resolve().parent.parent / "pi-server"
import sys
sys.path.insert(0, str(PI_SERVER_ROOT))

from server import ApplicationManager


class TestApplicationLogFallback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        logs_dir = Path(self.temp_dir.name)
        self.manager = ApplicationManager(SimpleNamespace(
            apps_dir=logs_dir / "apps",
            logs_dir=logs_dir,
            app_user="sdv-apps",
            systemctl_helper=logs_dir / "missing-controller"
        ))

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("server.shutil.which", return_value="/usr/bin/journalctl")
    @patch("server.subprocess.run")
    def test_journal_no_entries_falls_back_to_process_log(self, run, _which):
        run.return_value = subprocess.CompletedProcess([], 0, "-- No entries --\n", "")
        (self.manager.logs_dir / "sample-app.log").write_text("app started\napp heartbeat\n", encoding="utf-8")

        self.assertEqual(self.manager.get_logs("sample-app"), "app started\napp heartbeat\n")

    @patch("server.shutil.which", return_value="/usr/bin/journalctl")
    @patch("server.subprocess.run")
    def test_real_journal_entries_are_preferred(self, run, _which):
        run.return_value = subprocess.CompletedProcess([], 0, "Jun 10 app started\n", "")
        (self.manager.logs_dir / "sample-app.log").write_text("fallback log\n", encoding="utf-8")

        self.assertEqual(self.manager.get_logs("sample-app"), "Jun 10 app started\n")

    @patch("server.shutil.which", return_value="/usr/bin/journalctl")
    @patch("server.subprocess.run")
    def test_missing_journal_and_file_returns_empty_message(self, run, _which):
        run.return_value = subprocess.CompletedProcess([], 0, "-- No entries --\n", "")

        self.assertEqual(self.manager.get_logs("missing-app"), "No logs available yet.")


if __name__ == "__main__":
    unittest.main()
