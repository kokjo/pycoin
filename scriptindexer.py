import database
import msgs

script_idx = database.open_db("txs.dat", flags=[database.DB.DB_DUP], table_name="script_index")
script_idx.set_get_returns_none(0)

def search_script(sc):
    cur = script_idx.cursor()
    k, v = cur.set(h)
    while k == h:
        yield msgs.TxPoint.frombinary(v)[0]
        k, v = cur.next_dup()

def index_script(tx):
    for tx_idx, out_p in enumerate(tx.outputs):
        script_idx.put(out_p.script, msgs.TxPoint.make(tx.hash, tx_idx).tobinary())

