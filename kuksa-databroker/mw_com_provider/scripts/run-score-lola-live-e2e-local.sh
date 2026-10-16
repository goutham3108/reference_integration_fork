#!/usr/bin/env bash
set -euo pipefail

PROVIDER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCORE_COM_BAZEL_BIN="${SCORE_COM_BAZEL_BIN:-}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$PROVIDER_ROOT/generated/mw_com_provider_config.json}"
SCORE_CONFIG="${SCORE_CONFIG:-$PROVIDER_ROOT/generated/vehicle_dynamics_lola_config.json}"
SCORE_E2E_EXAMPLE="${SCORE_E2E_EXAMPLE:-score_lola_live_speed}"
SCORE_COM_PRODUCER_RUNFILE="score_communication/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example"
SCORE_COM_PRODUCER_BAZEL_BIN_SUFFIX="score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example"

find_runfile() {
    local path="$1"
    local suffix="$2"
    local candidate

    for candidate in \
        "${RUNFILES_DIR:-}/$path" \
        "${RUNFILES_DIR:-}/_main/$path" \
        "${RUNFILES_MANIFEST_DIR:-}/$path" \
        "${RUNFILES_MANIFEST_DIR:-}/_main/$path"; do
        if [[ -e "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    if [[ -n "${RUNFILES_DIR:-}" ]]; then
        candidate="$(find "$RUNFILES_DIR" -path "*/$suffix" -print -quit)"
        if [[ -n "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    return 1
}

if [[ -z "$SCORE_COM_BAZEL_BIN" ]]; then
    score_com_producer="$(find_runfile "$SCORE_COM_PRODUCER_RUNFILE" "$SCORE_COM_PRODUCER_BAZEL_BIN_SUFFIX" || true)"
    if [[ -z "$score_com_producer" ]]; then
        echo "S-Core communication producer runfile not found: $SCORE_COM_PRODUCER_RUNFILE" >&2
        echo "Set SCORE_COM_BAZEL_BIN to a prebuilt S-Core communication bazel-bin directory or run through Bazel with the score_communication module available." >&2
        exit 2
    fi

    score_com_producer_realpath="$(realpath "$score_com_producer")"
    if [[ "$score_com_producer_realpath" != */"$SCORE_COM_PRODUCER_BAZEL_BIN_SUFFIX" ]]; then
        echo "cannot derive S-Core communication bazel-bin from runfile: $score_com_producer_realpath" >&2
        exit 2
    fi
    SCORE_COM_BAZEL_BIN="${score_com_producer_realpath%/$SCORE_COM_PRODUCER_BAZEL_BIN_SUFFIX}"
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
export SCORE_CONFIG_PATH="$SCORE_CONFIG"
export SCORE_COM_BAZEL_BIN
export LD_LIBRARY_PATH="$SCORE_COM_BAZEL_BIN/score/mw/com/impl/bindings/lola:$SCORE_COM_BAZEL_BIN/score/mw/com/impl/rust/com-api/com-api-ffi-lola:$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/com-api-gen:${LD_LIBRARY_PATH:-}"

cargo build -p mw_com_provider --features score-lola --example "$SCORE_E2E_EXAMPLE"

"$SCORE_COM_BAZEL_BIN/score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example" \
    --run-mode producer \
    --service-instance-manifest "$SCORE_CONFIG_PATH" &
producer_pid=$!

cleanup() {
    kill "$producer_pid" 2>/dev/null || true
    wait "$producer_pid" 2>/dev/null || true
}
trap cleanup EXIT

"target/debug/examples/$SCORE_E2E_EXAMPLE"
