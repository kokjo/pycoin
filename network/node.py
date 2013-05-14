import eventlet
from eventlet.green import socket
import msgs
import logging
import struct
import traceback
from utils import *

MAGIC_MAINNET = 0xd9b4bef9
NETWORK_MAGIC = MAGIC_MAINNET

log = logging.getLogger(__name__)

class Disconnected(Exception):
    pass
    
class Node:
    def __init__(self, sock):
        self.sock = sock
        self._connected = True
        self.recving_thread = None
        self.connected()
        
    def sendmsg(self, msg):
        log.debug("sending %s to %s", msg.type, repr(self))
        if not self._connected:
            raise Disconnected()
        try: 
            self.sock.send(msgs.Header.serialize(msg))
        except socket.error:
            return self.close("socket closed")

    @property
    def peer_address(self):
        try:
            return self.sock.getpeername()
        except socket.error as e:
            return ("0.0.0.0", 0)
                
    def start_serving(self):
        self.recving_thread = eventlet.spawn_n(self.recv_thread)
        
    def recv_thread(self):
        while self._connected:
            msg = self.recvmsg()
            if msg:
                self.call_handler(msg)
    
    def call_handler(self, msg):
        pass
    def connected(self):
        pass
    def disconnected(self):
        pass
            
    def read(self, size):
        data = ""            
        while size > len(data):
             _ = self.sock.recv(min(size-len(data), 1024))
             if _ == "":
                return self.close("socket closed")
             data += _
        return data
             
    def recvmsg(self):
        header = self.read(24)
        magic, cmd, length, cksum = struct.unpack("<L12sL4s", header)
        cmd = cmd.strip("\x00")
        log.debug("recvived %s from %s", cmd, repr(self))
        
        if magic != NETWORK_MAGIC:
            return self.close("wrong magic")
            
        msg_data = self.read(length)
             
        try:
            msg_type = msgs.msgtable[cmd]
        except KeyError:
            print "unknown command %s" % cmd
            return None
            
        try:
            return msg_type.frombinary(msg_data)[0]
        except Exception as e:
            log.debug("%s: %s", cmd, msg_data.encode("hex"))
            self.close("protocolviolation", error=e)
                        
    def close(self, reason="unknown", error=None):
        if error:
            traceback.print_exc()
        try:
            self.sock.close()
        except socket.error:
            pass
        log.info("%s:%d has disconnected! reason:%s",
          self.peer_address[0], self.peer_address[1], reason)
        self._connected = False
        self.disconnected()
        
class BitcoinNode(Node):
    def __init__(self, sock, server):
        self.server = server
        self.active = False
        self.version_msg = None
        Node.__init__(self, sock)
          
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
        
    def connected(self):
        log.info("connected to %s:%d", self.peer_address[0], self.peer_address[1])
        self.sendmsg(msgs.Version.make())
        if self.server:
            self.server.connected(self)
            
    def disconnected(self):
        log.info("disconnected from %s:%d", self.peer_address[0], self.peer_address[1])
        if self.server:
            self.server.disconnected(self)
        
    def handle_version(self, msg):
        if msg.version < 31900:
            return self.close("to low version %d" % msg.version)
        self.version_msg = msg
        self.sendmsg(msgs.Verack.make())
    
    def call_handler(self, msg):
        if hasattr(self, "handle_" + msg.type):
            return getattr(self, "handle_" + msg.type)(msg)        
        if self.server:
            self.server.call_handler(self, msg)
            
    def __repr__(self):
        return "<Node %s:%d>" % (self.peer_address[0], self.peer_address[1])
    
    def handle_verack(self, msg):
        self.active = True

if __name__ == "__main__":
    import sys
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    node = BitcoinNode.connect_to((sys.argv[1], int(sys.argv[2])), None)
    
    def dump_inv(msg):
        print msg.tojson()
        node.sendmsg(msgs.Getdata.make(msg.objs))
    node.handle_inv = dump_inv
    
    def dump_tx(msg):
        log.info("got tx: %s", h2h(msg.hash))
        print msg.tojson()
    node.handle_tx = dump_tx
    
    def dump_addr(msg):
        print msg.tojson()
    node.handle_addr = dump_addr
    
    old_handle_version = node.handle_version
    def dump_version(msg):
        print msg.tojson()
        old_handle_version(msg)
        
    node.handle_version = dump_version
    while node._connected: eventlet.sleep(1)
