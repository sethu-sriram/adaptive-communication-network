#!/usr/bin/env python3
"""Aggregate results/*_client.json (+ per-packet CSVs) into tables and charts.

File naming (run_all.sh):  <mode>_<scenario>_<rate>pps_r<rep>_client.{json,csv}   (_r<rep> optional)
Outputs: results/runs.csv (one row per run), summary.csv / summary.md (mean +- std over repetitions),
         comparison.md (adaptive vs static), results/*.png (bars with error bars + timelines).

Recovery time = (ACK arrival of the first first-attempt-ACKed packet sent AFTER the first packet that
was actually affected by the failure) - (failure timestamp); 0 if the failure was fully masked,
NaN when there is no failure.  See recovery_ms() for the exact definition.
Interruption (longest ACK gap) is kept for reference, but is NOT a recovery time.
"""
import glob, json, os, re, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
PAT = re.compile(r'(static|adaptive)_(\w+?)_(\d+)pps(?:_r(\d+))?_client\.json')


def read_meta(prefix):
    p = prefix + '_meta.txt'
    if not os.path.exists(p):
        return {}
    return dict(kv.split('=', 1) for kv in open(p).read().split() if '=' in kv)


def recovery_ms(csv_path, start_epoch, meta, window=0.5, min_frac=0.8):
    """ms from the failure until the data path demonstrably works again (NaN if n/a).

    1. f = first packet sent at/after the failure that did NOT succeed on its first attempt.
       (Packets sent in the few ms between the failure timestamp and the failure really taking
       effect are ACKed first-try and are ignored.)
    2. Recovery packet = first first-attempt-ACKed packet sent after f that starts a SUSTAINED
       recovery: >= min_frac of all packets sent in the next `window` seconds are also ACKed on
       their first attempt.  This rejects the few packets that slip through while `tc` is still
       being (re)configured, which would otherwise look like a recovery.
    3. recovery = its ACK time - failure timestamp.
    If no packet was ever affected the failure was fully masked -> 0.0 ms; NaN if never recovered."""
    try:
        t_fail = float(meta.get('fail_epoch', '')) - start_epoch
    except (ValueError, TypeError):
        return float('nan')
    d = pd.read_csv(csv_path)
    after = d[d.send_t >= t_fail].sort_values('send_t').reset_index(drop=True)
    ok = (after.acked_attempt.fillna(-1) == 0).to_numpy()
    if len(ok) == 0 or ok.all():
        return 0.0
    send, ack = after.send_t.to_numpy(), after.ack_t.to_numpy()
    f = int(np.argmin(ok))                       # index of first affected packet
    for i in range(f + 1, len(after)):
        if ok[i] and ok[(send >= send[i]) & (send <= send[i] + window)].mean() >= min_frac:
            return round((ack[i] - t_fail) * 1000, 1)
    return float('nan')


rows = []
for f in sorted(glob.glob(os.path.join(R, '*_client.json'))):
    m = PAT.match(os.path.basename(f))
    if not m:
        continue
    s = json.load(open(f))
    prefix = f[:-len('_client.json')]
    rows.append(dict(
        mode=m[1], scenario=m[2], rate=int(m[3]), rep=int(m[4] or 1),
        sent=s['sent'], delivered=s['delivered'], lost=s['lost'],
        delivery_pct=100 * s['delivery_ratio'], retransmissions=s['retransmissions'],
        lat_mean_ms=s['latency_ms']['mean'] or 0, lat_p95_ms=s['latency_ms']['p95'] or 0,
        lat_max_ms=s['latency_ms']['max'] or 0, rtt_mean_ms=s['rtt_ms']['mean'] or 0,
        interruption_ms=max(0, s['max_ack_gap_ms'] - s['nominal_interval_ms']),
        recovery_ms=recovery_ms(prefix + '_client.csv', s.get('start_epoch'), read_meta(prefix)),
        goodput_pps=s['goodput_pps']))
if not rows:
    sys.exit('no results found in %s' % R)

runs = pd.DataFrame(rows).sort_values(['scenario', 'rate', 'mode', 'rep'])
runs.round(2).to_csv(os.path.join(R, 'runs.csv'), index=False)

METRICS = ['delivery_pct', 'lost', 'retransmissions', 'lat_mean_ms', 'lat_p95_ms',
           'rtt_mean_ms', 'interruption_ms', 'recovery_ms', 'goodput_pps']
g = runs.groupby(['scenario', 'rate', 'mode'])
mean, std = g[METRICS].mean(), g[METRICS].std(ddof=1).fillna(0)
n = g.size().rename('runs')
summary = mean.add_suffix('_mean').join(std.add_suffix('_std')).join(n).reset_index()
summary.round(2).to_csv(os.path.join(R, 'summary.csv'), index=False)

# compact markdown: "mean ± std"
md = pd.DataFrame({'scenario': mean.reset_index().scenario, 'rate': mean.reset_index().rate,
                   'mode': mean.reset_index()['mode'], 'runs': n.values})
for c in METRICS:
    md[c] = [('n/a' if np.isnan(a) else f'{a:.1f} ± {b:.1f}') for a, b in zip(mean[c], std[c])]
md = md.sort_values(['scenario', 'rate', 'mode'])
open(os.path.join(R, 'summary.md'), 'w').write(md.to_markdown(index=False))

# adaptive vs static (pooled over rates): difference of means, Welch-style z on run values
cmp_rows = []
for sc in ('none', 'linkdown', 'blackhole'):
    for c in ('delivery_pct', 'recovery_ms', 'lat_p95_ms', 'retransmissions'):
        a = runs[(runs.scenario == sc) & (runs['mode'] == 'adaptive')][c].dropna()
        b = runs[(runs.scenario == sc) & (runs['mode'] == 'static')][c].dropna()
        if len(a) < 2 or len(b) < 2:
            continue
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        diff = a.mean() - b.mean()
        z = diff / se if se > 0 else (0.0 if diff == 0 else float('inf'))
        cmp_rows.append(dict(scenario=sc, metric=c, adaptive=round(a.mean(), 2), static=round(b.mean(), 2),
                             diff=round(a.mean() - b.mean(), 2), n_adaptive=len(a), n_static=len(b),
                             significant='yes' if abs(z) > 2 else 'no'))
cmp_df = pd.DataFrame(cmp_rows)
open(os.path.join(R, 'comparison.md'), 'w').write(cmp_df.to_markdown(index=False) if len(cmp_df) else '')
print(md.to_string(index=False)); print(); print(cmp_df.to_string(index=False))

COL = {'static': '#c0504d', 'adaptive': '#4f81bd'}
scen = [s for s in ('none', 'linkdown', 'blackhole') if s in set(runs.scenario)]


def bars(metric, title, ylabel, fname):
    fig, ax = plt.subplots(figsize=(7, 4))
    w, x0 = 0.38, np.arange(len(scen))
    for i, mode in enumerate(('static', 'adaptive')):
        # mean/std over ALL runs of the scenario (rates pooled)
        vals = [runs[(runs.scenario == s) & (runs['mode'] == mode)][metric].mean() for s in scen]
        errs = [runs[(runs.scenario == s) & (runs['mode'] == mode)][metric].std(ddof=1) for s in scen]
        ax.bar(x0 + (i - .5) * w, np.nan_to_num(vals), w, yerr=np.nan_to_num(errs), capsize=3,
               label=mode, color=COL[mode])
    ax.set_xticks(x0); ax.set_xticklabels(scen)
    ax.set_title(title); ax.set_ylabel(ylabel); ax.legend(); ax.grid(axis='y', alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(R, fname), dpi=150); plt.close(fig)


bars('delivery_pct', 'Delivery ratio (mean ± std over runs)', '% packets delivered', 'delivery_ratio.png')
bars('recovery_ms', 'Recovery time after failure (mean ± std)', 'ms (0 = no failure)', 'recovery_time.png')
bars('interruption_ms', 'Longest ACK gap (mean ± std)', 'ms', 'interruption.png')
bars('lat_p95_ms', 'p95 delivery latency (mean ± std)', 'ms', 'latency_p95.png')

# recovery vs rate, failure scenarios
fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=False)
for ax, sc in zip(axes, [s for s in scen if s != 'none'] or []):
    for mode in ('static', 'adaptive'):
        d = runs[(runs.scenario == sc) & (runs['mode'] == mode)].groupby('rate').recovery_ms.agg(['mean', 'std'])
        if len(d):
            ax.errorbar(d.index, d['mean'], yerr=d['std'].fillna(0), marker='o', capsize=3,
                        color=COL[mode], label=mode)
    ax.set_title(f'{sc}: recovery vs load'); ax.set_xlabel('rate (pps)'); ax.set_ylabel('ms'); ax.grid(alpha=.3)
    ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(R, 'recovery_vs_rate.png'), dpi=150); plt.close(fig)

# timelines (rep 1, 50 pps or first rate)
for sc in [s for s in scen if s != 'none']:
    rate = 50 if 50 in set(runs.rate) else int(runs.rate.iloc[0])
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    for mode in ('static', 'adaptive'):
        cands = [os.path.join(R, f'{mode}_{sc}_{rate}pps_r1_client.csv'),
                 os.path.join(R, f'{mode}_{sc}_{rate}pps_client.csv')]
        p = next((c for c in cands if os.path.exists(c)), None)
        if not p:
            continue
        d = pd.read_csv(p)
        ok = d.dropna(subset=['latency_ms'])
        axes[0].scatter(ok.send_t, ok.latency_ms, s=5, color=COL[mode], label=mode)
        lost = d[d.latency_ms.isna()]
        if len(lost):
            axes[0].scatter(lost.send_t, [ok.latency_ms.max() * 1.1] * len(lost), marker='x', s=8,
                            color=COL[mode], alpha=.6)
        gp = ok.groupby(ok.ack_t.astype(int)).size()
        gp = gp.reindex(range(0, int(d.send_t.max()) + 2), fill_value=0)
        axes[1].plot(gp.index, gp.values, color=COL[mode], label=mode)
    axes[0].set_yscale('log'); axes[0].set_ylabel('latency ms (x = lost)')
    axes[0].set_title(f'{sc}: per-packet latency @ {rate} pps (run 1)'); axes[0].legend()
    axes[1].set_ylabel('goodput (pkts/s)'); axes[1].set_xlabel('time (s)')
    for a in axes:
        a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(R, f'timeline_{sc}.png'), dpi=150); plt.close(fig)
print('tables and charts written to', R)
