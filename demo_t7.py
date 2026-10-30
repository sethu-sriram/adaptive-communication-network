#!/usr/bin/env python3
"""T7 demo: several clients sending AT THE SAME TIME through the SDN network (needs root).

Controller must already be running (python3 run_controller.py controller.py --port 6653).

    sudo /usr/bin/python3 demo_t7.py            # 3 concurrent clients, no failure
    sudo /usr/bin/python3 demo_t7.py --fail     # ...and link s1-s2 goes down for 5 s in the middle

Prints a table with per-client results and a concurrency check, and saves it to /tmp/t7_summary.txt.
"""
import argparse, json, os, signal, sys, time

from mininet.log import info, setLogLevel
from topology import build_network

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clients', type=int, default=3)
    ap.add_argument('--rate', type=float, default=20)
    ap.add_argument('--duration', type=float, default=30)
    ap.add_argument('--fail', action='store_true', help='take link s1-s2 down in the middle')
    ap.add_argument('--fail-at', type=float, default=10)
    ap.add_argument('--fail-for', type=float, default=5)
    ap.add_argument('--warmup', type=float, default=6)
    ap.add_argument('--server-ip', default='10.0.0.2')
    ap.add_argument('--controller-port', type=int, default=6653)
    ap.add_argument('--out', default='/tmp/t7')
    ap.add_argument('--controller-log', default=os.environ.get('P30_LOG', '/tmp/p30_events.jsonl'),
                    help='controller event log (default: where run_controller.py writes it)')
    args = ap.parse_args()

    setLogLevel('info')
    net = build_network(controller_port=args.controller_port)
    try:
        h1, h2 = net.get('h1', 'h2')
        info('*** waiting %.0fs for topology discovery\n' % args.warmup)
        time.sleep(args.warmup)
        loss = h1.cmd('ping -c 2 -W 1 %s | grep -o "[0-9]*%% packet loss"' % args.server_ip).strip()
        info('*** connectivity check: %s\n' % loss)
        if not loss.startswith('0%'):
            sys.exit('ERROR: h1 cannot reach h2 - is the controller running (port %d)?'
                     % args.controller_port)

        srv = h2.popen(['python3', os.path.join(HERE, 'server.py'), '--stats-out',
                        args.out + '_server.json'], stdout=open(args.out + '_server.log', 'w'),
                       stderr=sys.stderr)
        time.sleep(2.0)                                # let the server finish starting

        info('*** starting %d clients at the same moment\n' % args.clients)
        t0 = time.time()
        t_fail = None
        clients = []
        for i in range(1, args.clients + 1):          # launched back-to-back, no waiting in between
            clients.append(h1.popen(
                ['python3', os.path.join(HERE, 'client.py'), '--client-id', str(i),
                 '--server', args.server_ip, '--rate', str(args.rate),
                 '--duration', str(args.duration), '--out-prefix', '%s_c%d' % (args.out, i)],
                stdout=open('%s_c%d.log' % (args.out, i), 'w'), stderr=sys.stderr))

        if args.fail:
            time.sleep(args.fail_at)
            info('*** [t=%.1fs] link s1-s2 DOWN\n' % (time.time() - t0))
            t_fail = time.time()
            net.configLinkStatus('s1', 's2', 'down')
            time.sleep(args.fail_for)
            info('*** [t=%.1fs] link s1-s2 UP\n' % (time.time() - t0))
            net.configLinkStatus('s1', 's2', 'up')

        for c in clients:                              # wait for ALL clients to finish
            c.wait()
        t_done = time.time()
        srv.send_signal(signal.SIGINT)                 # only now stop the server
        srv.wait(timeout=10)

        stats = json.load(open(args.out + '_server.json'))
        lines = ['T7: %d concurrent clients, %.0f pps each, %.0f s%s' % (
            args.clients, args.rate, args.duration,
            ', link s1-s2 down for %.0f s at t=%.0f s' % (args.fail_for, args.fail_at)
            if args.fail else ', no failure'), '',
            'client | sent | delivered | lost | server unique | server dups | first pkt (s) | last pkt (s)',
            '-------+------+-----------+------+---------------+-------------+---------------+-------------']
        firsts, lasts, ok = [], [], True
        base = min(v['first_t'] for v in stats.values())
        for i in range(1, args.clients + 1):
            c = json.load(open('%s_c%d.json' % (args.out, i)))
            s = next((v for k, v in stats.items() if k.startswith('%d@' % i)), None)
            if s is None:
                lines.append('%6d | %4d | %9d | %4d | (server saw nothing)' % (
                    i, c['sent'], c['delivered'], c['lost']))
                ok = False
                continue
            firsts.append(s['first_t'])
            lasts.append(s['last_t'])
            ok &= (c['delivered'] == c['sent'] and c['lost'] == 0)
            lines.append('%6d | %4d | %9d | %4d | %13d | %11d | %13.1f | %12.1f' % (
                i, c['sent'], c['delivered'], c['lost'], s['unique'], s['dups'],
                s['first_t'] - base, s['last_t'] - base))
        lines.append('')
        if firsts:
            lines.append('concurrency: first packets of all clients within %.1f s of each other; '
                         'last packets within %.1f s' % (max(firsts) - min(firsts),
                                                       max(lasts) - min(lasts)))
        lines.append('RESULT: ' + ('PASS - all clients delivered every packet'
                                   if ok else 'CHECK - some packets were not delivered'))
        # controller timeline of THIS run (from the controller's own event log)
        lines.append('')
        lines.append('controller events during the run (seconds after the clients started):')
        early = False
        try:
            seen = False
            for raw in open(args.controller_log):
                e = json.loads(raw)
                if not (t0 - 1 <= e['t'] <= t_done + 0.5):
                    continue
                if e['event'] not in ('LINK_DOWN', 'LINK_UP', 'PATH_INSTALLED', 'APP_REPORT',
                                      'PATH_SUSPECTED', 'NO_PATH_AVAILABLE'):
                    continue
                seen = True
                what = e.get('link') or e.get('path') or e.get('report') or ''
                lines.append('  %6.1f s  %-16s %-6s %s' % (e['t'] - t0, e['event'], what, e.get('reason', '')))
                if (t_fail and e['event'] == 'PATH_INSTALLED' and e['t'] < t_fail
                        and e.get('reason') == 'application-report'):
                    early = True
            if not seen:
                lines.append('  (no events found in %s)' % args.controller_log)
        except OSError:
            lines.append('  (controller log %s not readable)' % args.controller_log)
        if early:
            lines.append('NOTE: a client report moved traffic to path B BEFORE the link failed; '
                         'repeat the run to test the failure itself.')
        text = '\n'.join(lines)
        print('\n' + text + '\n')
        open('/tmp/t7_summary.txt', 'w').write(text + '\n')
    finally:
        net.stop()


if __name__ == '__main__':
    main()
