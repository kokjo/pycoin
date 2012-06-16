import database
import ec
from database import txn_required
import jserialize as js
import bserialize as bs
from utils import *

keychain = database.open_db("keychain.dat")
keychain.set_get_returns_none(0)
class KeyEntry(bs.Entity, js.Entity):
    bfields = [
        ("privatkey", bs.VarBytes),
        ("publickey", bs.VarBytes),
        ("txs", bs.VarList(bs.Hash))
    ]
    fields = {
        "privatkey": js.Bytes,
        "publickey": js.Bytes,
        "txs": js.List(js.Hash)
    }
    @property
    def hash(self):
        return hash160(self.publickey)
    @staticmethod
    def iter_keys(txn=None):
        try:
            cur = keychain.cursor(txn=txn)
            while True:
                try:
                    h, data = cur.next()
                except KeyError:
                    break
                yield KeyEntry.frombinary(data)[0]
        finally:
            cur.close()
    @property
    def bitcoinaddress(self):
        return hash2addr(self.hash)
    @staticmethod
    def get_by_hash(h, txn=None):
        return KeyEntry.frombinary(keychain.get(h, txn=txn))[0]
    @staticmethod
    def get_by_publickey(key, txn=None):
        return KeyEntry.get_by_hash(hash160(key), txn=txn)
        
    @constructor
    def generate(self):
        self.privatkey, self.publickey = ec.generate()
        self.txs = []
        
    @txn_required
    def put(self, txn=None):
        keychain.put(self.hash, self.tobinary(), txn=txn)

