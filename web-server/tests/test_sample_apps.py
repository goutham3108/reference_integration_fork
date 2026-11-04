import contextlib
import hashlib
import importlib.util
import io
import json
import signal
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class TestSampleAppSimulation(unittest.TestCase):
    def test_high_beam_output_is_simulated_for_reachable_and_unreachable_ports(self):
        path = EXAMPLES / "sample_sdv_python_app/high_beam_kuksa_controller.py"
        spec = importlib.util.spec_from_file_location("sample_high_beam", path)
        module = importlib.util.module_from_spec(spec)
        with patch.object(signal, "signal"):
            spec.loader.exec_module(module)
        for reachable in (True, False):
            with self.subTest(reachable=reachable):
                output = io.StringIO()
                module.keep_running = True
                cycles = 0

                def finish_after_three_cycles(seconds):
                    nonlocal cycles
                    cycles += 1
                    if cycles == 3:
                        module.keep_running = False

                with patch.object(module, "check_kuksa_available", return_value=reachable), \
                        patch.object(module.time, "sleep", side_effect=finish_after_three_cycles), \
                        contextlib.redirect_stdout(output):
                    module.main()
                logs = output.getvalue()
                self.assertIn("no signals are read or written", logs)
                self.assertIn("Local simulated Vehicle.Body.Lights.Beam.High.IsOn", logs)
                self.assertNotIn("Actuating signal", logs)

    def test_rebuilt_bundles_have_matching_checksums_and_simulation_metadata(self):
        for folder, archive in (
            ("sample_sdv_python_app", "kuksa-high-beam-controller-1.0.0.tar.gz"),
            ("sample_score_app", "vehicle-speed-reader-1.0.0.tar.gz"),
        ):
            with self.subTest(folder=folder), tarfile.open(EXAMPLES / folder / archive) as bundle:
                with bundle.extractfile("manifest.json") as manifest_file:
                    manifest = json.load(manifest_file)
                self.assertIn("simulation", manifest["description"].lower())
                for name, expected in manifest["checksums"].items():
                    with bundle.extractfile(name) as payload:
                        content = payload.read()
                        self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
                        self.assertEqual(content, (EXAMPLES / folder / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
