#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root." >&2
    exit 1
fi

apps_dir="$(python3 -c 'import json,sys; print(json.load(open("/etc/sdv-deployer/config.json")).get("apps_dir",""))' 2>/dev/null || true)"
systemctl disable --now sdv-deployer.service 2>/dev/null || true
# KillMode=process leaves deployed apps running, so stop them explicitly.
if [[ -n "$apps_dir" ]]; then
    pkill -f "$apps_dir/" 2>/dev/null || true
fi
rm -f /etc/systemd/system/sdv-deployer.service /etc/systemd/system/sdv-app@.service
systemctl daemon-reload
printf '%s\n' "Pi deployment API service removed." \
    "App data and /etc/sdv-deployer/config.json were preserved." \
    "Remove those directories manually only if you intend to delete deployed apps."
