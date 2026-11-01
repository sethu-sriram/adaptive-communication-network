### 5.1 Experimental setup
Two-path Mininet topology (10 Mbit/s, 2 ms links), OpenFlow 1.3 controller (OS-Ken), UDP client/server with ACK + retransmission (RTO 100 ms x1.5 backoff, 5 retries). Each configuration was run **5 times** (90 runs in total) for loads of 20, 50, 100 packets/s; a run lasts 30 s with the failure injected at t = 10 s and removed at t = 20 s on link s1-s2 (path A). **Baseline** = static mode (controller installs path A once and never reacts). **Adaptive** = this project (link-event detection + application reports). Values are mean ± standard deviation over runs.

Scenarios: `none` (no failure), `linkdown` (interface down, generates link events), `blackhole` (100 % loss, interface stays up: **no** link event, only the application can notice).

Metrics: delivery ratio, retransmissions, p95 delivery latency (first send -> ACK), **recovery time** (failure -> first packet of a sustained first-attempt-ACKed run, see `analyze.py`), longest ACK gap, goodput.

### 5.2 Adaptive vs static (all loads pooled)

| Scenario | Metric | Adaptive | Static |
|---|---|---|---|
| none | delivery (%) | 100.0 ± 0.0 | 100.0 ± 0.0 |
| none | p95 latency (ms) | 50 ± 18 | 48 ± 12 |
| none | retransmissions / run | 22 ± 38 | 11 ± 16 |
| linkdown | delivery (%) | 100.0 ± 0.0 | 70.8 ± 0.5 |
| linkdown | recovery time (ms) | 124 ± 94 | 10174 ± 102 |
| linkdown | p95 latency (ms) | 42 ± 13 | 502 ± 91 |
| linkdown | retransmissions / run | 17 ± 29 | 2803 ± 1698 |
| blackhole | delivery (%) | 100.0 ± 0.0 | 70.4 ± 0.6 |
| blackhole | recovery time (ms) | 390 ± 83 | 10320 ± 201 |
| blackhole | p95 latency (ms) | 54 ± 18 | 457 ± 76 |
| blackhole | retransmissions / run | 47 ± 43 | 2808 ± 1693 |

### 5.3 Results per load

| Scenario | pps | Mode | Delivery % | Lost | Retrans. | p95 lat (ms) | Recovery (ms) | Longest ACK gap (ms) |
|---|---|---|---|---|---|---|---|---|
| blackhole | 20 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 11 ± 4 | 49 ± 11 | 398 ± 93 | 301 ± 52 |
| blackhole | 20 | static | 70.2 ± 0.8 | 179 ± 5 | 995 ± 24 | 419 ± 116 | 10421 ± 289 | 10250 ± 246 |
| blackhole | 50 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 36 ± 13 | 48 ± 12 | 426 ± 82 | 329 ± 77 |
| blackhole | 50 | static | 70.5 ± 0.5 | 443 ± 7 | 2471 ± 32 | 465 ± 60 | 10278 ± 134 | 10210 ± 145 |
| blackhole | 100 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 94 ± 43 | 64 ± 26 | 345 ± 66 | 384 ± 107 |
| blackhole | 100 | static | 70.5 ± 0.4 | 885 ± 11 | 4958 ± 85 | 488 ± 3 | 10260 ± 142 | 10179 ± 107 |
| linkdown | 20 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 6 ± 6 | 41 ± 9 | 144 ± 108 | 222 ± 154 |
| linkdown | 20 | static | 71.1 ± 0.5 | 173 ± 3 | 974 ± 9 | 517 ± 169 | 10132 ± 38 | 10096 ± 64 |
| linkdown | 50 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 10 ± 7 | 38 ± 9 | 109 ± 68 | 215 ± 169 |
| linkdown | 50 | static | 70.8 ± 0.5 | 438 ± 7 | 2483 ± 58 | 496 ± 6 | 10141 ± 73 | 10113 ± 66 |
| linkdown | 100 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 34 ± 48 | 48 ± 19 | 118 ± 116 | 138 ± 94 |
| linkdown | 100 | static | 70.5 ± 0.4 | 885 ± 11 | 4952 ± 71 | 493 ± 4 | 10249 ± 138 | 10228 ± 136 |
| none | 20 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 4 ± 4 | 40 ± 12 | n/a | 158 ± 107 |
| none | 20 | static | 100.0 ± 0.0 | 0 ± 0 | 3 ± 2 | 46 ± 8 | n/a | 128 ± 64 |
| none | 50 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 13 ± 16 | 51 ± 10 | n/a | 246 ± 228 |
| none | 50 | static | 100.0 ± 0.0 | 0 ± 0 | 7 ± 6 | 46 ± 14 | n/a | 152 ± 111 |
| none | 100 | adaptive | 100.0 ± 0.0 | 0 ± 0 | 50 ± 57 | 59 ± 25 | n/a | 226 ± 151 |
| none | 100 | static | 100.0 ± 0.0 | 0 ± 0 | 24 ± 23 | 52 ± 14 | n/a | 214 ± 184 |

Charts: `results/delivery_ratio.png`, `recovery_time.png`, `recovery_vs_rate.png`, `latency_p95.png`, `interruption.png`, `timeline_linkdown.png`, `timeline_blackhole.png`.

![delivery_ratio](results/delivery_ratio.png)
![recovery_time](results/recovery_time.png)
![timeline_blackhole](results/timeline_blackhole.png)
![timeline_linkdown](results/timeline_linkdown.png)

### 5.4 Findings

1. **Hard failure (link down).** Adaptive delivered 100.0 % of packets versus 70.8 % for static and recovered in 124 ms versus 10174 ms (about 82x faster). Static only works again when the failure itself ends; adaptive restores service on the backup path while the failure is still present.
2. **Silent failure (black-hole).** Adaptive delivered 100.0 % of packets versus 70.4 % for static and recovered in 390 ms versus 10320 ms (about 26x faster). Static only works again when the failure itself ends; adaptive restores service on the backup path while the failure is still present.
3. **Detection path matters.** Link events recover in 124 ms; application reports need 390 ms (about 266 ms more) because the client first needs consecutive timeouts plus 250 ms of silence before it reports. This is the price of detecting failures that OpenFlow cannot see.
4. **No cost in normal operation.** Without failures both modes deliver the same share of packets (difference +0.00 percentage points); differences in latency and retransmissions are within VM jitter.
5. **Cost of application-level recovery grows with load.** In the black-hole case adaptive needs on average 11 retransmissions at 20 pps, 36 retransmissions at 50 pps, 94 retransmissions at 100 pps; static needs 995 to 4958 and still loses about 30 % of the packets.

### 5.5 Limits and design trade-offs

* The application can mask an outage only up to about RTO x retries (about 1.4 s); longer outages need the controller to reroute first, which is exactly what the application report triggers.
* After a silent failure there is no link-up event, so the controller returns to path A only when the 20 s hold-down (`P30_SUSPECT_HOLD`) expires: a short hold-down returns sooner but risks flapping, a long one keeps traffic on the backup path longer.
* If every usable path is suspect, the controller rotates to the other path on each fresh report instead of sticking with the preferred one (found and fixed during testing).
* Only one failure at a time on the s1-s2 link was evaluated; two simultaneous failures are covered by the logic tests (`NO_PATH_AVAILABLE`) but were not measured.
* Results come from one VirtualBox VM; scheduling jitter adds noise (visible in the `none` rows). Absolute numbers will differ on other machines; the relative comparison is the result.

### 5.6 Data-quality notes

* One run (`adaptive_linkdown_50pps_r3`) was discarded and repeated: its maximum latency (about 11 s) is impossible with a 1.4 s retry window, so the client process/VM had been stalled; the original files are kept in `results/discarded/`. The controller log of that run shows a normal reroute.
* The recovery metric requires a *sustained* first-attempt recovery: in an earlier version, packets that slipped through while `tc` was being reconfigured made 3 of 15 static black-hole runs look recovered after under 130 ms although their ACK gap (about 10 s) and delivery (about 70 %) show they did not. The metric was corrected and all runs re-analysed from the saved per-packet logs; no experiment was repeated for this reason.
* In 3 of the 15 adaptive no-failure runs (`adaptive_none_20pps_r2`, `adaptive_none_50pps_r3`, `adaptive_none_100pps_r3`) a client report, sent although nothing had failed, moved the traffic to path B; delivery stayed at 100 %. All 30 adaptive failure runs were checked and none had an early reroute. Re-check with `python3 check_startup_reroutes.py`.

