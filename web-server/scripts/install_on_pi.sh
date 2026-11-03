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

scp "$archive" "$target:/tmp/pi-deployment-server.tar.gz"
ssh -t "$target" 'cd /tmp && rm -rf pi-deployment-server && tar -xzf pi-deployment-server.tar.gz && cd pi-deployment-server && sudo bash deploy/install.sh && systemctl is-active sdv-deployer.service'

cat <<'EOF'

Next:
  1. Open the tunnel and UI:  bash web-server/scripts/launch_ui.sh
  2. Run the test:            python3 web-server/scripts/e2e_pi_test.py
EOF
