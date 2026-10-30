#!/usr/bin/env python3
"""UDP client (runs on h1).

Sends numbered DATA datagrams at a fixed rate and implements application-level recovery:
  * every datagram must be ACKed; un-ACKed datagrams are retransmitted after an RTO
    (exponential backoff) up to --retries times, then declared lost;
  * after --suspect-after consecutive timeouts the client tells the SDN controller
    (UNIX datagram socket, because hosts live in separate network namespaces) that the
    current path looks dead -> this lets the controller recover from *silent* failures
    (black-holing / gray failures) that OpenFlow port-status events cannot see;
  * when ACKs resume it reports RECOVERED.
Outputs a per-packet CSV and a summary JSON used by analyze.py.
"""
import argparse, csv, json, math, select, socket, time
import protocol as P


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = min(len(sorted_vals) - 1, max(0, math.ceil(p / 100 * len(sorted_vals)) - 1))
    return sorted_vals[k]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server', default='10.0.0.2')
    ap.add_argument('--port', type=int, default=5005)
    ap.add_argument('--client-id', type=int, default=1)
    ap.add_argument('--rate', type=float, default=50, help='packets per second')
    ap.add_argument('--duration', type=float, default=30, help='seconds of sending')
    ap.add_argument('--size', type=int, default=64, help='payload bytes')
    ap.add_argument('--rto', type=float, default=0.1, help='initial retransmission timeout (s)')
    ap.add_argument('--backoff', type=float, default=1.5)
    ap.add_argument('--retries', type=int, default=5)
    ap.add_argument('--suspect-after', type=int, default=3,
                    help='consecutive timeouts before notifying the controller')
    ap.add_argument('--suspect-silence', type=float, default=0.25,
                    help='...and no ACK at all for this many seconds (filters short stalls)')
    ap.add_argument('--report-every', type=float, default=1.0)
    ap.add_argument('--ctrl-sock', default='/tmp/p30_controller.sock')
    ap.add_argument('--no-notify', action='store_true', help='never contact the controller')
    ap.add_argument('--out-prefix', default='results/client', help='writes <prefix>.csv/.json')
    args = ap.parse_args()

    dest = (args.server, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    csock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notifications = []

    def notify(kind, **extra):
        msg = dict(type=kind, client=args.client_id, t=time.time(), **extra)
        notifications.append(msg)
        if args.no_notify:
            return
        try:
            csock.sendto(json.dumps(msg).encode(), args.ctrl_sock)
        except OSError:
            pass          # controller not listening (e.g. static baseline) - not fatal

    total = int(args.duration * args.rate)
    interval = 1.0 / args.rate
    payload = b'x' * args.size
    cid = args.client_id

    pending, rec = {}, {}
    sent = lost = retrans = consec = 0
    last_to_w = 0.0
    reported = False
    last_report_m = -1e9
    max_gap = 0.0
    t0m, t0w = time.monotonic(), time.time()
    last_ack_m = t0m

    def send(seq, attempt):
        ts = time.time_ns()
        sock.sendto(P.pack(P.DATA, cid, seq, attempt, ts, payload), dest)
        return ts / 1e9

    def drain():
        nonlocal consec, last_ack_m, max_gap, reported
        while select.select([sock], [], [], 0)[0]:
            try:
                data, _ = sock.recvfrom(2048)
            except BlockingIOError:
                return
            m = P.unpack(data)
            if m is None or m[0] != P.ACK or m[2] != cid or m[3] not in pending:
                continue                      # malformed / duplicate / late ACK
            _, attempt, _, seq, ts, _ = m
            now_m, now_w = time.monotonic(), time.time()
            r = rec[seq]
            r['ack_w'] = now_w
            r['acked_attempt'] = attempt
            r['latency_ms'] = (now_w - r['first_w']) * 1000
            r['rtt_ms'] = (time.time_ns() - ts) / 1e6
            del pending[seq]
            max_gap = max(max_gap, now_m - last_ack_m)
            last_ack_m = now_m
            consec = 0
            if reported:
                notify('RECOVERED')
                reported = False

    while True:
        now = time.monotonic()
        while sent < total and now >= t0m + sent * interval:
            w = send(sent, 0)
            pending[sent] = dict(attempt=0, deadline=now + args.rto, last_w=w)
            rec[sent] = dict(seq=sent, first_w=w, attempts=1, ack_w=None,
                             acked_attempt=None, latency_ms=None, rtt_ms=None)
            sent += 1

        for seq, p in list(pending.items()):
            if now >= p['deadline']:
                consec += 1
                last_to_w = p['last_w']
                if p['attempt'] >= args.retries:
                    del pending[seq]
                    lost += 1
                else:
                    p['attempt'] += 1
                    retrans += 1
                    rec[seq]['attempts'] += 1
                    p['last_w'] = send(seq, p['attempt'])
                    p['deadline'] = now + args.rto * (args.backoff ** p['attempt'])

        if (consec >= args.suspect_after and now - last_ack_m >= args.suspect_silence
                and now - last_report_m >= args.report_every):
            # 'since' = send time of the newest attempt that timed out: lets the controller
            # ignore reports about failures that predate its last path change.
            notify('PATH_SUSPECT', consecutive_timeouts=consec, since=last_to_w)
            last_report_m, reported = now, True

        if sent >= total and not pending:
            break
        nxt = [t0m + sent * interval] if sent < total else []
        nxt += [p['deadline'] for p in pending.values()]
        wait = max(0.0, min(min(nxt) - time.monotonic(), 0.02)) if nxt else 0.02
        select.select([sock], [], [], wait)
        drain()

    # polite session end
    for _ in range(3):
        sock.sendto(P.pack(P.FIN, cid, 0, 0, time.time_ns()), dest)
        if select.select([sock], [], [], 0.3)[0]:
            break

    # ---- results -------------------------------------------------------------------
    rows = [rec[s] for s in sorted(rec)]
    with open(args.out_prefix + '.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seq', 'send_t', 'ack_t', 'attempts', 'acked_attempt', 'latency_ms', 'rtt_ms'])
        for r in rows:
            w.writerow([r['seq'], round(r['first_w'] - t0w, 4),
                        '' if r['ack_w'] is None else round(r['ack_w'] - t0w, 4),
                        r['attempts'],
                        '' if r['acked_attempt'] is None else r['acked_attempt'],
                        '' if r['latency_ms'] is None else round(r['latency_ms'], 3),
                        '' if r['rtt_ms'] is None else round(r['rtt_ms'], 3)])

    delivered = [r for r in rows if r['ack_w'] is not None]
    lat = sorted(r['latency_ms'] for r in delivered)
    rtt = sorted(r['rtt_ms'] for r in delivered)
    elapsed = (max((r['ack_w'] for r in delivered), default=t0w) - t0w) or 1.0
    summary = dict(
        client_id=cid, start_epoch=t0w, rate_pps=args.rate, duration_s=args.duration, sent=total,
        delivered=len(delivered), lost=lost,
        delivery_ratio=len(delivered) / total if total else None,
        first_attempt_failures=sum(1 for r in rows if r['acked_attempt'] != 0),
        retransmissions=retrans,
        latency_ms=dict(mean=sum(lat) / len(lat) if lat else None, p50=pct(lat, 50),
                        p95=pct(lat, 95), p99=pct(lat, 99), max=lat[-1] if lat else None),
        rtt_ms=dict(mean=sum(rtt) / len(rtt) if rtt else None, p50=pct(rtt, 50),
                    p95=pct(rtt, 95)),
        max_ack_gap_ms=max_gap * 1000, nominal_interval_ms=interval * 1000,
        goodput_pps=len(delivered) / elapsed,
        controller_notifications=len(notifications),
        params=dict(rto=args.rto, retries=args.retries, backoff=args.backoff,
                    suspect_after=args.suspect_after, suspect_silence=args.suspect_silence, no_notify=args.no_notify))
    with open(args.out_prefix + '.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
