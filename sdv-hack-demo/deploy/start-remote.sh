#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${root}/network.env"

export HIGH_BEAM_BIND_IP=0.0.0.0
export HIGH_BEAM_BRIDGE_IP="${HIGH_BEAM_VEHICLE_IP}"
export HIGH_BEAM_KVS_DIR="${root}/state"

vsomeip_lib_dir="$(find "${root}/vehicle_high_beam_remote_app.runfiles" -name libvsomeip3.so.3 -printf '%h\n' -quit)"
test -n "${vsomeip_lib_dir}"
export LD_LIBRARY_PATH="${vsomeip_lib_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

exec "${root}/vehicle_high_beam_remote_app"
