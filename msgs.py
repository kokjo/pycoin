"""Contains the objects representing each message in the protocol
Serialization is provided by the jserialize (for json) and bserialize (for the
wire protocol) modules"""

import struct
import time
import random
import binhex

import jserialize as js
import bserialize as bs

from utils import *
MAGIC_MAINNET = 0xd9b4bef9

TYPE_TX = 1
TYPE_BLOCK = 2
    
class Header():
    def __init__(self, data, magic=MAGIC_MAINNET):
        self.magic, self.cmd, self.len, self.cksum = struct.unpack("<L12sL4s", data)
        if self.magic != magic:
            raise ProtocolViolation("wrong magic") # Client shutdown
        self.cmd = self.cmd.strip("\x00")
        try:
            self.type = msgtable[self.cmd]
        except KeyError:
            if self.cmd == "alert":
                return
            print "??",self.cmd
            raise ProtocolViolation # Unrecognized message type
            
    def deserialize(self, data):
        if self.cksum != checksum(data):
            raise ProtocolViolation
        if self.cmd == "alert":
            return None
        return self.type.frombinary(data)[0]
        
    @staticmethod
    def serialize(msg, magic=MAGIC_MAINNET):
        data = msg.tobinary()
        return struct.pack("<L12sL4s", magic, msg.type.encode('ascii'), len(data), checksum(data)[:4]) + data

class Address(js.Entity, bs.Entity):
    fields = {
        "services":js.Int,
        "ip":js.IPv4,
        "port":js.Int
    }
    bfields = [
        ("services", bs.structfmt("<Q")),
        ("ip", bs.IPv4Inv6),
        ("port", bs.structfmt("!H")),
    ]
    
    def __eq__(self, other):
        if isinstance(other, Address):
            return self.ip == other.ip and self.port == other.port
        return False
            
    def __hash__(self):
        return hash(self.ip) ^ hash(self.port)
        
    @constructor
    def make(self, ip, port):
        self.services = 1 # Always 1 in current protocol
        self.ip = ip
        self.port = port

class AddressTimestamp(js.Entity, bs.Entity):
    fields = {
        "timestamp":js.Int,
        "services":js.Int,
        "ip":js.IPv4,
        "port":js.Int
    }
    bfields = [
        ("timestamp", bs.structfmt("<I")),
        ("services", bs.structfmt("<Q")),
        ("ip", bs.IPv4Inv6),
        ("port", bs.structfmt("!H")),
    ]
    
    def __eq__(self, other):
        if isinstance(other, Address):
            return self.ip == other.ip and self.port == other.port
        return False
            
    def __hash__(self):
        return hash(self.ip) ^ hash(self.port)
        
    @constructor
    def make(self, ip, port):
        self.services = 1 # Always 1 in current protocol
        self.ip = ip
        self.port = port

class Version(js.Entity, bs.Entity):
    type = "version"
    fields = {
        "type":js.Str,
        "version":js.Int,
        "services":js.Int,
        "time":js.Int,
        "reciever":Address,
        "sender":Address,
        "nonce":js.Int,
        "useragent":js.Str,
        "finalblock":js.Int,
        #"realy":js.Bool
    }
    bfields = [
        ("version", bs.structfmt("<I")),
        ("services", bs.structfmt("<Q")),
        ("time", bs.structfmt("<Q")),
        ("reciever", Address),
        ("sender", Address),
        ("nonce", bs.structfmt("<Q")),
        ("useragent", bs.VarBytes),
        ("finalblock", bs.structfmt("<I")),
        #("relay", bs.structfmt("<?"))
    ]
    @constructor
    def make(self, version=60000, sender=Address.make("0.0.0.0",0), reciever=Address.make("0.0.0.0",0), useragent="/pycoin:0.0.1/"):
        self.version = version
        self.services = 0
        self.time = int(time.time())
        self.sender = sender
        self.reciever = reciever
        self.nonce = 1234134124
        self.useragent = useragent
        self.finalblock = 1
        #self.relay = True
        
class Verack(js.Entity, bs.Entity):
    type = "verack"
    fields = {
        "type":js.Str
    }
    bfields = []
    @constructor
    def make(self):
        pass

class Getblocks(js.Entity, bs.Entity):
    type = "getblocks"
    fields = {
        "type":js.Str,
        "version":js.Int,
        "starts":js.List(js.Hash),
        "end":js.Hash,
    }
    bfields = [
        ("version", bs.structfmt("<I")),
        ("starts", bs.VarList(bs.Hash)),
        ("end", bs.Hash),
    ]
        
    @constructor
    def make(self, starts, end=b"\x00"*32):
        self.version = 31900
        self.starts = starts
        self.end = end

class Addr(js.Entity, bs.Entity):
    type = "addr"
    fields = {
        "type":js.Str,
        "addrs":js.List(AddressTimestamp),
    }
    bfields = [
        ("addrs", bs.VarList(AddressTimestamp)),
    ]

class Getaddr(js.Entity, bs.Entity):
    type = "getaddr"
    fields = {
        "type":js.Str
    }
    bfields = []
    @constructor
    def make(self):
        pass

class InvVect(js.Entity, bs.Entity):
    fields = {
        "objtype":js.Int,
        "hash":js.Hash,
    }
    bfields = [
        ("objtype", bs.structfmt("<I")),
        ("hash", bs.Hash),
    ]
    def __eq__(self, other):
        if self.__class__ == other.__class__:
            return self.hash == other.hash and self.objtype == other.objtype
        return NotImplemented
    def __hash__(self):
        return hash(self.hash)
    @constructor
    def make(self, objtype, hash):
        self.objtype, self.hash = objtype, hash

class Inv(js.Entity, bs.Entity):
    type = "inv"
    fields = {
        "type":js.Str,
        "objs":js.List(InvVect),
    }
    bfields = [
        ("objs", bs.VarList(InvVect))
    ]
    @constructor
    def make(self, objs):
        self.objs = objs

class Getdata(js.Entity, bs.Entity):
    type = "getdata"
    # Content-wise identical to "inv"
    fields = {
        "type":js.Str,
        "objs":js.List(InvVect),
    }
    bfields = [
        ("objs", bs.VarList(InvVect))
    ]
    @constructor
    def make(self, objs):
        self.objs = objs

class TxPoint(js.Entity, bs.Entity):
    fields = {
        "tx":js.Hash,
        "index":js.Int,
    }
    bfields = [
        ("tx", bs.Hash),
        ("index", bs.structfmt("<I")),
    ]
    @constructor
    def make(self, tx, index):
        self.tx = tx
        self.index = index

class TxInput(js.Entity, bs.Entity):
    fields = {
        "outpoint":TxPoint,
        "script":js.Bytes,
        "sequence":js.Int,
    }
    bfields = [
        ("outpoint", TxPoint),
        ("script", bs.VarBytes),
        ("sequence", bs.structfmt("<I")),
    ]
    def __repr__(self):
        return "<TxIn outpoint: %s:%d>" % (h2h(self.outpoint.tx), self.outpoint.index)

class TxOutput(js.Entity, bs.Entity):
    fields = {
        "amount":js.Int,
        "script":js.Bytes,
    }
    bfields = [
        ("amount", bs.structfmt("<Q")),
        ("script", bs.VarBytes),
    ]
    def __repr__(self):
        return "<TxOut amount: %d>" % (self.amount)

class Tx(js.Entity, bs.Entity):
    type = "tx"
    fields = {
        "version":js.Int,
        "inputs":js.List(TxInput),
        "outputs":js.List(TxOutput),
        "locktime":js.Int,
    }
    bfields = [
        ("version", bs.structfmt("<I")),
        ("inputs", bs.VarList(TxInput)),
        ("outputs", bs.VarList(TxOutput)),
        ("locktime", bs.structfmt("<I")),
    ]
    @cachedproperty
    def hash(self):
        return doublesha(self.tobinary())
    @property
    def coinbase(self): 
        return len(self.inputs) == 1 and self.inputs[0].outpoint.tx == nullhash and self.inputs[0].outpoint.index == 0xffffffff
    def __repr__(self):
        return "<Tx %s, %d inputs, %d outputs, coinbase: %s>" % (h2h(self.hash), len(self.inputs), len(self.outputs), str(self.coinbase))
    

class Block(js.Entity, bs.Entity):
    fields = {
        "version":js.Int,
        "prev":js.Hash,
        "merkle":js.Hash,
        "time":js.Int,
        "bits":js.Int,
        "nonce":js.Int,
    }
    bfields = [
        ("version", bs.structfmt("<I")),
        ("prev", bs.Hash),
        ("merkle", bs.Hash),
        ("time", bs.structfmt("<I")),
        ("bits", bs.structfmt("<I")),
        ("nonce", bs.structfmt("<I")),
    ]
    
    @cachedproperty
    def hash(self):
        return doublesha(self.tobinary())
        
class merkelproof(js.Entity, bs.Entity):
    bfields = [
        ("pairs", bs.VarList(bs.structfmt("<32s32s"))),
        ("leaf", bs.Hash),
        ("block", bs.Hash),
    ]
    @constructor
    def make(self, block, tx):
        self.block = block.hash
        self.leaf = tx.hash
        self.pairs = utils.get_merkel_tree(block.txs, tx.hash)
        
    @cachedproperty
    def merkelroot(self):
        return doublesha("".join(self.pairs[-1]))
        
    @cachedproperty
    def valid(self, n):
        leaf = self.leaf
        for pair in pairs:
            if leaf not in pair:
                return False
            leaf = doublesha("".join(pair))
        return True
        
class Blockmsg(js.Entity, bs.Entity):
    type = "block"
    fields = {
        "type":js.Str,
        "block":Block,
        "txs":js.List(Tx)
    }
    bfields = [
        ("block", Block),
        ("txs", bs.VarList(Tx)),
    ]

msgtable = {
    'version':Version,
    'verack':Verack,
    'getblocks':Getblocks,
    'getaddr':Getaddr,
    'addr':Addr,
    'inv':Inv,
    'getdata':Getdata,
    'block':Blockmsg,
    'tx':Tx,
}
