from utils import *
import msgs
import jserialize as js
import bserialize as bs
import bsddb
import logging

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
        return tx.hash
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
        
class TxDatabase(object):
    def __init__(self, blockchain):
        self.db = bsddb.btopen("txs.dat")
        self.blockchain = blockchain
        
    def get_tx(self, h):
        return TxAux.frombinary(self.db[h])[0]
        
    def put_tx(self, tx):
        self.db[tx.hash] = tx.tobinary()
        
    def verify_tx(self, tx, spend_check=True):
        for txin in tx.tx.inputs:
            if txin.outpoint.tx != nullhash:
                parent_tx = self.get_tx(txin.outpoint.tx)
            else:
                parent_tx = None
    def add(self, tx):
        
