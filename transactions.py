import eventlet
from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging
import queue
import database
from database import txn_required
import blockchain
import struct
import ec

def tx_event(tx, tags=[]):
    queue.send_msg(tx.hash, "txs", tags=tags)
class TxError(Exception):
    pass
class TxInputAlreadySpend(TxError):
    pass
    
txs = database.open_db("txs.dat")
log = logging.getLogger("pycoin.transactions")

class Tx(js.Entity, bs.Entity):
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
        ("blkindex", bs.structfmt("<L"))
    ]
    
    @staticmethod
    def get_by_hash(h, txn=None):
        log.debug("getting tx %s", h2h(h))
        return Tx.frombinary(txs.get(h, txn=txn))[0]
    @txn_required
    def put(self, txn=None):
        log.debug("putting tx %s", h2h(self.hash))
        txs.put(self.hash, self.tobinary(), txn=txn)
    @staticmethod
    def exist(h, txn=None):
        return txs.has_key(h, txn=txn)
    @property
    def hash(self): return self.tx.hash
    @property
    def hexhash(self): return h2h(self.hash)
    @property
    def confirmed(self): return self.block != nullhash
    @property
    def inputs(self): return self.tx.inputs
    @property
    def outputs(self): return self.tx.outputs
    @property
    def coinbase(self): return self.tx.coinbase
    
    def get_block(self, txn=None):
        if self.confirmed:
            return blockchain.Block.get_by_hash(self.block)
        else:
            return None
            
    def confirm(self, block, coinbase=False, txn=None):
        log.info("confirming tx %s", h2h(self.hash))
        self.block = block.hash
        if coinbase:
            return
        for inp in self.tx.inputs:
            inp_tx = Tx.get_by_hash(inp.outpoint.tx, txn=txn)
            inp_tx.redeem_output(inp.outpoint, self) 
            inp_tx.put(txn=txn)
        tx_event(self, tags=["confirm"])
        
    def revert(self, block=None, coinbase=False, txn=None):
        log.info("reverting tx %s", h2h(self.hash))
        self.block = nullhash
        if coinbase:
            return
        for inp in self.tx.inputs:
            inp_tx = Tx.get_by_hash(inp.outpoint.tx, txn=txn)
            inp_tx.unredeem_output(inp.outpoint)
            inp_tx.put(txn=txn)
        tx_event(self, tags=["revert"])
            
    def get_amount_out(self): 
        return sum([i.amount for i in self.tx.outputs])
    
    def get_amount_in(self, block=None, txn=None):
        if self.coinbase:
            if block:
                reward = 50*COIN >> (block.number / 210000)
                fees = block.get_all_fees(txn=txn)
                return reward + fees
            else:        
                return 0
        amount = 0
        for inp in self.tx.inputs:
            inp_tx = Tx.get_by_hash(inp.outpoint.tx, txn=txn)
            amount += inp_tx.get_outpoint(inp.outpoint).amount
        return amount
    
    def get_fee(self, txn=None):
        if self.coinbase:
            return 0
        return self.get_amount_in(txn=txn) - self.get_amount_out()
    
    def verify(self, check_spend=False, check_scripts=False, block=None, coinbase=False, txn=None):
        if coinbase:
            return True
        if self.total_amount_out() > self.total_amount_in(block=block, txn=txn):
            return False
        if check_spend:
            pass #TODO: check if all inputs are not spend yet
        if check_scripts:
            pass #TODO: check if the scripts are valid.
        return True
    
    def __repr__(self):
        return "<Tx %s, %d inputs, %d outputs, coinbase: %s, in: %d, out: %d, fees: %d>" % (
        h2h(self.hash), len(self.tx.inputs), len(self.tx.outputs), str(self.coinbase),
        self.get_amount_in(), self.get_amount_out(), self.get_fee())
    
    def get_simple_hash(self, inputidx, hashtype):
        assert hashtype == 1
        tx = msgs.Tx.frombinary(self.tx.tobinary())[0] # copy the transaction
        for i, inp in enumerate(tx.inputs):
            if i == inputidx:
                outp = Tx.get_outpoint(inp.outpoint)
                inp.script = outp.script
            else:
                inp.script = ""
        return doublesha(tx.tobinary()+struct.pack("<L", hashtype))
    
    def extract_info(self, inputidx):
        inp = self.inputs[inputidx]
        outp = Tx.get_outpoint(inp.outpoint)
        if outp.script[:2] == "\x76\xa9" and outp.script[-2:] == "\x88\xac": #to address
            address = outp.script[3:-2]
            rest = inp.script
            sig_l, rest = ord(rest[0]), rest[1:]
            sig, rest = rest[:sig_l], rest[sig_l:]
            key_l, rest = ord(rest[0]), rest[1:]
            key, rest = rest[:key_l], rest[key_l:]
            if rest != "" or len(key) != key_l or len(sig) != sig_l:
                return (0, None, None, None)
            return (1, address, sig, key)
        if outp.script[-1:] == "\xac": # generation
            rest = outp.script
            key_l, rest = ord(rest[0]), rest[1:]
            key, rest = rest[:key_l], rest[key_l:]
            if rest != "\xac":
                return (0, None, None, None)
            rest = inp.script
            sig_l, rest = ord(rest[0]), rest[1:]
            sig, rest = rest[:sig_l], rest[sig_l:]
            if rest != "":
                return (0, None, None, None)
            if len(key) != key_l or len(sig) != sig_l:
                return (0, None, None, None)
            return (2, None, sig, key)
    def check_signatures(self):
        if self.coinbase:
            return True
        for idx in range(len(self.inputs)):
            sc_type, address, sig, key = self.extract_info(idx)
            
            if sc_type == 0:
                log.warning("tx input %s:%d could not be validated, could not extract info", h2h(self.hash), idx)
                continue
            if sc_type == 1:
                log.info("tx input %s:%d, is in address-form", h2h(self.hash), idx)
                if hash160(key) != address:
                     log.warning("tx input %s:%d is invalid, address and publickey does not match", h2h(self.hash), idx)
                     return False
                
            elif sc_type == 2:
                log.info("tx input %s:%d is from coin generation", h2h(self.hash), idx)
                     
            sig, hashtype = ec.load_sig(sig)
            if hashtype != 1:
                log.warning("tx input %s:%d could not be validated, hashtype is wrong", h2h(self.hash), idx)
                continue
            
            simple_hash = self.get_simple_hash(idx, hashtype)
            res = ec.verify_sig(sig, simple_hash, key)
            if res:
                log.info("tx input %s:%d, is valid", h2h(self.hash), idx)
            else:
                log.warning("tx input %s:%d, is invalid, signature is invalid", h2h(self.hash), idx)
                return False
        return True
                
    @constructor
    def make(self, tx):
        self.tx, self.block = tx, nullhash
        self.blkindex = 0
        self.redeemed = [nullhash] * len(tx.outputs)
        
    def get_inpoint(self, i):
        return msgs.TxPoint(self.hash, i)
        
    @staticmethod
    def get_outpoint(outpoint):
        tx = Tx.get_by_hash(outpoint.tx)
        assert outpoint.index < len(tx.outputs), "outpoint index out of range"
        return tx.outputs[outpoint.index]
    
    def is_redeemed(self, outpoint):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        return self.redeemed[outpoint.index] != nullhash
    
    def redeem_output(self, outpoint, tx):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        if self.redeemed[outpoint.index] != nullhash:
            raise TxInputAlreadySpend(outpoint)
        self.redeemed[outpoint.index] = tx.hash
        
    def unredeem_output(self, outpoint):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        self.redeemed[outpoint.index] = nullhash
    def fully_redeemed(self):
        return nullhash not in self.redeemed
        
def find_related_txs(tx):
    checked_txs = []
    unchecked_txs = [tx]
    while len(unchecked_txs) > 0:
        tx = unchecked_txs.pop()
        new_txs = [Tx.get_by_hash(inp.outpoint.tx) for inp in tx.inputs if inp.outpoint.tx != nullhash]
        new_txs = [tx for tx in new_txs if tx.hash not in checked_txs]
        unchecked_txs.extend(new_txs)
        checked_txs.append(tx.hash)
        yield tx
    return

