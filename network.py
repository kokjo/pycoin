import socket
import select
import msgs
import jserialize as js
from utils import *
import time
import random
import logging
import eventlet
import struct
import traceback
from eventlet.green import socket
from eventlet import queue
#import debug

log = logging.getLogger("pycoin.network")

MAGIC_MAINNET = 0xd9b4bef9
NETWORK_MAGIC = MAGIC_MAINNET

class Disconnected(Exception):
    pass
    
class Node:
    def __init__(self, sock):
        self.sock = sock
        self.connected = True
        self.outq = queue.Queue()
        self.sending_thread = None
        self.recving_thread = None
        
    def sendmsg(self, msg):
        if not self.connected:
            raise Disconnected()
        self.outq.put(msg)

    @property
    def peer_address(self):
        try:
            return self.sock.getpeername()
        except socket.error as e:
            return ("0.0.0.0", 0)
            
    def send_thread(self):
        while self.connected:
            msg = self.outq.get()
            try: 
                self.sock.send(msgs.Header.serialize(msg))
            except socket.error:
                return self.close("socket closed")
                
    def start_serving(self):
        self.sending_thread = eventlet.spawn_n(self.recv_thread)
        self.recving_thread = eventlet.spawn_n(self.send_thread)
        
    def recv_thread(self):
        while self.connected:
            msg = self.recvmsg()
            if msg:
                self.call_handler(msg)
    
    def call_handler(self, msg):
        pass
    def recvmsg(self):
        header = self.sock.recv(24)
        try:
            magic, cmd, length, cksum = struct.unpack("<L12sL4s", header)
        except struct.error as e:
            return self.close("struct.error", error=e)
        cmd = cmd.strip("\x00")
        
        log.debug("recvmsg: cmd: %s length:%d", cmd, length)
        
        if magic != NETWORK_MAGIC:
            return self.close("wrong magic")
            
        msg_data = ""            
        while length > len(msg_data):
             data = self.sock.recv(min(length-len(msg_data), 1024))
             if data == "":
                return self.close("socket closed")
             msg_data += data
             
        try:
            msg_type = msgs.msgtable[cmd]
        except KeyError:
            print "unknown command %s" % cmd
            return None
            
        try:
            return msg_type.frombinary(msg_data)[0]
        except ProtocolViolation as e:
            log.debug("%s: %s", cmd, msg_data.encode("hex"))
            self.close("protocolviolation", error=e)
                        
    def close(self, reason="unknown", error=None):
        if error:
            traceback.print_exc()
        try:
            self.sock.close()
        except socket.error:
            pass
        log.info("%s:%d has disconnected! reason:%s", self.peer_address[0], self.peer_address[1], reason)
        self.connected = False
        
class BitcoinNode(Node):
    def __init__(self, sock, server):
        Node.__init__(self, sock)
        self.server = server
        self.active = False
        self.sendmsg(msgs.Version.make())#sender=self.server.address, reciever=self.peer_address))
        if self.server:
            self.server.connected(self)
        
    @staticmethod
    def connect_to(addr, server):
        log.info("connecting to %s:%d", *addr)
        sock = socket.socket()
        try:
            sock.connect(addr)
        except socket.error as e:
            log.info("could not connect to %s:%d", *addr)
            return
        node = BitcoinNode(sock, server)
        node.start_serving()
        return node
        
    def close(self, *args, **kwargs):
        if self.server:
            self.server.disconnected(self)
        return Node.close(self, *args, **kwargs)
        
    def handle_version(self, msg):
        if msg.version < 31900:
            return self.close("to low version %d" % msg.version)
        self.sendmsg(msgs.Verack.make())
    
    def call_handler(self, msg):
        if hasattr(self, "handle_" + msg.type):
            return getattr(self, "handle_" + msg.type)(msg)        
        if self.server:
            if hasattr(self.server, "handle_" + msg.type):
                return getattr(self.server, "handle_" + msg.type)(self, msg)
            self.server.call_handler(self, msg)
            
    def __repr__(self):
        return "<Node %s:%d>" % (self.peer_address[0], self.peer_address[1])
    
    def handle_verack(self, msg):
        self.active = True

class BitcoinServer:
    def __init__(self, listensock=None, hosts=[]):
        self.nodes = set()
        self.listensock = listensock
        self.address = msgs.Address.make("127.0.0.1",8335)
        for ip in hosts:
            self.connect_to((ip, 8333))
                    
    def connect_to(self, addr):
        log.info("connection to %s:%d", addr[0], addr[1])
        eventlet.spawn_n(BitcoinNode.connect_to, addr, self)
        
    def connected(self, node):
        log.info("connected to %s:%d", node.peer_address[0], node.peer_address[1])
        self.nodes.add(node)
        node.sendmsg(msgs.Getaddr.make())
        
    def disconnected(self, node):
        log.info("disconnected from %s:%d", node.peer_address[0], node.peer_address[1])
        self.nodes.remove(node)
        
    def call_handler(self, node, msg):
        pass
        
    def handle_addr(self, node, msg):
        for addr in msg.addrs[:5]:
            if len(self.nodes) < 10:
                self.connect_to((addr.ip, addr.port))
            
    def handle_getdata(self, node, msg):
        pass
                    
    def broadcast(self, msg):
        for node in self.nodes:
            node.sendmsg(msg)
            
    def handle_inv(self, node, msg):
        objs = [obj for obj in msg.objs if obj.objtype in (msgs.TYPE_BLOCK, msgs.TYPE_TX)]
        node.sendmsg(msgs.Getdata.make(objs))
            
    def sendrandom(self, msg):
        node = random.choice(self.nodes)
        LOG.debug("sending a %s to %s", msg.type, repr(node))
        node.sendmsg(msg)
            
    def handle_block(self, node, msg):
        blockchain.process_blockmsg(msg)
        inv = msgs.Inv.make([msgs.InvVect.make(msgs.TYPE_BLOCK, msg.block.hash)])
        #self.broadcast(inv)
        
    def handle_tx(self, node, msg):
        inv = msgs.Inv.make([msgs.InvVect.make(msgs.TYPE_TX, msg.hash)])
        #self.broadcast(inv)
    def serve_forever(self):
        while True: 
            eventlet.sleep(10)
            print self.nodes

def start_network():
    global server
hosts = ["127.0.0.1"]

if __name__ == "__main__":
    import blockchain

    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    server = BitcoinServer(hosts=hosts)
    server.serve_forever()
        
