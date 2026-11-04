#!/usr/bin/env bash
# Build the Pi package, copy it to the target, and run the installer there.
# Usage: bash web-server/scripts/install_on_pi.sh <pi-user>@<pi-ip>
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <pi-user>@<pi-ip>" >&2
    exit 2
fi
target="$1"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

bash "$root/web-server/pi-server/package.sh"
archive="$root/web-server/pi-server/dist/pi-deployment-server.tar.gz"

arch="$(ssh "$target" uname -m)"
if [[ "$arch" != "aarch64" ]]; then
    echo "Target architecture is '$arch'; expected aarch64." >&2
    exit 1
fi

remote_dir="$(ssh "$target" 'mktemp -d /tmp/sdv-deployer.XXXXXXXXXX')"
if [[ ! "$remote_dir" =~ ^/tmp/sdv-deployer\.[A-Za-z0-9]+$ ]]; then
    echo "Target returned an invalid temporary directory." >&2
    exit 1
fi
cleanup() {
    ssh "$target" "rm -rf -- '$remote_dir'" ||
        echo "Could not remove remote temporary directory: $remote_dir" >&2
}
trap cleanup EXIT
scp "$archive" "$target:$remote_dir/pi-deployment-server.tar.gz"
ssh -t "$target" "cd '$remote_dir' && tar -xzf pi-deployment-server.tar.gz && cd pi-deployment-server && sudo bash deploy/install.sh && systemctl is-active sdv-deployer.service"

cat <<'EOF'

Next:
  1. Open the tunnel and UI:  bash web-server/scripts/launch_ui.sh
  2. Run the test:            python3 web-server/scripts/e2e_pi_test.py
EOF
