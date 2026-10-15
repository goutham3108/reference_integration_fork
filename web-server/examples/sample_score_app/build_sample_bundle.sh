#!/usr/bin/env bash
# Helper script to compile and package sample S-CORE native application
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${dir}"

# Check cross-compiler or native compiler
CC="${AARCH64_CC:-gcc}"
echo "Compiling vehicle_speed_reader with ${CC}..."
"${CC}" -O2 -Wall vehicle_speed_reader.c -o vehicle_speed_reader

# Compute checksums and write updated manifest
echo "Computing SHA-256 checksums..."
bin_hash=$(sha256sum vehicle_speed_reader | awk '{print $1}')
cfg_hash=$(sha256sum config/mw_com_config.json | awk '{print $1}')

cat <<EOF > manifest.json
{
  "app_id": "vehicle-speed-reader",
  "name": "S-CORE Vehicle Speed Reader",
  "version": "1.0.0",
  "description": "Native AArch64 binary consuming S-CORE mw::com vehicle dynamics from /dev/shm",
  "runtime": "native",
  "entrypoint": "vehicle_speed_reader",
  "target_architecture": "aarch64",
  "author": "Eclipse S-CORE SDV Team",
  "checksums": {
    "vehicle_speed_reader": "${bin_hash}",
    "config/mw_com_config.json": "${cfg_hash}"
  }
}
EOF

output_tar="${dir}/vehicle-speed-reader-1.0.0.tar.gz"
tar -czf "${output_tar}" manifest.json vehicle_speed_reader config/

echo "Sample bundle created: ${output_tar}"
