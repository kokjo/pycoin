from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
class BlockAux(js.Entity, bs.Entity):
    fields = {
        "block":msgs.Block,
        "txs":js.List(js.Hash),
        "number":js.Int,
        "totaldiff":js.Int,
        "succ": js.Hash,
    }
    bfields = [
        ("block", msgs.Block),
        ("txs", bs.VarList(bs.Hash)),
        ("number", bs.structfmt("<Q")),
        ("totaldiff", bs.structfmt("<Q")),
        ("succ", bs.Hash),
    ]
    @property
    def hash(self):
        return self.block.hash
    @constructor
    def make(self, blockmsg):
        self.block, self.txs, self.number = blockmsg.block, [tx.hash for tx in blockmsg.txs], 2**64-1
        self.totaldiff = 0
        self.succ = nullhash

class BlockList(js.Entity, bs.Entity):
    fields = {
        "blocks":js.List(js.Hash),
    }
    bfields = [
        ("blocks", bs.VarList(bs.Hash)),
    ]
class BlockChain:
    def __init__(self, db, server, txdb):
        self._db
        self.server = server
        self.txdb = txdb
        try:
            self.mainchain = self._db["mainchain"]
        except:
            self.add(genesisblock.blockmsg)
    def put_aux(aux):
        self._db[aux.hash] = aux.tobinary()
            
    def add(self, blockmsg):
        if blockmsg.block.hash in self._db:
            return
        aux = BlockAux.make(blockmsg)
        if blockmsg.block.prev == nullhash:
            aux.number = 1
            aux.totaldiff = bits_to_diff(aux.block.bits)
            self.put_aux(aux)
        
        
