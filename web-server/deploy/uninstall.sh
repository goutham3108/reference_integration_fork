#!/usr/bin/env bash
# Uninstallation script for SDV Web-Based Application Deployment Server
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (e.g. sudo bash uninstall.sh)" >&2
   exit 1
fi

echo "=== Stopping and removing SDV Deployer services ==="

systemctl stop sdv-deployer.service 2>/dev/null || true
systemctl disable sdv-deployer.service 2>/dev/null || true

# Stop any deployed applications
for unit in $(systemctl list-units --type=service --state=active --no-legend 'sdv-app@*.service' | awk '{print $1}'); do
    echo "Stopping ${unit}..."
    systemctl stop "${unit}" 2>/dev/null || true
done

rm -f /etc/systemd/system/sdv-deployer.service
rm -f /etc/systemd/system/sdv-app@.service
systemctl daemon-reload

echo "Service units removed."
echo "If you wish to remove all application binaries and logs, run:"
echo "  rm -rf /opt/sdv-deployer /var/lib/sdv-deployer /var/log/sdv-deployer"
echo "Note: S-CORE services, vsomeip, and KUKSA were left completely untouched."
