from bsddb import db as DB
from time import sleep
import collections
import logging
from utils import constructor
log = logging.getLogger("pycoin.database")

KILL_ON_DEADLOCK = True

homedir="./db"
envflags = [DB.DB_THREAD, DB.DB_CREATE, DB.DB_INIT_MPOOL, DB.DB_INIT_LOCK, DB.DB_INIT_LOG, DB.DB_INIT_TXN, DB.DB_RECOVER]
dbflags = [DB.DB_THREAD, DB.DB_AUTO_COMMIT, DB.DB_CREATE]

to_int = lambda l: reduce(lambda x, y: x|y, l)

env = DB.DBEnv()
env.open(homedir, to_int(envflags))
env.set_cachesize(512*1024*1024, 0)
env.set_timeout(1000, DB.DB_SET_TXN_TIMEOUT)
env.set_timeout(1000, DB.DB_SET_LOCK_TIMEOUT)
log.info("env opened")
class TxnAbort(Exception):
    pass

def open_db(filename, dbtype=DB.DB_BTREE, flags=[]):
    db = DB.DB(env)
    if not flags:
        flags = dbflags
    db.open(filename, dbtype, to_int(flags))
    log.info("database %s opened", filename)
    return db
    
def run_in_transaction(func, *args, **kwargs):
    i = 10
    sleeptime = 0.01
    while True:
        txn = env.txn_begin(flags=DB.DB_TXN_NOWAIT)
        print "TXN BEGIN", txn
        kwargs["txn"] = txn
        try:
            return func(*args, **kwargs)
        except DB.DBError:
            print "TXN ABORT", txn 
            _txn, txn = txn, None
            _txn.abort()

            if i <= 0:
                raise
            i -= 1
            if KILL_ON_DEADLOCK:
                raise
            print "Deadlock: sleeping %1.2f sec" % sleeptime
            sleep(sleeptime)
            sleeptime *= 2
        except TxnAbort:
            print "TXN ABORT(application)"
            _txn, txn = txn, None
            _txn.abort()
        except Exception as e:
            print "TXN ERROR(%s)"%repr(e), txn
            _txn, txn = txn, None
            _txn.abort()
            raise
        finally:
            print "TXN END", txn
            if txn:
                txn.commit()

def Transaction(func):
    def _func(*args, **kwargs):
        return run_in_transaction(func, *args, **kwargs)
    return _func

def txn_required(func):
    def _func(*args, **kwargs):
        txn = kwargs.get("txn", None)
        if txn:
            return func(*args, **kwargs)
        else:
            return run_in_transaction(func, *args, **kwargs)
    return _func
        
class dictdb(collections.MutableMapping):
    def __init__(self, db, txn=None):
        self.db = db
        self.txn = txn
    def __getitem__(self, key):
        item = self.db.get(key, txn=self.txn)
        if item == None:
            raise KeyError
        else:
            return item
    def __setitem__(self, key, item):
        self.db.put(key, item, txn=self.txn)
    def __delitem__(self, key):
        self.db.delete(key, txn=self.txn)
    def __contains__(self, key):
        return self.db.exists(key, txn=self.txn)
    def __iter__(self):
        cur = self.db.cursor(txn=self.txn)
        key = cur.first()
        while key:
            yield key[0]
            key = cur.next()
    def __len__(self):
        return self.db.stat()["nkeys"]
