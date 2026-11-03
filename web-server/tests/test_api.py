#!/usr/bin/env python3
"""
Integration tests for the SDV Deployment Server REST API endpoints.
"""

import os
import sys
import json
import platform
import time
import shutil
import hashlib
import subprocess
import tarfile
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import HTTPServer

SERVER_ROOT = Path(__file__).resolve().parent.parent
PI_SERVER_ROOT = SERVER_ROOT / "pi-server"
sys.path.insert(0, str(PI_SERVER_ROOT))

from server import (
    DeploymentConfig,
    EnvironmentInspector,
    BenchmarkValidator,
    ApplicationManager,
    DeploymentRequestHandler
)


class TestDeploymentApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="sdv_api_test_"))
        cls.config = DeploymentConfig()
        cls.config.host = "127.0.0.1"
        cls.config.port = 0
        cls.config.auth_token = "test-token-12345"
        cls.config.data_dir = str(cls.test_dir / "data")
        cls.config.apps_dir = str(cls.test_dir / "apps")
        cls.config.staging_dir = str(cls.test_dir / "staging")
        cls.config.logs_dir = str(cls.test_dir / "logs")
        cls.config.smoke_test_seconds = 1
        cls.config.use_tls = False

        Path(cls.config.apps_dir).mkdir(parents=True, exist_ok=True)
        Path(cls.config.staging_dir).mkdir(parents=True, exist_ok=True)
        Path(cls.config.logs_dir).mkdir(parents=True, exist_ok=True)

        cls.inspector = EnvironmentInspector(cls.config)
        cls.validator = BenchmarkValidator(cls.config)
        cls.app_manager = ApplicationManager(cls.config)
        DeploymentRequestHandler.config = cls.config
        DeploymentRequestHandler.inspector = cls.inspector
        DeploymentRequestHandler.validator = cls.validator
        DeploymentRequestHandler.app_manager = cls.app_manager

        cls.httpd = HTTPServer((cls.config.host, cls.config.port), DeploymentRequestHandler)
        cls.config.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _request(self, method, path, body=None, token="test-token-12345", origin=None, content_type="application/json"):
        url = f"http://127.0.0.1:{self.config.port}{path}"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if origin:
            headers["Origin"] = origin
        if content_type:
            headers["Content-Type"] = content_type

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read().decode("utf-8"))

    def test_00_ui_origin_is_accepted_without_a_token(self):
        status, data = self._request("GET", "/api/v1/apps", token=None, origin="http://localhost:8080")
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])

    def test_00_unknown_origin_without_a_token_is_rejected(self):
        status, data = self._request("GET", "/api/v1/apps", token=None, origin="http://evil.example")
        self.assertEqual(status, 401)
        self.assertFalse(data["success"])

    def test_00_state_changing_request_from_unknown_origin_is_rejected(self):
        status, _ = self._request("POST", "/api/v1/apps/upload", body=b"x", token=None,
                                  origin="http://evil.example", content_type="multipart/form-data; boundary=x")
        self.assertEqual(status, 401)

    def test_00_request_without_origin_or_token_is_rejected(self):
        status, data = self._request("GET", "/api/v1/apps", token=None)
        self.assertEqual(status, 401)
        self.assertFalse(data["success"])

    def test_01_auth_rejection(self):
        status, data = self._request("GET", "/api/v1/environment", token="invalid-token")
        self.assertEqual(status, 401)
        self.assertFalse(data["success"])

    def test_01_pi_server_does_not_serve_ui_files(self):
        status, data = self._request("GET", "/", token=None)
        self.assertEqual(status, 404)
        self.assertFalse(data["success"])

    def test_01_cors_allows_only_configured_laptop_origin(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.config.port}/api/v1/environment",
            headers={
                "Authorization": "Bearer test-token-12345",
                "Origin": "http://localhost:8080",
            },
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:8080")

        status, data = self._request("OPTIONS", "/api/v1/environment", token=None, origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertFalse(data["success"])

    def test_02_environment_endpoint(self):
        status, data = self._request("GET", "/api/v1/environment")
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        env = data["data"]
        self.assertIn("system", env)
        self.assertIn("toolchain", env)
        self.assertIn("middleware", env)
        self.assertEqual(env["system"]["architecture"], platform.machine())
        self.assertNotIn("target_arch_configured", env["system"])
        self.assertIn("gxx_version", env["toolchain"])

    def test_03_apps_list_initially_empty(self):
        status, data = self._request("GET", "/api/v1/apps")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 0)

    def test_04_multiple_applications_and_individual_logs(self):
        examples = SERVER_ROOT / "examples"
        package_paths = [
            examples / "sample_sdv_python_app" / "kuksa-high-beam-controller-1.0.0.tar.gz",
            examples / "hello-app" / "pi-heartbeat-monitor-1.0.0.tar.gz",
        ]
        expected_ids = ["kuksa-high-beam-controller", "pi-heartbeat-monitor"]
        try:
            for package_path in package_paths:
                with package_path.open("rb") as package_file:
                    status, response = self._request(
                        "POST",
                        "/api/v1/apps/upload",
                        body=package_file.read(),
                        content_type="application/gzip"
                    )
                self.assertEqual(status, 201, response)

            status, response = self._request("GET", "/api/v1/apps")
            self.assertEqual(status, 200)
            deployed_ids = {app["app_id"] for app in response["data"]}
            self.assertTrue(set(expected_ids).issubset(deployed_ids))

            for app_id in expected_ids:
                deadline = time.monotonic() + 2
                logs = ""
                while time.monotonic() < deadline and not logs.strip():
                    status, response = self._request("GET", f"/api/v1/apps/{app_id}/logs?lines=20")
                    self.assertEqual(status, 200)
                    logs = response["logs"]
                    if not logs.strip():
                        time.sleep(0.1)
                self.assertTrue(logs.strip(), f"Expected logs for {app_id}")
        finally:
            for app_id in expected_ids:
                self._request("DELETE", f"/api/v1/apps/{app_id}")

    def test_04_upload_and_deploy_package(self):
        # Create a valid test package
        pkg_dir = self.test_dir / "sample_pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        py_content = "import time\nprint('App active')\ntime.sleep(30)\n"
        py_hash = hashlib.sha256(py_content.encode("utf-8")).hexdigest()
        manifest = {
            "app_id": "test-pilot-app",
            "name": "Pilot App",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "app.py",
            "checksums": {"app.py": py_hash}
        }
        tar_path = self.test_dir / "pilot.tar.gz"
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (pkg_dir / "app.py").write_text(py_content, encoding="utf-8")

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(pkg_dir / "manifest.json", arcname="manifest.json")
            tar.add(pkg_dir / "app.py", arcname="app.py")

        with open(tar_path, "rb") as f:
            tar_bytes = f.read()

        status, data = self._request("POST", "/api/v1/apps/upload", body=tar_bytes, content_type="application/gzip")
        self.assertEqual(status, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["app"]["app_id"], "test-pilot-app")

        # Verify listed in apps
        status, data = self._request("GET", "/api/v1/apps")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["data"][0]["app_id"], "test-pilot-app")

    def test_05_lifecycle_actions(self):
        # Stop and verify the process is no longer running.
        status, data = self._request("POST", "/api/v1/apps/test-pilot-app/stop")
        self.assertEqual(status, 200)
        status, data = self._request("GET", "/api/v1/apps/test-pilot-app")
        self.assertEqual(status, 200)
        self.assertEqual(data["data"]["status"]["state"], "stopped")

        # Restart and verify the process is running again.
        status, data = self._request("POST", "/api/v1/apps/test-pilot-app/restart")
        self.assertEqual(status, 200)
        status, data = self._request("GET", "/api/v1/apps/test-pilot-app")
        self.assertEqual(status, 200)
        self.assertEqual(data["data"]["status"]["state"], "running")

        # Logs
        status, data = self._request("GET", "/api/v1/apps/test-pilot-app/logs")
        self.assertEqual(status, 200)
        self.assertIn("logs", data)

        # Simulate an orphan left by an earlier API run: forget the tracked process.
        orphaned_process = self.app_manager.processes.pop("test-pilot-app")
        process = orphaned_process["process"]
        log_handle = orphaned_process["log_handle"]

        def cleanup_orphaned_process():
            try:
                if process.poll() is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            finally:
                log_handle.close()

        self.addCleanup(cleanup_orphaned_process)
        self.assertEqual(len(self.app_manager._find_app_pids("test-pilot-app")), 1)
        status, _ = self._request("POST", "/api/v1/apps/test-pilot-app/stop")
        self.assertEqual(status, 200)
        self.assertEqual(self.app_manager._find_app_pids("test-pilot-app"), [])

        # Delete removes the app directory, processes and log file.
        status, data = self._request("DELETE", "/api/v1/apps/test-pilot-app")
        self.assertEqual(status, 200)
        self.assertFalse((Path(self.config.apps_dir) / "test-pilot-app").exists())
        self.assertFalse((Path(self.config.logs_dir) / "test-pilot-app.log").exists())


if __name__ == "__main__":
    unittest.main()
