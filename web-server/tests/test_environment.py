import sys
import tempfile
import unittest
from pathlib import Path

PI_SERVER_ROOT = Path(__file__).resolve().parent.parent / "pi-server"
sys.path.insert(0, str(PI_SERVER_ROOT))

from server import EnvironmentInspector


class TestEnvironmentInspection(unittest.TestCase):
    def test_kuksa_detection_uses_running_databroker_process_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            proc_root = Path(temporary_directory)
            for pid, process_name in {
                "101": "databroker-mw-com-demo",
                "102": "python3",
                "103": "kuksa-databroker",
                "104": "kuksa-client",
            }.items():
                process_dir = proc_root / pid
                process_dir.mkdir()
                (process_dir / "comm").write_text(process_name, encoding="utf-8")

            found = EnvironmentInspector._find_kuksa_processes(proc_root)

        self.assertEqual(found, ["databroker-mw-com-demo", "kuksa-databroker"])

    def test_kuksa_status_has_no_configured_endpoint(self):
        status = EnvironmentInspector(None)._check_kuksa()
        self.assertIn("running", status)
        self.assertIn("available", status)
        self.assertNotIn("endpoint", status)


if __name__ == "__main__":
    unittest.main()
