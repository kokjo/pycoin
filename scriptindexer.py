import database
import msgs

script_idx = None

def init_db():
    global script_idx
    if script_idx == None:
        script_idx = database.open_db("txs.dat", flags=[database.DB.DB_DUP], table_name="script_index")
        script_idx.set_get_returns_none(0)

def search_script(sc, txn=None):
    init_db()
    cur = script_idx.cursor(txn=txn)
    k, v = cur.set(h)
    while k == h:
        yield msgs.TxPoint.frombinary(v)[0]
        k, v = cur.next_dup()

def index_script(tx, txn=None):
    init_db()
    for tx_idx, out_p in enumerate(tx.outputs):
        script_idx.put(out_p.script, msgs.TxPoint.make(tx.hash, tx_idx).tobinary(), txn=txn)

