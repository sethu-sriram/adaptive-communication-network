#!/usr/bin/env python3
"""UDP server (runs on h2). One receiver thread + worker pool; serves many clients.

Every DATA datagram is ACKed. The server tracks, per (client_id, address): unique
packets, duplicates (caused by client retransmissions) and the highest sequence number.
"""
import argparse, json, queue, signal, socket, threading, time
import protocol as P


class ClientStats:
    def __init__(self):
        self.seen = set()
        self.received = 0
        self.dups = 0
        self.max_seq = -1
        self.first_t = time.time()
        self.last_t = self.first_t


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bind', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=5005)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--stats-out', help='write per-client stats JSON on exit')
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.5)

    clients, lock, q = {}, threading.Lock(), queue.Queue()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                data, addr = q.get(timeout=0.2)
            except queue.Empty:
                continue
            m = P.unpack(data)
            if m is None:
                continue                      # malformed datagram: ignore (error handling)
            t, attempt, cid, seq, ts, payload = m
            key = (cid, addr[0])
            if t == P.DATA:
                with lock:
                    st = clients.setdefault(key, ClientStats())
                    st.last_t = time.time()
                    st.received += 1
                    if seq in st.seen:
                        st.dups += 1
                    else:
                        st.seen.add(seq)
                        st.max_seq = max(st.max_seq, seq)
                sock.sendto(P.pack(P.ACK, cid, seq, attempt, ts), addr)
            elif t == P.FIN:
                sock.sendto(P.pack(P.FINACK, cid, seq, attempt, ts), addr)
                with lock:
                    st = clients.get(key)
                if st:
                    print(f'[server] client {cid}@{addr[0]} done: unique={len(st.seen)} '
                          f'dups={st.dups} max_seq={st.max_seq}', flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    for th in threads:
        th.start()

    def shutdown(*_):
        stop.set()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f'[server] listening on {args.bind}:{args.port} ({args.workers} workers)', flush=True)
    while not stop.is_set():
        try:
            q.put(sock.recvfrom(2048))
        except socket.timeout:
            continue
        except OSError:
            break

    out = {f'{cid}@{ip}': dict(unique=len(s.seen), received=s.received, dups=s.dups,
                              max_seq=s.max_seq, first_t=s.first_t, last_t=s.last_t)
           for (cid, ip), s in clients.items()}
    print('[server] stats:', json.dumps(out), flush=True)
    if args.stats_out:
        with open(args.stats_out, 'w') as f:
            json.dump(out, f, indent=2)


if __name__ == '__main__':
    main()
