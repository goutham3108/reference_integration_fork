import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PI_SERVER_ROOT = Path(__file__).resolve().parent.parent / "pi-server"
import sys
sys.path.insert(0, str(PI_SERVER_ROOT))

from server import ApplicationManager


class TestApplicationLogs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        logs_dir = Path(self.temp_dir.name)
        self.manager = ApplicationManager(SimpleNamespace(
            apps_dir=logs_dir / "apps",
            logs_dir=logs_dir,
            app_user="sdv-apps",
        ))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_returns_log_file_contents(self):
        (self.manager.logs_dir / "sample-app.log").write_text("app started\napp heartbeat\n", encoding="utf-8")

        self.assertEqual(self.manager.get_logs("sample-app"), "app started\napp heartbeat\n")

    def test_returns_only_the_last_requested_lines(self):
        (self.manager.logs_dir / "sample-app.log").write_text("one\ntwo\nthree\n", encoding="utf-8")

        self.assertEqual(self.manager.get_logs("sample-app", lines=2), "two\nthree\n")

    def test_missing_log_file_returns_empty_message(self):
        self.assertEqual(self.manager.get_logs("missing-app"), "No logs available yet.")


if __name__ == "__main__":
    unittest.main()
