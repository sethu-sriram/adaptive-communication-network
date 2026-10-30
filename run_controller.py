#!/usr/bin/env python3
"""Launcher replacing the `osken-manager` command (missing in os-ken 4.2.x).

Usage:  python3 run_controller.py [controller.py] [--port 6653]
Env:    P30_MODE=static|adaptive  (see controller.py)
Equivalent to: osken-manager --observe-links --ofp-tcp-listen-port 6653 controller.py
"""
import argparse, logging, os, sys

ap = argparse.ArgumentParser()
ap.add_argument('app', nargs='?', default='controller.py')
ap.add_argument('--port', type=int, default=6653)
a = ap.parse_args()
sys.path.insert(0, os.getcwd())

from os_ken import cfg, flags            # noqa: F401  (registers --observe-links etc.)
from os_ken.base.app_manager import AppManager   # must precede controller (circular import)
from os_ken.controller import controller  # noqa: F401  (registers --ofp-tcp-listen-port)
from os_ken.topology import switches      # noqa: F401  (registers --observe-links)
from os_ken.lib import hub

cfg.CONF(args=['--observe-links', '--ofp-tcp-listen-port', str(a.port)],
         project='os_ken', default_config_files=[])
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')

mgr = AppManager.get_instance()
mgr.load_apps([a.app])
services = mgr.instantiate_apps(**mgr.create_contexts())
print('controller running (port %d, mode=%s) - Ctrl+C to stop'
      % (a.port, os.environ.get('P30_MODE', 'adaptive')), flush=True)
try:
    hub.joinall(services)
except KeyboardInterrupt:
    pass
finally:
    mgr.close()
