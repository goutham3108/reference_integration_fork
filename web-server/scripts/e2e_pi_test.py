#!/usr/bin/env python3
"""End-to-end API test against a Pi API reached through the SSH tunnel.

Usage: python3 web-server/scripts/e2e_pi_test.py --email <email> [--base-url http://127.0.0.1:18443]
The password is read from SDV_E2E_PASSWORD or prompted; it is never taken from arguments.
"""

import argparse
import getpass
import http.cookiejar
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLES = {
    "pi-heartbeat-monitor": ROOT / "examples/hello-app/pi-heartbeat-monitor-1.0.0.tar.gz",
    "kuksa-high-beam-controller": ROOT / "examples/sample_sdv_python_app/kuksa-high-beam-controller-1.0.0.tar.gz",
}
ORIGIN = "http://127.0.0.1:8080"

failures = []


class Client:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method, path, body=None, content_type="application/json"):
        headers = {"Origin": ORIGIN}
        if body is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8") or "{}")


def check(name, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)
    return condition


def app_state(client, app_id):
    status, data = client.request("GET", f"/api/v1/apps/{app_id}")
    return data.get("data", {}).get("status", {}).get("state") if status == 200 else None


def wait_state(client, app_id, wanted, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if app_state(client, app_id) == wanted:
            return True
        time.sleep(1)
    return False


def read_logs(client, app_id, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status, data = client.request("GET", f"/api/v1/apps/{app_id}/logs?lines=50")
        if status == 200 and data.get("logs", "").strip():
            return data["logs"]
        time.sleep(1)
    return ""


def ensure_bundles():
    for app_id, path in BUNDLES.items():
        if not path.exists():
            builder = path.parent / ("build_bundle.sh" if "hello-app" in str(path) else "build_sample_bundle.sh")
            subprocess.run(["bash", str(builder)], check=True, stdout=subprocess.DEVNULL)


def upload(client, data):
    return client.request("POST", "/api/v1/apps/upload", body=data, content_type="application/gzip")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18443")
    parser.add_argument("--keep", action="store_true", help="leave deployed apps in place at the end")
    args = parser.parse_args()
    password = os.environ.get("SDV_E2E_PASSWORD") or getpass.getpass("Password: ")

    ensure_bundles()
    client = Client(args.base_url)

    bad_status, _ = Client(args.base_url).request("GET", "/api/v1/apps")
    check("unauthenticated request rejected", bad_status == 401, f"got HTTP {bad_status}")

    status, _ = Client(args.base_url).request(
        "POST", "/api/v1/login", json.dumps({"email": args.email, "password": password + "x"}).encode())
    check("wrong password rejected", status == 401, f"got HTTP {status}")

    status, data = client.request("POST", "/api/v1/login", json.dumps({"email": args.email, "password": password}).encode())
    if not check("login", status == 200 and data.get("success"), data.get("error", "")):
        return 1

    status, data = client.request("GET", "/api/v1/environment")
    env = data.get("data", {}) if status == 200 else {}
    arch = env.get("system", {}).get("architecture", "")
    check("environment reports aarch64", status == 200 and arch.lower() in ("aarch64", "arm64"), arch)

    wrong = io.BytesIO()
    with tarfile.open(fileobj=wrong, mode="w:gz") as tar:
        info = tarfile.TarInfo("payload.txt")
        payload = b"not an app"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    status, data = upload(client, wrong.getvalue())
    stages = data.get("benchmark_results", {}).get("stages", {})
    check("bundle without manifest rejected at stage 2",
          status == 422 and stages.get("stage2_manifest_checksum", {}).get("status") == "failed"
          and stages.get("stage3_compatibility", {}).get("status") == "not_run")

    try:
        for app_id, path in BUNDLES.items():
            status, data = upload(client, path.read_bytes())
            check(f"deploy {app_id}", status == 201 and data.get("success"), data.get("error", ""))

        status, data = client.request("GET", "/api/v1/apps")
        listed = {app["app_id"]: app for app in data.get("data", [])}
        for app_id in BUNDLES:
            check(f"{app_id} listed and running", app_id in listed and wait_state(client, app_id, "running"))

        for app_id in BUNDLES:
            check(f"{app_id} has its own logs", bool(read_logs(client, app_id)))

        target = "pi-heartbeat-monitor"
        other = "kuksa-high-beam-controller"
        status, _ = client.request("POST", f"/api/v1/apps/{target}/stop")
        check("stop returns success", status == 200)
        check("stopped app reports stopped", wait_state(client, target, "stopped"))
        check("other app unaffected by stop", app_state(client, other) == "running")

        status, _ = client.request("POST", f"/api/v1/apps/{target}/restart")
        check("restart returns success", status == 200)
        check("restarted app reports running", wait_state(client, target, "running"))
    finally:
        if not args.keep:
            for app_id in BUNDLES:
                client.request("DELETE", f"/api/v1/apps/{app_id}")

    if not args.keep:
        status, data = client.request("GET", "/api/v1/apps")
        remaining = [app["app_id"] for app in data.get("data", []) if app["app_id"] in BUNDLES]
        check("removed apps are gone from the server", status == 200 and not remaining, ", ".join(remaining))

    client.request("POST", "/api/v1/logout")
    print(f"\n{len(failures)} check(s) failed" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
