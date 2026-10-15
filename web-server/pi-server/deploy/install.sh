#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer as root: sudo bash deploy/install.sh" >&2
    exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_dir="/opt/sdv-deployer"
config_dir="/etc/sdv-deployer"
data_dir="/var/lib/sdv-deployer"
log_dir="/var/log/sdv-deployer"

if ! getent group sdv-apps >/dev/null; then
    groupadd --system sdv-apps
fi
if ! id sdv-apps >/dev/null 2>&1; then
    useradd --system --gid sdv-apps --home-dir /var/lib/sdv-apps --no-create-home --shell /usr/sbin/nologin sdv-apps
fi
if ! id sdv-deployer >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/sdv-deployer --no-create-home --shell /usr/sbin/nologin sdv-deployer
fi
extra_groups="sdv-apps"
if getent group systemd-journal >/dev/null; then
    extra_groups+=",systemd-journal"
fi
usermod -aG "$extra_groups" sdv-deployer

install -d -o root -g root -m 0755 "$install_dir" /usr/local/libexec
install -d -o root -g root -m 0755 "$data_dir"
install -d -o sdv-deployer -g sdv-deployer -m 0750 "$config_dir" "$log_dir"
install -d -o sdv-deployer -g sdv-apps -m 2770 "$data_dir/staging"
install -d -o sdv-deployer -g sdv-apps -m 2750 "$data_dir/apps"
install -m 0755 "$source_dir/server.py" "$install_dir/server.py"
install -m 0755 "$source_dir/runner.py" "$install_dir/runner.py"
install -m 0644 "$source_dir/auth.py" "$install_dir/auth.py"
install -m 0755 "$source_dir/manage_users.py" "$install_dir/manage_users.py"
install -o root -g root -m 0755 "$source_dir/sdv-appctl.py" /usr/local/libexec/sdv-appctl
install -o root -g root -m 0440 "$source_dir/deploy/sdv-deployer.sudoers" /etc/sudoers.d/sdv-deployer
visudo -cf /etc/sudoers.d/sdv-deployer

if [[ ! -f "$config_dir/config.json" ]]; then
    install -o sdv-deployer -g sdv-deployer -m 0600 "$source_dir/config.example.json" "$config_dir/config.json"
    python3 - "$config_dir/config.json" <<'PY'
import json
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8"))
config["auth_token"] = secrets.token_urlsafe(32)
path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
fi
chown sdv-deployer:sdv-deployer "$config_dir/config.json"
chmod 0600 "$config_dir/config.json"

install -m 0644 "$source_dir/deploy/sdv-deployer.service" /etc/systemd/system/sdv-deployer.service
install -m 0644 "$source_dir/deploy/sdv-app@.service" /etc/systemd/system/sdv-app@.service
systemctl daemon-reload
systemctl enable --now sdv-deployer.service

printf '\nPi API installed and started.\n'
printf 'Provision an account: sudo python3 %s/manage_users.py --config %s/config.json add user@example.com\n' "$install_dir" "$config_dir"
printf 'API listens on 127.0.0.1:8443. Open the SSH tunnel before using the laptop UI.\n'
