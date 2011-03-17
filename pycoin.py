#!/usr/bin/python3
import status # Importing this does some initialisation

from ipaddr import IPAddress

from utils import *

import network
import msgs
import protocol

try:
    status.state.version
except:
    status.state.version = 0
protocol.add_genesis()

def gethostipaddress():
    import re
    from urllib.request import urlopen
    def site1():
        return IPAddress(urlopen("http://ip.changeip.com").readline()[:-1].decode())
    return site1()

status.genesisblock = bytes(reversed(b'\x00\x00\x00\x00\x00\x19\xd6h\x9c\x08Z\xe1e\x83\x1e\x93O\xf7c\xaeF\xa2\xa6\xc1r\xb3\xf1\xb6\n\x8c\xe2o'))

status.localaddress = msgs.Address.make(IPAddress(gethostipaddress()), 8333)

import bserialize as bs

network.mainloop()
