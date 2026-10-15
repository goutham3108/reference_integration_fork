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
  1. Create a login on the Pi:
       python3 /opt/sdv-deployer/manage_users.py --config /etc/sdv-deployer/config.json add <email>
       sudo systemctl restart sdv-deployer.service
  2. Open the tunnel:  ssh -N -L 18443:127.0.0.1:8443 <pi-user>@<pi-ip>
  3. Run the test:     python3 web-server/scripts/e2e_pi_test.py --email <email>
EOF
