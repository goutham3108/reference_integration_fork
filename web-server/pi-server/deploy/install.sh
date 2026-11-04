#!/usr/bin/env bash
# Install the deployer as a systemd service that runs as a regular user.
# Apps are stored in, and run from, /home/<user>/sdv-apps.
#
#   sudo bash deploy/install.sh
#   sudo SDV_USER=pi SDV_MEMORY_MAX=768M SDV_CPU_QUOTA=150% bash deploy/install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer as root: sudo bash deploy/install.sh" >&2
    exit 1
fi

sdv_user="${SDV_USER:-${SUDO_USER:-}}"
if [[ -z "$sdv_user" || "$sdv_user" == "root" ]] || ! id "$sdv_user" >/dev/null 2>&1; then
    echo "Run with sudo from a regular user, or set SDV_USER=<existing non-root user>." >&2
    exit 1
fi
sdv_group="$(id -gn "$sdv_user")"
user_home="$(getent passwd "$sdv_user" | cut -d: -f6)"
memory_max="${SDV_MEMORY_MAX:-512M}"
cpu_quota="${SDV_CPU_QUOTA:-100%}"

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_dir="/opt/sdv-deployer"
config_dir="/etc/sdv-deployer"
data_dir="/var/lib/sdv-deployer"
log_dir="/var/log/sdv-deployer"
apps_dir="$user_home/sdv-apps"

# Remove artefacts of the earlier per-app systemd design.
systemctl stop 'sdv-app@*.service' 2>/dev/null || true
rm -f /etc/sudoers.d/sdv-deployer /usr/local/libexec/sdv-appctl /etc/systemd/system/sdv-app@.service

python3 - "$config_dir" "$install_dir" "$data_dir" "$log_dir" "$sdv_user" "$sdv_group" <<'PY'
import grp
import os
import pwd
import stat
import sys

config_dir, install_dir, data_dir, log_dir, user, group = sys.argv[1:7]
uid = pwd.getpwnam(user).pw_uid
gid = grp.getgrnam(group).gr_gid

def open_directory(path, owner, group, mode, parent_fd=None):
    try:
        os.mkdir(path, mode, dir_fd=parent_fd)
    except FileExistsError:
        pass
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=parent_fd)
    try:
        os.fchown(directory_fd, owner, group)
        os.fchmod(directory_fd, mode)
    except BaseException:
        os.close(directory_fd)
        raise
    return directory_fd

directory_fd = open_directory(config_dir, 0, 0, 0o755)
try:
    try:
        config_stat = os.stat("config.json", dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(config_stat.st_mode):
            raise SystemExit("Refusing to update a non-regular or symlink config.json")
finally:
    os.close(directory_fd)

os.close(open_directory(install_dir, 0, 0, 0o755))
data_fd = open_directory(data_dir, 0, 0, 0o755)
try:
    os.close(open_directory("staging", uid, gid, 0o750, parent_fd=data_fd))
finally:
    os.close(data_fd)
os.close(open_directory(log_dir, uid, gid, 0o750))
PY

install -m 0755 "$source_dir/server.py" "$install_dir/server.py"
install -m 0755 "$source_dir/runner.py" "$install_dir/runner.py"

python3 - "$config_dir" "$source_dir/config.example.json" "$sdv_user" "$sdv_group" "$user_home" "$apps_dir" "$data_dir" "$log_dir" <<'PY'
import json
import grp
import os
import pwd
import secrets
import stat
import sys
from pathlib import Path

directory = Path(sys.argv[1])
template_path = Path(sys.argv[2])
user, group, user_home, default_apps_dir, data_dir, log_dir = sys.argv[3:9]
uid = pwd.getpwnam(user).pw_uid
gid = grp.getgrnam(group).gr_gid

def provision_apps_dir(path):
    directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    parts = Path(path).parts[1:]
    try:
        for index, part in enumerate(parts):
            final = index == len(parts) - 1
            try:
                os.mkdir(part, 0o750 if final else 0o755, dir_fd=directory_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
            if final:
                os.fchown(directory_fd, uid, gid)
                os.fchmod(directory_fd, 0o750)
    finally:
        os.close(directory_fd)

directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    try:
        file_stat = os.stat("config.json", dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        config = json.loads(template_path.read_text(encoding="utf-8"))
    else:
        if not stat.S_ISREG(file_stat.st_mode):
            raise SystemExit("Refusing to read a non-regular or symlink config.json")
        config_fd = os.open("config.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(config_fd, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)

    token = config.get("auth_token")
    if not isinstance(token, str) or not token or token.startswith("replace-with"):
        config["auth_token"] = secrets.token_urlsafe(32)
    configured_apps_dir = config.get("apps_dir")
    if configured_apps_dir:
        configured_path = Path(configured_apps_dir)
        if not configured_path.is_absolute() or ".." in configured_path.parts:
            raise SystemExit("Configured apps_dir must be an absolute path without '..' components")
        allowed_roots = (Path(user_home), Path(data_dir))
        if not any(configured_path.is_relative_to(root) and configured_path != root
                   for root in allowed_roots):
            raise SystemExit("Configured apps_dir must be inside the service user's home or deployer data directory")
        apps_dir = str(configured_path)
    else:
        apps_dir = str(Path(default_apps_dir))
    provision_apps_dir(apps_dir)

    config.update({
        "app_user": user,
        "app_group": group,
        "apps_dir": apps_dir,
        "data_dir": data_dir,
        "staging_dir": f"{data_dir}/staging",
        "logs_dir": log_dir,
    })
    temp_name = f".config.json.{secrets.token_hex(8)}.tmp"
    try:
        config_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o640, dir_fd=directory_fd)
        with os.fdopen(config_fd, "w", encoding="utf-8") as config_file:
            os.fchown(config_file.fileno(), 0, grp.getgrnam(group).gr_gid)
            os.fchmod(config_file.fileno(), 0o640)
            config_file.write(json.dumps(config, indent=2) + "\n")
            config_file.flush()
            os.fsync(config_file.fileno())
        os.replace(temp_name, "config.json", src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
finally:
    os.close(directory_fd)
PY
apps_dir="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["apps_dir"])' "$config_dir/config.json")"
sed -e "s|@SDV_USER@|$sdv_user|g" \
    -e "s|@SDV_GROUP@|$sdv_group|g" \
    -e "s|@SDV_MEMORY_MAX@|$memory_max|g" \
    -e "s|@SDV_CPU_QUOTA@|$cpu_quota|g" \
    "$source_dir/deploy/sdv-deployer.service" > /etc/systemd/system/sdv-deployer.service
chmod 0644 /etc/systemd/system/sdv-deployer.service
systemctl daemon-reload
systemctl enable sdv-deployer.service
systemctl restart sdv-deployer.service

printf '\nDeployer installed and started as user %s (MemoryMax=%s, CPUQuota=%s).\n' "$sdv_user" "$memory_max" "$cpu_quota"
printf 'Apps are stored and run in %s\n' "$apps_dir"
printf 'API listens on 127.0.0.1:8443. Open the SSH tunnel before using the laptop UI.\n'
