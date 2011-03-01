import binascii

from utils import ProtocolViolation

def constructor(func):
    @classmethod
    def f(cls, *args):
        self = cls.__new__(cls)
        func(self, *args)
        return self
    return f

class Hash():
    def tojson(obj):
        return binascii.hexlify(obj).decode("ascii")
    def fromjson(json):
        return binascii.unhexlify(json.encode("ascii"))

class Entity():
    def tojson(self):
        retval = {}
        for (field, type) in self.fields.items():
            retval[field] = type.tojson(self.__getattribute__(field))
        return retval
    @constructor
    def fromjson(self, json):
        for (field, type) in self.fields.items():
            self.__setattr__(field, type.fromjson(json[field]))

def alreadyjson(type):
    class Foo():
        def tojson(object):
            return object
        def fromjson(json):
            return json
    return Foo

# Built-ins
Int = alreadyjson(int)
Str = alreadyjson(str)
Float = alreadyjson(float)
Bool = alreadyjson(bool)

def List(type):
    class _List():
        def tojson(self):
            return [type.tojson(x) for x in self]
        def fromjson(json):
            return [type.fromjson(x) for x in json]
    return _List

def Dict(ktype, vtype):
    class _Dict():
        def tojson(self):
            return dict(((ktype.tojson(k), vtype.tojson(v)) for (k, v) in self.items()))
        def fromjson(json):
            return dict(((ktype.fromjson(k), vtype.fromjson(v)) for (k, v) in json.items()))
    return _Dict

# Serialization for various types in stdlib modules

#This isn't technically a stdlib module
class IPv4():
    def tojson(obj):
        import ipaddr
        assert obj.__class__ == ipaddr.IPv4Address
        return str(obj)
    def fromjson(object):
        import ipaddr
        return ipaddr.IPv4Address(object)

