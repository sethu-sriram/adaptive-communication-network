# Development notes: problems found and fixed

Each item was found by running the system and changed the design or the analysis.
The same table is in section 7 of the project report (`docs/Project30_Report.pdf`).

| # | Observation | Cause | Fix (file) |
|---|---|---|---|
| 1 | Initial controller handled only some link failures; its cleanup also removed the table-miss rule | Delete of all flows; link check limited to two links | Per-path link tracking; cookie-based deletion of the controller's own rules only (`controller.py`) |
| 2 | `osken-manager` missing with OS-Ken 4.2.2 | That version ships no command-line entry point | `run_controller.py` starts the same application manager |
| 3 | First black-hole run: 89.8 % delivery, 4.35 s gap, controller stuck on the failed path | A short stall suspected path B as well; with both suspect the controller fell back to the preferred path A (down) | If all usable paths are suspect, rotate to the other path on every fresh report (`controller.py`, `choose(rotate=True)`) |
| 4 | Spurious reports from short client stalls | Reports triggered by timeout count alone | Extra condition: no ACK for 250 ms, `--suspect-silence` (`client.py`) |
| 5 | 3 of 15 static black-hole runs showed a recovery of 54-129 ms although they lost ~30 % of packets | A few packets slip through while `tc` is reconfigured; first metric accepted one first-attempt success | Recovery needs a *sustained* first-attempt success (80 % within 0.5 s); all runs re-analysed from the saved packet logs (`analyze.py`) |
| 6 | One adaptive link-down run (50 pps, rep 3) had an 11 s ACK gap | Client process / VM stalled; 11 s is impossible with a 1.4 s retry window | Run repeated; original files kept in `results/discarded/` |

Also: malformed or missing `since` values in application reports are logged and ignored (no exception);
the report receiver uses a timeout loop and cleans up its socket; flow-statistics changes are written to the JSONL log.

## Known limitation (documented, not hidden)

In 3 of the 15 adaptive no-failure runs a client report moved traffic to path B although nothing had failed
(`python3 check_startup_reroutes.py` lists them). Delivery stayed at 100 % because path B works. All 30 adaptive
failure runs were checked and none had an early reroute.

## Validation

* `./run_tests.sh` (no Mininet needed): controller logic (10 checks) and loopback client/server tests pass.
* Mininet experiments (90 runs) and the three-client demo `demo_t7.py` were run on Ubuntu in VirtualBox;
  raw data, controller logs, tables and charts are in `results/`.
