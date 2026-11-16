# Deliverables map: where each evaluation item is done

Project 30 – Adaptive Communication Network with Failure Recovery (UDP + SDN, Mininet, OS-Ken).
Full write-up: [docs/Project30_Report.pdf](docs/Project30_Report.pdf). Run instructions: [README.md](README.md).

## D1 (15 marks)

| Component | Marks | Where it is done | Evidence |
|---|---|---|---|
| Problem understanding and architecture | 2 | README sections 1–3; report sections 1–2 | Topology diagram in the README; message flow in report 2.3 |
| TCP/UDP socket implementation | 4 | `protocol.py` (18-byte header), `server.py` (receiver thread + 4 workers, duplicate counting), `client.py` (ACKs, retransmission, backoff) | `tests/test_loopback.py`; report 2.4, 3.1, 3.2 |
| Mininet + SDN implementation | 4 | `topology.py` (h1, h2, s1–s4, two paths), `controller.py` and `run_controller.py` (OS-Ken, OpenFlow 1.3 flow rules) | `tests/test_controller_logic.py`; `docs/screenshots/19_topology_ping_flows.png` |
| Socket–SDN integration | 3 | `client.py` sends PATH_SUSPECT / RECOVERED over a UNIX socket; `controller.py` `handle_report` reroutes | `results/*_controller.jsonl`; `docs/screenshots/08_controller_events_blackhole.png`; report 3.4 |
| Initial testing and demo | 2 | README section 5 (manual demo), `run_tests.sh`, `demo_t7.py` | `docs/screenshots/19_…`, `20_t7_three_clients_link_failure.png` |

## D2 (25 marks)

| Component | Marks | Where it is done | Evidence |
|---|---|---|---|
| Complete application functionality | 4 | `client.py`, `server.py`; three concurrent clients in `demo_t7.py` | `results/t7_nofailure_summary.txt`, `results/t7_failure_summary.txt` (600/600 packets per client) |
| Dynamic SDN functionality | 6 | `controller.py`: link-event rerouting, application-report rerouting, make-before-break, 20 s hold-down, stale-report filter, path rotation | Event traces in `results/*_controller.jsonl`; report section 8 |
| Challenging scenario / robustness | 4 | Link-down and black-hole (100 % silent loss) injected by `experiment.py` / `run_all.sh`; double failure and malformed input in the tests | `results/`; `CHANGES.md` (problems found and fixed) |
| Performance evaluation and comparison | 5 | `analyze.py`, `make_report.py`; adaptive vs static baseline (`P30_MODE=static`), 90 runs (3 scenarios × 3 loads × 2 modes × 5 repetitions) | `results/summary.md`, `results/comparison.md`, charts `results/*.png`; README section 7 |
| Documentation, final demo and viva | 6 | `README.md`, `docs/Project30_Report.pdf`, `CHANGES.md`, `RESULTS.md` | Reproduce with `run_all.sh`; `docs/screenshots/` |

## Headline results (90 runs)

| Scenario | Adaptive | Static |
|---|---|---|
| Link down: delivery / recovery | 100 % / 124 ms | 70.8 % / 10.2 s |
| Black-hole: delivery / recovery | 100 % / 390 ms | 70.4 % / 10.3 s |
| No failure | no significant difference | |

## Reproduce

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
chmod +x run_all.sh && ./run_tests.sh      # Mininet-free checks
python3 run_controller.py controller.py --port 6653     # terminal 1
sudo python3 topology.py                                # terminal 2
```
