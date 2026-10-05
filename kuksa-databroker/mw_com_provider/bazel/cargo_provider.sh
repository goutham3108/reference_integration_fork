#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
    cd "$BUILD_WORKSPACE_DIRECTORY"
else
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$script_dir/.."
fi

command="${1:-}"
if [[ $# -gt 0 ]]; then
    shift
fi

case "$command" in
    check)
        exec cargo check -p mw_com_provider "$@"
        ;;
    test)
        exec cargo test -p mw_com_provider "$@"
        ;;
    score-lola-build)
        exec cargo build -p mw_com_provider --features score-lola --example "${SCORE_E2E_EXAMPLE:-score_lola_live_speed}" "$@"
        ;;
    score-lola-live-e2e-local)
        exec scripts/run-score-lola-live-e2e-local.sh "$@"
        ;;
    codegen)
        exec cargo run -p xtask -- codegen "$@"
        ;;
    verify-codegen)
        exec cargo run -p xtask -- verify-codegen "$@"
        ;;
    *)
        echo "usage: $0 {check|test|score-lola-build|score-lola-live-e2e-local|codegen|verify-codegen} [args...]" >&2
        exit 2
        ;;
esac