from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging

log = logging.getLogger("pycoin.blockchain")


MAIN_CHAIN = 1
SIDE_CHAIN = 2
ORPHAN_CHAIN = 3

class BlockAux(js.Entity, bs.Entity):
    fields = {
        "block": msgs.Block,
        "number": js.Int,
        "totaldiff": js.Int,
        "chain": js.Int,
        "txs": js.List(js.Hash),
        "next": js.List(js.Hash)
    }
    bfields = [
        ("block", msgs.Block),
        ("number", bs.structfmt("<L")),
        ("totaldiff", bs.structfmt("<Q")),
        ("chain", bs.structfmt("<B")),
        ("txs", bs.VarList(bs.Hash)),
        ("next", bs.VarList(bs.Hash))
    ]
    
    def chain_block(self, next_aux):
        assert self.hash == next_aux.prev
        next_aux.number = self.number + 1
        next_aux.totaldiff = self.totaldiff + bits_to_diff(next_aux.block.bits)
        self.next += [next_aux.hash]
        
    @property
    def hash(self):
        return self.block.hash
    @property
    def prev(self):
        return self.block.prev    
    @constructor
    def make(self, blockmsg):
        self.block, self.txs = blockmsg.block, [tx.hash for tx in blockmsg.txs]
        self.number, self.totaldiff, self.chain, self.next = 0, 0, ORPHAN_CHAIN, []
        
class TxAux(js.Entity, bs.Entity):
    fields = {
        "tx":msgs.Tx,
        "block":js.Hash,
        "redeemed":js.List(js.Hash),
    }
    bfields = [
        ("tx", msgs.Tx),
        ("block", bs.Hash),
        ("redeemed", bs.VarList(bs.Hash)),
    ]
    
    @property
    def hash(self):
        return self.tx.hash
    @property
    def confirmed(self):
        return self.block != nullhash
    @property
    def coinbase(self):
        return self.tx.inputs[0].outpoint.tx == nullhash
    @constructor
    def make(self, tx):
        self.tx, self.block = tx, nullhash
        self.redeemed = [nullhash] * len(tx.outputs)
                
def set_chain(block, chain_type, tx_func=None):
    block.chain = chain_type
    if tx_func:
        for tx in block.txs:
            tx_func(tx)

class BlockChain(object):
    def __init__(self):
        self.chain = bsddb.btopen("chain.dat")
        self.txs = bsddb.btopen("txs.dat")
        self.orphans = {}
        if genesisblock.hash not in self.chain:
            self.add_genesis(genesisblock.blockmsg)

    def get_aux(self, h):
        """get a Block Aux in the database"""
        log.debug("getting %s", h2h(h))
        return BlockAux.frombinary(self.chain[h])[0]
    def put_aux(self, aux):
        """get a Block Aux in the database"""
        log.debug("putting %s", h2h(aux.hash))
        self.chain[aux.hash] = aux.tobinary()
        
    @property
    def missing_blocks(self):
        missing = self.orphans.keys()
        return [h for h in missing if not self.has_block(h)]
        
    def has_block(self, h):
        if h in self.chain:
            return True
        if h in map(lambda o: o.hash, sum(self.orphans.values(), [])): # hack: sum([["a", "b"], ["c"]], []) = ["a", "b", "c"]
            return True
        return False            
            
    def has_tx(self, h):
        return h in self.txs 
        
    def get_tx(self, h):
        return TxAux.frombinary(self.txs[h])[0]
        
    def put_tx(self, tx):
        self.txs[tx.hash] = tx.tobinary()
        
    @property
    def bestblock(self):
        """a property that holdes the bestblock. when set, it dicides if the new block is better then the old one. 
        it performs a reorg if the new block's prev is not the old block""" 
        return self.get_aux(self.chain["bestblock"])
        
    @bestblock.setter
    def bestblock(self, new):
        old = self.bestblock
        if old.totaldiff < new.totaldiff:
            if new.prev != old.hash:
                self.reorg(old, new)
            new.chain = MAIN_CHAIN
            self.put_aux(new)
            self.chain["bestblock"] = new.hash
            log.info("new best block %s(%d)", h2h(new.hash), new.number)
            #self.chain.sync()
        else:
            log.info("%s is not better then the currently best block %s", h2h(new.hash), h2h(old.hash))
            
    def findsplit(self, old, new):
        """finds the split between old and new. 
        Returns (spilt, old, new)"""
        log.info("finding spilt for %s(%d) and %s(%d)", h2h(old.hash), old.number, h2h(new.hash), new.number)
        while old.number != new.number:
            if old.number > new.number:
                old = self.get_aux(old.prev)
            else:
                new = self.get_aux(new.prev)
        while old.prev != new.prev:
            old = self.get_aux(old.prev)
            new = self.get_aux(new.prev)
        split = self.get_aux(new.prev)
        log.info("spilt found at %s(%d)", h2h(split.hash), split.number)
        return split, old, new
    
    def for_all_in_chain(self, tail_block, head_block, block_cb):
        """performs func on all nexts in chain(First_block included)"""
        block = head_block
        while block != tail_block:
            block_cb(block)
            self.put_aux(block)
            block = self.get_aux(block.prev)
                
    def reorg(self, old, new):
        """reorginizes the blockchain, so that the new block, is the main block. and all blocks in the old chain is invalidated."""
        #raise RuntimeError("reorg not implemented")
        split, oldhead, newhead = self.findsplit(old, new)
        self.for_all_in_chain(split, oldhead, lambda blk: set_chain(blk, SIDE_CHAIN, None))
        self.for_all_in_chain(split, newhead, lambda blk: set_chain(blk, MAIN_CHAIN, None))
        
    def add_genesis(self, blockmsg):
        """inits the block chain, by putting in the genesis block"""
        aux = BlockAux.make(blockmsg)
        aux.totaldiff = 1
        aux.number = 0
        self.put_aux(aux)
        self.chain["bestblock"] = aux.hash
        
    def verify_block(self, aux):
        return True
    
    def check_orphans(self, aux):
        blocks = self.orphans.pop(aux.hash, [])
        while blocks:
            aux = blocks.pop(0)
            self._add_block(aux, False)
            blocks += self.orphans.pop(aux.hash, [])
            
    def add_orphan(self, aux):
        orphans = self.orphans.pop(aux.prev, [])
        if aux.hash not in [o.hash for o in orphans]:
            self.orphans[aux.prev] = orphans + [aux]
        
    def add_tx(self, tx):
        tx = TxAux.make(tx)
        self.put_tx(tx)
                
    def add_block(self, blockmsg):
        aux = BlockAux.make(blockmsg)
        if self.has_block(aux.hash):
            log.info("already having %s", h2h(aux.hash))
            return
        for tx in blockmsg.txs:
            self.add_tx(tx)
        self._add_block(aux)
        
    def _add_block(self, aux, check_orphans=True):
        log.info("chaining %s to chain", h2h(aux.hash))
        if aux.prev in self.chain:
            aux_prev = self.get_aux(aux.prev)
            aux_prev.chain_block(aux)
            self.put_aux(aux_prev)
            self.put_aux(aux)
            self.bestblock = aux
            if check_orphans:
                self.check_orphans(aux)
        else:
            log.info("%s is missing %s", h2h(aux.hash), h2h(aux.prev))
            self.add_orphan(aux)
            
def test():
    import struct
    import sys
    blkfile = open(sys.argv[1],"r")
    chain = BlockChain()
    while True:
        try:
            magic, size = struct.unpack("<LL", blkfile.read(8))
        except struct.error:
            break
        blkdata = blkfile.read(size)
        blkmsg = msgs.Blockmsg.frombinary(blkdata)[0]
        chain.add(blkmsg)
if __name__ == "__main__":
    test()
