"""Contains the binary serialization logic, we import it "as bs".

Each object is provided with a binary serialization class, in most cases this
is the object's class.

Each binary-serialization class has two methods tobinary() and frombinary().
The tobinary() method takes an object as its first argument and returns it as a
bytes object. The frombinary() method takes a bytestring as its first
argument and returns (obj, rest of bytestring).

Throws ProtocolViolation when fed junk.
"""

from utils import ProtocolViolation

import struct

class Entity():
    """
Each Entity subclass has a class variable called bfields, which is list of
tuples contained as fieldname and a serialization class.

bfields = [
    ("field1", cls1),
    ("field2", cls2),
    ...
]

The object is serialized by tobinary() by concatanating the results of
serializing the value of each field with its serialization class.

Entity subclasses are serialization objects for their instances.
"""
    def tobinary(self):
        retval = b""
        for (field, type) in self.bfields:
            retval += type.tobinary(self.__getattribute__(field))
        return retval
    @classmethod
    def frombinary(cls, bdata):
        self = cls.__new__(cls)
        for (field, type) in self.bfields:
            obj, bdata = type.frombinary(bdata)
            self.__setattr__(field, obj)
        return self, bdata

def structfmt(fmt):
    """Produce a serialization object for a value understood by struct.
e.g. structfmt("<I") for 4-byte integers"""
    class Foo():
        def tobinary(obj):
            return struct.pack(fmt, obj)
        def frombinary(bdata):
            try:
                return struct.unpack(fmt, bdata[:struct.calcsize(fmt)])[0], bdata[struct.calcsize(fmt):]
            except struct.error:
                raise ProtocolViolation()
    return Foo

class Str():
    def tobinary(obj):
        return obj.encode("ascii") + b'\0'
    def frombinary(bdata):
        bytes, ch, bdata = bdata.partition(b'\0')
        if ch == b'':
            raise ProtocolViolation
        try:
            return bytes.decode("ascii"), bdata
        except UnicodeDecodeError:
            raise ProtocolViolation

Hash = structfmt("<32s")

class VarInt():
    def frombinary(bdata):
        try:
            if bdata[0] <= 0xfc:
                return bdata[0], bdata[1:]
            if bdata[0] == 0xfd:
                return struct.unpack("<xH", bdata[:3])[0], bdata[3:]
            if bdata[0] == 0xfe:
                return struct.unpack("<xI", bdata[:5])[0], bdata[5:]
            if bdata[0] == 0xff:
                return struct.unpack("<xQ", bdata[:9])[0], bdata[9:]
        except (struct.error, IndexError):
            raise ProtocolViolation
    def tobinary(int):
        if int <= 0xfc:
            return struct.pack("<B", int)
        elif int < 0xffff:
            return struct.pack("<BH", 0xfd, int)
        elif int < 0xffffffff:
            return struct.pack("<BI", 0xfe, int)
        else:
            return struct.pack("<BQ", 0xff, int)

def VarList(ty):
    class _():
        def frombinary(bdata):
            num, bdata = VarInt.frombinary(bdata)
            retval = []
            for _ in range(num):
                item, bdata = ty.frombinary(bdata)
                retval.append(item)
            return retval, bdata
        def tobinary(obj):
            return VarInt.tobinary(len(obj)) + b"".join((ty.tobinary(x) for x in obj))
    return _

class VarBytes():
    def frombinary(bdata):
        num, bdata = VarInt.frombinary(bdata)
        if len(bdata) < num:
            raise ProtocolViolation
        return bdata[:num], bdata[num:]
    def tobinary(obj):
        return VarInt.tobinary(len(obj)) + obj

class IPv4Inv6():
    def frombinary(bdata):
        import ipaddr
        try:
            obj, bdata = structfmt("!12xI").frombinary(bdata)
        except struct.error:
            raise ProtocolViolation
        return ipaddr.IPv4Address(obj), bdata
    def tobinary(object):
        return struct.pack("!10xHI", 2**16-1, int(object))
