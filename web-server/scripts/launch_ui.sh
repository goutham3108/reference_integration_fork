#!/usr/bin/env bash
# Run on the LAPTOP. Opens the SSH tunnel to the Pi and serves the browser UI.
#
#   bash web-server/scripts/launch_ui.sh                    # asks for the Pi username and IP
#   bash web-server/scripts/launch_ui.sh <pi-user>@<pi-ip>   # skips the questions
#   bash web-server/scripts/launch_ui.sh --no-tunnel        # UI only (API already reachable on 18443)
#
# Ctrl+C stops the UI server and closes the tunnel.
set -euo pipefail

# These ports are fixed: the Pi API only allows the UI origin on 8080, and config.js calls 18443.
UI_PORT=8080
API_PORT=18443
PI_API_PORT=8443

if [[ $# -gt 1 ]]; then
    echo "Usage: $0 [<pi-user>@<pi-ip> | --no-tunnel]" >&2
    exit 2
fi
if [[ $# -eq 1 ]]; then
    target="$1"
else
    read -r -p "Pi username: " pi_user
    read -r -p "Pi IP address: " pi_ip
    if [[ -z "$pi_user" || -z "$pi_ip" ]]; then
        echo "Both the username and the IP address are required." >&2
        exit 2
    fi
    target="$pi_user@$pi_ip"
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ui_dir="$root/web-server/laptop-ui"
control_socket=""

port_in_use() {
    ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN
}

cleanup() {
    if [[ -n "$control_socket" && -S "$control_socket" ]]; then
        ssh -S "$control_socket" -O exit "$target" >/dev/null 2>&1 || true
        echo "Tunnel closed."
    fi
}
trap cleanup EXIT

if port_in_use "$UI_PORT"; then
    echo "Port $UI_PORT is already in use. Stop the other UI server first." >&2
    exit 1
fi

if [[ "$target" != "--no-tunnel" ]]; then
    if port_in_use "$API_PORT"; then
        echo "Port $API_PORT is already in use. Close the old tunnel or local API first." >&2
        exit 1
    fi
    control_socket="$(mktemp -u /tmp/sdv-tunnel.XXXXXX)"
    echo "Opening SSH tunnel to $target (enter the SSH password if asked)..."
    ssh -M -S "$control_socket" -f -N \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
        -L "$API_PORT:127.0.0.1:$PI_API_PORT" "$target"
fi

if curl -fsS --max-time 5 "http://127.0.0.1:$API_PORT/api/v1/session" | grep -q authenticated; then
    echo "Pi API reachable on http://127.0.0.1:$API_PORT"
else
    echo "Warning: the Pi API did not answer. Check that sdv-deployer.service is running on the Pi." >&2
fi

url="http://localhost:$UI_PORT"
echo "UI: $url   (Ctrl+C to stop)"
(command -v wslview || command -v xdg-open) >/dev/null 2>&1 && \
    ( (wslview "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null) & ) || true

python3 -m http.server "$UI_PORT" --bind 127.0.0.1 --directory "$ui_dir"
