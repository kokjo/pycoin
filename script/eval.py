import opcodes
import bignum

class Stack(object):
    def __init__(self):
        self.stack = []
    def push(self, v):
        self.stack.append(v)
        return True
    def pop(self):
        return self.stack.pop()
    def pop2(self):
        return self.stack.pop(), self.stack.pop()
    def top(self):
        return self.stack[-1]

class SimpleContext(object):
    def __init__(self, in_script=None, out_script=None):
        self.stack = Stack()
        if in_script:
            self.in_ops = opcodes.decode_script(in_script)
        if out_script:
            self.out_ops = opcodes.decode_script(out_script)
        self.flow_stack = []
    
    def may_exec(self):
        return all(self.flow_stack)
    def eval_in(self):
        for op in self.in_ops:
            if op.may_exec(self):
                if not op.eval(self):
                    return False
        return True
    def eval_out(self):
        for op in self.out_ops:
            if op.may_exec(self):
                if not op.eval(self):
                    return False
        return True
    def eval(self):
        return self.eval_in() and self.eval_out()
    def op_checksig(self, key, sig):
        return False
class Context(SimpleContext):
    def __init__(self, to_tx, from_tx, to_idx, from_idx):
        self.to_tx = to_tx
        self.from_tx = from_tx
        self.to_idx = to_idx
        self.from_idx = from_idx
        self.in_script = to_tx.inputs[to_idx].script
        self.out_script = from_tx.outputs[from_idx].script
        SimpleContext.__init__(self.in_script, self.out_script)
