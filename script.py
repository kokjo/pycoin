class ScriptError(Exception):
    def __init__(self, err):
        self.err = err
    def __repr__(self):
        return "ScriptError(%s)" % self.err
        
class Stack:
    def __init__(self, initstack=[], maxlen = 10):
        self._stack = initstack
        self._maxlength = 10
    def push(self):    

opcodes = {}
def _add_opcode(opcode):
    opcodes[opcode.num] = opcode
    
class Opcode:
    type = "Unknown"
    num = None
    def eval(self, stack):
        pass
    def __repr__(self):
        return type
    @staticmethod
    def decode(data):
        return Opcode(),data
    def encode(self):
        return chr(num)
        
class OP_0(Opcode):
    type = "OP_0"
    num = 0
    def eval(self, stack):
        stack.push(0)
    @staticmethod
    def decode(data):
        return OP_0(), data[1:]
_add_opcode(OP_0)

class OP_PUSH(Opcode):
    type = "OP_PUSH"
    def __init__(self, value):
        self.type = value.encode("hex")
        self.value = value
    def eval(self, stack):
        stack.push(self.value)
    def encode(self):
        if not self.value:
            return ""
        if len(self.value) < 76:
            return chr(len(self.value))+self.value
        elif len(self.value) < 255:
            return chr(76)+chr(len(self.value))+self.value
for i in range(1,76):
    class _OP_PUSH(Opcode):
        type = "OP_PUSH"
        num = i
        @staticmethod
        def decode(data):
            l = ord(data[0])
            return OP_PUSH(data[1:l+1]),data[l+1:]
    _add_opcode(_OP_PUSH)
    
class Script:
    def __init__(self, data=None):
        self.opcodes = []
        self.decode(data)
    def eval(self, stack):
        for op in self.opcodes:
            op.eval(stack)
    
    def decode(self, data):
        
