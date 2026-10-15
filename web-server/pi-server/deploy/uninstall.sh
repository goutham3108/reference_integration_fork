#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root." >&2
    exit 1
fi

systemctl disable --now sdv-deployer.service 2>/dev/null || true
for unit in $(systemctl list-units --type=service --state=active --no-legend 'sdv-app@*.service' | awk '{print $1}'); do
    systemctl stop "$unit" 2>/dev/null || true
done
rm -f /etc/systemd/system/sdv-deployer.service /etc/systemd/system/sdv-app@.service
systemctl daemon-reload
printf '%s\n' "Pi deployment API service removed." \
    "App data and /etc/sdv-deployer/config.json were preserved." \
    "Remove those directories manually only if you intend to delete deployed apps and accounts."
