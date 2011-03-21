import status
import msgs
import jserialize as js

from utils import *

from binascii import unhexlify, hexlify
import json

def bits_to_target(bits):
    return (bits & 0x00ffffff) * 2 ** (8 * ((bits >> 24) - 3))

def bits_to_diff(bits):
    return bits_to_target(0x1d00ffff) // bits_to_target(bits)

def check_bits(bits, hash):
    if bits_to_target(bits) > int(js.Hash.tojson(hash), 16):
        return True
    return False

def get_merkle_root(tree):
    def pair_up(hashes):
        if len(hashes) % 2 == 0:
            return zip(*[iter(hashes)]*2)
        else:
            return list(zip(*[iter(hashes)]*2)) + [(hashes[-1], b"")]
    while len(tree) > 1:
        tree = [doublesha(b''.join(pair)) for pair in pair_up(tree)]
    return tree[0]

def storetx(tx):
    if tx.hash not in status.txs:
        status.txs[tx.hash] = msgs.TxAux.make(tx).tobinary()

def _storeblock(blockaux):
    status.blocks[blockaux.block.hash] = blockaux.tobinary()

def checktx(tx):
    return True # FIXME Implement checks

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

def add_block(block):
    blockaux = msgs.BlockAux.make(block)
    # Tests that we don't need the previous block for
    if not (blockaux.txs and check_bits(block.bits, block.hash) and
            block.version == 1 and block.prev != nullhash and
            block.get_merkle_root(blockaux.txs) == block.merkle):
        blockaux.invalid = True
        return
    if not block.prev in status.blocks:
        status.blocks[block.hash] = blockaux.tobinary()
        status.orphan_dict[block.prev].append(block.hash)
        return
    chain_block()
    # FIXME chain subsequent blocks
