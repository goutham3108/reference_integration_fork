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
from unittest.mock import patch
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
        for app_id in list(cls.app_manager.processes):
            cls.app_manager.stop_application(app_id)
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

    def test_invalid_delete_route_does_not_remove_apps_directory(self):
        apps_dir = Path(self.config.apps_dir)
        sentinel = apps_dir / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        try:
            for path in ("/api/v1/apps/", "/api/v1/apps/..", "/api/v1/apps/../other"):
                status, _ = self._request("DELETE", path)
                self.assertEqual(status, 404)
            self.assertTrue(sentinel.exists())
        finally:
            sentinel.unlink(missing_ok=True)

    def test_upload_rejects_oversized_request_before_body_processing(self):
        previous_limit = self.config.max_upload_size_mb
        self.config.max_upload_size_mb = 0
        try:
            status, data = self._request(
                "POST", "/api/v1/apps/upload", body=b"x",
                content_type="application/gzip"
            )
        finally:
            self.config.max_upload_size_mb = previous_limit
        self.assertEqual(status, 413)
        self.assertFalse(data["success"])

    def test_multipart_upload_streams_a_single_file_bundle(self):
        package_dir = self.test_dir / "multipart_pkg"
        package_dir.mkdir()
        (package_dir / "manifest.json").write_text(json.dumps({
            "app_id": "multipart-app",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "main.py",
        }), encoding="utf-8")
        (package_dir / "main.py").write_text("print('multipart bundle')\n", encoding="utf-8")
        archive_path = self.test_dir / "multipart.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(package_dir / "manifest.json", arcname="manifest.json")
            archive.add(package_dir / "main.py", arcname="main.py")

        boundary = "test-upload-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="package"; filename="bundle.tar.gz"\r\n'
            "Content-Type: application/gzip\r\n\r\n"
        ).encode() + archive_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        try:
            status, data = self._request(
                "POST", "/api/v1/apps/upload", body=body,
                content_type=f"multipart/form-data; boundary={boundary}"
            )
            self.assertEqual(status, 201, data)
            self.assertEqual(data["app"]["app_id"], "multipart-app")
        finally:
            self._request("DELETE", "/api/v1/apps/multipart-app")

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
                while time.monotonic() < deadline:
                    status, response = self._request("GET", f"/api/v1/apps/{app_id}/logs?lines=20")
                    self.assertEqual(status, 200)
                    logs = response["logs"]
                    if (logs.strip() and "No logs available yet." not in logs
                            and "Error reading log file:" not in logs):
                        break
                    time.sleep(0.1)
                self.assertTrue(
                    logs.strip() and "No logs available yet." not in logs
                    and "Error reading log file:" not in logs,
                    f"Expected application output logs for {app_id}, got {logs!r}"
                )
        finally:
            for app_id in expected_ids:
                self._request("DELETE", f"/api/v1/apps/{app_id}")

    def test_04_upload_and_deploy_package(self):
        # Create a valid test package
        pkg_dir = self.test_dir / "sample_pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        py_content = (
            "import json, subprocess, sys, time\n"
            "settings = json.load(open('settings.json', encoding='utf-8'))\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print('App active', settings['mode'], sys.argv[1], 'child', child.pid, flush=True)\n"
            "time.sleep(30)\n"
        )
        py_hash = hashlib.sha256(py_content.encode("utf-8")).hexdigest()
        manifest = {
            "app_id": "test-pilot-app",
            "name": "Pilot App",
            "version": "1.0.0",
            "runtime": "python",
            "entrypoint": "bin/app.py",
            "args": ["hello"],
            "checksums": {"bin/app.py": py_hash}
        }
        tar_path = self.test_dir / "pilot.tar.gz"
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (pkg_dir / "bin").mkdir(exist_ok=True)
        (pkg_dir / "bin" / "app.py").write_text(py_content, encoding="utf-8")
        (pkg_dir / "settings.json").write_text('{"mode": "root-cwd"}', encoding="utf-8")

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(pkg_dir / "manifest.json", arcname="manifest.json")
            tar.add(pkg_dir / "bin" / "app.py", arcname="bin/app.py")
            tar.add(pkg_dir / "settings.json", arcname="settings.json")

        with open(tar_path, "rb") as f:
            tar_bytes = f.read()

        status, data = self._request("POST", "/api/v1/apps/upload", body=tar_bytes, content_type="application/gzip")
        self.assertEqual(status, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["app"]["app_id"], "test-pilot-app")

        status, _ = self._request(
            "POST", "/api/v1/apps/upload", body=tar_bytes,
            content_type="application/gzip"
        )
        self.assertEqual(status, 400)

        second_manifest = dict(manifest)
        second_manifest.update({
            "version": "2.0.0",
            "entrypoint": "worker.py",
            "args": ["world"],
            "checksums": {}
        })
        second_script = (
            "import json, subprocess, sys, time\n"
            "settings = json.load(open('settings.json', encoding='utf-8'))\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print('App v2', settings['mode'], sys.argv[1], 'child', child.pid, flush=True)\n"
            "time.sleep(30)\n"
        )
        second_pkg = self.test_dir / "pilot-v2"
        second_pkg.mkdir()
        (second_pkg / "manifest.json").write_text(json.dumps(second_manifest), encoding="utf-8")
        (second_pkg / "worker.py").write_text(second_script, encoding="utf-8")
        (second_pkg / "settings.json").write_text('{"mode": "root-cwd-v2"}', encoding="utf-8")
        second_tar = self.test_dir / "pilot-v2.tar.gz"
        with tarfile.open(second_tar, "w:gz") as tar:
            for name in ("manifest.json", "worker.py", "settings.json"):
                tar.add(second_pkg / name, arcname=name)
        status, data = self._request(
            "POST", "/api/v1/apps/upload", body=second_tar.read_bytes(),
            content_type="application/gzip"
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(data["app"]["active_version"], "2.0.0")
        log_file = Path(self.config.logs_dir) / "test-pilot-app.log"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and "root-cwd-v2 world" not in log_file.read_text():
            time.sleep(0.05)
        self.assertIn("root-cwd-v2 world", log_file.read_text())

        failed_staging = self.test_dir / "failed-activation"
        failed_staging.mkdir()
        (failed_staging / "manifest.json").write_text(json.dumps({
            "app_id": "test-pilot-app",
            "version": "3.0.0",
            "runtime": "python",
            "entrypoint": "does-not-matter.py",
        }), encoding="utf-8")
        previous_start = self.app_manager.start_application
        activation_calls = 0

        def fail_then_restore(app_id):
            nonlocal activation_calls
            activation_calls += 1
            if activation_calls == 1:
                raise RuntimeError("activation failed")
            return previous_start(app_id)

        with patch.object(self.app_manager, "start_application", side_effect=fail_then_restore):
            with self.assertRaisesRegex(RuntimeError, "activation failed"):
                self.app_manager.install_and_activate(
                    "test-pilot-app", "3.0.0", failed_staging,
                    json.loads((second_pkg / "manifest.json").read_text())
                )
        self.assertEqual(
            os.readlink(Path(self.config.apps_dir) / "test-pilot-app" / "current"),
            "versions/2.0.0"
        )
        self.assertEqual(
            self.app_manager.get_application("test-pilot-app")["active_version"],
            "2.0.0"
        )

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

        status, data = self._request("POST", "/api/v1/apps/test-pilot-app/rollback")
        self.assertEqual(status, 200, data)
        self.assertEqual(data["data"]["active_version"], "1.0.0")
        self.assertEqual(data["data"]["entrypoint"], "bin/app.py")
        self.assertEqual(data["data"]["args"], ["hello"])

        unrelated = subprocess.Popen(
            [
                sys.executable, "-c", "import time; time.sleep(30)",
                str(Path(self.config.apps_dir) / "test-pilot-app" / "current" / "unrelated.py")
            ],
            start_new_session=True
        )

        def cleanup_unrelated():
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=2)

        self.addCleanup(cleanup_unrelated)

        # Simulate a process surviving an API restart: forget its in-memory handle.
        orphaned_process = self.app_manager.processes.pop("test-pilot-app")
        process = orphaned_process["process"]
        log_handle = orphaned_process["log_handle"]
        def cleanup_orphaned_process():
            try:
                self.app_manager.stop_application("test-pilot-app")
                process.wait(timeout=2)
            finally:
                if not log_handle.closed:
                    log_handle.close()

        self.addCleanup(cleanup_orphaned_process)
        group_members = self.app_manager._process_group_members(orphaned_process["record"])
        deadline = time.monotonic() + 2
        while len(group_members) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
            group_members = self.app_manager._process_group_members(orphaned_process["record"])
        self.assertIn(process.pid, group_members)
        child_pids = [pid for pid in group_members if pid != process.pid]
        self.assertTrue(child_pids, "Expected a child in the current app process group")
        status, _ = self._request("POST", "/api/v1/apps/test-pilot-app/stop")
        self.assertEqual(status, 200)
        self.assertFalse((Path(self.config.apps_dir) / "test-pilot-app" / "process.json").exists())
        self.assertIsNone(unrelated.poll())
        deadline = time.monotonic() + 2
        for child_pid in child_pids:
            child_stat = self.app_manager._read_proc_stat(child_pid)
            while child_stat and child_stat["state"] not in {"Z", "X"} and time.monotonic() < deadline:
                time.sleep(0.05)
                child_stat = self.app_manager._read_proc_stat(child_pid)
            self.assertTrue(child_stat is None or child_stat["state"] in {"Z", "X"})

        # Delete removes the app directory, processes and log file.
        status, data = self._request("DELETE", "/api/v1/apps/test-pilot-app")
        self.assertEqual(status, 200)
        self.assertFalse((Path(self.config.apps_dir) / "test-pilot-app").exists())
        self.assertFalse((Path(self.config.logs_dir) / "test-pilot-app.log").exists())


if __name__ == "__main__":
    unittest.main()
