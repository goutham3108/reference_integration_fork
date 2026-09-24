#!/usr/bin/env bash
# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************

set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runner="${workspace_root}/inc_someip_gateway/bazel-bin/tests/integration/vehicle_high_beam_remote_app/vehicle_high_beam_remote_app"

if [[ ! -x "${runner}" ]]; then
    echo "Build the gateway-workspace remote runner first:" >&2
    echo "  cd ${workspace_root}/inc_someip_gateway" >&2
    echo "  bazel build //tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app" >&2
    exit 1
fi

export VSOMEIP_CONFIGURATION="${workspace_root}/inc_someip_gateway/tests/integration/vsomeip-remote-domain.json"
exec "${runner}"
