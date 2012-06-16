import hashlib
from hashlib import sha256

import math
def ripe160(d=""):
    return hashlib.new("ripemd160", d)
#import jserialize as js
class ProtocolViolation(Exception):
    """Indicates that the communication protocol between this and a remote
    client has been violated. In this case we abort from the communication."""
    def __init__(self, reason="unknown"):
        self.reason = reason
    def __repr__(self):
        return "ProtocolViolation(%s)"%self.reason

def constructor(func):
    @classmethod
    def f(cls, *args, **kwargs):
        self = cls.__new__(cls)
        func(self, *args, **kwargs)
        return self
    return f

def cachedproperty(func):
    @property
    def f(self):
        if not hasattr(self, '_' + func.__name__):
            setattr(self, '_' + func.__name__, func(self))
        return getattr(self, '_' + func.__name__)
    return f
    
def cached(func):
    def f(self, *args, **kwargs):
        if not hasattr(self, "_cache_"+func.__name__):
            setattr(self, "_cache_"+func.__name__, func(*args, **kwargs))
        return getattr(self, "_cache_"+func.__name__)

def bits_to_target(bits):
    return (bits & 0x00ffffff) * 2 ** (8 * ((bits >> 24) - 3))

def target_to_bits(target):
    e = int(math.log(target, 2)/8) + 1 # byte length
    p = target >> 8*(e-3) # get the value bytes
    if p & (1 << 23): # if signed put zero byte in front
        p = p >> 8
        e = e + 1
    return (e << 24) + (p & 0xffffff)
    
def bits_to_diff(bits):
    return bits_to_target(0x1d00ffff) // bits_to_target(bits)

def hash_to_int(h):
    return int(h[::-1].encode("hex"), 16)
    
def check_bits(bits, h):
    if bits_to_target(bits) > int(h2h(h), 16):
        return True
    return False

def pair_up(hashes):
    if len(hashes) % 2 == 0:
        return zip(*[iter(hashes)]*2)
    else:
        return list(zip(*[iter(hashes)]*2)) + [(hashes[-1], "")]
            
def get_merkle_root(hashs):
    while len(hashs) > 1:
        hashs = [doublesha(''.join(pair)) for pair in pair_up(hashs)]
    return hashs[0]

def get_merkel_tree(hashs, hash_leaf):
    tree = []
    while len(hashs) > 1:
        hashs2 = []
        for pair in pair_up(hashs):
            hashs2.append(doublesha(''.join(pair)))
            if hash_leaf in pair:
                tree.append(pair)
                hash_leaf = hashs2[-1]
        hashs = hashs2
    return tree
            
    
def doublesha(data):
    return sha256(sha256(data).digest()).digest()

def hash160(data):
    return ripe160(sha256(data).digest()).digest()
    
def checksum(bdata):
    return doublesha(bdata)[:4]

def h2h(h):
    return h[::-1].encode("hex")


__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58.    
    """
    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

      # Bitcoin does a little leading-zero-compression:
      # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': 
            nPad += 1
        else: 
            break
    return (__b58chars[0]*nPad) + result

def b58decode(v, length):
    """ decode v into a string of len bytes
    """
    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += __b58chars.find(c) * (__b58base**i)

    result = ''
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result = chr(mod) + result
        long_value = div
    result = chr(long_value) + result

    nPad = 0
    for c in v:
        if c == __b58chars[0]: 
            nPad += 1
        else: 
            break

    result = chr(0)*nPad + result
    if length is not None and len(result) != length:
        return None

    return result

def pubkey2addr(pubkey):
    return hash2addr(hash160(pubkey))
def hash2addr(h160):
    vh160 = "\x00"+h160  # \x00 is version 0
    addr=vh160+checksum(vh160)
    return b58encode(addr)

def addr2hash(addr):
    bytes = b58decode(addr, 25)
    zero, hash160, chk = bytes[0], bytes[1:21], bytes[21:25]
    if checksum(hash160) == chk:
        return hash160
    else:
        return None
         
nullhash = "\x00"*32
COIN = 100000000
blockreward = 50*COIN
