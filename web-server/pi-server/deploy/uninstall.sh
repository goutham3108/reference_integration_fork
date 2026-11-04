#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root." >&2
    exit 1
fi

service_user="$(systemctl show sdv-deployer.service --property=User --value 2>/dev/null || true)"
apps_dir="$(python3 - <<'PY'
import json
import os
import stat

try:
    directory_fd = os.open("/etc/sdv-deployer", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    config_fd = os.open("config.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    if not stat.S_ISREG(os.fstat(config_fd).st_mode):
        raise ValueError("config.json is not a regular file")
    with os.fdopen(config_fd, "r", encoding="utf-8") as config_file:
        print(json.load(config_file).get("apps_dir", ""))
    os.close(directory_fd)
except (OSError, ValueError, json.JSONDecodeError) as error:
    print(f"Cannot safely read deployment config: {error}", file=__import__("sys").stderr)
    raise SystemExit(1)
PY
)" || apps_dir=""
systemctl disable --now sdv-deployer.service 2>/dev/null || true
if [[ -n "$apps_dir" ]]; then
    if [[ -n "$service_user" && "$service_user" != "root" ]] && id "$service_user" >/dev/null 2>&1; then
        runuser -u "$service_user" -- python3 - "$apps_dir" <<'PY'
import json
import os
import signal
import sys
import time
from pathlib import Path

apps_dir = Path(sys.argv[1])
try:
    apps_root = apps_dir.resolve(strict=True)
except (OSError, RuntimeError):
    raise SystemExit(0)
boot_id_path = Path("/proc/sys/kernel/random/boot_id")
try:
    boot_id = boot_id_path.read_text(encoding="ascii").strip()
except OSError:
    raise SystemExit("Cannot verify process records without the current boot ID")

def proc_stat(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = raw[raw.rfind(")") + 2:].split()
        return fields[0], int(fields[2]), int(fields[3]), fields[19]
    except (OSError, ValueError, IndexError):
        return None

def members(record):
    try:
        pgid = int(record["pgid"])
    except (KeyError, TypeError, ValueError):
        return []
    if pgid <= 1 or record.get("boot_id") != boot_id:
        return []
    result = []
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            stat = proc_stat(int(entry.name))
            if not stat or stat[0] in {"Z", "X"} or stat[1] != pgid or stat[2] != pgid:
                continue
            if int(entry.name) == pgid and stat[3] != record.get("start_time"):
                return []
            result.append(int(entry.name))
    except OSError:
        return []
    return result

for app_dir in apps_root.iterdir():
    if not app_dir.is_dir() or app_dir.is_symlink():
        continue
    record_path = app_dir / "process.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        continue
    except (OSError, json.JSONDecodeError):
        print(f"Could not read process record: {record_path}", file=sys.stderr)
        continue
    active = members(record)
    if not active:
        continue
    pgid = int(record["pgid"])
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        continue
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and members(record):
        time.sleep(0.1)
    if members(record):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and members(record):
            time.sleep(0.05)
PY
    else
        echo "Skipping app process cleanup: no non-root service user was found in the installed unit." >&2
    fi
fi
rm -f /etc/systemd/system/sdv-deployer.service /etc/systemd/system/sdv-app@.service
systemctl daemon-reload
printf '%s\n' "Pi deployment API service removed." \
    "App data and /etc/sdv-deployer/config.json were preserved." \
    "Remove those directories manually only if you intend to delete deployed apps."
