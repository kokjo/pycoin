from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging

import database
from database import txn_required
log = logging.getLogger("pycoin.blockchain")

class BlockError(Exception):
    pass
class TxError(Exception):
    pass
class TxInputAlreadySpend(TxError):
    pass
    
MAIN_CHAIN = 1
SIDE_CHAIN = 2
ORPHAN_CHAIN = 3
INVALID_CHAIN = 4

_chains = {MAIN_CHAIN: "Main", SIDE_CHAIN: "Side", ORPHAN_CHAIN: "Orphan", INVALID_CHAIN: "Invalid"}
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
        self.next.append(next_aux.hash)
        
    @property
    def hash(self):
        return self.block.hash
    
    @property
    def prev(self):
        return self.block.prev
    
    def __repr__(self):
        return "<Block %s(%d) - diff: %d - chain: %s>" % (
        h2h(self.hash), self.number, bits_to_diff(self.block.bits), _chains.get(self.chain, "unknown"))       
         
    @constructor
    def make(self, blockmsg):
        self.block, self.txs = blockmsg.block, [tx.hash for tx in blockmsg.txs]
        self.number, self.totaldiff, self.chain, self.next = 0, 0, ORPHAN_CHAIN, []
        
class TxAux(js.Entity, bs.Entity):
    fields = {
        "tx":msgs.Tx,
        "block":js.Hash,
        "redeemed":js.List(js.Hash),
        "blkindex":js.Int
    }
    bfields = [
        ("tx", msgs.Tx),
        ("block", bs.Hash),
        ("redeemed", bs.VarList(bs.Hash)),
        ("blkindex", bs.structfmt("<L")),
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
    
    @property
    def total_amount_spend(self):
        return sum([i.amount for i in self.tx.inputs])   
         
    @constructor
    def make(self, tx):
        self.tx, self.block = tx, nullhash
        self.blkindex = 0
        self.redeemed = [nullhash] * len(tx.outputs)
        
    def get_output(self, outpoint):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        return self.tx.outputs[outpoint.index]
        
    def spend_output(self, outpoint, tx):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        if self.redeemed[outpoint.index] != nullhash:
            raise TxInputAlreadySpend(outpoint)
        self.redeemed[outpoint.index] = tx.hash
        
    def unspend_output(self, outpoint):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        self.redeemed[outpoint.index] = nullhash
        
class BlockChain(object):
    def __init__(self):
        self.chain = database.open_db("chain.dat")
        self.txs = database.open_db("txs.dat")
        self.state = database.open_db("state.dat")
        self.blknums = database.open_db("blknum.dat")
        self.orphans = {}
        if not self.chain.has_key(genesisblock.hash):
            self.add_genesis(genesisblock.blockmsg)

    def get_aux(self, h, txn=None):
        """get a Block Aux in the database"""
        log.debug("getting block %s", h2h(h))
        return BlockAux.frombinary(self.chain.get(h, txn=txn))[0]
    
    @txn_required    
    def put_aux(self, aux, txn=None):
        """get a Block Aux in the database"""
        log.debug("putting block %s", h2h(aux.hash))
        self.chain.put(aux.hash, aux.tobinary(), txn=txn)
        if aux.chain == MAIN_CHAIN:
            self.blknums.put(str(aux.number), aux.hash, txn=txn)
    
    def get_aux_by_num(self, idx, txn=None):
        return self.get_aux(self.blknums.get(str(idx), txn=txn), txn=txn)
            
    @property
    def missing_blocks(self):
        missing = self.orphans.keys()
        return [h for h in missing if not self.has_block(h)]
        
    def has_block(self, h, txn=None):
        if self.chain.has_key(h):
            return True
        if h in map(lambda o: o.hash, sum(self.orphans.values(), [])): # hack: sum([["a", "b"], ["c"]], []) = ["a", "b", "c"]
            return True
        return False            
            
    def has_tx(self, h):
        return h in self.txs 
        
    def get_tx(self, h, txn=None):
        return TxAux.frombinary(self.txs[h])[0]
        
    def put_tx(self, tx, txn=None):
        self.txs[tx.hash] = tx.tobinary()
        
    def get_bestblock(self, txn=None):
        return self.get_aux(self.state.get("bestblock", txn=txn), txn=txn)
        
    def get_target(self, prev_aux, txn=None):        
        targettimespan = 14 * 24 * 60 * 60 # 2 weeks in secounds
        spacing = 10 * 60 # 10 min in secounds
        interval = timespan/spacing
        if (prev_aux.number + 1) % interval != 0:
            return prev_aux.block.bits
        log.info("DIFF: retarget, current bits: %s", hex(prev_aux.block.bits))
        first_aux = prev_aux
        for i in range(interval-1):
            first_aux = self.get_aux(first_aux.prev, txn=txn)
        realtimespan = last_aux.block.time - first_aux.block.time
        log.info("DIFF: timespan before limits: %d", realtimespan)
        if realtimespan < targettimespan/4:
            realtimespan = targettimespan/4
        if realtimespan > targettimespan*4:
            realtimespan = targettimespan*4
        log.info("DIFF: timespan after limits: %d", realtimespan)
        newtarget = (bits_to_target(prev_aux.block.bits)*realtimespan)/targettimespan
        return target_to_bits(newtarget)
        
    @txn_required
    def put_bestblock(self, new, txn=None):
        old = self.get_bestblock(txn=txn)
        if old.totaldiff < new.totaldiff:
            if new.prev != old.hash:
                self.reorg(old, new, txn=txn)
            new.chain = MAIN_CHAIN
            self.put_aux(new, txn=txn)
            self.state.put("bestblock", new.hash, txn=txn)
            if new.number % 2016 == 0:
                self.diff_retarget(aux, txn=txn)
            log.info("new best block %s(%d)", h2h(new.hash), new.number)
        else:
            log.info("%s is not better then the currently best block %s", h2h(new.hash), h2h(old.hash))
            
    def findsplit(self, old, new, txn=None):
        """finds the split between old and new. 
        Returns (spilt, old, new)"""
        log.info("finding spilt for %s(%d) and %s(%d)", h2h(old.hash), old.number, h2h(new.hash), new.number)
        oldlist = []
        newlist = []
        while old.number != new.number:
            if old.number > new.number:
                oldlist.append(old.hash)
                old = self.get_aux(old.prev, txn=txn)
            else:
                newlist.append(new.hash)
                new = self.get_aux(new.prev, txn=txn)
        while old.prev != new.prev:
            oldlist.append(old.hash)
            newlist.append(new.hash)
            old = self.get_aux(old.prev, txn=txn)
            new = self.get_aux(new.prev, txn=txn)
        split = self.get_aux(new.prev, txn=txn)
        log.info("spilt found at %s(%d)", h2h(split.hash), split.number)
        return split.hash, oldlist, newlist
    
    def revert_tx(self, tx, coinbase=False, txn=None):
        tx.block = nullhash
        if coinbase:
            return tx
        for i in tx.tx.inputs:
            input_tx = self.get_tx(i.outpoint.tx, txn=txn)
            input_tx.redeemed[i.outpoint.index] = nullhash
            self.put_tx(input_tx, txn=txn)     
        return tx    
        
    def verify_tx(self, tx, coinbase=False, txn=None):
        pass
            
    def comfirm_tx(self, tx, blk, coinbase=False, txn=None):
        tx.block = blk.hash
        if coinbase:
            return tx        
        for i in tx.tx.inputs:
            input_tx = self.get_tx(i.outpoint.tx, txn=txn)
            if input_tx.redeemed[i.outpoint.index] != nullhash:
                raise TxError("input already spend", tx, input_tx)
            input_tx.redeemed[i.outpoint.index] = tx.hash
            self.put_tx(input_tx, txn=txn)
        return tx
    
    def sum_tx_amount_input(self, tx, txn=None):
        amount = 0
        for inp in t.tx.inputs:
            input_tx = self.get_tx(inp.outpoint.tx, txn=txn)
            amount += input_tx.tx.outputs[inp.outpoint.index].amount
            
    def sum_tx_amount_output(self, tx, txn=None):
        return sum([outp.amount for outp in tx.tx.outputs])
              
    def revert_block(self, aux, txn=None):
        aux.chain = SIDE_CHAIN
        self.state.put("bestblock", aux.prev, txn=txn)
        tx = self.get_tx(aux.txs[0], txn=txn)
        tx = self.revert_tx(tx, True, txn=txn)
        self.put_tx(tx, txn=txn)
        for tx_h in aux.txs[1:]:
            tx = self.get_tx(tx_h, txn=txn)
            tx = self.revert_tx(tx, txn=txn)
            self.put_tx(tx, txn=txn)
        return aux
        
    def chain_block(self, aux, txn=None):
        aux.chain = MAIN_CHAIN
        self.state.put("bestblock", aux.hash, txn=txn)
        tx = self.get_tx(aux.txs[0], txn=txn)
        tx = self.comfirm_tx(tx, aux, True, txn=txn)
        self.put_tx(tx, txn=txn)
        for tx_h in aux.txs[1:]:
            tx = self.get_tx(tx_h, txn=txn)
            tx = self.comfirm_tx(tx, aux, txn=txn)
            self.put_tx(tx, txn=txn)
        return aux
        
    def for_all_blocks(self, l, func, txn=None):
        for h in l:
            aux = self.get_aux(h, txn=txn)
            aux = func(aux, txn=txn)
            self.put_aux(aux, txn=txn)
            
    @txn_required
    def reorg(self, old, new, txn=None):
        """reorginizes the blockchain, so that the new block, is the main block. and all blocks in the old chain is invalidated."""
        log.info("REORG old: %s, new: %s", h2h(old.hash), h2h(new.hash))
        split, oldchain, newchain = self.findsplit(old, new, txn=txn)
        log.info("blocks to revert: %s", ", ".join(map(h2h, oldchain)))
        log.info("blocks to chain: %s", ", ".join(map(h2h, newchain)))
        self.for_all_blocks(oldchain, self.revert_block, txn=txn)
        self.for_all_blocks(newchain[::-1], self.chain_block, txn=txn)
        log.info("REORG done.")
        
    def add_genesis(self, blockmsg):
        """inits the block chain, by putting in the genesis block"""
        aux = BlockAux.make(blockmsg)
        aux.totaldiff = 1
        aux.number = 0
        aux.chain = MAIN_CHAIN
        self.put_aux(aux)
        self.state.put("bestblock", aux.hash)
        
    def verify_block(self, aux):
        return True
    
    def check_orphans(self, aux, txn=None):
        blocks = self.orphans.pop(aux.hash, [])
        while blocks:
            aux = blocks.pop(0)
            self._add_block(aux, False, txn=txn)
            blocks += self.orphans.pop(aux.hash, [])
            
    def add_orphan(self, aux):
        orphans = self.orphans.pop(aux.prev, [])
        if aux.hash not in [o.hash for o in orphans]:
            self.orphans[aux.prev] = orphans + [aux]
        
    def add_tx(self, tx):
        tx = TxAux.make(tx)
        self.put_tx(tx)
        
    @txn_required            
    def add_block(self, blockmsg, txn=None):
        aux = BlockAux.make(blockmsg)
        for tx in blockmsg.txs:
            self.add_tx(tx)
        if self.has_block(aux.hash, txn=txn):
            log.info("already having block %s", h2h(aux.hash))
            return
        self._add_block(aux, txn=txn)
    
        
    def _add_block(self, aux, check_orphans=True, txn=None):
        log.info("chaining %s to chain", h2h(aux.hash))
        if self.chain.has_key(aux.prev, txn=txn):
            aux_prev = self.get_aux(aux.prev, txn=txn)
            aux_prev.chain_block(aux)
            self.put_aux(aux_prev, txn=txn)
            self.put_aux(aux, txn=txn)
            self.put_bestblock(aux, txn=txn)
            if check_orphans:
                self.check_orphans(aux, txn=txn)
        else:
            log.info("%s is missing %s", h2h(aux.hash), h2h(aux.prev))
            self.add_orphan(aux)
            
def test():
    import struct
    import sys
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.INFO)
    blkfile = open(sys.argv[1],"r")
    chain = BlockChain()
    while True:
        try:
            magic, size = struct.unpack("<LL", blkfile.read(8))
        except struct.error:
            break
        blkdata = blkfile.read(size)
        blkmsg = msgs.Blockmsg.frombinary(blkdata)[0]
        chain.add_block(blkmsg)
if __name__ == "__main__":
    test()
