#!/usr/bin/python3
import status # Importing this does some initialisation

import collections

from ipaddr import IPAddress

from utils import *

import network
import msgs
import protocol

try:
    status.state.version
except:
    status.state.version = 0
    status.state.orphan_dict = collections.defaultdict(list)
    status.state.requestq = collections.deque()
    protocol.add_genesis()

def gethostipaddress():
    import re
    from urllib.request import urlopen
    def site1():
        return IPAddress(urlopen("http://ip.changeip.com").readline()[:-1].decode())
    return site1()

status.localaddress = msgs.Address.make(IPAddress(gethostipaddress()), 8333)

import bserialize as bs

network.mainloop()
