#!/usr/bin/env python3
"""Run ONE experiment inside Mininet (needs root; controller must already be running).

  sudo python3 experiment.py --run adaptive_linkdown_50pps --scenario linkdown --rate 50

Scenarios
  none       no failure (baseline latency / overhead)
  linkdown   hard failure : `link s1 s2 down` at --fail-at, `up` after --fail-for seconds
  blackhole  silent failure: 100 % loss on s1<->s2 (interface stays UP -> no port-status event)
"""
import argparse, os, signal, sys, time

from mininet.log import info, setLogLevel
from topology import build_network

HERE = os.path.dirname(os.path.abspath(__file__))


def set_loss(net, a, b, loss):
    for link in net.linksBetween(net.get(a), net.get(b)):
        for intf in (link.intf1, link.intf2):
            intf.config(bw=10, delay='2ms', loss=loss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, help='name used for output files')
    ap.add_argument('--scenario', choices=['none', 'linkdown', 'blackhole'], default='none')
    ap.add_argument('--rate', type=float, default=50)
    ap.add_argument('--duration', type=float, default=30)
    ap.add_argument('--fail-at', type=float, default=10)
    ap.add_argument('--fail-for', type=float, default=10)
    ap.add_argument('--fail-link', default='s1,s2', help='link to fail, e.g. s1,s2 or s2,s4')
    ap.add_argument('--clients', type=int, default=1, help='concurrent client processes on h1')
    ap.add_argument('--warmup', type=float, default=6, help='wait for LLDP link discovery')
    ap.add_argument('--controller-port', type=int, default=6653)
    ap.add_argument('--results', default=os.path.join(HERE, 'results'))
    args = ap.parse_args()
    os.makedirs(args.results, exist_ok=True)
    prefix = os.path.join(args.results, args.run)
    fail_epoch = restore_epoch = ''

    setLogLevel('info')
    net = build_network(controller_port=args.controller_port)
    try:
        h1, h2 = net.get('h1', 'h2')
        info('*** waiting %.0fs for topology discovery\n' % args.warmup)
        time.sleep(args.warmup)
        loss = h1.cmd('ping -c 2 -W 1 10.0.0.2 | grep -o "[0-9]*% packet loss"').strip()
        info('*** connectivity check: %s\n' % loss)
        if not loss.startswith('0%'):
            sys.exit('ERROR: h1 cannot reach h2 - is the controller running (port %d)?'
                     % args.controller_port)

        srv = h2.popen(['python3', os.path.join(HERE, 'server.py'), '--stats-out',
                        prefix + '_server.json'], stdout=open(prefix + '_server.log', 'w'),
                       stderr=sys.stderr)
        time.sleep(0.5)

        t0 = time.time()
        clients = []
        for i in range(args.clients):
            suffix = '_client' if args.clients == 1 else '_client%d' % (i + 1)
            clients.append(h1.popen(
                ['python3', os.path.join(HERE, 'client.py'), '--client-id', str(i + 1),
                 '--rate', str(args.rate), '--duration', str(args.duration),
                 '--out-prefix', prefix + suffix], stdout=open(prefix + suffix + '.log', 'w'),
                stderr=sys.stderr))

        a, b = args.fail_link.split(',')
        if args.scenario != 'none':
            time.sleep(args.fail_at)
            info('*** [t=%.1fs] FAILURE (%s on %s-%s)\n' % (time.time() - t0, args.scenario, a, b))
            fail_epoch = time.time()
            if args.scenario == 'linkdown':
                net.configLinkStatus(a, b, 'down')
            else:
                set_loss(net, a, b, 100)
            time.sleep(args.fail_for)
            info('*** [t=%.1fs] RESTORE\n' % (time.time() - t0))
            restore_epoch = time.time()
            if args.scenario == 'linkdown':
                net.configLinkStatus(a, b, 'up')
            else:
                set_loss(net, a, b, 0)

        for c in clients:
            c.wait()
        srv.send_signal(signal.SIGINT)
        srv.wait(timeout=5)
        with open(prefix + '_meta.txt', 'w') as f:
            f.write('scenario=%s fail_at=%s fail_for=%s link=%s,%s fail_epoch=%s restore_epoch=%s\n' % (
                args.scenario, args.fail_at, args.fail_for, a, b, fail_epoch, restore_epoch))
        info('*** done: %s\n' % prefix)
    finally:
        net.stop()


if __name__ == '__main__':
    main()
