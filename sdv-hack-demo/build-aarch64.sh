#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gateway_root="${repo_root}/inc_someip_gateway"

cd "${repo_root}"
bazel build --config=aarch64-linux \
  //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com

cd "${gateway_root}"
bazel build --config=aarch64-linux \
  //score/config:config_file \
  //score/gatewayd \
  //score/serializer:null_serializer \
  //score/someipd

cd "${repo_root}"
bazel build --config=aarch64-linux --host_copt=-std=gnu11 \
  //sdv-hack-demo/bridge:vehicle_high_beam_bridge \
  //sdv-hack-demo/remote_app:vehicle_high_beam_remote_app
