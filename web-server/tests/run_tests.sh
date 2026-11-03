#!/usr/bin/env bash
# Runs all unit and integration tests for web-server deployment manager
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${dir}/..:${PYTHONPATH:-}"

echo "==========================================================="
echo " Running SDV Deployment Manager & Benchmark Test Suite"
echo "==========================================================="

python3 -m unittest discover -s "${dir}" -p "test_*.py" -v

echo ""
echo "All tests passed successfully!"
