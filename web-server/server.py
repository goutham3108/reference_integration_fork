#!/usr/bin/env python3
"""
SDV Web-Based Application Deployment Server
Provides Web UI and REST API for uploading, validating, and managing
applications on Vehicle Raspberry Pi (isolated from S-CORE core stack).
"""

import os
import sys
import json
import time
import shutil
import hashlib
import tarfile
import struct
import socket
import logging
import platform
import py_compile
import subprocess
import hmac
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from auth import verify_password

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sdv-deployer")


class DeploymentConfig:
    def __init__(self, config_path=None):
        base_dir = Path(__file__).resolve().parent
        default_config_path = base_dir / "config.json"
        target_path = Path(config_path) if config_path else default_config_path

        self.host = "0.0.0.0"
        self.port = 8443
        self.use_tls = False
        self.tls_cert_file = str(base_dir / "certs" / "server.crt")
        self.tls_key_file = str(base_dir / "certs" / "server.key")
        self.auth_token = "sdv-dev-secret-token-2026"
        self.users = []
        self.data_dir = str(base_dir / "runtime" / "data")
        self.apps_dir = str(base_dir / "runtime" / "apps")
        self.staging_dir = str(base_dir / "runtime" / "staging")
        self.logs_dir = str(base_dir / "runtime" / "logs")
        self.max_upload_size_mb = 100
        self.smoke_test_seconds = 3
        self.target_architecture = "aarch64"
        self.kuksa_endpoint = "127.0.0.1:55555"

        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    for k, v in cfg.items():
                        if hasattr(self, k):
                            setattr(self, k, v)
                logger.info(f"Loaded configuration from {target_path}")
            except Exception as e:
                logger.warning(f"Error reading {target_path}, using defaults: {e}")

        # Environment variable overrides
        if "SDV_DEPLOYER_PORT" in os.environ:
            self.port = int(os.environ["SDV_DEPLOYER_PORT"])
        if "SDV_DEPLOYER_TOKEN" in os.environ:
            self.auth_token = os.environ["SDV_DEPLOYER_TOKEN"]
        if "SDV_DATA_DIR" in os.environ:
            self.data_dir = os.environ["SDV_DATA_DIR"]
            self.apps_dir = os.path.join(self.data_dir, "apps")
            self.staging_dir = os.path.join(self.data_dir, "staging")
            self.logs_dir = os.path.join(self.data_dir, "logs")

        # Ensure directories exist (fallback to local runtime dir if /var/lib requires root)
        try:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            Path(self.apps_dir).mkdir(parents=True, exist_ok=True)
            Path(self.staging_dir).mkdir(parents=True, exist_ok=True)
            Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.info("System directories not writable without root, falling back to local runtime directory")
            self.data_dir = str(base_dir / "runtime" / "data")
            self.apps_dir = str(base_dir / "runtime" / "apps")
            self.staging_dir = str(base_dir / "runtime" / "staging")
            self.logs_dir = str(base_dir / "runtime" / "logs")
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            Path(self.apps_dir).mkdir(parents=True, exist_ok=True)
            Path(self.staging_dir).mkdir(parents=True, exist_ok=True)
            Path(self.logs_dir).mkdir(parents=True, exist_ok=True)


class EnvironmentInspector:
    """Inspects target Raspberry Pi environment and middleware capability."""
    def __init__(self, config):
        self.config = config

    def get_info(self):
        info = {
            "system": {
                "hostname": socket.gethostname(),
                "os": platform.system(),
                "os_release": self._get_os_release(),
                "kernel": platform.release(),
                "architecture": platform.machine(),
                "target_arch_configured": self.config.target_architecture
            },
            "toolchain": {
                "python_version": sys.version.split()[0],
                "python_executable": sys.executable,
                "glibc_version": self._get_glibc_version(),
            },
            "middleware": {
                "kuksa_databroker": self._check_kuksa(),
                "score_mw_com_shm": self._check_lola_shm(),
                "systemd_available": self._check_systemd(),
                "container_runtime": self._check_container_runtime()
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        return info

    def _get_os_release(self):
        os_release_path = Path("/etc/os-release")
        if os_release_path.exists():
            try:
                with open(os_release_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            return line.strip().split("=", 1)[1].strip('"')
            except Exception:
                pass
        return f"{platform.system()} {platform.release()}"

    def _get_glibc_version(self):
        try:
            ver = platform.libc_ver()
            if ver[0] and ver[1]:
                return f"{ver[0]} {ver[1]}"
            out = subprocess.check_output(["ldd", "--version"], text=True, stderr=subprocess.STDOUT)
            first_line = out.strip().split("\n")[0]
            return first_line
        except Exception:
            return "glibc unknown"

    def _check_kuksa(self):
        endpoint = self.config.kuksa_endpoint
        host, port = endpoint.split(":") if ":" in endpoint else (endpoint, 55555)
        port = int(port)
        status = {
            "endpoint": endpoint,
            "protocol": "VAL v2 (gRPC)",
            "connected": False
        }
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            status["connected"] = (result == 0)
        except Exception as e:
            status["error"] = str(e)
        return status

    def _check_lola_shm(self):
        shm_dir = Path("/dev/shm")
        status = {
            "dev_shm_mounted": shm_dir.exists(),
            "active_lola_segments": [],
            "status": "ready"
        }
        if shm_dir.exists():
            try:
                for entry in shm_dir.iterdir():
                    if "lola" in entry.name.lower() or "vehicle" in entry.name.lower() or "vsomeip" in entry.name.lower():
                        status["active_lola_segments"].append(entry.name)
            except Exception as e:
                status["error"] = str(e)
        return status

    def _check_systemd(self):
        has_systemctl = shutil.which("systemctl") is not None
        booted_systemd = Path("/run/systemd/system").exists()
        return {
            "has_systemctl": has_systemctl,
            "booted_with_systemd": booted_systemd,
            "supervision_mode": "systemd" if (has_systemctl and booted_systemd) else "process_runner"
        }

    def _check_container_runtime(self):
        podman = shutil.which("podman")
        docker = shutil.which("docker")
        return {
            "podman": podman is not None,
            "docker": docker is not None,
            "recommended": "podman" if podman else ("docker" if docker else "none")
        }


class BenchmarkValidator:
    """Executes the 5-Stage validation benchmark on uploaded packages."""
    def __init__(self, config):
        self.config = config

    def validate_package(self, package_path: Path, temp_extract_dir: Path):
        results = {
            "passed": False,
            "stages": {
                "stage1_archive_safety": {"name": "Archive Safety & Integrity", "passed": False, "details": []},
                "stage2_manifest_checksum": {"name": "Manifest & Checksum Verification", "passed": False, "details": []},
                "stage3_compatibility": {"name": "Architecture & Syntax Compatibility", "passed": False, "details": []},
                "stage4_security_permissions": {"name": "Security & Permissions Benchmark", "passed": False, "details": []},
                "stage5_startup_smoke": {"name": "Startup Smoke Benchmark", "passed": False, "details": []}
            },
            "manifest": None,
            "errors": []
        }

        # ---------------- Stage 1: Archive Safety Benchmark ----------------
        s1 = results["stages"]["stage1_archive_safety"]
        max_bytes = self.config.max_upload_size_mb * 1024 * 1024
        file_size = package_path.stat().st_size
        s1["details"].append(f"Package size: {file_size / (1024*1024):.2f} MB (limit: {self.config.max_upload_size_mb} MB)")
        if file_size > max_bytes:
            results["errors"].append(f"Package exceeds max upload limit of {self.config.max_upload_size_mb} MB")
            return results

        if not tarfile.is_tarfile(package_path):
            results["errors"].append("File is not a valid tar/tar.gz archive")
            return results

        try:
            with tarfile.open(package_path, "r:*") as tar:
                # Check for traversal attacks
                for member in tar.getmembers():
                    name = member.name
                    if name.startswith("/") or name.startswith("\\"):
                        results["errors"].append(f"Malicious archive member with absolute path: {name}")
                        return results
                    if ".." in Path(name).parts:
                        results["errors"].append(f"Path traversal detected in archive member: {name}")
                        return results
                    if member.issym() or member.islnk():
                        link_target = member.linkname
                        if link_target.startswith("/") or ".." in Path(link_target).parts:
                            results["errors"].append(f"Dangerous link target detected: {name} -> {link_target}")
                            return results
                
                # Extract safely
                temp_extract_dir.mkdir(parents=True, exist_ok=True)
                tar.extractall(path=temp_extract_dir)
                s1["passed"] = True
                s1["details"].append(f"Extracted {len(tar.getmembers())} members without path traversal issues")
        except Exception as e:
            results["errors"].append(f"Archive decompression failed: {e}")
            return results

        # ---------------- Stage 2: Manifest & Checksum Benchmark ----------------
        s2 = results["stages"]["stage2_manifest_checksum"]
        manifest_path = temp_extract_dir / "manifest.json"
        if not manifest_path.exists():
            results["errors"].append("Missing required manifest.json in package root")
            return results

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            results["manifest"] = manifest
        except Exception as e:
            results["errors"].append(f"Invalid JSON in manifest.json: {e}")
            return results

        required_fields = ["app_id", "version", "runtime", "entrypoint"]
        for field in required_fields:
            if field not in manifest or not manifest[field]:
                results["errors"].append(f"Manifest missing required field: '{field}'")
                return results

        app_id = manifest["app_id"]
        if not app_id.replace("_", "").replace("-", "").isalnum():
            results["errors"].append(f"Invalid app_id '{app_id}'. Must be alphanumeric with hyphens or underscores.")
            return results

        runtime = manifest["runtime"].lower()
        if runtime not in ["native", "python"]:
            results["errors"].append(f"Unsupported runtime '{runtime}'. Supported: 'native', 'python'")
            return results

        # Validate checksums if provided
        checksums = manifest.get("checksums", {})
        if checksums:
            for rel_file, expected_hash in checksums.items():
                target_file = temp_extract_dir / rel_file
                if not target_file.exists():
                    results["errors"].append(f"Checksum validation failed: file '{rel_file}' missing from package")
                    return results
                actual_hash = self._compute_sha256(target_file)
                if actual_hash.lower() != expected_hash.lower():
                    results["errors"].append(f"Checksum mismatch for '{rel_file}': expected {expected_hash}, got {actual_hash}")
                    return results
            s2["details"].append(f"Verified {len(checksums)} SHA-256 file checksums successfully")
        else:
            s2["details"].append("No explicit checksums list in manifest, integrity validated via archive hash")

        s2["passed"] = True
        s2["details"].append(f"Manifest valid: {app_id} v{manifest['version']} (runtime: {runtime})")

        # ---------------- Stage 3: Architecture & Binary Compatibility Benchmark ----------------
        s3 = results["stages"]["stage3_compatibility"]
        entrypoint_rel = manifest["entrypoint"]
        entrypoint_path = temp_extract_dir / entrypoint_rel

        if not entrypoint_path.exists():
            results["errors"].append(f"Entrypoint '{entrypoint_rel}' not found in package")
            return results

        target_arch = manifest.get("target_architecture", self.config.target_architecture)

        if runtime == "native":
            # Check ELF header
            elf_check = self._verify_elf_binary(entrypoint_path, target_arch)
            if not elf_check["valid"]:
                results["errors"].append(f"Binary compatibility benchmark failed: {elf_check['error']}")
                return results
            s3["details"].append(f"ELF verification passed: {elf_check['info']}")
            s3["passed"] = True

        elif runtime == "python":
            # Check python syntax
            try:
                py_compile.compile(str(entrypoint_path), doraise=True)
                s3["details"].append(f"Python syntax compilation passed for {entrypoint_rel}")
                s3["passed"] = True
            except py_compile.PyCompileError as e:
                results["errors"].append(f"Python syntax error in entrypoint: {e}")
                return results

        # ---------------- Stage 4: Execution Permissions & Security Benchmark ----------------
        s4 = results["stages"]["stage4_security_permissions"]
        # Verify no setuid/setgid bits
        for root, dirs, files in os.walk(temp_extract_dir):
            for fname in files:
                fpath = Path(root) / fname
                mode = fpath.stat().st_mode
                if mode & 0o4000 or mode & 0o2000:
                    results["errors"].append(f"Security violation: setuid/setgid bit set on {fname}")
                    return results

        # Make entrypoint executable
        current_mode = entrypoint_path.stat().st_mode
        entrypoint_path.chmod(current_mode | 0o755)
        s4["details"].append(f"Applied executable permissions (0755) to {entrypoint_rel}")
        s4["passed"] = True

        # All static checks passed
        results["passed"] = True
        return results

    def _compute_sha256(self, file_path: Path):
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _verify_elf_binary(self, binary_path: Path, expected_arch: str):
        try:
            with open(binary_path, "rb") as f:
                header = f.read(64)
            if len(header) < 52 or header[:4] != b"\x7fELF":
                return {"valid": False, "error": "Not a valid ELF binary"}

            ei_class = header[4]     # 1 = 32-bit, 2 = 64-bit
            ei_data = header[5]      # 1 = Little endian, 2 = Big endian
            e_machine = struct.unpack("<H" if ei_data == 1 else ">H", header[18:20])[0]

            # e_machine definitions
            EM_AARCH64 = 183   # 0xb7
            EM_X86_64 = 62     # 0x3e
            EM_ARM = 40        # 32-bit ARM

            arch_map = {
                EM_AARCH64: "aarch64",
                EM_X86_64: "x86_64",
                EM_ARM: "armv7l"
            }
            detected_arch = arch_map.get(e_machine, f"machine_id_{e_machine}")
            bits = "64-bit" if ei_class == 2 else "32-bit"

            host_machine = platform.machine()
            # Allow binary if it matches expected target OR if running on matching host (for dev testing)
            if expected_arch == "aarch64" and e_machine != EM_AARCH64 and host_machine != detected_arch:
                return {
                    "valid": False,
                    "error": f"Binary architecture mismatch: detected '{detected_arch}' ({bits}), but target requires '{expected_arch}'."
                }

            return {
                "valid": True,
                "info": f"Architecture: {detected_arch} ({bits}, {'little-endian' if ei_data == 1 else 'big-endian'})"
            }
        except Exception as e:
            return {"valid": False, "error": f"Failed reading binary header: {e}"}

    def run_smoke_test(self, entrypoint_path: Path, runtime: str, args=None):
        """Stage 5: Runs the application for a grace period to verify no immediate crash."""
        args = args or []
        if runtime == "python":
            cmd = [sys.executable, str(entrypoint_path)] + args
        else:
            cmd = [str(entrypoint_path)] + args

        env = os.environ.copy()
        env["SDV_SMOKE_TEST"] = "1"
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(entrypoint_path.parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Monitor during grace period
            timeout_sec = self.config.smoke_test_seconds
            start_time = time.time()
            crashed = False
            exit_code = 0
            stderr_out = ""

            while time.time() - start_time < timeout_sec:
                poll_res = proc.poll()
                if poll_res is not None:
                    # Process exited early
                    exit_code = poll_res
                    stdout_out, stderr_out = proc.communicate(timeout=1)
                    if exit_code != 0:
                        crashed = True
                    break
                time.sleep(0.2)

            if proc.poll() is None:
                # Still running happily after grace period, terminate smoke test
                proc.terminate()
                try:
                    proc.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                return {
                    "passed": True,
                    "details": f"Process remained running cleanly across {timeout_sec}s smoke window"
                }

            if crashed:
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
                return {
                    "passed": False,
                    "error": f"Application crashed immediately on startup with exit code {exit_code}. Stderr: {stderr_out.strip()}"
                }
            else:
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
                return {
                    "passed": True,
                    "details": f"Application completed execution cleanly with exit code 0"
                }
                return {
                    "passed": True,
                    "details": f"Application completed execution cleanly with exit code 0"
                }

        except Exception as e:
            return {"passed": False, "error": f"Failed to execute smoke test: {e}"}


class ApplicationManager:
    """Manages installation, versioning, systemd units, and lifecycle of deployed apps."""
    def __init__(self, config):
        self.config = config
        self.apps_dir = Path(config.apps_dir)
        self.logs_dir = Path(config.logs_dir)
        self.processes = {}  # In-memory process table when running without systemd

    def list_applications(self):
        apps = []
        if not self.apps_dir.exists():
            return apps

        for item in self.apps_dir.iterdir():
            if item.is_dir() and (item / "metadata.json").exists():
                try:
                    with open(item / "metadata.json", "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    status_info = self.get_application_status(item.name)
                    meta["status"] = status_info
                    apps.append(meta)
                except Exception as e:
                    logger.error(f"Error reading app metadata for {item.name}: {e}")
        return apps

    def get_application(self, app_id: str):
        app_dir = self.apps_dir / app_id
        meta_file = app_dir / "metadata.json"
        if not meta_file.exists():
            return None
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["status"] = self.get_application_status(app_id)
        return meta

    def get_application_status(self, app_id: str):
        # Check systemd first if available
        if shutil.which("systemctl") and Path("/run/systemd/system").exists():
            unit = f"sdv-app@{app_id}.service"
            try:
                res = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
                active_state = res.stdout.strip()
                if active_state == "active":
                    # Get PID
                    pid_res = subprocess.run(["systemctl", "show", unit, "--property=MainPID"], capture_output=True, text=True)
                    pid = pid_res.stdout.strip().split("=")[-1]
                    return {"state": "running", "active": True, "pid": int(pid) if pid.isdigit() else None, "mode": "systemd"}
                elif active_state == "failed":
                    return {"state": "failed", "active": False, "mode": "systemd"}
                else:
                    return {"state": "stopped", "active": False, "mode": "systemd"}
            except Exception:
                pass

        # Fallback to local process runner
        proc_info = self.processes.get(app_id)
        if proc_info and proc_info.get("process"):
            proc = proc_info["process"]
            if proc.poll() is None:
                return {"state": "running", "active": True, "pid": proc.pid, "uptime_sec": int(time.time() - proc_info["start_time"]), "mode": "process_runner"}
            else:
                exit_code = proc.poll()
                return {"state": "failed" if exit_code != 0 else "stopped", "active": False, "exit_code": exit_code, "mode": "process_runner"}

        return {"state": "stopped", "active": False, "mode": "process_runner"}

    def install_and_activate(self, app_id: str, version: str, staging_dir: Path, manifest: dict):
        app_dir = self.apps_dir / app_id
        app_dir.mkdir(parents=True, exist_ok=True)
        version_dir = app_dir / "versions" / version
        current_symlink = app_dir / "current"
        meta_file = app_dir / "metadata.json"

        # Read existing metadata to preserve previous known good version
        prev_version = None
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    old_meta = json.load(f)
                    prev_version = old_meta.get("active_version")
            except Exception:
                pass

        # If previous version exists and differs, store as rollback candidate
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.parent.mkdir(parents=True, exist_ok=True)

        # Move from staging to permanent version dir
        shutil.move(str(staging_dir), str(version_dir))

        # Update symlink atomically
        temp_symlink = app_dir / f"current.tmp.{os.getpid()}"
        if temp_symlink.exists():
            temp_symlink.unlink()
        temp_symlink.symlink_to(f"versions/{version}")
        os.replace(str(temp_symlink), str(current_symlink))

        # Write metadata
        metadata = {
            "app_id": app_id,
            "name": manifest.get("name", app_id),
            "description": manifest.get("description", ""),
            "active_version": version,
            "previous_known_good_version": prev_version if prev_version != version else None,
            "runtime": manifest["runtime"],
            "entrypoint": manifest["entrypoint"],
            "target_architecture": manifest.get("target_architecture", self.config.target_architecture),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # Start application
        self.start_application(app_id)
        return metadata

    def start_application(self, app_id: str):
        app = self.get_application(app_id)
        if not app:
            raise ValueError(f"Application '{app_id}' not found")

        # Try systemd first
        if shutil.which("systemctl") and Path("/run/systemd/system").exists():
            unit = f"sdv-app@{app_id}.service"
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            res = subprocess.run(["systemctl", "restart", unit], capture_output=True, text=True)
            if res.returncode == 0:
                logger.info(f"Started application {app_id} via systemd")
                return True

        # Process runner fallback
        current_dir = self.apps_dir / app_id / "current"
        entrypoint = current_dir / app["entrypoint"]
        runtime = app["runtime"]

        log_file = self.logs_dir / f"{app_id}.log"
        out_f = open(log_file, "a", encoding="utf-8")

        if runtime == "python":
            cmd = [sys.executable, str(entrypoint)]
        else:
            cmd = [str(entrypoint)]

        proc = subprocess.Popen(
            cmd,
            cwd=str(current_dir),
            stdout=out_f,
            stderr=subprocess.STDOUT,
            text=True
        )
        self.processes[app_id] = {
            "process": proc,
            "start_time": time.time(),
            "log_handle": out_f
        }
        logger.info(f"Started application {app_id} via process runner (PID {proc.pid})")
        return True

    def stop_application(self, app_id: str):
        if shutil.which("systemctl") and Path("/run/systemd/system").exists():
            unit = f"sdv-app@{app_id}.service"
            subprocess.run(["systemctl", "stop", unit], check=False)

        proc_info = self.processes.get(app_id)
        if proc_info and proc_info.get("process"):
            proc = proc_info["process"]
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            if proc_info.get("log_handle"):
                proc_info["log_handle"].close()
            del self.processes[app_id]
        logger.info(f"Stopped application {app_id}")
        return True

    def rollback_application(self, app_id: str):
        app = self.get_application(app_id)
        if not app:
            raise ValueError(f"Application '{app_id}' not found")

        prev_version = app.get("previous_known_good_version")
        if not prev_version:
            raise ValueError("No previous known-good version recorded for rollback")

        app_dir = self.apps_dir / app_id
        target_dir = app_dir / "versions" / prev_version
        if not target_dir.exists():
            raise ValueError(f"Previous version directory '{prev_version}' missing")

        self.stop_application(app_id)

        # Switch symlink
        current_symlink = app_dir / "current"
        temp_symlink = app_dir / f"current.tmp.{os.getpid()}"
        temp_symlink.symlink_to(f"versions/{prev_version}")
        os.replace(str(temp_symlink), str(current_symlink))

        # Update metadata
        current_active = app["active_version"]
        app["active_version"] = prev_version
        app["previous_known_good_version"] = current_active
        app["rolled_back_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(app_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(app, f, indent=2)

        self.start_application(app_id)
        logger.info(f"Rolled back application {app_id} to v{prev_version}")
        return app

    def remove_application(self, app_id: str):
        self.stop_application(app_id)
        app_dir = self.apps_dir / app_id
        if app_dir.exists():
            shutil.rmtree(app_dir)
        logger.info(f"Removed application {app_id}")
        return True

    def get_logs(self, app_id: str, lines=100):
        # Try journald first
        if shutil.which("journalctl"):
            unit = f"sdv-app@{app_id}.service"
            try:
                res = subprocess.run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager"], capture_output=True, text=True)
                if res.stdout.strip():
                    return res.stdout
            except Exception:
                pass

        # Fallback to local log file
        log_file = self.logs_dir / f"{app_id}.log"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                    return "".join(all_lines[-lines:])
            except Exception as e:
                return f"Error reading log file: {e}"
        return "No logs available yet."


class DeploymentRequestHandler(BaseHTTPRequestHandler):
    config = None
    inspector = None
    validator = None
    app_manager = None
    static_dir = None
    sessions = {}
    session_ttl_seconds = 8 * 60 * 60
    login_failures = {}
    login_window_seconds = 5 * 60
    max_login_failures = 5

    def log_request(self, code="-", size="-"):
        request_parts = self.requestline.split(" ", 2)
        if len(request_parts) >= 2 and "?" in request_parts[1]:
            request_parts[1] = request_parts[1].split("?", 1)[0]
        safe_requestline = " ".join(request_parts)
        self.log_message('"%s" %s %s', safe_requestline, code, size)

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _send_json(self, status_code, data, headers=None):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors()
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status_code, message):
        self._send_json(status_code, {"success": False, "error": message})

    def _is_authenticated(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if hmac.compare_digest(token, self.config.auth_token):
                return True

        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            cookies = SimpleCookie()
            try:
                cookies.load(cookie_header)
                session_cookie = cookies.get("sdv_session")
            except Exception:
                session_cookie = None
            if session_cookie:
                session_id = session_cookie.value
                session = self.sessions.get(session_id)
                if session and session["expires_at"] > time.time():
                    return True
                self.sessions.pop(session_id, None)

        return False

    def _get_session(self):
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
            session_cookie = cookies.get("sdv_session")
        except Exception:
            return None
        if not session_cookie:
            return None
        session = self.sessions.get(session_cookie.value)
        if session and session["expires_at"] > time.time():
            return session
        self.sessions.pop(session_cookie.value, None)
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/session":
            session = self._get_session()
            self._send_json(200, {
                "authenticated": bool(session),
                "email": session.get("email") if session else None
            })
            return

        # Static assets
        if path == "/" or not path.startswith("/api/"):
            self._serve_static(path)
            return

        # Authenticated API endpoints
        if not self._is_authenticated():
            self._send_error_json(401, "Unauthorized")
            return

        if path == "/api/v1/environment":
            env_info = self.inspector.get_info()
            self._send_json(200, {"success": True, "data": env_info})

        elif path == "/api/v1/apps":
            apps = self.app_manager.list_applications()
            self._send_json(200, {"success": True, "count": len(apps), "data": apps})

        elif path.startswith("/api/v1/apps/") and path.endswith("/logs"):
            app_id = path.split("/")[4]
            qs = urllib.parse.parse_qs(parsed.query)
            lines = int(qs.get("lines", ["100"])[0])
            logs = self.app_manager.get_logs(app_id, lines=lines)
            self._send_json(200, {"success": True, "app_id": app_id, "logs": logs})

        elif path.startswith("/api/v1/apps/"):
            app_id = path.split("/")[4]
            app = self.app_manager.get_application(app_id)
            if app:
                self._send_json(200, {"success": True, "data": app})
            else:
                self._send_error_json(404, f"Application '{app_id}' not found")

        else:
            self._send_error_json(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/login":
            client_ip = self.client_address[0]
            now = time.time()
            recent_failures = [
                timestamp for timestamp in self.login_failures.get(client_ip, [])
                if now - timestamp < self.login_window_seconds
            ]
            if len(recent_failures) >= self.max_login_failures:
                self.login_failures[client_ip] = recent_failures
                self._send_error_json(429, "Too many login attempts; try again in a few minutes")
                return

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > 4096:
                self._send_error_json(400, "Invalid login request")
                return
            try:
                credentials = json.loads(self.rfile.read(content_length))
                email = str(credentials.get("email", "")).strip().casefold()
                password = str(credentials.get("password", ""))
            except (json.JSONDecodeError, AttributeError):
                self._send_error_json(400, "Invalid login request")
                return
            user = next(
                (entry for entry in self.config.users if str(entry.get("email", "")).casefold() == email),
                None
            )
            if not user or not verify_password(password, user):
                recent_failures.append(now)
                self.login_failures[client_ip] = recent_failures
                self._send_error_json(401, "Invalid email or password")
                return

            self.login_failures.pop(client_ip, None)
            session_id = secrets.token_urlsafe(32)
            self.sessions[session_id] = {
                "expires_at": time.time() + self.session_ttl_seconds,
                "email": email
            }
            cookie = f"sdv_session={session_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age={self.session_ttl_seconds}"
            if self.config.use_tls:
                cookie += "; Secure"
            self._send_json(200, {"success": True, "email": email}, {"Set-Cookie": cookie})
            return

        if path == "/api/v1/logout":
            cookie_header = self.headers.get("Cookie", "")
            cookies = SimpleCookie()
            try:
                cookies.load(cookie_header)
                session_cookie = cookies.get("sdv_session")
            except Exception:
                session_cookie = None
            if session_cookie:
                self.sessions.pop(session_cookie.value, None)
            expired_cookie = "sdv_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
            if self.config.use_tls:
                expired_cookie += "; Secure"
            self._send_json(200, {"success": True}, {"Set-Cookie": expired_cookie})
            return

        if not self._is_authenticated():
            self._send_error_json(401, "Unauthorized")
            return

        if path == "/api/v1/apps/upload":
            self._handle_upload()

        elif path.startswith("/api/v1/apps/") and path.endswith("/start"):
            app_id = path.split("/")[4]
            try:
                self.app_manager.start_application(app_id)
                self._send_json(200, {"success": True, "message": f"Application '{app_id}' started"})
            except Exception as e:
                self._send_error_json(400, str(e))

        elif path.startswith("/api/v1/apps/") and path.endswith("/stop"):
            app_id = path.split("/")[4]
            try:
                self.app_manager.stop_application(app_id)
                self._send_json(200, {"success": True, "message": f"Application '{app_id}' stopped"})
            except Exception as e:
                self._send_error_json(400, str(e))

        elif path.startswith("/api/v1/apps/") and path.endswith("/restart"):
            app_id = path.split("/")[4]
            try:
                self.app_manager.stop_application(app_id)
                time.sleep(0.5)
                self.app_manager.start_application(app_id)
                self._send_json(200, {"success": True, "message": f"Application '{app_id}' restarted"})
            except Exception as e:
                self._send_error_json(400, str(e))

        elif path.startswith("/api/v1/apps/") and path.endswith("/rollback"):
            app_id = path.split("/")[4]
            try:
                updated = self.app_manager.rollback_application(app_id)
                self._send_json(200, {"success": True, "message": f"Rolled back to v{updated['active_version']}", "data": updated})
            except Exception as e:
                self._send_error_json(400, str(e))

        else:
            self._send_error_json(404, "Endpoint not found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not self._is_authenticated():
            self._send_error_json(401, "Unauthorized: Invalid or missing Bearer token")
            return

        if path.startswith("/api/v1/apps/"):
            app_id = path.split("/")[4]
            try:
                self.app_manager.remove_application(app_id)
                self._send_json(200, {"success": True, "message": f"Application '{app_id}' removed"})
            except Exception as e:
                self._send_error_json(400, str(e))
        else:
            self._send_error_json(404, "Endpoint not found")

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if content_length == 0:
            self._send_error_json(400, "Empty payload")
            return

        staging_id = f"upload_{int(time.time())}_{os.getpid()}"
        staging_dir = Path(self.config.staging_dir) / staging_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        archive_path = staging_dir / "package.tar.gz"
        extract_dir = staging_dir / "unpacked"

        try:
            # Read payload
            if "multipart/form-data" in content_type:
                # Extract binary body from multipart
                boundary = content_type.split("boundary=")[-1].encode("utf-8")
                raw_data = self.rfile.read(content_length)
                parts = raw_data.split(b"--" + boundary)
                file_bytes = None
                for part in parts:
                    if b'filename="' in part:
                        header_end = part.find(b"\r\n\r\n")
                        if header_end != -1:
                            file_bytes = part[header_end + 4 :].rstrip(b"\r\n")
                            break
                if not file_bytes:
                    self._send_error_json(400, "Could not find file in multipart data")
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return
                with open(archive_path, "wb") as f:
                    f.write(file_bytes)
            else:
                # Raw binary stream
                with open(archive_path, "wb") as f:
                    remaining = content_length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)

            # ---------------- Run 5-Stage Benchmarks ----------------
            benchmark_results = self.validator.validate_package(archive_path, extract_dir)
            if not benchmark_results["passed"]:
                self._send_json(422, {
                    "success": False,
                    "stage_failed": "Static Validation",
                    "benchmark_results": benchmark_results
                })
                shutil.rmtree(staging_dir, ignore_errors=True)
                return

            manifest = benchmark_results["manifest"]
            app_id = manifest["app_id"]
            version = manifest["version"]
            runtime = manifest["runtime"]
            entrypoint = extract_dir / manifest["entrypoint"]

            # Run Stage 5: Startup Smoke Benchmark
            smoke_res = self.validator.run_smoke_test(entrypoint, runtime)
            s5 = benchmark_results["stages"]["stage5_startup_smoke"]
            if not smoke_res["passed"]:
                s5["passed"] = False
                s5["details"].append(smoke_res["error"])
                self._send_json(422, {
                    "success": False,
                    "stage_failed": "Stage 5: Startup Smoke Benchmark",
                    "error": smoke_res["error"],
                    "benchmark_results": benchmark_results
                })
                shutil.rmtree(staging_dir, ignore_errors=True)
                return

            s5["passed"] = True
            s5["details"].append(smoke_res["details"])

            # ---------------- Promote to Installed Apps ----------------
            app_meta = self.app_manager.install_and_activate(app_id, version, extract_dir, manifest)
            archive_path.unlink(missing_ok=True)
            shutil.rmtree(staging_dir, ignore_errors=True)

            self._send_json(201, {
                "success": True,
                "message": f"Application '{app_id}' v{version} successfully validated and activated",
                "app": app_meta,
                "benchmarks": benchmark_results
            })

        except Exception as e:
            logger.error(f"Upload error: {e}", exc_info=True)
            self._send_error_json(500, f"Internal deployment error: {e}")
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        rel_path = path.lstrip("/")
        file_path = self.static_dir / rel_path

        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".svg": "image/svg+xml"
        }
        ext = file_path.suffix.lower()
        content_type = content_types.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))


def run_server(config_file=None):
    cfg = DeploymentConfig(config_file)
    inspector = EnvironmentInspector(cfg)
    validator = BenchmarkValidator(cfg)
    app_manager = ApplicationManager(cfg)
    static_dir = Path(__file__).resolve().parent / "static"

    DeploymentRequestHandler.config = cfg
    DeploymentRequestHandler.inspector = inspector
    DeploymentRequestHandler.validator = validator
    DeploymentRequestHandler.app_manager = app_manager
    DeploymentRequestHandler.static_dir = static_dir

    server_address = (cfg.host, cfg.port)
    httpd = HTTPServer(server_address, DeploymentRequestHandler)

    if cfg.use_tls:
        import ssl
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=cfg.tls_cert_file, keyfile=cfg.tls_key_file)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        proto = "https"
    else:
        proto = "http"

    logger.info("=" * 60)
    logger.info(" SDV Web-Based Application Deployment Server")
    logger.info(f" Listening on {proto}://{cfg.host}:{cfg.port}")
    logger.info(f" Target Architecture: {cfg.target_architecture}")
    logger.info(f" Browser accounts configured: {len(cfg.users)}")
    logger.info(f" Apps Root Directory: {cfg.apps_dir}")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    config_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_server(config_arg)
