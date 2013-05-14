from bsddb3 import db as DB
from time import sleep
import collections
import logging
import functools
import atexit
import traceback
from threading import local
from eventlet import sleep
from contextlib import contextmanager
DB_HOME = "./db"
KILL_ON_DEADLOCK = False
DEFAULT_TXN_FLAGS = [DB.DB_TXN_NOWAIT, DB.DB_TXN_NOSYNC, DB.DB_TXN_BULK]        

db_log = logging.getLogger("pycoin.database")
txn_log = logging.getLogger("pycoin.database.txn")

envflags = [DB.DB_THREAD, DB.DB_CREATE, DB.DB_INIT_MPOOL, DB.DB_INIT_LOCK, DB.DB_INIT_LOG, DB.DB_INIT_TXN] #DB.DB_RECOVER, DB.DB_JOINENV]
dbflags = [DB.DB_THREAD, DB.DB_AUTO_COMMIT, DB.DB_CREATE, DB.DB_READ_UNCOMMITTED]

th_local = local()

to_int = lambda l: reduce(lambda x, y: x|y, l)

env = DB.DBEnv()
env.set_lk_max_locks(10000)
env.set_lk_max_objects(10000)
env.set_lk_max_lockers(100)
env.open(DB_HOME, to_int(envflags))
#env.set_cachesize(512*1024*1024, 0)
#env.set_timeout(1000, DB.DB_SET_TXN_TIMEOUT)
#env.set_timeout(1000, DB.DB_SET_LOCK_TIMEOUT)

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
            
def open_db(filename, dbtype=DB.DB_BTREE, open_flags=[], flags=[], table_name=None):
    db = DB.DB(env)
    def _close_db():
        db.close()
    atexit.register(_close_db)
    if flags:
        db.set_flags(to_int(flags))
    if not open_flags:
        open_flags = dbflags
    db.open(filename, table_name, dbtype, to_int(open_flags))
    db_log.info("database %s opened", filename)
    return Database(db)

def run_in_transaction(func, *args, **kwargs):
    sleep(0)
    txn_name = kwargs.pop("txn_name","run_in_transaction")
    txn_flags = kwargs.pop("txn_flags", DEFAULT_TXN_FLAGS)
    i = 10
    sleeptime = 0.01
    while True:
        try:
            with Transaction(txn_name, txn_flags) as txn:
                return func(*args, **kwargs)
        except DB.DBError:
            if i <= 0:
                raise
            i -= 1
            
            if KILL_ON_DEADLOCK:
                raise
                
            txn_log.debug("Deadlock: sleeping %1.2f sec", sleeptime)
            sleep(sleeptime)
            sleeptime *= 2
        except TxnAbort as e:
            txn_log.debug("TXN ABORT(application) %s", repr(txn))
            return e()
        except Exception as e:
            txn_log.debug("TXN ERROR(%s) %s", repr(e), repr(txn))
            raise

        sleep(0)

@contextmanager
def Transaction(name="*UNKNOWN*", flags=DEFAULT_TXN_FLAGS):
        txn = begin_txn(flags)
        txn.set_name(name)
        txn_log.debug("TXN BEGIN %s", repr(txn))
        try:
            yield txn
        except Exception as e:
            txn_log.debug("TXN ABORT %s", repr(txn)) 
            abort_txn()
            raise
        txn_log.debug("TXN COMMIT %s", repr(txn))
        commit_txn()
        

def txn_stack():
    try:
        stack = th_local.txn_stack
    except AttributeError:
        stack = th_local.txn_stack = []
    return stack
    
def current_txn():
    stack = txn_stack()
    try:
        return stack[-1]
    except IndexError:
        return None
        
def begin_txn(flags=DEFAULT_TXN_FLAGS):
    stack = txn_stack()
    txn = env.txn_begin(parent=current_txn(), flags=to_int(flags))
    stack.append(txn)
    return txn
    
def commit_txn():
    stack = txn_stack()
    try:
        txn = stack.pop()
        txn.commit()
    except IndexError:
        pass

def abort_txn():
    stack = txn_stack()
    try:
        txn = stack.pop()
        txn.abort()
    except IndexError:
        pass
    
class Database(object):
    def __init__(self, db):
        self.db = db
    def __getattr__(self, attr):
        return getattr(self.db, attr)
    def get(self, key):
        return self.db.get(key, txn=current_txn())
    def put(self, key, value):
        self.db.put(key, value, txn=current_txn())
    def cursor(self):
        return self.db.cursor(txn=current_txn())
    def exist(self, key):
        return self.db.exist(key, txn=current_txn())
    def has_key(self, key):
        return self.db.has_key(key, txn=current_txn())
        
def txn_required(func):
    @functools.wraps(func)
    def _func(*args, **kwargs):
        txn = current_txn()
        if txn:
            return func(*args, **kwargs)
        else:
            return run_in_transaction(func, txn_name=func.__name__, *args, **kwargs)
    return _func
