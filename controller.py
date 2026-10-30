"""Project 30 - Adaptive Communication Network with Failure Recovery (OS-Ken, OpenFlow 1.3)

Topology (port numbers follow the link-creation order in topology.py):

            +---- s2 ----+              Path A: h1 - s1 - s2 - s4 - h2   (preferred)
    h1 - s1               s4 - h2       Path B: h1 - s1 - s3 - s4 - h2   (backup)
            +---- s3 ----+

Three ways the controller learns about failures:
  1. LINK EVENTS    : EventLinkDelete / EventLinkAdd from os_ken.topology (needs --observe-links).
                      Detects hard failures (interface down) within milliseconds.
  2. APPLICATION    : the UDP client sends JSON datagrams on a UNIX socket (P30_SOCK) after
                      several consecutive timeouts. Detects SILENT failures (black-holing,
                      100 % loss) that never generate a port-status event.
  3. FLOW STATS     : periodic OFPFlowStatsRequest; counters are logged so the demo can show
                      which path actually carries traffic.

Environment variables
  P30_MODE          adaptive (default) | static   (static = baseline: installs path A and never reacts)
  P30_SOCK          UNIX socket for application reports      (default /tmp/p30_controller.sock)
  P30_LOG           JSON-lines event log for the experiments (default /tmp/p30_events.jsonl)
  P30_SUSPECT_HOLD  seconds a path stays 'suspect' after an application report (default 20)
  P30_REVERT        1 = go back to path A when it recovers (default 1)
  P30_STATS         seconds between flow-stats polls, 0 = off (default 2)
"""
import json
import os
import socket
import threading
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls)
from os_ken.lib import hub
from os_ken.ofproto import ofproto_v1_3
from os_ken.topology import event

COOKIE = 0x30
COOKIE_MASK = 0xFFFFFFFFFFFFFFFF
H1_MAC = '00:00:00:00:00:01'
H2_MAC = '00:00:00:00:00:02'

# {dpid: out_port} per direction. 'fwd' = traffic towards h2, 'rev' = towards h1.
PATHS = {
    'A': dict(links=[frozenset((1, 2)), frozenset((2, 4))],
              fwd={1: 2, 2: 2, 4: 3}, rev={4: 1, 2: 1, 1: 1}),
    'B': dict(links=[frozenset((1, 3)), frozenset((3, 4))],
              fwd={1: 3, 3: 2, 4: 3}, rev={4: 2, 3: 1, 1: 1}),
}
PREFERENCE = ['A', 'B']
NUM_SWITCHES = 4


def _name(link):
    return '-'.join('s%d' % d for d in sorted(link))


class Project30Controller(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Project30Controller, self).__init__(*args, **kwargs)
        self.adaptive = os.environ.get('P30_MODE', 'adaptive').lower() != 'static'
        self.sock_path = os.environ.get('P30_SOCK', '/tmp/p30_controller.sock')
        self.log_path = os.environ.get('P30_LOG', '/tmp/p30_events.jsonl')
        self.hold = float(os.environ.get('P30_SUSPECT_HOLD', '20'))
        self.revert = os.environ.get('P30_REVERT', '1') == '1'
        self.stats_interval = float(os.environ.get('P30_STATS', '2'))

        self.switches = {}          # dpid -> datapath
        self.down_links = set()     # frozenset({dpidA, dpidB}) currently known to be down
        self.suspect = {}           # path name -> time.time() until which it is distrusted
        self.active = None          # 'A' | 'B' | None
        self.last_install = 0.0
        self.last_pkts = {}
        self.lock = threading.RLock()   # os-ken may run handlers in real threads

        open(self.log_path, 'w').close()
        self.log_event('CONTROLLER_START', mode='adaptive' if self.adaptive else 'static')
        hub.spawn(self._hint_server)
        hub.spawn(self._housekeeping)

    # ------------------------------------------------------------------ logging
    def log_event(self, kind, **kw):
        rec = dict(t=time.time(), event=kind, **kw)
        self.logger.info('%-16s %s', kind, ' '.join('%s=%s' % kv for kv in kw.items()))
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(rec) + '\n')
        except OSError:
            pass

    # ------------------------------------------------------------------ switches
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.switches[dp.id] = dp
        self.log_event('SWITCH_UP', switch='s%d' % dp.id)

        # table-miss: unknown packets go to the controller (only logged)
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, priority=0, match=parser.OFPMatch(),
            instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]))

        if len(self.switches) == NUM_SWITCHES:
            self.reconcile('all-switches-connected', force=True)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change(self, ev):
        dp = ev.datapath
        if ev.state == DEAD_DISPATCHER and self.switches.get(dp.id) is dp:
            del self.switches[dp.id]
            self.log_event('SWITCH_DOWN', switch='s%d' % dp.id)

    # ------------------------------------------------------------------ flows
    def _add_flow(self, dp, dst_mac, out_port):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        actions = [parser.OFPActionOutput(out_port)]
        # identical match+priority -> OFPFC_ADD *replaces* the old entry in place (no gap)
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, cookie=COOKIE, priority=100,
            match=parser.OFPMatch(eth_dst=dst_mac),
            instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]))

    def _delete_our_flows(self, dp):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, cookie=COOKIE, cookie_mask=COOKIE_MASK, table_id=ofp.OFPTT_ALL,
            command=ofp.OFPFC_DELETE, out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()))

    def install(self, name, reason):
        """Make-before-break: (re)write flows on the new path (middle switch first, edge
        switches last), then remove our flows from switches only the old path used.
        The table-miss entry (cookie 0) is never touched."""
        t0 = time.time()
        plan, previous = PATHS[name], self.active
        order = sorted(set(plan['fwd']) | set(plan['rev']), key=lambda d: (d in (1, 4), d))
        for dpid in order:
            dp = self.switches[dpid]
            if dpid in plan['fwd']:
                self._add_flow(dp, H2_MAC, plan['fwd'][dpid])
            if dpid in plan['rev']:
                self._add_flow(dp, H1_MAC, plan['rev'][dpid])
        used = set(plan['fwd']) | set(plan['rev'])
        for other, o in PATHS.items():
            for dpid in (set(o['fwd']) | set(o['rev'])) - used:
                if dpid in self.switches:
                    self._delete_our_flows(self.switches[dpid])
        self.active, self.last_install = name, time.time()
        self.log_event('PATH_INSTALLED', path=name, previous=previous, reason=reason,
                   install_ms=round((time.time() - t0) * 1000, 2))

    # ------------------------------------------------------------------ path selection
    def path_ok(self, name, ignore_suspect=False):
        if any(l in self.down_links for l in PATHS[name]['links']):
            return False
        return ignore_suspect or self.suspect.get(name, 0) <= time.time()

    def choose(self, rotate=False):
        if not self.revert and self.active and self.path_ok(self.active):
            return self.active
        for n in PREFERENCE:
            if self.path_ok(n):
                return n
        # Every topologically usable path is currently suspect.
        usable = [n for n in PREFERENCE if self.path_ok(n, ignore_suspect=True)]
        if rotate:
            # A fresh failure report just arrived for the ACTIVE path, so sticking with it
            # (or falling back to "prefer A") is wrong: try the other usable path instead.
            others = [n for n in usable if n != self.active]
            if others:
                return others[0]
        if self.active in usable:
            return self.active
        return usable[0] if usable else None

    def reconcile(self, reason, force=False, rotate=False):
        with self.lock:
            self._reconcile(reason, force, rotate)

    def _reconcile(self, reason, force, rotate=False):
        if len(self.switches) < NUM_SWITCHES:
            return
        if not self.adaptive:                      # static baseline: path A forever
            if self.active is None:
                self.install('A', reason)
            return
        target = self.choose(rotate)
        if target is None:
            self.log_event('NO_PATH_AVAILABLE', reason=reason)
            return
        if target != self.active or force:
            self.install(target, reason)

    # ------------------------------------------------------------------ topology events
    @set_ev_cls(event.EventLinkDelete)
    def link_delete(self, ev):
        link = frozenset((ev.link.src.dpid, ev.link.dst.dpid))
        if link in self.down_links:                # second direction of the same link
            return
        self.down_links.add(link)
        self.log_event('LINK_DOWN', link=_name(link), active=self.active)
        self.reconcile('link-down %s' % _name(link))

    @set_ev_cls(event.EventLinkAdd)
    def link_add(self, ev):
        link = frozenset((ev.link.src.dpid, ev.link.dst.dpid))
        was_down = link in self.down_links
        self.down_links.discard(link)
        # a restored link also clears distrust of the paths that use it
        for n, p in PATHS.items():
            if link in p['links']:
                self.suspect.pop(n, None)
        if was_down:
            self.log_event('LINK_UP', link=_name(link), active=self.active)
            self.reconcile('link-up %s' % _name(link))

    # ------------------------------------------------------------------ application reports
    def _hint_server(self):
        """Receives JSON datagrams from the UDP client (socket <-> SDN integration)."""
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.bind(self.sock_path)
        os.chmod(self.sock_path, 0o666)           # clients run as root inside Mininet
        s.settimeout(1.0)
        self.logger.info('listening for application reports on %s', self.sock_path)
        try:
            while True:
                try:
                    data = s.recv(4096)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode('utf-8'))
                    if not isinstance(msg, dict):
                        raise ValueError('report must be a JSON object')
                    self.handle_report(msg)
                except (ValueError, TypeError, UnicodeDecodeError) as exc:
                    self.logger.warning('malformed application report ignored: %s', exc)
        finally:
            s.close()
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

    def handle_report(self, msg):
        kind = msg.get('type')
        self.log_event('APP_REPORT', report=kind, client=msg.get('client'),
                   timeouts=msg.get('consecutive_timeouts'))
        if kind != 'PATH_SUSPECT' or not self.adaptive or self.active is None:
            return
        # Ignore reports about timeouts of packets sent before our last path change.
        try:
            since = float(msg.get('since', 0))
        except (TypeError, ValueError):
            self.log_event('APP_REPORT_INVALID', reason='missing-or-invalid-since')
            return
        if since <= self.last_install + 0.05:
            self.log_event('APP_REPORT_STALE', path=self.active)
            return
        self.suspect[self.active] = time.time() + self.hold
        self.log_event('PATH_SUSPECTED', path=self.active, hold_s=self.hold)
        self.reconcile('application-report', rotate=True)

    # ------------------------------------------------------------------ housekeeping / stats
    def _housekeeping(self):
        last_poll = 0.0
        while True:
            hub.sleep(0.5)
            now = time.time()
            expired = [n for n, until in self.suspect.items() if until <= now]
            for n in expired:
                del self.suspect[n]
                self.log_event('SUSPECT_EXPIRED', path=n)
            if expired:
                self.reconcile('suspect-expired')
            if self.stats_interval and now - last_poll >= self.stats_interval:
                last_poll = now
                for dp in list(self.switches.values()):
                    p = dp.ofproto_parser
                    dp.send_msg(p.OFPFlowStatsRequest(
                        dp, 0, dp.ofproto.OFPTT_ALL, dp.ofproto.OFPP_ANY, dp.ofproto.OFPG_ANY,
                        COOKIE, COOKIE_MASK, p.OFPMatch()))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply(self, ev):
        dpid = ev.msg.datapath.id
        pkts = sum(s.packet_count for s in ev.msg.body)
        if pkts != self.last_pkts.get(dpid):
            self.logger.info('flow-stats s%d: %d packets matched (active path %s)',
                             dpid, pkts, self.active)
            self.last_pkts[dpid] = pkts
            self.log_event('FLOW_STATS', switch='s%d' % dpid, packets=pkts, active=self.active)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        self.logger.debug('packet-in at s%d', ev.msg.datapath.id)
