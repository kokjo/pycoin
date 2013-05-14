import script
import script.opcodes
import msgs
import json
import bitcoind
import jsonrpc
from utils import h2h

for hex_tx in bitcoind.get_latests_txs():
    tx = msgs.Tx.frombinary(hex_tx.decode("hex"))[0]
    print "Tx %s" % h2h(tx.hash)

    print json.dumps(tx.tojson(), sort_keys=True, indent=4, separators=(',', ': '))

    for i, inp in enumerate(tx.inputs):
        print "decoding input #%d: %s" % (i, str(script.opcodes.decode_script(inp.script)))

    for i, outp in enumerate(tx.outputs):
        print "decoding output #%d: %s" % (i, str(script.opcodes.decode_script(outp.script)))
