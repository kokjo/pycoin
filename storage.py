"""Code for the disk serialization
    Addresses are stored on disk as jserialized objects
    An in memory copy is stored as _addrdict"""

import os
import json
import random

import jserialize as js
import msgs
import status

def jdump(obj, fp): # "compact" json serialization
    json.dump(obj, fp, separators=(',',':'))

def store(key, data, type):
    permname = os.path.join(status.datadir, key + ".txt")
    tmpname = os.path.join(status.datadir, key + ".txt.tmp")
    with open(tmpname, "w") as tmp:
        jdump(type.tojson(data), tmp)
    os.rename(tmpname, permname)

def load(key, type):
    name = os.path.join(status.datadir, key + ".txt")
    with open(name, "r") as file:
        return type.fromjson(json.load(file))

def storeaddrs(addrs):
    for addr in addrs:
        _addrdict[addr.address.ip] = addr
    store("addr", _addrdict, js.Dict(js.IPv4, msgs.TimedAddress))

_addrdict = load("addr", js.Dict(js.IPv4, msgs.TimedAddress))
