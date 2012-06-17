import eventlet
from bsddb3 import db as DB
from time import sleep
import collections
import logging
from utils import constructor
import functools
import atexit

db_log = logging.getLogger("pycoin.database")
txn_log = logging.getLogger("pycoin.database.txn")
KILL_ON_DEADLOCK = False

homedir="./db"
envflags = [DB.DB_THREAD, DB.DB_CREATE, DB.DB_INIT_MPOOL, DB.DB_INIT_LOCK, DB.DB_INIT_LOG, DB.DB_INIT_TXN] #DB.DB_RECOVER, DB.DB_JOINENV]
dbflags = [DB.DB_THREAD, DB.DB_AUTO_COMMIT, DB.DB_CREATE]

to_int = lambda l: reduce(lambda x, y: x|y, l)

env = DB.DBEnv()
env.set_lk_max_locks(10000)
env.set_lk_max_objects(10000)
env.set_lk_max_lockers(100)
env.open(homedir, to_int(envflags))
env.set_cachesize(512*1024*1024, 0)
env.set_timeout(1000, DB.DB_SET_TXN_TIMEOUT)
env.set_timeout(1000, DB.DB_SET_LOCK_TIMEOUT)

def close_env():
    env.close()

atexit.register(close_env)

db_log.info("env opened")

class TxnAbort(Exception):
    def __init__(self, callback=None, *args, **kwargs):
        self.__callback = callback
        self.__args = args
        self.__kwargs = kwargs
        
    @property
    def callback(self):
        if self.__callback:
            return lambda: self.__callback(*self.__args, **self.__kwargs)
        else:
            return None
            
    def __call__(self):
        cb = self.callback
        if cb: return cb()
            
def open_db(filename, dbtype=DB.DB_BTREE, flags=[]):
    db = DB.DB(env)
    def _close_db():
        db.close()
    atexit.register(_close_db)
    if not flags:
        flags = dbflags
    db.open(filename, dbtype, to_int(flags))
    db_log.info("database %s opened", filename)
    return db

DEFAULT_TXN_FLAGS = [DB.DB_TXN_NOWAIT, DB.DB_TXN_NOSYNC]
def run_in_transaction(func, *args, **kwargs):
    eventlet.sleep(0)
    i = 10
    sleeptime = 0.01
    while True:
        txn = env.txn_begin(flags=to_int(DEFAULT_TXN_FLAGS))
        txn_log.debug("TXN BEGIN %s", repr(txn))
        kwargs["txn"] = txn
        try:
            return func(*args, **kwargs)
        except DB.DBError:
            txn_log.debug("TXN ABORT %s", repr(txn)) 
            _txn, txn = txn, None
            _txn.abort()

            if i <= 0:
                raise
            i -= 1
            if KILL_ON_DEADLOCK:
                raise
            txn_log.debug("Deadlock: sleeping %1.2f sec", sleeptime)
            eventlet.sleep(0)
            sleep(sleeptime)
            sleeptime *= 2
        except TxnAbort as e:
            txn_log.debug("TXN ABORT(application) %s", repr(txn))
            _txn, txn = txn, None
            _txn.abort()
            return e()
        except Exception as e:
            txn_log.debug("TXN ERROR(%s) %s", repr(e), repr(txn))
            _txn, txn = txn, None
            _txn.abort()
            raise
        finally:
            if txn:
                txn_log.debug("TXN COMMIT %s", repr(txn))
                txn.commit()
            txn_log.debug("TXN END %s", repr(txn))
            eventlet.sleep(0)

def Transaction(func):
    @functools.wraps(func)
    def _func(*args, **kwargs):
        return run_in_transaction(func, *args, **kwargs)
    return _func


def txn_required(func):
    @functools.wraps(func)
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
