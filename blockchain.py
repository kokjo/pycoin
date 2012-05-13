from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging

import database
from database import txn_required
from transactions import Tx
MAIN_CHAIN = 1
SIDE_CHAIN = 2
ORPHAN_CHAIN = 3
INVALID_CHAIN = 4


_chains = {MAIN_CHAIN: "Main", SIDE_CHAIN: "Side", ORPHAN_CHAIN: "Orphan", INVALID_CHAIN: "Invalid"}
_diff_cache = {}

class BlockError(Exception):
    pass

    
log = logging.getLogger("pycoin.blockchain")

chain = database.open_db("chain.dat")
chain.set_get_returns_none(0)
state = database.open_db("state.dat")
blknums = database.open_db("blknum.dat")
blknums.set_get_returns_none(0)
orphans = {}

class Block(js.Entity, bs.Entity):
    fields = {
        "block": msgs.Block,
        "number": js.Int,
        "totaldiff": js.Int,
        "chain": js.Int,
        "txs": js.List(js.Hash),
        "nexts": js.List(js.Hash)
    }
    bfields = [
        ("block", msgs.Block),
        ("number", bs.structfmt("<L")),
        ("totaldiff", bs.structfmt("<Q")),
        ("chain", bs.structfmt("<B")),
        ("txs", bs.VarList(bs.Hash)),
        ("nexts", bs.VarList(bs.Hash))
    ]
    
    @property
    def hash(self): return self.block.hash
    @property
    def hexhash(self): return h2h(self.hash)
    @property
    def prev(self): return self.block.prev
    
    @staticmethod
    def iter_blocks(txn=None):
        i = 0
        while True:
            try:
                yield Block.get_by_number(i, txn=txn)
            except KeyError:
                raise StopIteration
            i += 1
            
    @staticmethod
    def get_by_hash(h, txn=None):
        log.debug("getting block %s", h2h(h))
        return Block.frombinary(chain.get(h, txn=txn))[0]
    @staticmethod
    def get_by_number(num, txn=None):
        h = blknums.get(str(num), txn=txn)
        return Block.get_by_hash(h, txn=txn)
        
    @staticmethod
    def exist_by_hash(h, txn=None):
        return chain.has_key(h, txn=txn)
    @staticmethod
    def exist_by_number(num, txn=None):
        return blknums.has_key(str(num), txn=txn)
        
    @txn_required
    def put(self, txn=None):
        if self.chain in (ORPHAN_CHAIN, INVALID_CHAIN):
            log.debug("trying to put an invalid or orphan block in db? (bug?)")
            return False
        log.debug("putting block %s", h2h(self.hash))
        chain.put(self.hash, self.tobinary(), txn=txn)
        if self.chain == MAIN_CHAIN:
            blknums.put(str(self.number), self.hash, txn=txn)
    
    def get_tx(self, idx, txn=None):
        return Tx.get_by_hash(self.txs[idx], txn=txn)
        
    def iter_tx(self, from_idx=None, to_idx=None, reverse=False, txn=None):
        sl = self.txs[from_idx:to_idx]
        if reverse: sl.reverse()
        for tx_h in sl:
            yield Tx.get_by_hash(tx_h, txn=txn)
                
    def get_prev(self, txn=None):
        return Block.get_by_hash(self.prev, txn=txn)
        
    def get_next_bits(self, txn=None):
        try: #try get calculated diff from cache.
            return _diff_cache[self.hash]
        except KeyError: #no, not in cache? calculate it.
            targettimespan = 14 * 24 * 60 * 60 # 2 weeks in secounds
            spacing = 10 * 60 # 10 min in secounds
            interval = targettimespan/spacing
            if (self.number + 1) % interval != 0:
                return self.block.bits
            prev_blk = self.get_prev(txn=txn)
            log.info("DIFF: retarget, current bits: %s", hex(prev_blk.block.bits))
            first_blk = self
            for i in range(interval-1):
                first_blk = first_blk.get_prev(txn=txn)
            realtimespan = self.block.time - first_blk.block.time
            log.info("DIFF: timespan before limits: %d", realtimespan)
            if realtimespan < targettimespan/4:
                realtimespan = targettimespan/4
            if realtimespan > targettimespan*4:
                realtimespan = targettimespan*4
            log.info("DIFF: timespan after limits: %d", realtimespan)
            newtarget = (bits_to_target(self.block.bits)*realtimespan)/targettimespan
            if newtarget > bits_to_target(0x1d00ffff):
                newtarget = bits_to_target(0x1d00ffff)
            bits = target_to_bits(newtarget)
                
            _diff_cache[self.hash] = bits
            log.info("DIFF: next bits: %s", hex(bits))
            return bits
        
    def verify(self, txn=None):
        prev_blk = self.get_prev(txn=txn)
        if self.chain in (ORPHAN_CHAIN, INVALID_CHAIN):
            return False
        if not check_bits(self.block.bits, self.hash):
            return False
        if self.prev != nullhash:
            if prev_blk.get_next_bits(txn=txn) != self.block.bits:
                return False
        #for tx in self.iter_tx(1, txn=txn):
        #    if not tx.verify(self, txn=txn):
        #        return False
        return True
        
    @txn_required    
    def confirm(self, txn=None):
        log.info("confirming block %s(%d)", h2h(self.hash), self.number)
        if not set_bestblock(self, txn=txn):
            log.info("block %s(%d) not good", h2h(self.hash), self.number)
            return False
        if not self.verify(txn=txn):
            raise BlockError()
        self.chain = MAIN_CHAIN
        coinbase_tx = Tx.get_by_hash(self.txs[0], txn=txn)
        coinbase_tx.confirm(block=self, coinbase=True)
        coinbase_tx.put(txn=txn)
        for tx in self.iter_tx(from_idx=1, txn=txn):
            tx.confirm(self, coinbase=False, txn=txn)
            tx.put(txn=txn)

    @txn_required    
    def revert(self, txn=None):
        log.info("reverting block %s(%d)", h2h(self.hash), self.number)
        set_bestblock(self.get_prev(txn=txn), check=False, txn=txn)
        if self.chain != MAIN_CHAIN:
            log.debug("reverting a block, that is not in main chain? (bug?)")
        self.chain = SIDE_CHAIN 
        for tx_h in reversed(self.txs[1:]):
            tx = Tx.get_by_hash(tx_h, txn=txn)
            tx.revert(block=self, coinbase=False, txn=txn)
            tx.put(txn=txn)
        coinbase_tx = Tx.get_by_hash(self.txs[0], txn=txn)
        coinbase_tx.revert(block=self, coinbase=True, txn=txn)    
        coinbase_tx.put(txn=txn)
    
    @txn_required        
    def link(self, txn=None):
        prev = self.get_prev(txn=txn)
        prev.nexts.append(self.hash)
        self.chain = prev.chain
        self.number = prev.number + 1
        self.totaldiff = prev.totaldiff + bits_to_diff(self.block.bits)
        prev.put(txn=txn)
        self.put(txn=txn)
    
    def get_all_fees(self, txn=None):
        fees = 0
        for tx_h in self.txs:
            tx = Tx.get_by_hash(tx_h, txn=txn)
            fees += tx.get_fee(txn=txn)
        return fees
        
    def __repr__(self):
        return "<Block %s(%d) - diff: %d - chain: %s>" % (
        self.hexhash, self.number, bits_to_diff(self.block.bits), _chains.get(self.chain, "unknown(BUG)"))       
         
    @constructor
    def make(self, blockmsg):
        self.block, self.txs = blockmsg.block, [tx.hash for tx in blockmsg.txs]
        self.number, self.totaldiff, self.chain, self.nexts = 0, 0, ORPHAN_CHAIN, []

@txn_required
def add_genesis(blkmsg, txn=None):
    blk = Block.make(blkmsg)
    blk.chain = MAIN_CHAIN
    blk.totaldiff = 1
    blk.number = 0
    blk.put(txn=txn)
    for num, txmsg in enumerate(blkmsg.txs):
        tx = Tx.make(txmsg)
        tx.put(txn=txn)
        tx.block = blk.hash
        tx.blkindex = num
    set_bestblock(blk, check=False, txn=txn)
    
def get_bestblock(txn=None, raw=False):
    h = state.get("bestblock", txn=txn)
    if raw:
        return h
    return Block.get_by_hash(h, txn=txn)
 
@txn_required
def set_bestblock(blk, check=True, txn=None):
    if check:
        best = get_bestblock(txn=txn)
        if blk.totaldiff <= best.totaldiff:
            log.info("%s(%d) is not better then %s(%d)", h2h(blk.hash), blk.number, h2h(best.hash), best.number)
            return False
        if best.hash != blk.prev:
            reorganize(best, blk, txn=txn)
    state.put("bestblock", blk.hash, txn=txn)
    return True

@txn_required
def reorganize(old, new, txn=None):
    log.info("reorginizing blockchain:")
    split, old_blocks, new_blocks = find_split(old, new, txn=txn)
    log.info("REORG: split:%s(%d)", h2h(split.hash), split.number)
    for blk in old_blocks:
        blk.revert(txn=txn)
        blk.put(txn=txn)
    for blk in reversed(new_blocks):
        blk.confirm(txn=txn)
        blk.put(txn=txn)
        
def find_split(old, new, txn=None):
    """finds the split between old and new. Returns (spilt, oldlist, newlist)"""
    log.info("finding spilt for %s(%d) and %s(%d)", h2h(old.hash), old.number, h2h(new.hash), new.number)
    oldlist = []
    newlist = []
    while old.number != new.number:
        if old.number > new.number:
            oldlist.append(old)
            old = old.get_prev(txn=txn)
        else:
            newlist.append(new)
            new = new.get_prev(txn=txn)
    while old.hash != new.hash:
        oldlist.append(old)
        newlist.append(new)
        old = old.get_prev(txn=txn)
        new = new.get_prev(txn=txn)
    split = new # = old
    log.info("spilt found at %s(%d)", h2h(split.hash), split.number)
    return split, oldlist, newlist[1:]

@txn_required
def process_blockmsg(blkmsg, txn=None):
    if Block.exist_by_hash(blkmsg.block.hash, txn=txn):
        log.info("already have block %s", h2h(blkmsg.block.hash))
        return
    blk = Block.make(blkmsg)
    for txmsg in blkmsg.txs:
        if not Tx.exist(txmsg.hash, txn=txn):
            tx = Tx.make(txmsg)
            tx.put(txn=txn)
    if Block.exist_by_hash(blk.prev):
        blk.link(txn=txn)
        blk.confirm(txn=txn)
        blk.put(txn=txn)
        
if not Block.exist_by_hash(genesisblock.hash):
    add_genesis(genesisblock.blkmsg)
    
import struct
def read_blocks(f):
    while True:
        try:
            magic, size = struct.unpack("<LL", f.read(8))
            blkdata = f.read(size)
            blkmsg = msgs.Blockmsg.frombinary(blkdata)[0]
            yield blkmsg
        except struct.error:
            return

if __name__ == "__main__":
    import sys
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.INFO)
    blkfile = open(sys.argv[1],"r")
    for blkmsg in read_blocks(blkfile):
        process_blockmsg(blkmsg)
