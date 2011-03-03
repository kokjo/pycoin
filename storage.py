import os
import struct
import random

import msgs
import status

def storeaddrs(addrs):
    for addr in addrs:
        status.addrs[addr.address.ip.packed] = addr.tobinary()
