#!/usr/bin/env python3
"""Project 30 topology.

            +---- s2 ----+              Path A: h1 - s1 - s2 - s4 - h2
    h1 - s1               s4 - h2       Path B: h1 - s1 - s3 - s4 - h2
            +---- s3 ----+

Port numbering (follows link creation order; controller.py depends on it):
    s1: 1=h1 2=s2 3=s3     s2: 1=s1 2=s4     s3: 1=s1 2=s4     s4: 1=s2 2=s3 3=h2

Usage:  sudo python3 topology.py [--controller-port 6653]      (interactive CLI)
Also imported by experiment.py via build_network().
"""
import argparse

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


def build_network(controller_ip='127.0.0.1', controller_port=6653, bw=10, delay='2ms'):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=False)

    info('*** Adding controller\n')
    net.addController('c0', controller=RemoteController, ip=controller_ip, port=controller_port)

    info('*** Adding hosts and switches\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    s1, s2, s3, s4 = [net.addSwitch('s%d' % i, protocols='OpenFlow13') for i in (1, 2, 3, 4)]

    info('*** Creating links (order matters: it defines the port numbers)\n')
    net.addLink(h1, s1)                                  # s1-eth1
    net.addLink(s1, s2, bw=bw, delay=delay)              # s1-eth2 / s2-eth1   path A
    net.addLink(s1, s3, bw=bw, delay=delay)              # s1-eth3 / s3-eth1   path B
    net.addLink(s2, s4, bw=bw, delay=delay)              # s2-eth2 / s4-eth1   path A
    net.addLink(s3, s4, bw=bw, delay=delay)              # s3-eth2 / s4-eth2   path B
    net.addLink(h2, s4)                                  # s4-eth3

    net.start()

    # Static ARP: the controller installs eth_dst flows only (no ARP handling needed).
    h1.cmd('arp -s 10.0.0.2 00:00:00:00:00:02')
    h2.cmd('arp -s 10.0.0.1 00:00:00:00:00:01')
    for h in (h1, h2):
        h.cmd('sysctl -w net.ipv6.conf.all.disable_ipv6=1')
    return net


def create_network(controller_port):
    net = build_network(controller_port=controller_port)
    info('\n=== Project 30 - Adaptive Communication Network ===\n'
         ' Path A: h1-s1-s2-s4-h2   Path B: h1-s1-s3-s4-h2\n'
         ' Try:  h2 python3 server.py &      h1 python3 client.py --duration 30\n'
         '       link s1 s2 down   /   link s1 s2 up\n'
         '       sh ovs-ofctl -O OpenFlow13 dump-flows s1\n\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--controller-port', type=int, default=6653)
    setLogLevel('info')
    create_network(ap.parse_args().controller_port)
