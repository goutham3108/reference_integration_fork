#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${root}/network.env"

export HIGH_BEAM_BIND_IP=0.0.0.0

cp "${root}/vsomeip-gateway-services.json" "${root}/vsomeip-vehicle.json"
sed -i "s/\"unicast\": \"127.0.0.1\"/\"unicast\": \"${HIGH_BEAM_VEHICLE_IP}\"/" \
    "${root}/vsomeip-vehicle.json"

vsomeip_lib_dir="$(find "${root}/someipd.runfiles" -name libvsomeip3.so.3 -printf '%h\n' -quit)"
test -n "${vsomeip_lib_dir}"
export LD_LIBRARY_PATH="${root}:${vsomeip_lib_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

pkill -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
rm -f /tmp/vsomeip*.lck

VSOMEIP_CONFIGURATION="${root}/vsomeip-vehicle.json" \
    "${root}/someipd" --configuration "${root}/mw_someip_config.bin" >"${root}/someipd.log" 2>&1 &

"${root}/gatewayd" \
    --configuration "${root}/mw_someip_config.bin" \
    --service_instance_manifest "${root}/mw_com_config.json" >"${root}/gatewayd.log" 2>&1 &

VSOMEIP_CONFIGURATION="${root}/vsomeip-vehicle.json" \
VEHICLE_DOMAIN_CONFIG="${root}/vsomeip-vehicle.json" \
    "${root}/vehicle_high_beam_bridge" >"${root}/bridge.log" 2>&1 &

exec "${root}/vehicle_high_beam_mw_com" --configuration "${root}/mw_com_config.json"
