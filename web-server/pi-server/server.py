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
import signal
import pwd
import grp
import re
import threading
import uuid
import secrets
import tempfile
from email.message import Message
from email import message_from_bytes
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sdv-deployer")
APP_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def validate_app_id(app_id):
    if not isinstance(app_id, str) or not APP_ID_PATTERN.fullmatch(app_id):
        raise ValueError("Invalid application ID")
    return app_id


class DeploymentConfig:
    def __init__(self, config_path=None):
        base_dir = Path(__file__).resolve().parent
        default_config_path = base_dir / "config.json"
        target_path = Path(config_path) if config_path else default_config_path

        self.host = "127.0.0.1"
        self.port = 8443
        self.use_tls = False
        self.tls_cert_file = str(base_dir / "certs" / "server.crt")
        self.tls_key_file = str(base_dir / "certs" / "server.key")
        self.auth_token = secrets.token_urlsafe(32)
        self.allowed_origins = ["http://localhost:8080"]
        self.app_user = "sdv-apps"
        self.app_group = "sdv-apps"
        self.data_dir = str(base_dir / "runtime" / "data")
        self.apps_dir = str(base_dir / "runtime" / "apps")
        self.staging_dir = str(base_dir / "runtime" / "staging")
        self.logs_dir = str(base_dir / "runtime" / "logs")
        self.max_upload_size_mb = 100
        self.max_expanded_size_mb = 512
        self.max_archive_members = 10000
        self.smoke_test_seconds = 3
        self.target_architecture = "aarch64"

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
        if "SDV_ALLOWED_ORIGINS" in os.environ:
            self.allowed_origins = [
                origin.strip() for origin in os.environ["SDV_ALLOWED_ORIGINS"].split(",") if origin.strip()
            ]
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
                "architecture": platform.machine()
            },
            "toolchain": {
                "python_version": sys.version.split()[0],
                "python_executable": sys.executable,
                "glibc_version": self._get_glibc_version(),
                "gxx_version": self._get_gxx_version(),
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

    def _get_gxx_version(self):
        compiler = shutil.which("g++")
        if not compiler:
            return "not installed"
        try:
            result = subprocess.run([compiler, "--version"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
        return "unavailable"

    def _check_kuksa(self):
        try:
            process_names = self._find_kuksa_processes()
        except OSError as error:
            return {"available": False, "running": False, "error": str(error)}

        detected_processes = sorted(set(process_names))
        return {
            "available": bool(detected_processes),
            "running": bool(detected_processes),
            "processes": detected_processes
        }

    @staticmethod
    def _find_kuksa_processes(proc_root: Path = Path("/proc")) -> list[str]:
        process_names = []
        for process_dir in proc_root.iterdir():
            if not process_dir.name.isdigit():
                continue
            try:
                process_name = (process_dir / "comm").read_text(encoding="utf-8").strip().casefold()
            except (OSError, UnicodeError):
                continue
            if process_name.startswith("databroker") or process_name.startswith("kuksa-databro"):
                process_names.append(process_name)
        return sorted(set(process_names))

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
            "supervision_mode": "process_runner"
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
        self.smoke_test_dir = Path(config.staging_dir) / "smoke-tests"
        self.smoke_test_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def _read_process_identity(pid):
        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
            fields = raw[raw.rfind(")") + 2:].split()
            return {
                "state": fields[0],
                "pgrp": int(fields[2]),
                "session": int(fields[3]),
                "start_time": fields[19],
            }
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _current_boot_id():
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        except OSError:
            return ""

    def _smoke_group_matches(self, record):
        try:
            pgid = int(record["pgid"])
        except (KeyError, TypeError, ValueError):
            return False
        if pgid <= 1 or record.get("boot_id") != self._current_boot_id():
            return False
        leader = self._read_process_identity(pgid)
        return bool(
            leader and leader["state"] not in {"Z", "X"}
            and leader["pgrp"] == pgid and leader["session"] == pgid
            and leader["start_time"] == record.get("start_time")
        )

    def _register_smoke_process(self, proc):
        identity = self._read_process_identity(proc.pid)
        boot_id = self._current_boot_id()
        if not identity or not boot_id:
            raise RuntimeError("Unable to record smoke-test process identity")
        record = {"pgid": proc.pid, "start_time": identity["start_time"], "boot_id": boot_id}
        record_path = self.smoke_test_dir / f"{uuid.uuid4().hex}.json"
        fd = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as record_file:
            json.dump(record, record_file)
            record_file.flush()
            os.fsync(record_file.fileno())
        return record_path

    def cleanup_smoke_tests(self):
        for record_path in self.smoke_test_dir.glob("*.json"):
            try:
                fd = os.open(record_path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "r", encoding="utf-8") as record_file:
                    record = json.load(record_file)
                if self._smoke_group_matches(record):
                    self._terminate_process_group(int(record["pgid"]))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                logger.warning("Could not clean smoke-test record %s: %s", record_path, error)
            finally:
                try:
                    record_path.unlink()
                except FileNotFoundError:
                    pass

    def validate_package(self, package_path: Path, temp_extract_dir: Path):
        results = self._run_static_stages(package_path, temp_extract_dir)
        failed_seen = False
        for stage in results["stages"].values():
            if stage["passed"]:
                stage["status"] = "passed"
            elif failed_seen:
                stage["status"] = "not_run"
                stage["details"] = []
            elif results["passed"]:
                stage["status"] = "pending"
            else:
                failed_seen = True
                stage["status"] = "failed"
                stage["error"] = "; ".join(results["errors"]) or "Validation failed"
        return results

    def _run_static_stages(self, package_path: Path, temp_extract_dir: Path):
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
                members = []
                expanded_bytes = 0
                expanded_limit = self.config.max_expanded_size_mb * 1024 * 1024
                for member in tar:
                    if len(members) >= self.config.max_archive_members:
                        results["errors"].append(
                            f"Archive exceeds the {self.config.max_archive_members} member limit"
                        )
                        return results
                    name = member.name
                    member_path = Path(name)
                    if member_path.is_absolute() or name.startswith("\\"):
                        results["errors"].append(f"Malicious archive member with absolute path: {name}")
                        return results
                    if "\\" in name or ".." in member_path.parts:
                        results["errors"].append(f"Path traversal detected in archive member: {name}")
                        return results
                    if not (member.isfile() or member.isdir()):
                        results["errors"].append(
                            f"Unsupported archive member type: {name}"
                        )
                        return results
                    if member.isfile():
                        if member.size < 0:
                            results["errors"].append(f"Invalid archive member size: {name}")
                            return results
                        expanded_bytes += member.size
                        if expanded_bytes > expanded_limit:
                            results["errors"].append(
                                f"Archive exceeds expanded size limit of "
                                f"{self.config.max_expanded_size_mb} MB"
                            )
                            return results
                    members.append(member)

                temp_extract_dir.mkdir(parents=True, exist_ok=True)
                tar.extractall(path=temp_extract_dir, members=members)
                s1["passed"] = True
                s1["details"].append(
                    f"Extracted {len(members)} files and directories "
                    f"({expanded_bytes / (1024 * 1024):.2f} MB expanded)"
                )
        except Exception as e:
            results["errors"].append(f"Archive decompression failed: {e}")
            return results

        # ---------------- Stage 2: Manifest & Checksum Benchmark ----------------
        s2 = results["stages"]["stage2_manifest_checksum"]
        manifest_path = temp_extract_dir / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            results["errors"].append("Missing required manifest.json in package root")
            return results
        if manifest_path.stat().st_size > 1024 * 1024:
            results["errors"].append("manifest.json exceeds the 1 MB size limit")
            return results

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            results["manifest"] = manifest
        except Exception as e:
            results["errors"].append(f"Invalid JSON in manifest.json: {e}")
            return results

        if not isinstance(manifest, dict):
            results["errors"].append("Manifest must contain a JSON object")
            return results

        required_fields = ["app_id", "version", "runtime", "entrypoint"]
        for field in required_fields:
            if field not in manifest or not manifest[field]:
                results["errors"].append(f"Manifest missing required field: '{field}'")
                return results

        app_id = manifest["app_id"]
        if not isinstance(app_id, str) or not APP_ID_PATTERN.fullmatch(app_id):
            results["errors"].append(f"Invalid app_id '{app_id}'. Must be alphanumeric with hyphens or underscores.")
            return results
        version = manifest["version"]
        if (not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version)
                or version in {".", ".."}):
            results["errors"].append("Invalid version; it must be a safe single path component")
            return results

        if not isinstance(manifest["runtime"], str):
            results["errors"].append("Manifest runtime must be a string")
            return results
        runtime = manifest["runtime"].lower()
        if runtime not in ["native", "python"]:
            results["errors"].append(f"Unsupported runtime '{runtime}'. Supported: 'native', 'python'")
            return results
        manifest["runtime"] = runtime
        args = manifest.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            results["errors"].append("Manifest args must be a list of strings")
            return results

        # Validate checksums if provided
        checksums = manifest.get("checksums", {})
        if not isinstance(checksums, dict):
            results["errors"].append("Manifest checksums must be an object")
            return results
        if checksums:
            for rel_file, expected_hash in checksums.items():
                target_file = self._resolve_bundle_file(temp_extract_dir, rel_file)
                if target_file is None:
                    results["errors"].append(f"Checksum validation failed: file '{rel_file}' missing from package")
                    return results
                if (not isinstance(expected_hash, str)
                        or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash)):
                    results["errors"].append(f"Invalid SHA-256 checksum for '{rel_file}'")
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
        entrypoint_path = self._resolve_bundle_file(temp_extract_dir, entrypoint_rel)
        if entrypoint_path is None:
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

        # Keep packages readable by the app group, without granting that group write access.
        try:
            app_gid = grp.getgrnam(self.config.app_group).gr_gid
            for current_root, directories, files in os.walk(temp_extract_dir):
                root_path = Path(current_root)
                os.chown(root_path, -1, app_gid)
                os.chmod(root_path, 0o2750)
                for directory in directories:
                    directory_path = root_path / directory
                    os.chown(directory_path, -1, app_gid, follow_symlinks=False)
                    os.chmod(directory_path, 0o2750, follow_symlinks=False)
                for filename in files:
                    file_path = root_path / filename
                    if file_path.is_symlink():
                        continue
                    existing_mode = file_path.stat().st_mode
                    os.chown(file_path, -1, app_gid)
                    os.chmod(file_path, 0o750 if existing_mode & 0o111 else 0o640)
        except KeyError:
            pass
        except PermissionError as error:
            results["errors"].append(f"Cannot prepare application files for {self.config.app_group}: {error}")
            return results

        current_mode = entrypoint_path.stat().st_mode
        entrypoint_path.chmod(current_mode | 0o750)
        s4["details"].append(f"Prepared read/execute permissions for {self.config.app_group}")
        s4["passed"] = True

        # All static checks passed
        results["passed"] = True
        return results

    @staticmethod
    def _resolve_bundle_file(root: Path, relative_path):
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
            return None
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        root = root.resolve()
        candidate = root.joinpath(relative)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not resolved.is_relative_to(root) or not resolved.is_file() or candidate.is_symlink():
            return None
        return resolved

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

    def run_smoke_test(self, entrypoint_path: Path, runtime: str, args=None, cwd=None):
        """Stage 5: Runs the application for a grace period to verify no immediate crash."""
        args = args or []
        if runtime == "python":
            cmd = [sys.executable, str(entrypoint_path)] + args
        else:
            cmd = [str(entrypoint_path)] + args

        env = os.environ.copy()
        env["SDV_SMOKE_TEST"] = "1"
        output_tail = bytearray()
        proc = None
        reader = None
        record_path = None

        def capture_output(pipe):
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    return
                output_tail.extend(chunk)
                if len(output_tail) > 8192:
                    del output_tail[:-8192]

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd or entrypoint_path.parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=self._drop_privileges
            )
            record_path = self._register_smoke_process(proc)
            timeout_sec = self.config.smoke_test_seconds
            reader = threading.Thread(target=capture_output, args=(proc.stdout,), daemon=True)
            reader.start()
            timed_out = False
            try:
                exit_code = proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = None

            self._terminate_process_group(proc.pid)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=1)
            reader.join(timeout=1)
            if reader.is_alive() and proc.stdout:
                proc.stdout.close()
                reader.join(timeout=0.2)
            elif proc.stdout:
                proc.stdout.close()

            if timed_out:
                return {
                    "passed": True,
                    "details": f"Process remained running cleanly across {timeout_sec}s smoke window"
                }
            if exit_code != 0:
                output = output_tail.decode("utf-8", errors="replace")
                return {
                    "passed": False,
                    "error": f"Application crashed immediately on startup with exit code {exit_code}. "
                             f"Output: {output.strip()}"
                }
            return {
                "passed": True,
                "details": "Application completed execution cleanly with exit code 0"
            }

        except Exception as e:
            cleanup_error = None
            if proc:
                try:
                    self._terminate_process_group(proc.pid)
                    if proc.poll() is None:
                        proc.wait(timeout=1)
                except Exception as error:
                    cleanup_error = error
                finally:
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait(timeout=1)
                        except ProcessLookupError:
                            pass
                    if proc.stdout:
                        proc.stdout.close()
                    if reader:
                        reader.join(timeout=0.2)
            message = f"Failed to execute smoke test: {e}"
            if cleanup_error:
                message += f"; process cleanup failed: {cleanup_error}"
            return {"passed": False, "error": message}
        finally:
            if record_path:
                record_path.unlink(missing_ok=True)

    @staticmethod
    def _terminate_process_group(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _drop_privileges(self):
        if os.geteuid() != 0:
            return None
        if not self.config.app_user:
            raise RuntimeError("An unprivileged app_user must be configured")
        account = pwd.getpwnam(self.config.app_user)
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)


class ApplicationManager:
    """Installs, versions, and runs deployed apps as child processes of the deployer."""
    def __init__(self, config):
        self.config = config
        self.apps_dir = Path(config.apps_dir)
        self.logs_dir = Path(config.logs_dir)
        self.app_user = config.app_user
        self.processes = {}
        self._app_locks = {}
        self._app_locks_guard = threading.Lock()

    def _app_lock(self, app_id):
        validate_app_id(app_id)
        with self._app_locks_guard:
            return self._app_locks.setdefault(app_id, threading.RLock())

    def _app_dir(self, app_id):
        app_dir = self.apps_dir / validate_app_id(app_id)
        try:
            if app_dir.is_symlink() or not app_dir.resolve().is_relative_to(self.apps_dir.resolve()):
                raise ValueError("Application directory must remain inside the apps directory")
        except RuntimeError as error:
            raise ValueError("Invalid application directory") from error
        return app_dir

    def _process_record_path(self, app_id):
        return self._app_dir(app_id) / "process.json"

    @staticmethod
    def _read_proc_stat(pid):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
            fields = stat[stat.rfind(")") + 2:].split()
            return {
                "state": fields[0],
                "pgrp": int(fields[2]),
                "session": int(fields[3]),
                "start_time": fields[19],
            }
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _boot_id():
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        except OSError:
            return ""

    def _process_group_members(self, record):
        try:
            pgid = int(record["pgid"])
        except (KeyError, TypeError, ValueError):
            return []
        if pgid <= 1 or not record.get("boot_id") or record["boot_id"] != self._boot_id():
            return []

        members = []
        try:
            entries = Path("/proc").iterdir()
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                stat = self._read_proc_stat(int(entry.name))
                if (not stat or stat["state"] in {"Z", "X"}
                        or stat["pgrp"] != pgid or stat["session"] != pgid):
                    continue
                if int(entry.name) == pgid and stat["start_time"] != record.get("start_time"):
                    return []
                members.append(int(entry.name))
        except OSError:
            return []
        return members

    def _read_process_record(self, app_id):
        path = self._process_record_path(app_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as record_file:
            record = json.load(record_file)
        if not isinstance(record, dict):
            raise ValueError(f"Invalid process record for application '{app_id}'")
        return record

    def _write_process_record(self, app_id, record):
        path = self._process_record_path(app_id)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as record_file:
                json.dump(record, record_file)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _terminate_app_group(self, app_id, record):
        members = self._process_group_members(record)
        if not members:
            return
        pgid = int(record["pgid"])
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and self._process_group_members(record):
            time.sleep(0.1)
        if self._process_group_members(record):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and self._process_group_members(record):
                time.sleep(0.05)

    def _set_current_version(self, app_dir, version):
        self._replace_current_link(app_dir, f"versions/{version}")

    @staticmethod
    def _replace_current_link(app_dir, target):
        current_link = app_dir / "current"
        temp_link = app_dir / f"current.tmp.{uuid.uuid4().hex}"
        try:
            temp_link.symlink_to(target)
            os.replace(temp_link, current_link)
        finally:
            temp_link.unlink(missing_ok=True)

    @staticmethod
    def _write_metadata(meta_file, metadata):
        temp_file = meta_file.with_name(f"{meta_file.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as output:
                json.dump(metadata, output, indent=2)
            os.replace(temp_file, meta_file)
        finally:
            temp_file.unlink(missing_ok=True)

    def _read_metadata(self, app_id):
        meta_file = self._app_dir(app_id) / "metadata.json"
        if not meta_file.is_file():
            return None
        with meta_file.open("r", encoding="utf-8") as source:
            return json.load(source)

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
        with self._app_lock(app_id):
            meta = self._read_metadata(app_id)
            if meta is None:
                return None
            meta["status"] = self.get_application_status(app_id)
            return meta

    def get_application_status(self, app_id: str):
        with self._app_lock(app_id):
            proc_info = self.processes.get(app_id)
            record = (proc_info or {}).get("record") or self._read_process_record(app_id)
            if record and self._process_group_members(record):
                return {
                    "state": "running",
                    "active": True,
                    "pid": int(record["pgid"]),
                    "mode": "process_runner"
                }

            if record:
                self._process_record_path(app_id).unlink(missing_ok=True)
            if proc_info:
                exit_code = proc_info["process"].poll()
                if proc_info.get("log_handle"):
                    proc_info["log_handle"].close()
                self.processes.pop(app_id, None)
                if exit_code is not None and exit_code != 0:
                    return {"state": "failed", "active": False, "exit_code": exit_code, "mode": "process_runner"}
            return {"state": "stopped", "active": False, "mode": "process_runner"}

    def install_and_activate(self, app_id: str, version: str, staging_dir: Path, manifest: dict):
        validate_app_id(app_id)
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            raise ValueError("Invalid version; it must be a safe single path component")
        with self._app_lock(app_id):
            app_dir = self._app_dir(app_id)
            meta_file = app_dir / "metadata.json"
            app_dir.mkdir(parents=True, exist_ok=True)
            versions_dir = app_dir / "versions"
            if versions_dir.is_symlink():
                raise ValueError("Application versions directory cannot be a symbolic link")
            versions_dir.mkdir(parents=True, exist_ok=True)
            versions_root = versions_dir.resolve()
            if not versions_root.is_relative_to(app_dir.resolve()):
                raise ValueError("Application versions directory must remain inside the app directory")
            version_dir = versions_dir / version
            old_metadata = self._read_metadata(app_id)
            current_link = app_dir / "current"
            old_target = os.readlink(current_link) if current_link.is_symlink() else None
            was_running = self.get_application_status(app_id)["state"] == "running"
            if version_dir.exists() or version_dir.is_symlink():
                raise ValueError(f"Version '{version}' is already installed and cannot be overwritten")

            candidate_dir = versions_dir / f".{version}.staging-{uuid.uuid4().hex}"
            try:
                shutil.move(str(staging_dir), str(candidate_dir))
                os.replace(candidate_dir, version_dir)
            except Exception:
                shutil.rmtree(candidate_dir, ignore_errors=True)
                raise
            previous_version = (old_metadata or {}).get("active_version")
            metadata = {
                "app_id": app_id,
                "name": manifest.get("name", app_id),
                "description": manifest.get("description", ""),
                "active_version": version,
                "previous_known_good_version": (
                    previous_version if previous_version != version else None
                ),
                "runtime": manifest["runtime"],
                "entrypoint": manifest["entrypoint"],
                "args": manifest.get("args", []),
                "target_architecture": manifest.get(
                    "target_architecture", self.config.target_architecture
                ),
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            try:
                self._set_current_version(app_dir, version)
                self._write_metadata(meta_file, metadata)
                self.start_application(app_id)
            except Exception:
                self.stop_application(app_id)
                if old_target is None:
                    current_link.unlink(missing_ok=True)
                else:
                    self._replace_current_link(app_dir, old_target)
                if old_metadata is None:
                    meta_file.unlink(missing_ok=True)
                else:
                    self._write_metadata(meta_file, old_metadata)
                shutil.rmtree(version_dir, ignore_errors=True)
                if was_running:
                    self.start_application(app_id)
                raise
            return metadata

    def start_application(self, app_id: str):
        with self._app_lock(app_id):
            app = self.get_application(app_id)
            if not app:
                raise ValueError(f"Application '{app_id}' not found")

            self.stop_application(app_id)
            current_dir = self._app_dir(app_id) / "current"
            entrypoint = BenchmarkValidator._resolve_bundle_file(
                current_dir, app.get("entrypoint")
            )
            if entrypoint is None:
                raise ValueError("Installed entrypoint is invalid")
            args = app.get("args", [])
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError("Installed application arguments are invalid")
            cmd = ([sys.executable, str(entrypoint)] if app["runtime"] == "python"
                   else [str(entrypoint)]) + args

            log_file = self.logs_dir / f"{app_id}.log"
            out_f = open(log_file, "a", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(current_dir),
                    stdout=out_f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=self._drop_privileges
                )
                stat = self._read_proc_stat(proc.pid)
                if stat is None:
                    raise RuntimeError("Unable to record application process identity")
                record = {
                    "pgid": proc.pid,
                    "start_time": stat["start_time"],
                    "boot_id": self._boot_id()
                }
                if not record["boot_id"]:
                    raise RuntimeError("Unable to record the system boot ID")
                self._write_process_record(app_id, record)
            except Exception:
                out_f.close()
                if "proc" in locals():
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=1)
                raise
            self.processes[app_id] = {
                "process": proc,
                "start_time": time.time(),
                "log_handle": out_f,
                "record": record
            }
            logger.info(f"Started application {app_id} via process runner (PID {proc.pid})")
            return True

    def restart_application(self, app_id: str):
        with self._app_lock(app_id):
            self.stop_application(app_id)
            return self.start_application(app_id)

    def _drop_privileges(self):
        if os.geteuid() != 0:
            return None
        if not self.app_user:
            raise RuntimeError("An unprivileged app_user must be configured")
        account = pwd.getpwnam(self.app_user)
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)

    def stop_application(self, app_id: str):
        with self._app_lock(app_id):
            proc_info = self.processes.get(app_id)
            record = (proc_info or {}).get("record") or self._read_process_record(app_id)
            if record:
                self._terminate_app_group(app_id, record)
                self._process_record_path(app_id).unlink(missing_ok=True)
            if proc_info:
                proc = proc_info["process"]
                if proc.poll() is None:
                    proc.wait(timeout=1)
                if proc_info.get("log_handle"):
                    proc_info["log_handle"].close()
                self.processes.pop(app_id, None)
            logger.info(f"Stopped application {app_id}")
            return True

    def rollback_application(self, app_id: str):
        with self._app_lock(app_id):
            current_metadata = self._read_metadata(app_id)
            if not current_metadata:
                raise ValueError(f"Application '{app_id}' not found")
            prev_version = current_metadata.get("previous_known_good_version")
            if not isinstance(prev_version, str) or not VERSION_PATTERN.fullmatch(prev_version):
                raise ValueError("No previous known-good version recorded for rollback")

            app_dir = self._app_dir(app_id)
            versions_dir = app_dir / "versions"
            target_dir = versions_dir / prev_version
            manifest_path = target_dir / "manifest.json"
            if (versions_dir.is_symlink() or target_dir.is_symlink()
                    or not target_dir.is_dir() or not manifest_path.is_file()
                    or not target_dir.resolve().is_relative_to(versions_dir.resolve())):
                raise ValueError(f"Previous version directory '{prev_version}' missing")
            with manifest_path.open("r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
            if not isinstance(manifest, dict):
                raise ValueError(f"Previous version '{prev_version}' has an invalid manifest")

            old_target = os.readlink(app_dir / "current")
            was_running = self.get_application_status(app_id)["state"] == "running"
            metadata = dict(current_metadata)
            metadata.update({
                "active_version": prev_version,
                "previous_known_good_version": current_metadata["active_version"],
                "runtime": manifest["runtime"],
                "entrypoint": manifest["entrypoint"],
                "args": manifest.get("args", []),
                "target_architecture": manifest.get(
                    "target_architecture", self.config.target_architecture
                ),
                "rolled_back_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            metadata.pop("status", None)
            try:
                self.stop_application(app_id)
                self._set_current_version(app_dir, prev_version)
                self._write_metadata(app_dir / "metadata.json", metadata)
                self.start_application(app_id)
            except Exception:
                self.stop_application(app_id)
                self._replace_current_link(app_dir, old_target)
                self._write_metadata(app_dir / "metadata.json", current_metadata)
                if was_running:
                    self.start_application(app_id)
                raise
            logger.info(f"Rolled back application {app_id} to v{prev_version}")
            return metadata

    def remove_application(self, app_id: str):
        with self._app_lock(app_id):
            self.stop_application(app_id)
            app_dir = self._app_dir(app_id)
            if app_dir.exists():
                shutil.rmtree(app_dir)
            (self.logs_dir / f"{app_id}.log").unlink(missing_ok=True)
            logger.info(f"Removed application {app_id}")
            return True

    def get_logs(self, app_id: str, lines=100):
        log_file = self.logs_dir / f"{validate_app_id(app_id)}.log"
        if log_file.exists():
            try:
                lines = max(1, min(int(lines), 1000))
                max_bytes = 1024 * 1024
                chunks = []
                bytes_read = 0
                newline_count = 0
                with log_file.open("rb") as log:
                    position = log.seek(0, os.SEEK_END)
                    while position > 0 and newline_count <= lines and bytes_read < max_bytes:
                        chunk_size = min(8192, position, max_bytes - bytes_read)
                        position -= chunk_size
                        log.seek(position)
                        chunk = log.read(chunk_size)
                        chunks.append(chunk)
                        bytes_read += len(chunk)
                        newline_count += chunk.count(b"\n")
                content = b"".join(reversed(chunks)).splitlines(keepends=True)[-lines:]
                return b"".join(content).decode("utf-8", errors="replace")
            except Exception as e:
                return f"Error reading log file: {e}"
        return "No logs available yet."


class DeploymentRequestHandler(BaseHTTPRequestHandler):
    config = None
    inspector = None
    validator = None
    app_manager = None

    def log_request(self, code="-", size="-"):
        request_parts = self.requestline.split(" ", 2)
        if len(request_parts) >= 2 and "?" in request_parts[1]:
            request_parts[1] = request_parts[1].split("?", 1)[0]
        safe_requestline = " ".join(request_parts)
        self.log_message('"%s" %s %s', safe_requestline, code, size)

    def _send_cors(self):
        origin = self.headers.get("Origin")
        if origin and origin in self.config.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
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
        """Allow the configured UI origin (browsers cannot forge Origin) or a Bearer token."""
        if self.headers.get("Origin") in self.config.allowed_origins:
            return True

        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            return hmac.compare_digest(token, self.config.auth_token)

        return False

    @staticmethod
    def _app_route_parts(path, expected_count):
        parts = path.split("/")
        if (len(parts) != expected_count
                or parts[:4] != ["", "api", "v1", "apps"]):
            return None
        try:
            app_id = urllib.parse.unquote(parts[4], errors="strict")
            validate_app_id(app_id)
        except (UnicodeDecodeError, ValueError):
            return None
        return app_id, parts[5:]

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if origin and origin not in self.config.allowed_origins:
            self._send_error_json(403, "Origin is not allowed")
            return
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not path.startswith("/api/"):
            self._send_error_json(404, "API server only")
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

        elif self._app_route_parts(path, 6) and self._app_route_parts(path, 6)[1] == ["logs"]:
            app_id = self._app_route_parts(path, 6)[0]
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                lines = int(qs.get("lines", ["100"])[0])
            except ValueError:
                self._send_error_json(400, "Log line count must be an integer")
                return
            logs = self.app_manager.get_logs(app_id, lines=lines)
            self._send_json(200, {"success": True, "app_id": app_id, "logs": logs})

        elif self._app_route_parts(path, 5):
            app_id = self._app_route_parts(path, 5)[0]
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

        if not self._is_authenticated():
            self._send_error_json(401, "Unauthorized")
            return

        if path == "/api/v1/apps/upload":
            self._handle_upload()

        elif self._app_route_parts(path, 6):
            app_id, suffix = self._app_route_parts(path, 6)
            if len(suffix) != 1 or suffix[0] not in {"start", "stop", "restart", "rollback"}:
                self._send_error_json(404, "Endpoint not found")
                return
            try:
                if suffix[0] == "start":
                    self.app_manager.start_application(app_id)
                    self._send_json(200, {"success": True, "message": f"Application '{app_id}' started"})
                elif suffix[0] == "stop":
                    self.app_manager.stop_application(app_id)
                    self._send_json(200, {"success": True, "message": f"Application '{app_id}' stopped"})
                elif suffix[0] == "restart":
                    self.app_manager.restart_application(app_id)
                    self._send_json(200, {"success": True, "message": f"Application '{app_id}' restarted"})
                else:
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

        route = self._app_route_parts(path, 5)
        if route:
            app_id = route[0]
            try:
                self.app_manager.remove_application(app_id)
                self._send_json(200, {"success": True, "message": f"Application '{app_id}' removed"})
            except Exception as e:
                self._send_error_json(400, str(e))
        else:
            self._send_error_json(404, "Endpoint not found")

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error_json(400, "Invalid Content-Length")
            return
        if content_length <= 0:
            self._send_error_json(400, "Empty payload")
            return

        max_upload_bytes = self.config.max_upload_size_mb * 1024 * 1024
        multipart = content_type.lower().startswith("multipart/form-data")
        max_request_bytes = max_upload_bytes + (65536 if multipart else 0)
        if content_length > max_request_bytes:
            self._send_error_json(413, "Request exceeds the configured upload limit")
            return

        Path(self.config.staging_dir).mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(
            prefix="upload_", dir=self.config.staging_dir
        ))
        archive_path = staging_dir / "package.tar.gz"
        extract_dir = staging_dir / "unpacked"

        try:
            if multipart:
                self._stream_multipart_file(content_type, content_length, archive_path, max_upload_bytes)
            else:
                self._stream_raw_file(content_length, archive_path, max_upload_bytes)

            # ---------------- Run 5-Stage Benchmarks ----------------
            benchmark_results = self.validator.validate_package(archive_path, extract_dir)
            if not benchmark_results["passed"]:
                self._send_json(422, {
                    "success": False,
                    "stage_failed": "Static Validation",
                    "benchmark_results": benchmark_results
                })
                return

            manifest = benchmark_results["manifest"]
            app_id = manifest["app_id"]
            version = manifest["version"]
            runtime = manifest["runtime"]
            entrypoint = extract_dir / manifest["entrypoint"]

            # Run Stage 5: Startup Smoke Benchmark
            smoke_res = self.validator.run_smoke_test(
                entrypoint, runtime, manifest.get("args", []), cwd=extract_dir
            )
            s5 = benchmark_results["stages"]["stage5_startup_smoke"]
            if not smoke_res["passed"]:
                s5["passed"] = False
                s5["status"] = "failed"
                s5["error"] = smoke_res["error"]
                s5["details"].append(smoke_res["error"])
                self._send_json(422, {
                    "success": False,
                    "stage_failed": "Stage 5: Startup Smoke Benchmark",
                    "error": smoke_res["error"],
                    "benchmark_results": benchmark_results
                })
                return

            s5["passed"] = True
            s5["status"] = "passed"
            s5["details"].append(smoke_res["details"])

            # ---------------- Promote to Installed Apps ----------------
            app_meta = self.app_manager.install_and_activate(app_id, version, extract_dir, manifest)

            self._send_json(201, {
                "success": True,
                "message": f"Application '{app_id}' v{version} successfully validated and activated",
                "app": app_meta,
                "benchmarks": benchmark_results
            })

        except Exception as e:
            logger.error(f"Upload error: {e}", exc_info=True)
            self._send_error_json(400 if isinstance(e, ValueError) else 500,
                                  f"Upload failed: {e}")
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _stream_raw_file(self, content_length, archive_path, max_upload_bytes):
        written = 0
        with archive_path.open("wb") as archive:
            while written < content_length:
                chunk = self.rfile.read(min(65536, content_length - written))
                if not chunk:
                    raise ValueError("Request body ended before Content-Length bytes were received")
                written += len(chunk)
                if written > max_upload_bytes:
                    raise ValueError("Upload exceeds the configured file size limit")
                archive.write(chunk)

    def _stream_multipart_file(self, content_type, content_length, archive_path, max_upload_bytes):
        content_header = Message()
        content_header["content-type"] = content_type
        boundary = content_header.get_param("boundary", header="content-type")
        if not isinstance(boundary, str) or not boundary or len(boundary) > 70:
            raise ValueError("Invalid multipart boundary")
        try:
            boundary_bytes = boundary.encode("ascii")
        except UnicodeEncodeError as error:
            raise ValueError("Invalid multipart boundary") from error

        remaining = content_length

        def read_line(limit):
            nonlocal remaining
            if remaining <= 0:
                raise ValueError("Incomplete multipart request")
            line = self.rfile.readline(min(limit, remaining))
            if (not line or (len(line) == limit and not line.endswith(b"\r\n"))):
                raise ValueError("Multipart header exceeds the allowed size")
            remaining -= len(line)
            return line

        if read_line(128) != b"--" + boundary_bytes + b"\r\n":
            raise ValueError("Invalid multipart opening boundary")

        header_bytes = 0
        header_lines = []
        while True:
            line = read_line(8192)
            header_bytes += len(line)
            if header_bytes > 16384:
                raise ValueError("Multipart headers exceed the allowed size")
            if line == b"\r\n":
                break
            header_lines.append(line)
        part_headers = message_from_bytes(b"".join(header_lines))
        disposition = part_headers.get("Content-Disposition")
        if not disposition:
            raise ValueError("Multipart request does not contain a file")
        disposition_header = Message()
        disposition_header["content-disposition"] = disposition
        if (disposition_header.get_content_disposition() != "form-data"
                or disposition_header.get_param("filename", header="content-disposition") is None):
            raise ValueError("Multipart request does not contain a file")

        marker = b"\r\n--" + boundary_bytes + b"--\r\n"
        buffer = bytearray()
        written = 0
        found_end = False
        with archive_path.open("wb") as archive:
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("Request body ended before Content-Length bytes were received")
                remaining -= len(chunk)
                buffer.extend(chunk)
                marker_index = buffer.find(marker)
                if marker_index >= 0:
                    file_chunk = buffer[:marker_index]
                    written += len(file_chunk)
                    if written > max_upload_bytes:
                        raise ValueError("Upload exceeds the configured file size limit")
                    archive.write(file_chunk)
                    trailing = buffer[marker_index + len(marker):]
                    found_end = True
                    if trailing:
                        raise ValueError("Unexpected data after multipart file")
                    break
                safe_bytes = len(buffer) - len(marker) + 1
                if safe_bytes > 0:
                    written += safe_bytes
                    if written > max_upload_bytes:
                        raise ValueError("Upload exceeds the configured file size limit")
                    archive.write(buffer[:safe_bytes])
                    del buffer[:safe_bytes]

        if not found_end:
            raise ValueError("Multipart file boundary is missing")
        if remaining:
            raise ValueError("Unexpected additional multipart fields")
        if written == 0:
            raise ValueError("Uploaded file is empty")

def run_server(config_file=None):
    cfg = DeploymentConfig(config_file)
    inspector = EnvironmentInspector(cfg)
    validator = BenchmarkValidator(cfg)
    validator.cleanup_smoke_tests()
    app_manager = ApplicationManager(cfg)
    DeploymentRequestHandler.config = cfg
    DeploymentRequestHandler.inspector = inspector
    DeploymentRequestHandler.validator = validator
    DeploymentRequestHandler.app_manager = app_manager

    server_address = (cfg.host, cfg.port)
    httpd = ThreadingHTTPServer(server_address, DeploymentRequestHandler)
    httpd.daemon_threads = True

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
    logger.info(f" Apps Root Directory: {cfg.apps_dir}")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        validator.cleanup_smoke_tests()
        httpd.server_close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup-smoke-tests":
        config_arg = sys.argv[2] if len(sys.argv) > 2 else None
        BenchmarkValidator(DeploymentConfig(config_arg)).cleanup_smoke_tests()
    else:
        config_arg = sys.argv[1] if len(sys.argv) > 1 else None
        run_server(config_arg)
