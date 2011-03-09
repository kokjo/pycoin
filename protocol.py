import status
import msgs
import jserialize as js

from utils import *

from binascii import unhexlify, hexlify
import json

def storetx(tx):
    if tx.hash not in status.txs:
        status.txs[tx.hash] = msgs.TxAux.make(tx).tobinary()
