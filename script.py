import struct
import hashlib
def hash160(d):
    sha256 = hashlib.sha256()
    sha256.update(d)
    ripemd160 = hashlib.new("ripemd160")
    ripemd160.update(sha256.digest())
    return ripemd160.digest()
    
class InvalidScript(Exception):
    pass
    
class Engine:
    def __init__(self, script=None):
        self.stack = []
        self.invalid = True
        self.alt_stack = []
        if script:
            self.eval(script)
    def push(self, i):
        self.stack.append(i)
    def pop(self):
        return self.stack.pop()
    def eval(self, script):
        while script != "":
            opcode, script = ord(script[0]), script[1:]
            if opcode == 0:
                self.push("\x00")
            elif 1 <= opcode <= 75:
                data, script = script[:opcode], script[opcode:]
                if len(data) != opcode:
                    raise InvalidScript
                self.push(data)
            elif opcode == 76:
                length, script = struct.unpack("<B", script[0])[0], script[1:]
                data, script = script[:lenght], script[opcode:]
                if len(data) != lenght:
                    raise InvalidScript
            elif opcode == 81:
                self.push("\x01")
            elif 82 <= opcode <= 96:
                self.push(opcode-80)
            elif opcode == 97:
                pass
            elif opcode == 105:
                i = bool(self.pop())
                self.invalid = not i
            elif opcode == 106:
                self.invalid = True
            elif opcode == 107:
                self.alt_stack.append(self.pop())
            elif opcode == 108:
                self.push(self.alt_stack.pop()
            elif opcode == 116:
                self.push(len(self.stack))
            elif opcode == 117:
                self.pop()
            elif opcode == 118:
                i = self.pop()
                self.push(i)
                self.push(i)
            elif opcode == 119:
                i = self.pop()
                self.pop()
                self.push(i)
            elif opcode == 120:
                i = self.pop()
                n = self.pop()
                self.push(n)
                self.push(i)
                self.push(n)
            elif opcode == 169:
                self.push(hash160(self.pop()))
