"""Module to contain loads of misc globals"""

import os
import random
import dbm
import shelve
import collections

import ipaddr

from ipaddr import IPAddress

import jserialize as js

class PersistantObject(shelve.DbfilenameShelf):
    def __init__(self, *args, **kwargs):
        object.__setattr__(self, "_shelf", shelve.DbfilenameShelf(
                writeback = True, *args, **kwargs))
    def __getattr__(self, name):
        try:
            return self._shelf[name]
        except KeyError:
            raise AttributeError
    def __setattr__(self, name, value):
        self._shelf[name] = value
    def __delattr__(self, name):
        try:
            del self._shelf[name]
        except KeyError:
            raise AttributeError

datadir = os.path.join(os.environ["HOME"],".pycoin")
if not os.path.exists(datadir):
    os.makedirs(datadir)

state = PersistantObject(os.path.join(datadir, "state"))
blocks = dbm.open(os.path.join(datadir, "blocks"), 'c')
txs = dbm.open(os.path.join(datadir, "txs"), 'c')
addrs = dbm.open(os.path.join(datadir, "addrs"), 'c')

protocolversion = 31900
genesisblock = js.Hash.fromjson('000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f')
services = 1
nonce = random.randrange(2**64)
currentblock = 0
