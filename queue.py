import random
rand_id = lambda: random.randint(0, 2**32-1)

class Message(object):
    def __init__(self, msg_data, dest_key, tags, attr, msg_id):
        self.msg_data = msg_data
        self.dest_key = dest_key
        self.tags = tags
        self.attr = attr
        self.msg_id = msg_id
        
class Exchange(object):
    def __init__(self, rule=None):
        self.queues = {}
        self.rule = rule
        
    def route_msg(self, msg):
        if self.rule:
            if not self.rule.fits(msg):
                return
        dest_queues = self.queues.get(msg.dest_key, [])
        for queue in dest_queues:
            queue.route_msg(msg)
            
    def send_msg(self, msg_data, dest_key, tags=[], attr={}, msg_id=None):
        if msg_id == None:
            msg_id = rand_id()
        msg = Message(msg_data, dest_key, tags, attr, msg_id)
        self.route_msg(msg)
        
    def bind_queue(self, queue, dest_key):
        queues = self.queues.get(dest_key, [])
        queues.append(queue)
        self.queues[dest_key] = queues
        queue.add_on_close(lambda: self.unbind_queue(queue, dest_key))
             
    def unbind_queue(self, queue, dest_key):
        queues = self.queues.get(dest_key, [])
        queues.remove(queue)
        self.queues[dest_key] = queues

    def new_queue(self, dest_key):
        q = Queue()
        self.bind_queue(q, dest_key)
        return q
        
class Queue(object):
    def __init__(self, rule=None):
        self.rule = rule
        self.queue = []
        self.on_close = []
    def route_msg(self, msg):
        if self.rule:
            if not self.rule.fits(msg):
                return
        self.handle_msg(msg)
    def handle_msg(self, msg):
        self.queue.append(msg)
    def pop(self):
        return self.queue.pop(0)
    def add_on_close(self, cb):
        self.on_close.append(cb)
    def close(self):
        for cb in self.on_close:
            cb()
        
        
class Rule(object):
    def __call__(self, msg):
        return True
    @property
    def cost(self):
        return 1
        
class AllRule(Rule):
    def __init__(self, *args):
        self.rules = args
    def __call__(self, msg):
        return all(rule(msg) for rule in self.rules)
    @property
    def cost(self):
        return sum(rule.cost for rule in self.rules) + 1
        
class AnyRule(Rule):
    def __init__(self, *args):
        self.rules = args
    def __call__(self, msg):
        return any(rule(msg) for rule in self.rules)
    @property
    def cost(self):
        return sum(rule.cost for rule in self.rules) + 1
                
class NotRule(Rule):
    def __init__(self, rule):
        self.rule = rule
    def __call__(self, msg):
        return not self.rule(msg)
        
class HasTagRule(Rule):
    def __init__(self, tag):
        self.tag = tag
    def __call__(self, msg):
        return self.tag in msg.tags

class AttrMatchRule(Rule):
    def __init__(self, attr, value):
        self.attr = attr
        self.value = value
    def __call__(self, msg):
        return msg.attr.get(self.attr, "") == self.value
        
main_exch = Exchange()
send_msg = main_exch.send_msg
new_queue = main_exch.new_queue
    
