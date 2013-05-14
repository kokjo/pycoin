import msgs
import settings
from utils import *

from node import BitcoinNode

import random
import logging
import struct
import traceback
import eventlet
from eventlet.green import socket
from eventlet import queue

log = logging.getLogger(__name__)

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
        for addr in msg.addrs:
            if addr.ip not in self.known_addresses:
                if len(self.nodes) < settings.NETWORK_MAXNODES:
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


def start_network(hosts=[]):
    server = BitcoinServer(hosts=hosts)
    eventlet.spawn_n(server.serve)
    return server
    
if __name__ == "__main__":
    import debug
    #import chaindownloader
    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    server = start_network(settings.NETWORK_NODES)
    #dl = chaindownloader.Downloader(server)
    debug.debug_locals["server"] = server
    #debug.debug_locals["dl"] = dl
    while True:
        if len(server.nodes) < 10:
            server.sendrandom(msgs.Getaddr.make())
        eventlet.sleep(10)
