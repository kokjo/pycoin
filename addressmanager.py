import database
import eventlet
import jserialize as js
import bserialize as bs
import msgs

class Tx(js.Entity, bs.Entity):
    fields = {
        "tx":msgs.Tx,
        "block":js.Hash,
        "blkindex":js.Int,
        #"flags":js.Int,
        "redeemed":js.List(js.Hash),
    }
    bfields = [
        ("tx", msgs.Tx),
        ("block", bs.Hash),
        ("blkindex", bs.structfmt("<L")),
        #("flags", bs.VarInt),
        ("redeemed", bs.VarList(bs.Hash)),
    ]
    
addrs = database.open_db("txs.dat", table_name="txs")
addrs.set_get_returns_none(0)

class AddressManager(object):
    def __init__(self, server):
        self.server = server
        self.server.add_handler("addr", self.handle_addr)
        self.server.add_handler("addr", self.handle_addr)
        
        eventlet.spawn_n(self.main_thread)
        
    def handle_addr(self, node, msg):
        
    def main_thread(self):
        while True:
            
