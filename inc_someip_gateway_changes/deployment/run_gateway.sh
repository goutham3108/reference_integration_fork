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
# Launch script for the S-CORE SOME/IP Gateway.
#
# Start each daemon in a separate terminal, in this order:
#   1. ./run_gateway.sh someipd
#   2. ./run_gateway.sh gatewayd
#
# someipd requires VSOMEIP_CONFIGURATION to point to a vsomeip JSON config:
#   export VSOMEIP_CONFIGURATION=/path/to/vsomeip.json
#   ./run_gateway.sh someipd

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    cat <<EOF
S-CORE SOME/IP Gateway
======================

Usage: $0 {gatewayd|someipd}

    $0 someipd    -- SOME/IP stack daemon (start first)
    $0 gatewayd   -- gateway daemon (start after someipd)

Set VSOMEIP_CONFIGURATION to your vsomeip config before running someipd.
EOF
    exit 1
}

[ "$#" -lt 1 ] && usage
daemon="$1"
shift

add_library_directory() {
    directory=$(find "${SCRIPT_DIR}/$1" -name "$2" -exec dirname {} \; 2>/dev/null | head -1)
    if [ -n "${directory}" ]; then
        export LD_LIBRARY_PATH="${directory}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    fi
}

case "$daemon" in
    gatewayd)
        echo "Starting gatewayd..."
        add_library_directory . "score_com_serializer.so"
        "${SCRIPT_DIR}/gatewayd" \
            --service_instance_manifest "${SCRIPT_DIR}/gatewayd_mw_com_config.json" \
            --configuration "${SCRIPT_DIR}/gatewayd_config.bin" "$@"
        ;;
    someipd)
        echo "Starting someipd..."
        add_library_directory someipd.runfiles "libvsomeip3.so.3"
        "${SCRIPT_DIR}/someipd" \
            --configuration "${SCRIPT_DIR}/gatewayd_config.bin" "$@"
        ;;
    *)
        usage
        ;;
esac
