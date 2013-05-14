
import eventlet
from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
#import bsddb
import logging
import settings

import database
from database import txn_required, TxnAbort, Transaction
import transactions

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

chain = database.open_db("chain.dat", dbtype=database.DB.DB_HASH, table_name="blks")
chain.set_get_returns_none(0)
state = database.open_db("chain.dat", dbtype=database.DB.DB_HASH, table_name="state")
blknums = database.open_db("chain.dat", dbtype=database.DB.DB_HASH, table_name="blknum")
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
    def iter_blocks():
        i = 0
        while True:
            try:
                yield Block.get_by_number(i)
            except KeyError:
                raise StopIteration
            i += 1
            
    @staticmethod
    def get_by_hash(h):
        log.debug("getting block %s", h2h(h))
        return Block.frombinary(chain.get(h))[0]
    @staticmethod
    def get_by_number(num):
        h = blknums.get(str(num))
        return Block.get_by_hash(h)
        
    @staticmethod
    def exist_by_hash(h):
        return chain.has_key(h)
    @staticmethod
    def exist_by_number(num):
        return blknums.has_key(str(num))
    
    @staticmethod
    def get_or_make(blkmsg):
        if not Block.exist_by_hash(blkmsg.hash):
            blk = Block.make(blkmsg)
            for txmsg in blkmsg.txs:
                tx = transactions.Tx.get_or_make(txmsg)
                if tx: tx.put()
            blk.link()
            blk.put()
        else:
            blk = Block.get_by_hash(blkmsg.hash)
        return blk
            
    @txn_required
    def put(self):
        if self.chain == ORPHAN_CHAIN:
            log.debug("trying to put orphan block in db? (bug?)")
            return False
        log.debug("putting block %s", h2h(self.hash))
        chain.put(self.hash, self.tobinary())
        if self.chain == MAIN_CHAIN:
            blknums.put(str(self.number), self.hash)
    
    def get_tx(self, idx):
        return transactions.Tx.get_by_hash(self.txs[idx])
        
    def iter_tx(self, from_idx=0, to_idx=None, reverse=False, enum=False):
        sl = list(enumerate(self.txs[from_idx:to_idx], start=from_idx))
        if reverse: sl.reverse()
        if enum:
            for blkidx, tx_h in sl:
                yield (blkidx, transactions.Tx.get_by_hash(tx_h))
        else:
            for blkidx, tx_h in sl:
                yield transactions.Tx.get_by_hash(tx_h)
                
    def get_prev(self):
        return Block.get_by_hash(self.prev)
        
    def get_next_bits(self):
        targettimespan = 14 * 24 * 60 * 60 # 2 weeks in secounds
        spacing = 10 * 60 # 10 min in secounds
        interval = targettimespan/spacing # 2 weeks of blocks(2016)
        if (self.number + 1) % interval != 0:
            return self.block.bits
        log.info("DIFF: retarget, current bits: %s", hex(self.block.bits))
        first_blk = self
        for i in range(interval-1):
            first_blk = first_blk.get_prev()
        realtimespan = self.block.time - first_blk.block.time
        log.info("DIFF: timespan before limits: %d", realtimespan)
        if realtimespan < targettimespan/4: realtimespan = targettimespan/4
        if realtimespan > targettimespan*4: realtimespan = targettimespan*4
        log.info("DIFF: timespan after limits: %d", realtimespan)
        newtarget = (bits_to_target(self.block.bits)*realtimespan)/targettimespan
        if newtarget > bits_to_target(0x1d00ffff):
            newtarget = bits_to_target(0x1d00ffff)
        bits = target_to_bits(newtarget)
        log.info("DIFF: next bits: %s", hex(bits))
        return bits
        
    def verify(self):
        if self.chain == INVALID_CHAIN:
            return False
        if not check_bits(self.block.bits, self.hash):
            return False
        prev_blk = self.get_prev()
        if prev_blk.chain == INVALID_CHAIN:
            return False
        if prev_blk.get_next_bits() != self.block.bits:
            return False
        return True
        
    @txn_required    
    def confirm(self):
        log.info("confirming block %s(%d)", h2h(self.hash), self.number)
        if not self.verify():
            raise Invalidblock()
        if not set_bestblock(self):
            log.info("block %s(%d) not good", h2h(self.hash), self.number)
            return False
        self.chain = MAIN_CHAIN
        self.put()
        run_hooks(settings.BLOCK_CONFIRM_HOOKS, self)
            
    @txn_required    
    def revert(self):
        log.info("reverting block %s(%d)", h2h(self.hash), self.number)
        set_bestblock(self.get_prev(), check=False)
        if self.chain != MAIN_CHAIN:
            log.debug("reverting a block, that is not in main chain? (bug?)")
        self.chain = SIDE_CHAIN 
        self.put()
        run_hooks(settings.BLOCK_REVERT_HOOKS, self)
                    
    @txn_required
    def invalidate(self):
        self.chain = CHAIN_INVALID
        self.put()
        blocks_to_invalidate = set(self.nexts)
        while blocks_to_invalidate:
            blk_h = blocks_to_invalidate.pop()
            blk = Block.get_by_hash(blk_h)
            blk.chain = CHAIN_INVALID
            blk.put()
            blocks_to_invalidate.update(blk.nexts)

    @txn_required        
    def link(self):
        prev = self.get_prev()
        prev.nexts.append(self.hash)
        prev.put()
        if prev.chain == MAIN_CHAIN:
            self.chain = SIDE_CHAIN
        else:
            self.chain = prev.chain
        if not self.verify():
            self.invalidate()
        self.number = prev.number + 1
        self.totaldiff = prev.totaldiff + bits_to_diff(self.block.bits)
        self.put()
    
    def get_all_fees(self):
        return sum(tx.get_fee() for tx in self.iter_tx())
    
    def changes_since(self):
        bestblock = get_bestblock()
        split, reverted, confirmed = find_split(self, bestblock)
        result = {}
        result["reverted"] = [(blk.hash, [tx_h for tx_h in blk.txs]) for blk in reverted]
        result["confirmed"] = [(blk.hash, [tx_h for tx_h in blk.txs]) for blk in confirmed]
        return result
        
    def __repr__(self):
        return "<Block %s(%d) - diff: %d - chain: %s, txs: %s>" % (
        self.hexhash, self.number, bits_to_diff(self.block.bits), _chains.get(self.chain, "unknown(BUG)"), len(self.txs))       
         
    @constructor
    def make(self, blockmsg):
        self.block, self.txs = blockmsg.block, [tx.hash for tx in blockmsg.txs]
        self.number, self.totaldiff, self.chain, self.nexts = 0, 0, ORPHAN_CHAIN, []
    
    def tonetwork(self):
        return msgs.Blockmsg(self.block, list(self.iter_tx()))
        
@txn_required
def add_genesis(blkmsg, txn=None):
    blk = Block.make(blkmsg)
    blk.chain = MAIN_CHAIN
    blk.totaldiff = 1
    blk.number = 0
    blk.put()
    #for num, txmsg in enumerate(blkmsg.txs):
    #    tx = transactions.Tx.make(txmsg)
    #    tx.block = blk.hash
    #    tx.blkindex = num
    #    tx.put()
    set_bestblock(blk, check=False)
    
def get_bestblock(txn=None, raw=False):
    h = state.get("bestblock")
    if raw:
        return h
    return Block.get_by_hash(h)
 
@txn_required
def set_bestblock(blk, check=True):
    if check:
        best = get_bestblock()
        if blk.totaldiff <= best.totaldiff:
            log.info("%s(%d) is not better then %s(%d)", h2h(blk.hash), blk.number, h2h(best.hash), best.number)
            return False
        if best.hash != blk.prev:
            reorganize(best, blk)
    state.put("bestblock", blk.hash)
    return True

@txn_required
def reorganize(old, new):
    log.info("reorginizing blockchain:")
    split, old_blocks, new_blocks = find_split(old, new)
    log.info("REORG: split:%s(%d)", h2h(split.hash), split.number)
    for blk in old_blocks:
        blk.revert()
    for blk in reversed(new_blocks):
        try:
            blk.confirm()
        except InvalidBlock:
            raise TxnAbort(blk.invalidate)
        
def find_split(old, new):
    """finds the split between old and new. Returns (spilt, oldlist, newlist)"""
    log.info("finding spilt for %s(%d) and %s(%d)", h2h(old.hash), old.number, h2h(new.hash), new.number)
    oldlist = []
    newlist = []
    while old.number != new.number:
        if old.number > new.number:
            oldlist.append(old)
            old = old.get_prev()
        else:
            newlist.append(new)
            new = new.get_prev()
    while old.hash != new.hash:
        oldlist.append(old)
        newlist.append(new)
        old = old.get_prev()
        new = new.get_prev()
    split = new # = old
    log.info("spilt found at %s(%d)", h2h(split.hash), split.number)
    return split, oldlist, newlist[1:]

@txn_required
def process_blockmsg(blkmsg):
    if Block.exist_by_hash(blkmsg.block.hash):
        log.info("already have block %s", h2h(blkmsg.block.hash))
        return
    blk = Block.make(blkmsg)
    #for txmsg in blkmsg.txs:
    #    if not transactions.Tx.exist(txmsg.hash):
    #        tx = transactions.Tx.make(txmsg)
    #        tx.put()
    if Block.exist_by_hash(blk.prev):
        blk.link()
        blk.confirm()
        blk.put()
    else:
        log.info("block(%s) missing prev(%s)", h2h(blk.hash), h2h(blk.prev))
        
if not Block.exist_by_hash(genesisblock.hash):
    add_genesis(genesisblock.blkmsg)
    
import struct
def read_blocks(f):
    while True:
        try:
            print "reading block at %d" % f.tell()
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
        try:
            blkfile.seek(int(sys.argv[3]))
        except IndexError:
            pass
        for blkmsg in read_blocks(blkfile):
            process_blockmsg(blkmsg)
            eventlet.sleep(0)
    if cmd == "bestblock":
        with Transaction("bestblock", flags=[database.DB.DB_READ_UNCOMMITTED]):
            blk = get_bestblock()
        print blk
        print time.ctime(blk.block.time)
        print "%d days ago" % ((time.time()-blk.block.time)/60/60/24)
