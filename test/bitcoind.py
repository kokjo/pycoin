from os.path import expanduser
import jsonrpc
import sys

class BitcoinProxy(jsonrpc.ServiceProxy):
    JSONRPCException = jsonrpc.JSONRPCException
    def __init__(self, url, conf):
        jsonrpc.ServiceProxy.__init__(self, url % conf)
        self.conf = conf
    def get_latest_block(self):
        return self.getblock(self.getblockhash(self.getblockcount()))

    def get_latests_txs(self):
        for txh in self.get_latest_block()["tx"]:
            try:
                yield self.getrawtransaction(txh)
            except self.JSONRPCException:
                pass
                
conf = {p[0]: p[1].strip() for p in 
    (l.split("=") for l in open(expanduser("~/.bitcoin/bitcoin.conf")))
    if len(p) == 2}
    
proxy = BitcoinProxy("http://%(rpcuser)s:%(rpcpassword)s@127.0.0.1:8332", conf)

#awesome hack!
sys.modules[__name__] = proxy
