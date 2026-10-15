#!/usr/bin/env bash
# Run on the RASPBERRY PI as your normal user (not root). It uses sudo where needed.
#
#   bash pi_setup.sh                       install or upgrade from ./pi-deployment-server.tar.gz or /tmp/
#   bash pi_setup.sh /path/to/archive.tar.gz
#   bash pi_setup.sh status                show service state, limits, and deployed apps
#   bash pi_setup.sh adduser               add or replace a browser login
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Run as your normal user, not root: bash $0" >&2
    exit 1
fi

config="/etc/sdv-deployer/config.json"
manage_users="/opt/sdv-deployer/manage_users.py"

show_status() {
    echo "== Service =="
    systemctl is-active sdv-deployer.service || true
    systemctl is-enabled sdv-deployer.service || true
    systemctl show sdv-deployer -p User -p MemoryMax -p MemoryCurrent -p CPUQuotaPerSecUSec
    echo
    echo "== Listening on 8443 =="
    ss -ltnp 2>/dev/null | grep 8443 || echo "nothing is listening on 8443"
    echo
    echo "== Deployed apps =="
    apps_dir="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["apps_dir"])' "$config" 2>/dev/null || true)"
    if [[ -n "$apps_dir" && -d "$apps_dir" ]]; then
        ls -1 "$apps_dir"
        echo
        echo "== App processes =="
        ps -eo pid,user,args | grep -F "$apps_dir/" | grep -v grep || echo "no app processes running"
    else
        echo "apps directory not found (run the install first)"
    fi
    echo
    echo "== Users =="
    python3 "$manage_users" --config "$config" list
}

add_user() {
    read -r -p "Email for the new login: " email
    python3 "$manage_users" --config "$config" add "$email"
    sudo systemctl restart sdv-deployer.service
    echo "Login added and service restarted."
}

install_server() {
    local archive="${1:-}"
    if [[ -z "$archive" ]]; then
        for candidate in ./pi-deployment-server.tar.gz /tmp/pi-deployment-server.tar.gz; do
            [[ -f "$candidate" ]] && archive="$candidate" && break
        done
    fi
    if [[ -z "$archive" || ! -f "$archive" ]]; then
        echo "Archive not found. Pass its path: bash $0 /path/to/pi-deployment-server.tar.gz" >&2
        exit 1
    fi
    if [[ "$(uname -m)" != "aarch64" ]]; then
        echo "This machine is $(uname -m); the deployer targets aarch64." >&2
        exit 1
    fi

    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT
    tar -xzf "$archive" -C "$work"
    sudo bash "$work/pi-deployment-server/deploy/install.sh"

    echo
    show_status
    if python3 "$manage_users" --config "$config" list | grep -q "No users configured"; then
        echo
        add_user
    fi
    echo
    echo "Done. On your laptop run: bash web-server/scripts/launch_ui.sh $(id -un)@<this-pi-ip>"
}

case "${1:-install}" in
    status)  show_status ;;
    adduser) add_user ;;
    install) install_server "" ;;
    *)       install_server "$1" ;;
esac
