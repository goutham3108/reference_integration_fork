#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gateway_root="${repo_root}/inc_someip_gateway"
dist_dir="${repo_root}/sdv-hack-demo/dist"
kuksa_release_dir="${repo_root}/kuksa-databroker/target/aarch64-unknown-linux-gnu/release"
staging_dir="$(mktemp -d)"
trap 'rm -rf "${staging_dir}"' EXIT

vehicle_dir="${staging_dir}/vehicle"
remote_dir="${staging_dir}/remote"
mkdir -p "${vehicle_dir}/run" "${remote_dir}/run"
mkdir -p "${vehicle_dir}/mw_com_provider/generated"

copy_target() {
    local target_dir="$1"
    local binary="$2"
    local runfiles="$3"

    cp -a "${binary}" "${target_dir}/"
    cp -aL "${runfiles}" "${target_dir}/"
}

copy_target "${vehicle_dir}" \
    "${gateway_root}/bazel-bin/score/someipd/someipd" \
    "${gateway_root}/bazel-bin/score/someipd/someipd.runfiles"
copy_target "${vehicle_dir}" \
    "${gateway_root}/bazel-bin/score/gatewayd/gatewayd" \
    "${gateway_root}/bazel-bin/score/gatewayd/gatewayd.runfiles"
copy_target "${vehicle_dir}" \
    "${repo_root}/bazel-bin/sdv-hack-demo/bridge/vehicle_high_beam_bridge" \
    "${repo_root}/bazel-bin/sdv-hack-demo/bridge/vehicle_high_beam_bridge.runfiles"
copy_target "${vehicle_dir}" \
    "${repo_root}/bazel-bin/sdv-hack-demo/vehicle_app/vehicle_high_beam_mw_com" \
    "${repo_root}/bazel-bin/sdv-hack-demo/vehicle_app/vehicle_high_beam_mw_com.runfiles"
cp -a "${kuksa_release_dir}/databroker-mw-com-demo" "${vehicle_dir}/"
cp -a "${kuksa_release_dir}/databroker-cli" "${vehicle_dir}/"
cp -a "${repo_root}/kuksa-databroker/mw_com_provider/generated/mw_com_provider_config.json" \
    "${vehicle_dir}/mw_com_provider/generated/"
cp -a "${repo_root}/kuksa-databroker/mw_com_provider/generated/vehicle_dynamics_lola_config.json" \
    "${vehicle_dir}/mw_com_provider/generated/"
copy_target "${remote_dir}" \
    "${repo_root}/bazel-bin/sdv-hack-demo/remote_app/vehicle_high_beam_remote_app" \
    "${repo_root}/bazel-bin/sdv-hack-demo/remote_app/vehicle_high_beam_remote_app.runfiles"

cp -a "${gateway_root}/bazel-bin/score/config/mw_someip_config.bin" "${vehicle_dir}/"
cp -a "${gateway_root}/score/gatewayd/etc/mw_com_config.json" "${vehicle_dir}/"
cp -a "${gateway_root}/tests/integration/vsomeip-gateway-services.json" "${vehicle_dir}/"
cp -a "${gateway_root}/bazel-bin/score/serializer/score_com_serializer.so" "${vehicle_dir}/"
cp -a "${repo_root}/sdv-hack-demo/deploy/start-vehicle.sh" "${vehicle_dir}/run/"
cp -a "${repo_root}/sdv-hack-demo/deploy/start-remote.sh" "${remote_dir}/run/"
cp -a "${repo_root}/sdv-hack-demo/deploy/network.env" "${vehicle_dir}/"
cp -a "${repo_root}/sdv-hack-demo/deploy/network.env" "${remote_dir}/"
cp -a "${repo_root}/sdv-hack-demo/signal_routes.json" "${vehicle_dir}/"
cp -a "${repo_root}/sdv-hack-demo/signal_routes.json" "${remote_dir}/"
chmod +x "${vehicle_dir}/run/start-vehicle.sh" "${remote_dir}/run/start-remote.sh"

mkdir -p "${dist_dir}"
tar -chzf "${dist_dir}/vehicle-aarch64.tar.gz" -C "${vehicle_dir}" .
tar -chzf "${dist_dir}/remote-aarch64.tar.gz" -C "${remote_dir}" .

printf 'Created:\n  %s\n  %s\n' \
    "${dist_dir}/vehicle-aarch64.tar.gz" \
    "${dist_dir}/remote-aarch64.tar.gz"
cd 