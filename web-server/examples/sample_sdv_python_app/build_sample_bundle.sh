#!/usr/bin/env bash
# Helper script to package sample SDV Python application
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${dir}"

echo "Computing SHA-256 checksums..."
script_hash=$(sha256sum high_beam_kuksa_controller.py | awk '{print $1}')

cat <<EOF > manifest.json
{
  "app_id": "kuksa-high-beam-controller",
  "name": "KUKSA High Beam Controller",
  "version": "1.0.0",
  "description": "Python SDV application connecting to KUKSA Databroker on 127.0.0.1:55555",
  "runtime": "python",
  "entrypoint": "high_beam_kuksa_controller.py",
  "target_architecture": "aarch64",
  "author": "Eclipse S-CORE SDV Team",
  "checksums": {
    "high_beam_kuksa_controller.py": "${script_hash}"
  }
}
EOF

chmod +x high_beam_kuksa_controller.py
output_tar="${dir}/kuksa-high-beam-controller-1.0.0.tar.gz"
tar -czf "${output_tar}" manifest.json high_beam_kuksa_controller.py

echo "Sample Python bundle created: ${output_tar}"
