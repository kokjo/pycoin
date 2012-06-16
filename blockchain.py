import eventlet
from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging
#import debug

import database
from database import txn_required, TxnAbort
import transactions

try:
    import psyco
    psyco.full()
except ImportError:
    print 'Psyco not installed, the program will just run slower'


MAIN_CHAIN = 1
SIDE_CHAIN = 2
ORPHAN_CHAIN = 3
INVALID_CHAIN = 4


_chains = {MAIN_CHAIN: "Main", SIDE_CHAIN: "Side", ORPHAN_CHAIN: "Orphan", INVALID_CHAIN: "Invalid"}


class BlockError(Exception):
    pass

class InvalidBlock(BlockError):
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
    
    @staticmethod
    def get_or_make(blkmsg, txn=None):
        if not Block.exist_by_hash(blkmsg.hash, txn=txn):
            blk = Block.make(blkmsg)
            for txmsg in blkmsg.txs:
                tx = transactions.Tx.get_or_make(txmsg, txn=txn)
                if tx: tx.put(txn=txn)
            blk.link(txn=txn)
            blk.put(txn=txn)
        else:
            blk = Block.get_by_hash(blkmsg.hash, txn=txn)
        return blk
            
    @txn_required
    def put(self, txn=None):
        if self.chain == ORPHAN_CHAIN:
            log.debug("trying to put orphan block in db? (bug?)")
            return False
        log.debug("putting block %s", h2h(self.hash))
        chain.put(self.hash, self.tobinary(), txn=txn)
        if self.chain == MAIN_CHAIN:
            blknums.put(str(self.number), self.hash, txn=txn)
    
    def get_tx(self, idx, txn=None):
        return transactions.Tx.get_by_hash(self.txs[idx], txn=txn)
        
    def iter_tx(self, from_idx=None, to_idx=None, reverse=False, enum=False, txn=None):
        sl = list(enumerate(self.txs[from_idx:to_idx], start=from_idx))
        if reverse: sl.reverse()
        for blkidx, tx_h in sl:
            if enum:
                yield (blkid, transactions.Tx.get_by_hash(tx_h, txn=txn))
            else:
                yield transactions.Tx.get_by_hash(tx_h, txn=txn)
                
    def get_prev(self, txn=None):
        return Block.get_by_hash(self.prev, txn=txn)
        
    def get_next_bits(self, txn=None):
        targettimespan = 14 * 24 * 60 * 60 # 2 weeks in secounds
        spacing = 10 * 60 # 10 min in secounds
        interval = targettimespan/spacing
        if (self.number + 1) % interval != 0:
            return self.block.bits
        log.info("DIFF: retarget, current bits: %s", hex(self.block.bits))
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
        newtarget = bits_to_target(self.block.bits)
        newtarget *= realtimespan
        newtarget /= targettimespan
        if newtarget > bits_to_target(0x1d00ffff):
            newtarget = bits_to_target(0x1d00ffff)
        bits = target_to_bits(newtarget)
            
        log.info("DIFF: next bits: %s", hex(bits))
        return bits
        
    def verify(self, txn=None):
        if self.chain == INVALID_CHAIN:
            return False
        if not check_bits(self.block.bits, self.hash):
            return False
        prev_blk = self.get_prev(txn=txn)
        if prev_blk.chain == INVALID_CHAIN:
            return False
        if prev_blk.get_next_bits(txn=txn) != self.block.bits:
            return False
        return True
        
    @txn_required    
    def confirm(self, txn=None):
        log.info("confirming block %s(%d)", h2h(self.hash), self.number)
        if not self.verify(txn=txn):
            raise Invalidblock()
        if not set_bestblock(self, txn=txn):
            log.info("block %s(%d) not good", h2h(self.hash), self.number)
            return False
        self.chain = MAIN_CHAIN
        try:
            coinbase_tx = self.get_tx(0, txn=txn)
            coinbase_tx.confirm(block=self, blkidx=0, coinbase=True, txn=txn)
            coinbase_tx.put(txn=txn)
            for blkidx, tx in self.iter_tx(from_idx=1, enum=True, txn=txn):
                tx.confirm(self, coinbase=False, blkidx=blkidx, txn=txn)
                tx.put(txn=txn)
        except TxError:
            raise InvalidBlock()

    @txn_required    
    def revert(self, txn=None):
        log.info("reverting block %s(%d)", h2h(self.hash), self.number)
        set_bestblock(self.get_prev(txn=txn), check=False, txn=txn)
        if self.chain != MAIN_CHAIN:
            log.debug("reverting a block, that is not in main chain? (bug?)")
        self.chain = SIDE_CHAIN 
        for tx in self.iter_tx(from_idx=1, reverse=True, txn=txn):
            tx.revert(block=self, coinbase=False, txn=txn)
            tx.put(txn=txn)
        coinbase_tx = self.get_tx(0, txn=txn)
        coinbase_tx.revert(block=self, coinbase=True, txn=txn)    
        coinbase_tx.put(txn=txn)
    
    @txn_required
    def invalidate(self, txn=None):
        self.chain = CHAIN_INVALID
        blocks_to_invalidate = set(self.nexts)
        while blocks_to_invalidate:
            blk_h = blocks_to_invalidate.pop()
            blk = Block.get_by_hash(blk_h, txn=txn)
            blk.chain = CHAIN_INVALID
            blk.put(txn=txn)
            blocks_to_invalidate.update(blk.nexts)
        self.put(txn=txn)
        
    @txn_required        
    def link(self, txn=None):
        prev = self.get_prev(txn=txn)
        prev.nexts.append(self.hash)
        if prev.chain == MAIN_CHAIN:
            self.chain = SIDE_CHAIN
        else:
            self.chain = prev.chain
        if not self.verify(txn=txn):
            self.chain = CHAIN_INVALID
        self.number = prev.number + 1
        self.totaldiff = prev.totaldiff + bits_to_diff(self.block.bits)
        prev.put(txn=txn)
        self.put(txn=txn)
    
    def get_all_fees(self, txn=None):
        fees = 0
        for tx_h in self.txs:
            tx = transactions.Tx.get_by_hash(tx_h, txn=txn)
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
        tx = transactions.Tx.make(txmsg)
        tx.block = blk.hash
        tx.blkindex = num
        tx.put(txn=txn)
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
        try:
            blk.confirm(txn=txn)
        except InvalidBlock:
            raise TxnAbort(blk.invalidate)
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
        if not transactions.Tx.exist(txmsg.hash, txn=txn):
            tx = transactions.Tx.make(txmsg)
            tx.put(txn=txn)
    if Block.exist_by_hash(blk.prev):
        blk.link(txn=txn)
        blk.confirm(txn=txn)
        blk.put(txn=txn)
        return True
    else:
        log.info("block(%s) missing prev(%s)", h2h(blk.hash), h2h(blk.prev))
        return False
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
    import time
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.INFO)
    cmd = sys.argv[1]
    if cmd == "loadblocks":
        import debug
        blkfile = open(sys.argv[2],"r")
        pos = state.get("blkfilepos")
        if pos:
            blkfile.seek(int(pos))
        for blkmsg in read_blocks(blkfile):
            process_blockmsg(blkmsg)
            state.put("blkfilepos", str(blkfile.tell()))
            eventlet.sleep(0)
    if cmd == "bestblock":
        blk = get_bestblock()
        print blk
        print time.ctime(blk.block.time)
        print "%d days ago" % ((time.time()-blk.block.time)/60/60/24)
