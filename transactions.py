from utils import *
import genesisblock
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging

import database
from database import txn_required
#import blockchain

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
            
    def revert(self, block=None, coinbase=False, txn=None):
        log.info("reverting tx %s", h2h(self.hash))
        self.block = nullhash
        if coinbase:
            return
        for inp in self.tx.inputs:
            inp_tx = Tx.get_by_hash(inp.outpoint.tx, txn=txn)
            inp_tx.unredeem_output(inp.outpoint)
            inp_tx.put(txn=txn)
            
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
    
    def valid(self, check_spend=False, check_scripts=False, block=None, coinbase=False, txn=None):
        if self.total_amount_out() > self.total_amount_in(block=block, txn=txn):
            return False
        if check_spend:
            pass #TODO: check if all inputs are not spend yet
        if check_scripts:
            pass #TODO: check if the scripts are valid.
    
    def __repr__(self):
        return "<Tx %s, %d inputs, %d outputs, coinbase: %s, in: %d, out: %d, fees: %d>" % (
        h2h(self.hash), len(self.tx.inputs), len(self.tx.outputs), str(self.coinbase),
        self.get_amount_in(), self.get_amount_out(), self.get_fee())
    
    @constructor
    def make(self, tx):
        self.tx, self.block = tx, nullhash
        self.blkindex = 0
        self.redeemed = [nullhash] * len(tx.outputs)
        
    def get_inpoint(self, i):
        return msgs.TxPoint(self.hash, i)
    def get_outpoint(self, outpoint):
        assert self.hash == outpoint.tx, "outpoint hash does not point to tx"
        assert outpoint.index < len(self.tx.outputs), "outpoint index out of range"
        return self.tx.outputs[outpoint.index]
    
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

