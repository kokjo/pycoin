import transactions
import logging
import msgs
import json
from utils import h2h, hash2addr

def load_tx(filename):
    txdata = "".join(open(filename,"r").read().split("\n")).decode("hex")
    return msgs.Tx.frombinary(txdata)[0]
    
def save_tx(filename, tx):
    bintx = tx.tobinary().encode("hex")
    open(filename,"w").write("\n".join([bintx[i:i+80] for i in range(0, len(bintx), 80)]))

def getaddress(script):
    sc = script.decode("hex")
    if sc[:2] == "\x76\xa9" and sc[-2:] == "\x88\xac":
        return hash2addr(sc[3:-2])
        
if __name__ == "__main__":
    import sys
    import time
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    cmd = sys.argv[1]
    
    if cmd == "exporttx":
        txhash = sys.argv[2].decode("hex")[::-1]
        tx = transactions.Tx.get_by_hash(txhash)
        save_tx(sys.argv[3], tx.tx)
        
    if cmd == "importtx":
        tx = load_tx(sys.argv[2])
        print transactions.Tx.get_or_make(tx).hexhash
        
    if cmd == "infotx":
        txhash = sys.argv[2].decode("hex")[::-1]
        tx = transactions.Tx.get_by_hash(txhash)
        print json.dumps(tx.tojson(), sort_keys=True, indent=2)
    
    if cmd == "getoutputs":
        txhash = sys.argv[2].decode("hex")[::-1]
        tx = transactions.Tx.get_by_hash(txhash)
        outputs = []
        for output, spend in zip(tx.tx.tojson()["outputs"], tx.redeemed):
            output["address"] = getaddress(output["script"])
            output["spend"] = h2h(spend)
            outputs.append(output)
        print json.dumps(outputs, sort_keys=True, indent=2)
            
