import database
import ec
from database import txn_required
import jserialize as js
import bserialize as bs
from utils import *

# 1huR1oV8uEE77HqQHCAuCzCzoq9HzXDSh
# L5TG3BkBgABJ1EXqznUSgRNXbdXwUpXEAEd6MDSFPsEnS5v2yX1i

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
            
    def __init_key(self):
        self._key = ec.Key.from_privkey(self.privatkey)
    
    @property
    def bitcoinaddress(self):
        return hash2addr(self.hash)
        
    @staticmethod
    def get_by_hash(h, txn=None):
        ret = KeyEntry.frombinary(keychain.get(h, txn=txn))[0]
        ret.__init_key()
        return ret
        
    @staticmethod
    def get_by_publickey(key, txn=None):
        return KeyEntry.get_by_hash(hash160(key), txn=txn)
    
    def tosecret(self):
        secret = "\x80" + self._key.get_secret()
        if self._key.get_compressed():
            secret += "\x01"
        secret = secret+doublesha(secret)[:4]
        return b58encode(secret)
        
    @classmethod    
    def fromsecret(cls, secret):
        self = cls()
        secret = b58decode(secret, None)
        secret, cksum = secret[:-4], secret[-4:]
        if doublesha(secret)[:4] != cksum:
            return None
        valid, secret, compressed = secret[0]=="\x80", secret[1:33], secret[33:] == "\x01" 
        if not valid:
            return None
        self._key = ec.Key.generate(secret, compressed)
        self.privatkey = self._key.get_privkey()
        self.publickey = self._key.get_pubkey() 
        self.txs = []
        return cls
        
    @classmethod
    def generate(cls):
        self = cls()
        self._key = ec.Key.generate()
        self.privatkey = self._key.get_privkey()
        self.publickey = self._key.get_pubkey() 
        self.txs = []
        return self
        
    @txn_required
    def put(self, txn=None):
        keychain.put(self.hash, self.tobinary(), txn=txn)

