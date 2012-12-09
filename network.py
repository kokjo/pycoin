import msgs
from utils import *
import time
import random
import logging
import struct
import traceback
import eventlet
from eventlet.green import socket
from eventlet import queue
import blockchain

import settings

log = logging.getLogger("pycoin.network")

MAGIC_MAINNET = 0xd9b4bef9
NETWORK_MAGIC = MAGIC_MAINNET

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
        self.sendmsg(msgs.Version.make())#sender=self.server.address, reciever=self.peer_address))
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

class BitcoinServer:
    def __init__(self, listensock=None, hosts=[]):
        self.nodes = set()
        self.listensock = listensock
        self.address = msgs.Address.make("127.0.0.1", 8335)
        self.handlers = {}
        for ip in hosts:
            self.connect_to((ip, 8333))
                    
    def connect_to(self, addr):
        eventlet.spawn_n(BitcoinNode.connect_to, addr, self)
        
    def connected(self, node):
        self.nodes.add(node)
        node.sendmsg(msgs.Getaddr.make())
        
    def disconnected(self, node):
        log.info("disconnected from %s:%d", node.peer_address[0], node.peer_address[1])
        self.nodes.remove(node)
        
    def add_handler(self, msgtype, handler):
        handlers = self.handlers.get(msgtype, set())
        handlers.add(handler)
        self.handlers[msgtype] = handlers
        
    def call_handler(self, node, msg):
        handler = getattr(self, "handle_" + msg.type, None)
        if handler:
            handler(node, msg)

        for handler in self.handlers.get(msg.type, set()):
            handler(node, msg)
            
    def handle_addr(self, node, msg):
        for addr in msg.addrs[:5]:
            if len(self.nodes) < 100:
                self.connect_to((addr.ip, addr.port))
                    
    def broadcast(self, msg):
        for node in self.nodes:
            node.sendmsg(msg)
            
    def sendrandom(self, msg):
        try:
            node = random.choice(list(self.nodes))
        except IndexError:
            return
        log.debug("sending a %s to %s", msg.type, repr(node))
        node.sendmsg(msg)
        
    def serve(self):
        while True: 
            if self.listensock:
                sock, addr = self.listensock.accept()
                node = BitcoinNode(sock, self)
                node.start_serving()
            else:
                eventlet.sleep(10)


def start_network(hosts=["127.0.0.1", "192.168.1.11"]):
    server = BitcoinServer(hosts=hosts)
    eventlet.spawn_n(server.serve)
    return server
    
if __name__ == "__main__":
    import debug
    import chaindownloader
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    server = start_network(settings.NETWORK_NODES)
    dl = chaindownloader.Downloader(server)
    debug.debug_locals["server"] = server
    debug.debug_locals["dl"] = dl
    while True:
        if len(server.nodes)<10:
            server.sendrandom(msgs.Getaddr.make())
        eventlet.sleep(1)
