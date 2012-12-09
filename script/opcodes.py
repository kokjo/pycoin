import struct
from bignum import *

class Opcode(object):
    num = None    
    def encode(self):
        return struct.pack("<B", self.num)
    @classmethod
    def decode(cls, script):
        return cls(), script[1:]
    def may_exec(self, ctx):
        return ctx.may_exec()
    def eval(self, ctx):
        return False
    def __repr__(self):
        return self.__class__.__name__
    def __len__(self):
        return len(self.encode())

class OP_FALSE(Opcode):
    num = 0
    def eval(self, ctx):
        return ctx.stack.push("")
            
HEX_ONLY_PUSH = True
class _OP_PUSH(Opcode):
    num = None
    def __init__(self, data):
        self.data = data
    def eval(self, ctx):
        return ctx.stack.push(self.data)
    def __repr__(self):
        if HEX_ONLY_PUSH:
            return '"%s"' % (self.data.encode("hex"))
        else:
            return '%s("%s")' % (self.__class__.__name__, self.data.encode("hex"))
        
class _OP_PUSHN(_OP_PUSH):
    num = None
    def __init__(self, data):
        self.data = data
    
    def encode(self):
        return struct.pack("<B", self.num) + self.data
    
    @classmethod
    def decode(cls, script):
        data = script[1:1+cls.num]
        if len(data) != cls.num:
            return None
        return cls(data), script[1+cls.num:]

push_n = """
class OP_PUSH%d(_OP_PUSHN):
    num = %d
"""
for i in range(1,76):
    exec push_n % (i, i)

class OP_PUSHDATA1(_OP_PUSH):
    num = 76
    def encode(self):
        return struct.pack("<BB", self.num, len(self.data)) + self.data
    @classmethod
    def decode(cls, script):
        length = struct.unpack("<B", script[1:2])[0]
        data = script[2:length+2]
        if len(data) != length:
            return None
        return cls(data), script[2+length:]

class OP_PUSHDATA2(_OP_PUSH):
    num = 77
    def encode(self):
        return struct.pack("<BH", self.num, len(self.data)) + data
    @classmethod
    def decode(cls, script):
        length = struct.unpack("<H", script[1:3])[0]
        data = script[3:length+3]
        if len(data) != length:
            return None
        return cls(data), script[3+length:]

class OP_PUSHDATA4(_OP_PUSH):
    num = 78
    def encode(self):
        return struct.pack("<BL", self.num, len(self.data)) + data
    @classmethod
    def decode(cls, script):
        length = struct.unpack("<L", script[1:5])[0]
        data = script[5:length+5]
        if len(data) != length:
            return None
        return cls(data), script[5+length:]
        
def OP_PUSH(data):
    length = len(data)
    if length < 76:
        op = _OP_PUSHN(data)
        op.num = length
    elif length < 2**8-1:
        op = OP_PUSHDATA1(data)
    elif length < 2**16-1:
        op = OP_PUSHDATA2(data)
    elif length < 2**32-1:
        op = OP_PUSHDATA4(data)
    return op

class OP_1NEG(Opcode):
    num = 79
    def eval(self, ctx):
        return ctx.stack.push("\x81")
            
class _OP_NUM(Opcode):
    num = None
    def eval(self, ctx):
        return ctx.stack.push(struct.pack("<B", self.num-0x50))
        
num_n = """
class OP_%d(_OP_NUM):
    num = %d
"""
for i in range(1, 17):
    exec num_n % (i, i+0x50)

class OP_NOP(Opcode):
    num = 97
    def eval(self, ctx):
        return True
class OP_IF(Opcode):
    num = 99
    def may_exec(self, ctx):
        return True
    def eval(self, ctx):
        if not ctx.may_exec():
            ctx.flow_stack.append(False)
        else:
            val = CastToBool(ctx.stack.pop())
            ctx.flow_stack.append(val)
        return True
class OP_NOTIF(Opcode):
    num = 100
    def may_exec(self, ctx):
        return True
    def eval(self, ctx):
        if not ctx.may_exec():
            ctx.flow_stack.append(False)
        else:
            val = CastToBool(ctx.stack.pop())
            ctx.flow_stack.append(not val)
        return True
class OP_ELSE(Opcode):
    num = 103
    def may_exec(self, ctx):
        return True
    def eval(self, ctx):
        ctx.flow_stack[-1] = not ctx.flow_stack[-1]
        return True
class OP_ENDIF(Opcode):
    num = 104
    def may_exec(self, ctx):
        return True
    def eval(self, ctx):
        ctx.flow_stack.pop()
        return True

class OP_VERIFY(Opcode):
    num = 105
    def eval(self, ctx):
        if ctx.stack.top():
            return ctx.stack.pop()
        else:
            return False  
class OP_DROP(Opcode):
    num = 117
    def eval(self, ctx):
        ctx.stack.pop()
        return True
opcode_dict = {}
for op_name, op in locals().items():
    if op_name.startswith("OP_"):
        try:
            opcode_dict[op.num] = op
        except AttributeError:
            pass
            
def decode_script(script):
    ops = []
    while script:
        op_num = struct.unpack("<B", script[0])[0]
        op, script = opcode_dict[op_num].decode(script)
        ops.append(op)
    return ops

def encode_script(ops):
    script = ""
    for op in ops:
        script += op.encode()
    return script
