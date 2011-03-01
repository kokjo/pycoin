"""Module to contain loads of misc globals"""

import os
import random

import msgs

import ipaddr

from ipaddr import IPAddress

datadir = os.path.join(os.environ["HOME"],".pycoin")
if not os.path.exists(datadir):
    os.makedirs(datadir)

protocolversion = 31900
services = 1
nonce = random.randrange(2**64)
currentblock = 0
