import eventlet
import eventlet.debug
from eventlet.green import socket

TX_CHECK_SCRIPTS = False

NETWORK_DNS_SEEDS = ["dnsseed.bluematt.me", "bitseed.xf2.org", "seed.bitcoin.sipa.be", "dnsseed.bitcoin.dashjr.org"]
NETWORK_NODES = ["127.0.0.1", "192.168.1.11"] + NETWORK_DNS_SEEDS

NETWORK_MAXNODES = 50

NEW_TX_HOOKS = []
NEW_TXMSG_HOOKS = []

BLOCK_CONFIRM_HOOKS = []
BLOCK_REVERT_HOOKS = []

