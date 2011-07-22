import binascii

from utils import ProtocolViolation, constructor

class Bytes():
    @staticmethod
    def tojson(obj):
        return binascii.hexlify(obj).decode("ascii")
    @staticmethod
    def fromjson(json):
        return binascii.unhexlify(json.encode("ascii"))

class Hash():
    @staticmethod
    def tojson(obj):
        return obj[::-1].encode("hex")
    @staticmethod
    def fromjson(json):
        return json.decode("hex")[::-1]

class Entity(object):
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
        @staticmethod
        def tojson(object):
            return object
        @staticmethod
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
        @staticmethod
        def tojson(self):
            return [type.tojson(x) for x in self]
        @staticmethod
        def fromjson(json):
            return [type.fromjson(x) for x in json]
    return _List

def Dict(ktype, vtype):
    class _Dict():
        def tojson(self):
            return dict(((ktype.tojson(k), vtype.tojson(v)) for (k, v) in self.items()))
        @staticmethod
        def fromjson(json):
            return dict(((ktype.fromjson(k), vtype.fromjson(v)) for (k, v) in json.items()))
    return _Dict

# Serialization for various types in stdlib modules

#This isn't technically a stdlib module
class IPv4():
    @staticmethod
    def tojson(obj):
        return str(obj)
    @staticmethod
    def fromjson(object):
        return object

