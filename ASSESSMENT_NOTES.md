# Project 30 — assessment and verification notes

## Source-grounded findings

The uploaded assessment workbook says earlier results showed normal traffic at 100% delivery, link-down recovery, and blackhole delivery around 71% with roughly 10 seconds of interruption. Adaptive and static were nearly identical. The workbook explicitly says the controller code was not re-reviewed, so these are historical results—not proof that this ZIP has the same defects.

The workbook flags recovery-time measurement, nonzero interruption in no-failure runs, need for at least five repetitions with mean/std, error-bar plots, and verifying static mode truly does not reroute.

The uploaded rubric PDF (page 1) totals 40 marks: D1=15 and D2=25. Page 2 weights dynamic SDN functionality (6), documentation/demo/viva (6), performance evaluation (5), and robustness (4).

## Changes in this revision

- Application-report receiver uses a timeout loop and cleanup.
- JSON reports are decoded and validated as objects; malformed reports are ignored and logged.
- Invalid/missing `since` timestamps are logged and ignored rather than raising an exception.
- Flow-stat changes are persisted to the JSONL event log as `FLOW_STATS`.
- Controller logic tests include an invalid-timestamp report.

## Validation limitation

This environment does not provide a running Mininet/Open vSwitch/OS-Ken network, so no end-to-end reroute or performance claim is made here. Run tests and linkdown/blackhole experiments on Ubuntu, inspect logs for `PATH_SUSPECTED` and `PATH_INSTALLED`, and regenerate charts from fresh results.
