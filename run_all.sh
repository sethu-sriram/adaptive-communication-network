#!/usr/bin/env bash
# Full evaluation: {static, adaptive} x {none, linkdown, blackhole} x {20,50,100 pps} x REPS repetitions
# Usage:  ./run_all.sh                 (REPS=5 -> 90 runs x ~45 s, about 70 min; needs sudo for Mininet)
#         QUICK=1 ./run_all.sh         (50 pps only: 30 runs, about 25 min)
#         REPS=2 ./run_all.sh          (fewer repetitions)
#         START_REP=3 REPS=5 ./run_all.sh   (resume: only repetitions 3..5)
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p results
DURATION=${DURATION:-30}; FAIL_AT=${FAIL_AT:-10}; FAIL_FOR=${FAIL_FOR:-10}
REPS=${REPS:-5}; START_REP=${START_REP:-1}
RATES="20 50 100"; [ "${QUICK:-0}" = "1" ] && RATES="50"
PORT=6653

# repetitions outermost, so an interrupted sweep still has complete sets of runs
for REP in $(seq "$START_REP" "$REPS"); do
  for MODE in static adaptive; do
    for SCEN in none linkdown blackhole; do
      for RATE in $RATES; do
        RUN="${MODE}_${SCEN}_${RATE}pps_r${REP}"
        echo "=== $RUN"
        sudo mn -c >/dev/null 2>&1
        P30_MODE=$MODE P30_LOG="results/${RUN}_controller.jsonl" \
          python3 run_controller.py controller.py --port $PORT \
          > "results/${RUN}_controller.log" 2>&1 &
        CPID=$!
        sleep 3
        sudo -E /usr/bin/python3 experiment.py --run "$RUN" --scenario "$SCEN" \
          --rate "$RATE" --duration "$DURATION" --fail-at "$FAIL_AT" --fail-for "$FAIL_FOR" \
          --controller-port $PORT || echo "!!! $RUN failed"
        kill $CPID 2>/dev/null; wait $CPID 2>/dev/null
      done
    done
  done
done
sudo mn -c >/dev/null 2>&1
python3 analyze.py
