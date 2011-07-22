from hashlib import sha256
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
            return list(zip(*[iter(hashes)]*2)) + [(hashes[-1], "")]
    while len(tree) > 1:
        tree = [doublesha(''.join(pair)) for pair in pair_up(tree)]
    return tree[0]
    
def doublesha(data):
    return sha256(sha256(data).digest()).digest()

def checksum(bdata):
    return doublesha(bdata)[:4]
    
nullhash = "\x00"*32
blockreward = 5000000000
