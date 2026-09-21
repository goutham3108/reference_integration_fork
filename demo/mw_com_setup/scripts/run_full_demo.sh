#!/usr/bin/env bash
set -euo pipefail

# run_full_demo.sh <vss_json> [out_paths_file]
#
# Generates a newline-separated list of VSS leaf paths from the provided
# VSS JSON, writes it to `out_paths_file` (default: ./vss_paths.txt), then
# starts `mw_com_receiver` in the background and runs `kuksa_to_com` in the
# foreground. Kills the background receiver when the script exits.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VSS_JSON="${1:-}"
OUT_PATH="${2:-$SCRIPT_DIR/vss_paths.txt}"

if [[ -z "$VSS_JSON" ]]; then
  echo "Usage: $0 /path/to/SDV-Hack_vss.json [out_paths_file]"
  exit 2
fi

echo "Generating VSS path list from '$VSS_JSON' -> '$OUT_PATH'..."
python3 "$SCRIPT_DIR/extract_vss_paths.py" "$VSS_JSON" > "$OUT_PATH"
echo "Wrote $(wc -l < "$OUT_PATH") paths to $OUT_PATH"

export KUKSA_VSS_PATHS_FILE="$OUT_PATH"

RECEIVER_LOG="$SCRIPT_DIR/receiver.log"

if ! command -v bazel >/dev/null 2>&1; then
  echo "Error: bazel not found in PATH" >&2
  exit 3
fi

echo "Starting mw_com_receiver (logs -> $RECEIVER_LOG) in background..."
bazel run --config=linux-x86_64 //demo/mw_com_setup/mw_com_receiver:mw_com_receiver &> "$RECEIVER_LOG" &
RECV_PID=$!

cleanup() {
  echo "Stopping background receiver (pid $RECV_PID)..."
  kill "$RECV_PID" 2>/dev/null || true
  wait "$RECV_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Waiting 3s for receiver to initialize..."
sleep 3

echo "Running kuksa_to_com (foreground). Press Ctrl+C to stop both." 
bazel run --config=linux-x86_64 //demo/mw_com_setup/kuksa_to_com:kuksa_to_com

# When the producer exits, cleanup will be invoked by the trap.
