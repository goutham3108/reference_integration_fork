#!/bin/sh
# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
#
# Launch script for the packaged Raspberry Pi demo applications.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    cat <<EOF
S-CORE SOME/IP Gateway demo
===========================

Usage: $0 {tire-pressure|headlight|kuksa-bridge} [databroker-host:port]

  $0 tire-pressure             Start the tire-pressure SOME/IP publisher
  $0 headlight                 Start the headlight SOME/IP publisher
    $0 kuksa-bridge [host:port]  Start the KUKSA bridge (default: 127.0.0.1:55555)
EOF
    exit 1
}

[ "$#" -lt 1 ] && usage
demo="$1"
shift

add_vsomeip_library_directory() {
    directory=$(find "${SCRIPT_DIR}/$1.runfiles" -name "libvsomeip3.so.3" -exec dirname {} \; 2>/dev/null | head -1)
    if [ -n "${directory}" ]; then
        export LD_LIBRARY_PATH="${directory}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    fi
}

case "$demo" in
    tire-pressure)
        add_vsomeip_library_directory tire_pressure_publisher
        export VSOMEIP_CONFIGURATION="${SCRIPT_DIR}/vsomeip-gateway-services.json"
        exec "${SCRIPT_DIR}/tire_pressure_publisher" "$@"
        ;;
    headlight)
        add_vsomeip_library_directory headlight_publisher
        export VSOMEIP_CONFIGURATION="${SCRIPT_DIR}/vsomeip-gateway-services.json"
        exec "${SCRIPT_DIR}/headlight_publisher" "$@"
        ;;
    kuksa-bridge)
        export RUNFILES_DIR="${SCRIPT_DIR}/kuksa_tire_pressure_bridge.runfiles"
        exec "${SCRIPT_DIR}/kuksa_tire_pressure_bridge" "${1:-127.0.0.1:55555}"
        ;;
    *)
        usage
        ;;
esac
