"""Module to contain loads of misc globals"""

import os
import random
import dbm

import msgs

import ipaddr

from ipaddr import IPAddress

datadir = os.path.join(os.environ["HOME"],".pycoin")
if not os.path.exists(datadir):
    os.makedirs(datadir)

blocks = dbm.open(os.path.join(datadir, "blocks"), 'c')
txs = dbm.open(os.path.join(datadir, "txs"), 'c')
addrs = dbm.open(os.path.join(datadir, "addrs"), 'c')

protocolversion = 31900
services = 1
nonce = random.randrange(2**64)
currentblock = 0
