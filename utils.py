from hashlib import sha256
import math
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
    e = int(math.log(target, 2))/8 + 2
    p = target >> 8*(e-3)
    return (e << 24) + p
    
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

def checksum(bdata):
    return doublesha(bdata)[:4]

def h2h(h):
    return h[::-1].encode("hex")
        
nullhash = "\x00"*32
COIN = 100000000
blockreward = 50*COIN
