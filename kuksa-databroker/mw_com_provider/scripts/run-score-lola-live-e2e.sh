#!/usr/bin/env bash
set -euo pipefail

PROVIDER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCORE_E2E_CONTAINER="${SCORE_E2E_CONTAINER:-loving_payne}"
SCORE_COM_BAZEL_BIN="${SCORE_COM_BAZEL_BIN:-}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$PROVIDER_ROOT/generated/mw_com_provider_config.json}"
SCORE_CONFIG="${SCORE_CONFIG:-$PROVIDER_ROOT/generated/vehicle_dynamics_lola_config.json}"
REMOTE_PROVIDER_DIR="${REMOTE_PROVIDER_DIR:-/tmp/provider}"
REMOTE_SCORE_BAZEL_BIN="${REMOTE_SCORE_BAZEL_BIN:-/tmp/score_bazel_bin}"
SCORE_E2E_EXAMPLE="${SCORE_E2E_EXAMPLE:-score_lola_live_speed}"
SCORE_E2E_SAMPLE_COUNT="${SCORE_E2E_SAMPLE_COUNT:-25}"
SCORE_E2E_TIMEOUT_SECS="${SCORE_E2E_TIMEOUT_SECS:-60}"
SCORE_E2E_POLL_MS="${SCORE_E2E_POLL_MS:-10}"

if [[ -z "$SCORE_COM_BAZEL_BIN" ]]; then
    echo "SCORE_COM_BAZEL_BIN must point to the S-Core communication bazel-bin directory" >&2
    exit 2
fi

if ! docker inspect "$SCORE_E2E_CONTAINER" >/dev/null 2>&1; then
    echo "container not found: $SCORE_E2E_CONTAINER" >&2
    exit 2
fi

for path in \
    "$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example" \
    "$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen" \
    "$SCORE_COM_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola" \
    "$SCORE_COM_BAZEL_BIN/score/mw/com/impl/bindings/lola" \
    "$PROVIDER_CONFIG" \
    "$SCORE_CONFIG"; do
    if [[ ! -e "$path" ]]; then
        echo "required path not found: $path" >&2
        exit 2
    fi
done

cd "$PROVIDER_ROOT"
LD_LIBRARY_PATH="$SCORE_COM_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola:$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen:${LD_LIBRARY_PATH:-}" \
    cargo build -p mw_com_provider --features score-lola --example "$SCORE_E2E_EXAMPLE"

docker exec "$SCORE_E2E_CONTAINER" sh -lc "rm -rf '$REMOTE_PROVIDER_DIR' '$REMOTE_SCORE_BAZEL_BIN' && mkdir -p '$REMOTE_PROVIDER_DIR/generated' '$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example' '$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/rust/com-api' '$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/bindings'"

docker cp "$PROVIDER_ROOT/target/debug/examples/$SCORE_E2E_EXAMPLE" "$SCORE_E2E_CONTAINER:$REMOTE_PROVIDER_DIR/$SCORE_E2E_EXAMPLE"
docker cp "$PROVIDER_CONFIG" "$SCORE_E2E_CONTAINER:$REMOTE_PROVIDER_DIR/generated/mw_com_provider_config.json"
docker cp "$SCORE_CONFIG" "$SCORE_E2E_CONTAINER:$REMOTE_PROVIDER_DIR/generated/vehicle_dynamics_lola_config.json"
docker cp "$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example" "$SCORE_E2E_CONTAINER:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example"
docker cp "$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen" "$SCORE_E2E_CONTAINER:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen"
docker cp "$SCORE_COM_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola" "$SCORE_E2E_CONTAINER:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola"
docker cp "$SCORE_COM_BAZEL_BIN/score/mw/com/impl/bindings/lola" "$SCORE_E2E_CONTAINER:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/bindings/lola"

docker exec "$SCORE_E2E_CONTAINER" sh -lc "chmod +x '$REMOTE_PROVIDER_DIR/$SCORE_E2E_EXAMPLE' '$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example'"

docker exec "$SCORE_E2E_CONTAINER" sh -lc "cd '$REMOTE_PROVIDER_DIR'
export SCORE_CONFIG_PATH='$REMOTE_PROVIDER_DIR/generated/vehicle_dynamics_lola_config.json'
export LD_LIBRARY_PATH='$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/bindings/lola:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola:$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen':\${LD_LIBRARY_PATH:-}
'$REMOTE_SCORE_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example' --run-mode producer --service-instance-manifest \"\$SCORE_CONFIG_PATH\" &
producer_pid=\$!
export SCORE_E2E_SAMPLE_COUNT='$SCORE_E2E_SAMPLE_COUNT'
export SCORE_E2E_TIMEOUT_SECS='$SCORE_E2E_TIMEOUT_SECS'
export SCORE_E2E_POLL_MS='$SCORE_E2E_POLL_MS'
'$REMOTE_PROVIDER_DIR/$SCORE_E2E_EXAMPLE'
provider_status=\$?
kill \"\$producer_pid\" 2>/dev/null || true
wait \"\$producer_pid\" 2>/dev/null || true
exit \"\$provider_status\"
"
