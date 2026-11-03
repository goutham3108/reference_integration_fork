#!/usr/bin/env bash
# Installation script for SDV Web-Based Application Deployment Server on Raspberry Pi
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (e.g. sudo bash install.sh)" >&2
   exit 1
fi

INSTALL_DIR="/opt/sdv-deployer"
DATA_DIR="/var/lib/sdv-deployer"
LOG_DIR="/var/log/sdv-deployer"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Installing SDV Application Deployer ==="
echo "Source: ${SRC_DIR}"
echo "Target: ${INSTALL_DIR}"

# 1. Create directories
mkdir -p "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}/static"
mkdir -p "${INSTALL_DIR}/certs"
mkdir -p "${DATA_DIR}/apps"
mkdir -p "${DATA_DIR}/staging"
mkdir -p "${LOG_DIR}"

# 2. Copy application files
cp -a "${SRC_DIR}/server.py" "${INSTALL_DIR}/"
cp -a "${SRC_DIR}/auth.py" "${INSTALL_DIR}/"
cp -a "${SRC_DIR}/manage_users.py" "${INSTALL_DIR}/"
cp -a "${SRC_DIR}/static/"* "${INSTALL_DIR}/static/"

# Only copy config if not already present, preserving user settings
if [[ ! -f "${INSTALL_DIR}/config.json" ]]; then
    cp -a "${SRC_DIR}/config.json" "${INSTALL_DIR}/"
    # Generate random secret token for production if desired
    # TOKEN=$(openssl rand -hex 16)
    # sed -i "s/sdv-dev-secret-token-2026/${TOKEN}/" "${INSTALL_DIR}/config.json"
fi

chmod +x "${INSTALL_DIR}/server.py"

# 3. Install systemd services
cp -a "${SRC_DIR}/deploy/sdv-deployer.service" "/etc/systemd/system/"
cp -a "${SRC_DIR}/deploy/sdv-app@.service" "/etc/systemd/system/"

systemctl daemon-reload
systemctl enable sdv-deployer.service
systemctl restart sdv-deployer.service

echo ""
echo "=== SDV Deployer Installed & Started Successfully ==="
echo "Status check:  sudo systemctl status sdv-deployer"
echo "Service Logs:  sudo journalctl -u sdv-deployer -f"
echo "Create a user: sudo python3 ${INSTALL_DIR}/manage_users.py --config ${INSTALL_DIR}/config.json add user@example.com"
echo "Web Interface: http://$(hostname -I | awk '{print $1}'):8443"
echo "====================================================="
