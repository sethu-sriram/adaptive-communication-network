#!/usr/bin/env bash
# Mininet-free checks: syntax, controller decision logic, real client/server over a lossy relay.
set -e
cd "$(dirname "$0")"
python3 -m py_compile controller.py run_controller.py client.py server.py protocol.py topology.py \
        experiment.py demo_t7.py analyze.py make_report.py check_startup_reroutes.py
echo "syntax OK"
python3 tests/test_controller_logic.py
python3 tests/test_loopback.py
echo "ALL TESTS PASSED"
