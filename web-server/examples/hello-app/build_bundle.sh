#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"

script_hash="$(sha256sum pi_heartbeat.py | awk '{print $1}')"
cat > manifest.json <<EOF
{
  "app_id": "pi-heartbeat-monitor",
  "name": "Pi Heartbeat Monitor",
  "version": "1.0.0",
  "description": "Periodic host uptime, memory, and load logs for deployment testing",
  "runtime": "python",
  "entrypoint": "pi_heartbeat.py",
  "target_architecture": "aarch64",
  "author": "SDV Deployment Demo",
  "checksums": {
    "pi_heartbeat.py": "${script_hash}"
  }
}
EOF

chmod +x pi_heartbeat.py
archive="${root}/pi-heartbeat-monitor-1.0.0.tar.gz"
tar -czf "$archive" manifest.json pi_heartbeat.py
printf 'Created sample app bundle: %s\n' "$archive"
