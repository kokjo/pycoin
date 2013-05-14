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
from socket import inet_ntoa, inet_aton

class Entity(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def tobinary(self):
        retval = b""
        for (field, type) in self.bfields:
            retval += type.tobinary(self.__getattribute__(field))
        return retval
    @classmethod
    def frombinary(cls, bdata, rest=True):
        self = cls.__new__(cls)
        for (field, type) in self.bfields:
            obj, bdata = type.frombinary(bdata)
            self.__setattr__(field, obj)
        if rest:
            return self, bdata
        else:
            if bdata != "":
                raise ProtocolViolation()
            else:
                return self
def structfmt(fmt):
    """Produce a serialization object for a value understood by struct.
e.g. structfmt("<I") for 4-byte integers"""
    fmtsize = struct.calcsize(fmt)
    class _():
        @staticmethod
        def tobinary(obj):
            return struct.pack(fmt, obj)
        @staticmethod
        def frombinary(bdata):
            try:
                return struct.unpack(fmt, bdata[:fmtsize])[0], bdata[fmtsize:]
            except struct.error:
                raise ProtocolViolation()
    return _

class Str():
    @staticmethod
    def tobinary(obj):
        return obj.encode("ascii") + '\0'
    @staticmethod
    def frombinary(bdata):
        bytes, ch, bdata = bdata.partition('\0')
        if ch == '':
            raise ProtocolViolation
        try:
            return bytes.decode("ascii"), bdata
        except UnicodeDecodeError:
            raise ProtocolViolation

Hash = structfmt("<32s")

class VarInt():
    @staticmethod
    def frombinary(bdata):
        try:
            if ord(bdata[0]) <= 0xfc:
                return ord(bdata[0]), bdata[1:]
            if ord(bdata[0]) == 0xfd:
                return struct.unpack("<xH", bdata[:3])[0], bdata[3:]
            if ord(bdata[0]) == 0xfe:
                return struct.unpack("<xI", bdata[:5])[0], bdata[5:]
            if ord(bdata[0]) == 0xff:
                return struct.unpack("<xQ", bdata[:9])[0], bdata[9:]
        except (struct.error, IndexError):
            raise ProtocolViolation
    @staticmethod
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
        @staticmethod
        def frombinary(bdata):
            num, bdata = VarInt.frombinary(bdata)
            retval = []
            for _ in range(num):
                item, bdata = ty.frombinary(bdata)
                retval.append(item)
            return retval, bdata
        @staticmethod
        def tobinary(obj):
            return VarInt.tobinary(len(obj)) + "".join(ty.tobinary(x) for x in obj)
    return _

class VarBytes():
    @staticmethod
    def frombinary(bdata):
        num, bdata = VarInt.frombinary(bdata)
        if len(bdata) < num:
            raise ProtocolViolation
        return bdata[:num], bdata[num:]
    @staticmethod
    def tobinary(obj):
        return VarInt.tobinary(len(obj)) + obj

class IPv4Inv6():
    @staticmethod
    def frombinary(bdata):
        try:
            obj, bdata = structfmt("!12x4s").frombinary(bdata)
        except struct.error:
            raise ProtocolViolation
        return inet_ntoa(obj), bdata
    @staticmethod
    def tobinary(object):
        return struct.pack("!10xH4s", 2**16-1, inet_aton(object))
