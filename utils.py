class ProtocolViolation(Exception):
    """Indicates that the communication protocol between this and a remote
    client has been violated. In this case we abort from the communication."""
    pass

def constructor(func):
    @classmethod
    def f(cls, *args):
        self = cls.__new__(cls)
        func(self, *args)
        return self
    return f

def cachedproperty(func):
    @property
    def f(self):
        if not hasattr(self, '_' + func.__name__):
            setattr(self, '_' + func.__name__, func(self))
        return getattr(self, '_' + func.__name__)
    return f

def simplerepr(self):
    return "<" + ",".join(["{}={}".format(n, getattr(self, n)) for n in self.fields]) + ">"

def doublesha(data):
    from hashlib import sha256
    "Call sha on a bytestream and then again on the hash"
    hash1 = sha256(data)
    return sha256(hash1.digest()).digest()

nullhash = b"\0"*32
blockreward = 5000000000
