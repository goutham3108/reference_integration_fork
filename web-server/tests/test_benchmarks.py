#!/usr/bin/env python3
"""
Unit and benchmark tests for the 5-Stage validation pipeline.
"""

import os
import sys
import json
import shutil
import tarfile
import hashlib
import tempfile
import unittest
from pathlib import Path

# Add web-server root to python path
SERVER_ROOT = Path(__file__).resolve().parent.parent
PI_SERVER_ROOT = SERVER_ROOT / "pi-server"
sys.path.insert(0, str(PI_SERVER_ROOT))

from server import DeploymentConfig, BenchmarkValidator


class TestValidationBenchmarks(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="sdv_test_"))
        self.config = DeploymentConfig()
        self.config.data_dir = str(self.test_dir / "data")
        self.config.staging_dir = str(self.test_dir / "staging")
        self.config.smoke_test_seconds = 1
        self.validator = BenchmarkValidator(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_tar(self, files_dict, tar_name="test_pkg.tar.gz"):
        tar_path = self.test_dir / tar_name
        with tarfile.open(tar_path, "w:gz") as tar:
            for rel_name, content in files_dict.items():
                temp_file = self.test_dir / rel_name
                temp_file.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, str):
                    temp_file.write_text(content, encoding="utf-8")
                else:
                    temp_file.write_bytes(content)
                tar.add(temp_file, arcname=rel_name)
        return tar_path

    # ------------ Stage 1: Archive Safety Benchmark ------------
    def test_stage1_path_traversal_rejected(self):
        tar_path = self.test_dir / "malicious.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add an entry with path traversal
            dummy = self.test_dir / "dummy.txt"
            dummy.write_text("evil", encoding="utf-8")
            tar.add(dummy, arcname="../evil.txt")

        extract_dir = self.test_dir / "extract_traversal"
        res = self.validator.validate_package(tar_path, extract_dir)
        self.assertFalse(res["passed"])
        self.assertTrue(any("traversal" in err.lower() for err in res["errors"]))

    def test_stage1_corrupted_archive_rejected(self):
        corrupt_path = self.test_dir / "corrupted.tar.gz"
        corrupt_path.write_bytes(b"This is definitely not a gzip tar archive!")
        extract_dir = self.test_dir / "extract_corrupt"
        res = self.validator.validate_package(corrupt_path, extract_dir)
        self.assertFalse(res["passed"])
        self.assertTrue(any("not a valid" in err.lower() for err in res["errors"]))

    # ------------ Stage 2: Manifest & Checksum Benchmark ------------
    def test_stage2_missing_manifest_rejected(self):
        tar_path = self._create_tar({"payload.txt": "hello world"})
        extract_dir = self.test_dir / "extract_no_manifest"
        res = self.validator.validate_package(tar_path, extract_dir)
        self.assertFalse(res["passed"])
        self.assertTrue(any("manifest.json" in err.lower() for err in res["errors"]))
        stages = res["stages"]
        self.assertEqual(stages["stage1_archive_safety"]["status"], "passed")
        self.assertEqual(stages["stage2_manifest_checksum"]["status"], "failed")
        self.assertIn("manifest.json", stages["stage2_manifest_checksum"]["error"])
        for key in ("stage3_compatibility", "stage4_security_permissions", "stage5_startup_smoke"):
            self.assertEqual(stages[key]["status"], "not_run")
            self.assertEqual(stages[key]["details"], [])

    def test_stage2_checksum_mismatch_rejected(self):
        content = "print('hello from python')\n"
        wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        manifest = {
            "app_id": "test-app",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "main.py",
            "checksums": {"main.py": wrong_hash}
        }
        tar_path = self._create_tar({
            "manifest.json": json.dumps(manifest),
            "main.py": content
        })
        extract_dir = self.test_dir / "extract_bad_checksum"
        res = self.validator.validate_package(tar_path, extract_dir)
        self.assertFalse(res["passed"])
        self.assertTrue(any("checksum mismatch" in err.lower() for err in res["errors"]))

    # ------------ Stage 3: Compatibility Benchmark ------------
    def test_stage3_python_syntax_error_rejected(self):
        bad_python = "def broken_syntax(:\n    pass\n"
        manifest = {
            "app_id": "test-bad-python",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "bad.py"
        }
        tar_path = self._create_tar({
            "manifest.json": json.dumps(manifest),
            "bad.py": bad_python
        })
        extract_dir = self.test_dir / "extract_bad_py"
        res = self.validator.validate_package(tar_path, extract_dir)
        self.assertFalse(res["passed"])
        self.assertTrue(any("syntax error" in err.lower() for err in res["errors"]))

    def test_stage3_valid_python_package_accepted(self):
        good_python = "import sys\nprint('Running cleanly')\nsys.exit(0)\n"
        py_hash = hashlib.sha256(good_python.encode("utf-8")).hexdigest()
        manifest = {
            "app_id": "test-good-python",
            "name": "Good Python App",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "main.py",
            "checksums": {"main.py": py_hash}
        }
        tar_path = self._create_tar({
            "manifest.json": json.dumps(manifest),
            "main.py": good_python
        })
        extract_dir = self.test_dir / "extract_good_py"
        res = self.validator.validate_package(tar_path, extract_dir)
        self.assertTrue(res["passed"], f"Expected pass, got errors: {res.get('errors')}")
        self.assertTrue(res["stages"]["stage1_archive_safety"]["passed"])
        self.assertTrue(res["stages"]["stage2_manifest_checksum"]["passed"])
        self.assertTrue(res["stages"]["stage3_compatibility"]["passed"])
        self.assertTrue(res["stages"]["stage4_security_permissions"]["passed"])

    def test_sample_heartbeat_bundle_validates_and_smoke_tests(self):
        package = SERVER_ROOT / "examples" / "hello-app" / "pi-heartbeat-monitor-1.0.0.tar.gz"
        extract_dir = self.test_dir / "extract_heartbeat"
        result = self.validator.validate_package(package, extract_dir)
        self.assertTrue(result["passed"], f"Expected pass, got errors: {result.get('errors')}")

        entrypoint = extract_dir / result["manifest"]["entrypoint"]
        smoke_result = self.validator.run_smoke_test(entrypoint, "python", result["manifest"].get("args", []))
        self.assertTrue(smoke_result["passed"], f"Expected smoke-test pass, got: {smoke_result}")

    # ------------ Stage 5: Startup Smoke Benchmark ------------
    def test_stage5_smoke_test_crashing_app_rejected(self):
        crashing_script = self.test_dir / "crash.py"
        crashing_script.write_text("import sys\nprint('Crashing!')\nsys.exit(1)\n", encoding="utf-8")
        smoke_res = self.validator.run_smoke_test(crashing_script, "python")
        self.assertFalse(smoke_res["passed"])
        self.assertTrue("crashed immediately" in smoke_res["error"].lower())

    def test_stage5_smoke_test_healthy_app_passes(self):
        healthy_script = self.test_dir / "healthy.py"
        healthy_script.write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
        smoke_res = self.validator.run_smoke_test(healthy_script, "python")
        self.assertTrue(smoke_res["passed"])


if __name__ == "__main__":
    unittest.main()
