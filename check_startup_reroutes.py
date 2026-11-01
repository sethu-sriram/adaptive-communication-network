#!/usr/bin/env python3
"""Did an application report move traffic to path B BEFORE the failure was injected (or in a no-failure run)?

Reads results/adaptive_*_controller.jsonl together with results/*_meta.txt (fail_epoch).
  failure runs : a PATH_INSTALLED with reason 'application-report' before fail_epoch = the failure
                 hit a path that traffic had already left, so that run did not test the failure.
  none runs    : any such reroute = a spurious report (nothing was wrong).
Usage: python3 check_startup_reroutes.py [--results results]
"""
import argparse, glob, json, os, re

ap = argparse.ArgumentParser()
ap.add_argument('--results', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results'))
R = ap.parse_args().results
PAT = re.compile(r'adaptive_(\w+?)_(\d+)pps_r(\d+)_controller\.jsonl')
bad, total = [], 0
for f in sorted(glob.glob(os.path.join(R, 'adaptive_*_controller.jsonl'))):
    m = PAT.match(os.path.basename(f))
    if not m:
        continue
    sc, rate, rep = m[1], int(m[2]), int(m[3])
    ev = [json.loads(l) for l in open(f) if l.strip()]
    meta = {}
    mp = f.replace('_controller.jsonl', '_meta.txt')
    if os.path.exists(mp):
        meta = dict(kv.split('=', 1) for kv in open(mp).read().split() if '=' in kv)
    try:
        t_fail = float(meta.get('fail_epoch', ''))
    except ValueError:
        t_fail = None
    t_end = None
    cands = [e['t'] for e in ev if e['event'] == 'PATH_INSTALLED' and e.get('reason') == 'application-report']
    total += 1
    if sc == 'none':
        hits = cands
    else:
        hits = [t for t in cands if t_fail is not None and t < t_fail]
    if hits:
        bad.append((os.path.basename(f)[:-len('_controller.jsonl')], sc, len(hits),
                    (hits[0] - t_fail) if t_fail else None))
print('adaptive runs checked: %d' % total)
if not bad:
    print('OK: no application-report reroute before a failure / in a no-failure run.')
else:
    print('%d run(s) had a reroute caused by an application report BEFORE the failure (or with no failure):' % len(bad))
    for name, sc, n, dt in bad:
        print('  %-36s %s  reroutes=%d%s' % (name, sc, n, '' if dt is None else '  first at %.1f s before failure' % -dt))
