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

install -d -o root -g root -m 0755 "$install_dir"
install -d -o "$sdv_user" -g "$sdv_group" -m 0750 "$config_dir" "$log_dir" "$data_dir" "$data_dir/staging" "$apps_dir"
chown -R "$sdv_user:$sdv_group" "$log_dir" "$data_dir/staging"
install -m 0755 "$source_dir/server.py" "$install_dir/server.py"
install -m 0755 "$source_dir/runner.py" "$install_dir/runner.py"
install -m 0644 "$source_dir/auth.py" "$install_dir/auth.py"
install -m 0755 "$source_dir/manage_users.py" "$install_dir/manage_users.py"

if [[ ! -f "$config_dir/config.json" ]]; then
    install -o "$sdv_user" -g "$sdv_group" -m 0600 "$source_dir/config.example.json" "$config_dir/config.json"
fi
python3 - "$config_dir/config.json" "$sdv_user" "$sdv_group" "$apps_dir" "$data_dir" "$log_dir" <<'PY'
import json
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
user, group, apps_dir, data_dir, log_dir = sys.argv[2:7]
config = json.loads(path.read_text(encoding="utf-8"))
if not config.get("auth_token") or config["auth_token"].startswith("replace-with"):
    config["auth_token"] = secrets.token_urlsafe(32)
config.update({
    "app_user": user,
    "app_group": group,
    "apps_dir": apps_dir,
    "data_dir": data_dir,
    "staging_dir": f"{data_dir}/staging",
    "logs_dir": log_dir,
})
path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
chown "$sdv_user:$sdv_group" "$config_dir/config.json"

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
printf 'Provision an account: python3 %s/manage_users.py --config %s/config.json add user@example.com\n' "$install_dir" "$config_dir"
printf 'then: sudo systemctl restart sdv-deployer.service\n'
printf 'API listens on 127.0.0.1:8443. Open the SSH tunnel before using the laptop UI.\n'
