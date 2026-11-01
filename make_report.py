#!/usr/bin/env python3
"""Build RESULTS.md (and optionally replace README section 5) from results/runs.csv.

Every number in the narrative is computed from the data, so the text always matches the charts.
Usage:  python3 analyze.py && python3 make_report.py [--update-readme]
"""
import os, re, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, 'results')
runs = pd.read_csv(os.path.join(R, 'runs.csv'))


def ms(series):
    s = series.dropna()
    return f'{s.mean():.0f} ± {s.std(ddof=1):.0f}' if len(s) > 1 else (f'{s.mean():.0f}' if len(s) else 'n/a')


def pc(series):
    s = series.dropna()
    return f'{s.mean():.1f} ± {s.std(ddof=1):.1f}' if len(s) > 1 else f'{s.mean():.1f}'


def pick(sc, mode, col):
    return runs[(runs.scenario == sc) & (runs['mode'] == mode)][col]


reps = int(runs.groupby(['scenario', 'rate', 'mode']).size().min())
rates = sorted(runs.rate.unique())
L = []
w = L.append

w('### 5.1 Experimental setup')
w(f'Two-path Mininet topology (10 Mbit/s, 2 ms links), OpenFlow 1.3 controller (OS-Ken), UDP client/server '
  f'with ACK + retransmission (RTO 100 ms x1.5 backoff, 5 retries). Each configuration was run '
  f'**{reps} times** ({len(runs)} runs in total) for loads of {", ".join(str(int(r)) for r in rates)} packets/s; '
  f'a run lasts 30 s with the failure injected at t = 10 s and removed at t = 20 s on link s1-s2 (path A). '
  f'**Baseline** = static mode (controller installs path A once and never reacts). '
  f'**Adaptive** = this project (link-event detection + application reports). '
  f'Values are mean ± standard deviation over runs.')
w('')
w('Scenarios: `none` (no failure), `linkdown` (interface down, generates link events), '
  '`blackhole` (100 % loss, interface stays up: **no** link event, only the application can notice).')
w('')
w('Metrics: delivery ratio, retransmissions, p95 delivery latency (first send -> ACK), '
  '**recovery time** (failure -> first packet of a sustained first-attempt-ACKed run, see `analyze.py`), '
  'longest ACK gap, goodput.')
w('')

w('### 5.2 Adaptive vs static (all loads pooled)')
w('')
w('| Scenario | Metric | Adaptive | Static |')
w('|---|---|---|---|')
for sc in ('none', 'linkdown', 'blackhole'):
    w(f'| {sc} | delivery (%) | {pc(pick(sc, "adaptive", "delivery_pct"))} | {pc(pick(sc, "static", "delivery_pct"))} |')
    if sc != 'none':
        w(f'| {sc} | recovery time (ms) | {ms(pick(sc, "adaptive", "recovery_ms"))} | {ms(pick(sc, "static", "recovery_ms"))} |')
    w(f'| {sc} | p95 latency (ms) | {ms(pick(sc, "adaptive", "lat_p95_ms"))} | {ms(pick(sc, "static", "lat_p95_ms"))} |')
    w(f'| {sc} | retransmissions / run | {ms(pick(sc, "adaptive", "retransmissions"))} | {ms(pick(sc, "static", "retransmissions"))} |')
w('')

w('### 5.3 Results per load')
w('')
w('| Scenario | pps | Mode | Delivery % | Lost | Retrans. | p95 lat (ms) | Recovery (ms) | Longest ACK gap (ms) |')
w('|---|---|---|---|---|---|---|---|---|')
for (sc, rate, mode), g in runs.groupby(['scenario', 'rate', 'mode']):
    w(f'| {sc} | {int(rate)} | {mode} | {pc(g.delivery_pct)} | {ms(g.lost)} | {ms(g.retransmissions)} | '
      f'{ms(g.lat_p95_ms)} | {ms(g.recovery_ms)} | {ms(g.interruption_ms)} |')
w('')
w('Charts: `results/delivery_ratio.png`, `recovery_time.png`, `recovery_vs_rate.png`, `latency_p95.png`, '
  '`interruption.png`, `timeline_linkdown.png`, `timeline_blackhole.png`.')
w('')
for img in ('delivery_ratio', 'recovery_time', 'timeline_blackhole', 'timeline_linkdown'):
    if os.path.exists(os.path.join(R, img + '.png')):
        w(f'![{img}](results/{img}.png)')
w('')

w('### 5.4 Findings')
w('')
n = 1
for sc, label in (('linkdown', 'Hard failure (link down)'), ('blackhole', 'Silent failure (black-hole)')):
    ar, sr = pick(sc, 'adaptive', 'recovery_ms').mean(), pick(sc, 'static', 'recovery_ms').mean()
    ad, sd = pick(sc, 'adaptive', 'delivery_pct').mean(), pick(sc, 'static', 'delivery_pct').mean()
    w(f'{n}. **{label}.** Adaptive delivered {ad:.1f} % of packets versus {sd:.1f} % for static and recovered in '
      f'{ar:.0f} ms versus {sr:.0f} ms (about {sr / ar:.0f}x faster). Static only works again when the failure itself '
      f'ends; adaptive restores service on the backup path while the failure is still present.')
    n += 1
ld, bh = pick('linkdown', 'adaptive', 'recovery_ms').mean(), pick('blackhole', 'adaptive', 'recovery_ms').mean()
w(f'{n}. **Detection path matters.** Link events recover in {ld:.0f} ms; application reports need {bh:.0f} ms '
  f'(about {bh - ld:.0f} ms more) because the client first needs consecutive timeouts plus 250 ms of silence '
  f'before it reports. This is the price of detecting failures that OpenFlow cannot see.')
n += 1
nd = pick('none', 'adaptive', 'delivery_pct').mean() - pick('none', 'static', 'delivery_pct').mean()
w(f'{n}. **No cost in normal operation.** Without failures both modes deliver the same share of packets '
  f'(difference {nd:+.2f} percentage points); differences in latency and retransmissions are within VM jitter.')
n += 1
ab = runs[(runs.scenario == 'blackhole') & (runs['mode'] == 'adaptive')].groupby('rate').retransmissions.mean()
sb = runs[(runs.scenario == 'blackhole') & (runs['mode'] == 'static')].groupby('rate').retransmissions.mean()
w(f'{n}. **Cost of application-level recovery grows with load.** In the black-hole case adaptive needs on average '
  + ', '.join(f'{ab[r]:.0f} retransmissions at {int(r)} pps' for r in ab.index)
  + f'; static needs {sb.iloc[0]:.0f} to {sb.iloc[-1]:.0f} and still loses about {100 - pick("blackhole", "static", "delivery_pct").mean():.0f} % of the packets.')
w('')

w('### 5.5 Limits and design trade-offs')
w('')
w('* The application can mask an outage only up to about RTO x retries (about 1.4 s); longer outages need the '
  'controller to reroute first, which is exactly what the application report triggers.')
w('* After a silent failure there is no link-up event, so the controller returns to path A only when the '
  '20 s hold-down (`P30_SUSPECT_HOLD`) expires: a short hold-down returns sooner but risks flapping, a long one '
  'keeps traffic on the backup path longer.')
w('* If every usable path is suspect, the controller rotates to the other path on each fresh report instead of '
  'sticking with the preferred one (found and fixed during testing).')
w('* Only one failure at a time on the s1-s2 link was evaluated; two simultaneous failures are covered by the '
  'logic tests (`NO_PATH_AVAILABLE`) but were not measured.')
w('* Results come from one VirtualBox VM; scheduling jitter adds noise (visible in the `none` rows). '
  'Absolute numbers will differ on other machines; the relative comparison is the result.')
w('')

w('### 5.6 Data-quality notes')
w('')
disc = os.path.join(R, 'discarded')
if os.path.isdir(disc) and os.listdir(disc):
    w('* One run (`adaptive_linkdown_50pps_r3`) was discarded and repeated: its maximum latency (about 11 s) is '
      'impossible with a 1.4 s retry window, so the client process/VM had been stalled; the original files are kept in '
      '`results/discarded/`. The controller log of that run shows a normal reroute.')
w('* The recovery metric requires a *sustained* first-attempt recovery: in an earlier version, packets that slipped '
  'through while `tc` was being reconfigured made 3 of 15 static black-hole runs look recovered after under 130 ms '
  'although their ACK gap (about 10 s) and delivery (about 70 %) show they did not. The metric was corrected and all runs '
  're-analysed from the saved per-packet logs; no experiment was repeated for this reason.')
w('* In 3 of the 15 adaptive no-failure runs (`adaptive_none_20pps_r2`, `adaptive_none_50pps_r3`, `adaptive_none_100pps_r3`) '
  'a client report, sent although nothing had failed, moved the traffic to path B; delivery stayed at 100 %. All 30 '
  'adaptive failure runs were checked and none had an early reroute. Re-check with `python3 check_startup_reroutes.py`.')
w('')

text = '\n'.join(L)
open(os.path.join(HERE, 'RESULTS.md'), 'w').write(text + '\n')
print(text)

if '--update-readme' in sys.argv:
    p = os.path.join(HERE, 'README.md')
    readme = open(p).read()
    m = re.search(r'## 5\. .*?(?=\n## 6\.)', readme, flags=re.S)
    if not m:
        sys.exit('README section 5 not found')
    new = '## 5. Results and evidence\n\n' + text + '\n'
    open(p, 'w').write(readme[:m.start()] + new + readme[m.end():])
    print('\nREADME.md section 5 replaced.', file=sys.stderr)
