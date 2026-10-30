"""Mininet-free test of the controller's decision logic using stub datapaths.
Run:  python3 tests/test_controller_logic.py     (needs: pip install os-ken)
"""
import os, sys, time, tempfile, types
tmp = tempfile.mkdtemp()
os.environ['P30_LOG'] = os.path.join(tmp, 'ev.jsonl')
os.environ['P30_STATS'] = '0'
os.environ['P30_SOCK'] = os.path.join(tmp, 's.sock')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from os_ken.ofproto import ofproto_v1_3 as ofp, ofproto_v1_3_parser as parser
import controller as C


class DP:
    def __init__(self, i):
        self.id, self.ofproto, self.ofproto_parser, self.sent = i, ofp, parser, []
    def send_msg(self, m): self.sent.append(m)


def link(a, b):
    n = lambda d: types.SimpleNamespace(dpid=d)
    return types.SimpleNamespace(link=types.SimpleNamespace(src=n(a), dst=n(b)))


def flows(dp):
    """{eth_dst: out_port} for non-table-miss ADD flowmods sent to dp."""
    out = {}
    for m in dp.sent:
        if m.command == ofp.OFPFC_ADD and m.priority == 100:
            out[m.match['eth_dst']] = m.instructions[0].actions[0].port
    return out


def fresh(mode='adaptive'):
    os.environ['P30_MODE'] = mode
    c = C.Project30Controller()
    for i in range(1, 5):
        c.switches[i] = DP(i)
    c.reconcile('boot', force=True)
    return c


def reset(c):
    for d in c.switches.values(): d.sent.clear()

# 1. boot -> path A with the right ports
c = fresh()
assert c.active == 'A'
assert flows(c.switches[1]) == {C.H2_MAC: 2, C.H1_MAC: 1}
assert flows(c.switches[2]) == {C.H2_MAC: 2, C.H1_MAC: 1}
assert flows(c.switches[4]) == {C.H2_MAC: 3, C.H1_MAC: 1}
assert flows(c.switches[3]) == {}
print('OK boot installs path A')

# 2. link s1-s2 fails (both directions reported) -> path B, once
reset(c); c.link_delete(link(1, 2)); c.link_delete(link(2, 1))
assert c.active == 'B'
assert flows(c.switches[1]) == {C.H2_MAC: 3, C.H1_MAC: 1}
assert flows(c.switches[3]) == {C.H2_MAC: 2, C.H1_MAC: 1}
assert flows(c.switches[4]) == {C.H2_MAC: 3, C.H1_MAC: 2}
deleted = [m for m in c.switches[2].sent if m.command == ofp.OFPFC_DELETE]
assert len(deleted) == 1 and deleted[0].cookie == C.COOKIE      # only OUR flows removed on s2
assert sum(1 for m in c.switches[1].sent if m.command == ofp.OFPFC_ADD) == 2   # no double install
print('OK link failure -> path B (single install, make-before-break, s2 cleaned)')

# 3. restore -> back to A
reset(c); c.link_add(link(1, 2)); c.link_add(link(2, 1))
assert c.active == 'A'
print('OK link restored -> preferred path A')

# 4. s3-s4 fails while on A -> nothing changes
reset(c); c.link_delete(link(3, 4))
assert c.active == 'A' and not any(m.command == ofp.OFPFC_ADD for d in c.switches.values() for m in d.sent)
c.link_add(link(3, 4))
print('OK failure of unused backup path does not disturb traffic')

# 5. both paths down -> no path, no crash; recovery when one returns
c.link_delete(link(1, 2)); c.link_delete(link(1, 3))
assert c.active == 'B'      # stays on last path; NO_PATH logged
c.link_add(link(1, 3)); c.link_add(link(1, 2))
assert c.active == 'A'
print('OK double failure handled')

# 6. silent failure: application report
c = fresh(); t = c.last_install
c.handle_report(dict(type='PATH_SUSPECT', client=1, since=t - 1))     # stale -> ignored
assert c.active == 'A'
c.handle_report(dict(type='PATH_SUSPECT', client=1, since=t + 1))
assert c.active == 'B' and 'A' in c.suspect
c.handle_report(dict(type='PATH_SUSPECT', client=1, since=c.last_install - 0.5))  # stale again
assert c.active == 'B'
print('OK application report reroutes silent failure; stale reports ignored')

# 6b. malformed 'since' must not crash and must not reroute
c = fresh()
c.handle_report(dict(type='PATH_SUSPECT', client=1, since='not-a-number'))
c.handle_report(dict(type='PATH_SUSPECT', client=1))        # missing -> 0 -> stale
assert c.active == 'A'
print('OK invalid/missing since ignored')
c = fresh(); c.handle_report(dict(type='PATH_SUSPECT', since=time.time() + 1))

# 7. suspect expiry -> revert to A
c.suspect['A'] = time.time() - 1
c.reconcile('expiry'); assert c.active == 'A'
print('OK hold-down expiry reverts to A')

# 8. repeated reports on B while A suspect -> falls back, never None
c = fresh(); c.handle_report(dict(type='PATH_SUSPECT', since=time.time() + 1))
assert c.active == 'B'
c.handle_report(dict(type='PATH_SUSPECT', since=c.last_install + 1))
assert c.active == 'A'          # everything suspect -> trust topology, try A again
c.handle_report(dict(type='PATH_SUSPECT', since=c.last_install + 1))
assert c.active == 'B'          # still failing on A -> rotate again, never stuck on one path
print('OK both paths suspect -> rotate between them on each fresh report')

# 9. static baseline never reacts
c = fresh('static'); reset(c)
c.link_delete(link(1, 2)); c.handle_report(dict(type='PATH_SUSPECT', since=time.time() + 1))
assert c.active == 'A' and not any(d.sent for d in c.switches.values())
print('OK static baseline: no reaction to failures')
print('ALL CONTROLLER LOGIC TESTS PASSED')
os._exit(0)   # os-ken worker threads are non-daemon
