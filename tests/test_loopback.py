"""Mininet-free check of the UDP app: a relay drops ALL packets during an outage window.
Run:  python3 tests/test_loopback.py
"""
import json, os, socket, subprocess, sys, threading, time, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY, SERVER = 15005, 15006


def relay(outage, t0, stop):
    """client <-> relay <-> server; drop everything while outage[0] <= t < outage[1]."""
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); c.bind(('127.0.0.1', PROXY))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('127.0.0.1', 0))
    c.settimeout(0.05); s.settimeout(0.05)
    caddr = None
    while not stop.is_set():
        down = outage and outage[0] <= time.time() - t0 < outage[1]
        for sock, other, to_server in ((c, s, True), (s, c, False)):
            try:
                d, a = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if to_server:
                caddr = a
            if down:
                continue
            if to_server:
                s.sendto(d, ('127.0.0.1', SERVER))
            elif caddr:
                c.sendto(d, caddr)


def run(outage, retries, out=None):
    tmp = tempfile.mkdtemp()
    ctl = os.path.join(tmp, 'ctl.sock')
    hints = []
    ls = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); ls.bind(ctl); ls.settimeout(0.2)
    stop = threading.Event()

    def listen():
        while not stop.is_set():
            try:
                hints.append(json.loads(ls.recv(4096)))
            except socket.timeout:
                pass
    threading.Thread(target=listen, daemon=True).start()

    srv = subprocess.Popen([sys.executable, f'{ROOT}/server.py', '--bind', '127.0.0.1',
                            '--port', str(SERVER)], stdout=subprocess.DEVNULL)
    time.sleep(0.5)
    t0 = time.time()
    threading.Thread(target=relay, args=(outage, t0 + 1.0, stop), daemon=True).start()
    out = out or os.path.join(tmp, 'c')
    subprocess.run([sys.executable, f'{ROOT}/client.py', '--server', '127.0.0.1',
                    '--port', str(PROXY), '--rate', '50', '--duration', '5', '--retries',
                    str(retries), '--ctrl-sock', ctl, '--out-prefix', out],
                   check=True, stdout=subprocess.DEVNULL)
    srv.terminate(); stop.set()
    return json.load(open(out + '.json')), hints


# 1) no failure -> everything delivered first time
s, h = run(None, 5)
assert s['delivery_ratio'] == 1.0 and s['retransmissions'] == 0 and not h, s
print('OK no-failure: ratio=1.0, 0 retransmissions, 0 notifications')

# 2) 0.5 s outage, 5 retries -> app-level recovery masks it completely
s, h = run((0, 0.5), 5)
assert s['delivery_ratio'] == 1.0 and s['retransmissions'] > 0, s
assert s['latency_ms']['max'] > 400, s
print(f"OK 0.5 s outage: ratio=1.0 via {s['retransmissions']} retransmissions, "
      f"max latency {s['latency_ms']['max']:.0f} ms, max ack gap {s['max_ack_gap_ms']:.0f} ms, "
      f"{len(h)} controller message(s): {[x['type'] for x in h]}")
assert any(x['type'] == 'PATH_SUSPECT' for x in h) and any(x['type'] == 'RECOVERED' for x in h)

# 3) 3 s outage, 2 retries -> retries exhausted, packets genuinely lost
s, h = run((0, 3.0), 2)
assert s['lost'] > 0 and s['delivery_ratio'] < 1.0, s
print(f"OK 3 s outage / 2 retries: lost={s['lost']}, ratio={s['delivery_ratio']:.2f}")
print('ALL LOOPBACK TESTS PASSED')
