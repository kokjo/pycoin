import status
import msgs
import jserialize as js

from utils import *

from binascii import unhexlify, hexlify
import json

def bits_to_target(bits):
    return (bits & 0x00ffffff) * 2 ** (8 * (bits >> 24))

def bits_to_diff(bits):
    return bits_to_target(0x1d00ffff) // bits_to_target(bits)

def storetx(tx):
    if tx.hash not in status.txs:
        status.txs[tx.hash] = msgs.TxAux.make(tx).tobinary()

def add_genesis():
    from genesisblock import blockmsg
    blockmsg = msgs.Blockmsg.fromjson(blockmsg)
    block = blockmsg.block
    storetx(blockmsg.txs[0]) # There's only one tx in the genesis block
    blockaux = msgs.BlockAux()
    blockaux.block, blockaux.txs = blockmsg.block, [blockmsg.txs[0].hash]
    blockaux.number, blockaux.totaldiff = 0, bits_to_diff(block.bits)
    blockaux.invalid, blockaux.mainchain, blockaux.chained = False, True, True
    blockaux.succ = nullhash
    status.blocks[blockaux.block.hash] = blockaux.tobinary()
    print(blockaux.block.hash)
