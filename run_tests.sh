#!/usr/bin/env bash
# Run Mininet-free test suite for Project 30
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Running controller logic tests ==="
python3 tests/test_controller_logic.py

echo "=== Running loopback UDP recovery tests ==="
python3 tests/test_loopback.py

echo "=== All Mininet-free tests passed! ==="
