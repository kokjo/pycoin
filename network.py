import socket
import select
import json
import msgs
import timerq
import threading
import jserialize as js
from utils import *
import genesisblock
import time
import bsddb
import random
import logging
#import debug
LOG = logging.getLogger("pycoin.network")

class NodeDisconnected(Exception):
    def __init__(self, reason=""):
        self.reason = reason
    def __repr__(self):
        return "NodeDisconnected(%s)" % self.reason
        
class Node:
    def __init__(self, sock):
        self.socket = sock
        self.outbuf = ""
        self.inbuf = ""
        self.hdr = None
        self.connected = False
        self.dead = False

    def fileno(self):
        return self.socket.fileno()
        
    def want_write(self):
        return self.outbuf != ""
        
    def sendmsg(self, msg):
        self.outbuf += msgs.Header.serialize(msg)
    
    def init(self):
        try:
            peer_addr = self.socket.getpeername() 
        except:
            self.close("never connected")
        self.peer_address = msgs.Address.make(*peer_addr)
        self.connected = True
        self.on_init()
                
    def _write(self):
        if self.dead:
            return
        if not self.connected:
            self.init()
        if self.outbuf:
            try:
                bytessent = self.socket.send(self.outbuf)
                self.outbuf = self.outbuf[bytessent:]
            except:
                self.close("write failed")

    def _read(self):
        if self.dead:
            return
        if not self.connected:
            self.init()
        try:
            data = self.socket.recv(1024)
        except:
            self.close("read failed")
        if data == "":
            self.close("peer shutdown")
        self.inbuf += data
        if not self.hdr:
            if len(self.inbuf) >= 24:
                try:
                    self.hdr,self.inbuf = msgs.Header(self.inbuf[:24]), self.inbuf[24:]
                except ProtocolViolation as e:
                    self.close(repr(e))
            else:
                return
        if len(self.inbuf) < self.hdr.len:
            return
        try:
            msg, self.inbuf = self.hdr.deserialize(self.inbuf[:self.hdr.len]), self.inbuf[self.hdr.len:]
        except ProtocolViolation as e:
            self.close(repr(e))
        self.hdr = None
        self.call_handler(msg)

    def call_handler(self, msg):
        if hasattr(self, "handle_" + msg.type):
            getattr(self, "handle_" + msg.type)(msg)
        elif hasattr(self.server, "handle_" + msg.type):
            getattr(self.server, "handle_" + msg.type)(self, msg)
            
    def close(self, reason="unknown"):
        self.on_close(reason)
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass # There is no guarantee that we were ever connected
        self.socket.close()
        self.dead = True
        raise NodeDisconnected(reason)

class BitcoinNode(Node):
    def __init__(self, server=None, *args, **kwargs):
        Node.__init__(self, *args, **kwargs)
        self.server = server
        self.active = False
        self.peer_address = msgs.Address.make("0.0.0.0",8333)
        self.sendmsg(msgs.Version.make(sender=self.server.address, reciever=self.peer_address))
    
    def on_init(self):
        pass
    
    def on_close(self, reason):
        pass
            
    def handle_version(self, msg):
        if msg.version < 31900:
            self.close("to low version %d" % msg.version)
        self.sendmsg(msgs.Verack.make())
    
    def __repr__(self):
        return "<Node %s:%d - %s>" %(self.peer_address.ip, self.peer_address.port, self.active and "Active" or "Inactive")
    
    def handle_verack(self, msg):
        self.active = True
        self.server.node_connected(self)

class BitcoinServer:
    def __init__(self, listen_sock=None, hosts=[], txs={}, chain=None):
        self.nodes = []
        self.txs = txs
        self.chain = chain
        if listen_sock:
            self.listeners = [listen_sock]
        else:
            self.listeners = []
        self.addrs = set()
        self.timers = timerq.Timerq()
        self.address = msgs.Address.make("127.0.0.1",833)
        for h in map(lambda h: (h, 8333), hosts):
            self.check_host(h)
        self.timers.add_event(15, self.search_for_missing_blocks)
        self.timers.add_event(30, self.sync_dbs)
    def sync_dbs(self):
        self.chain.chain.sync()
        self.chain.txs.sync()
        self.timers.add_event(30, self.sync_dbs)
    def serve_forever(self):
        while self.nodes:
            want_write = filter(lambda n: n.want_write(), self.nodes)
            read, write, _ = select.select(self.nodes+self.listeners, want_write, [], self.timers.wait_for())
            self.timers.do_events()
            for n in read:
                if n in self.listeners:
                    sock = n.accept()[0]
                    sock.setblocking(False)
                    node = BitcoinNode(self, sock)
                    self.nodes.append(node)
                else:
                    try:
                        n._read()
                    except NodeDisconnected as e:
                        self.nodes.remove(n)
            for n in write:
                try:
                    n._write()
                except NodeDisconnected as e:
                    self.nodes.remove(n)
                    
    def node_connected(self, node):
        LOG.info("connected to %s", node.peer_address.ip)
        node.sendmsg(msgs.Getaddr.make())
        
    def handle_addr(self, node, msg):
        for addr in msg.addrs:
            self.check_host((addr.address.ip, addr.address.port))
            
    def check_host(self, addr):
        self.addrs.add(addr)
        if len(self.nodes) < 100:
            sock = socket.socket()
            sock.setblocking(False)
            try:
                sock.connect(addr)
            except:
                pass
            node = BitcoinNode(self, sock)
            self.nodes.append(node)
            
    def handle_getdata(self, node, msg):
        for obj in msg.objs:
            if obj.objtype == msgs.TYPE_TX:
                if obj.hash in self.txs:
                    msg = msgs.Tx.frombinary(self.txs[obj.hash])[0]
                    node.sendmsg(msg)
                    
    def search_for_missing_blocks(self):
        self.sendrandom(msgs.Getblocks.make([self.chain.bestblock.hash]))
        for blk in self.chain.missing_blocks:
            self.sendrandom(msgs.Getdata.make([msgs.InvVect.make(msgs.TYPE_BLOCK, blk)]))
        self.timers.add_event(5, self.search_for_missing_blocks)
        
    def broadcast(self, msg):
        for node in self.nodes:
            node.sendmsg(msg)
            
    def handle_inv(self, node, msg):
        objs = [obj for obj in msg.objs if obj.objtype == msgs.TYPE_BLOCK and not self.chain.has_block(obj.hash)]
        node.sendmsg(msgs.Getdata.make(objs))
            
    def sendrandom(self, msg):
        active_nodes = filter(lambda n: n.active, self.nodes)
        if not active_nodes:
            LOG.debug("no nodes connected, not sending %s", msg.type)
            return
        node = random.choice(active_nodes)
        LOG.debug("sending a %s to %s", msg.type, repr(node))
        node.sendmsg(msg)
            
    def handle_block(self, node, msg):
        self.chain.add_block(msg)
        inv = msgs.Inv.make([msgs.InvVect.make(msgs.TYPE_BLOCK, msg.block.hash)])
        self.broadcast(inv)
        
    def handle_tx(self, node, msg):
        self.chain.add_tx(msg)
        inv = msgs.Inv.make([msgs.InvVect.make(msgs.TYPE_TX, msg.hash)])
        self.broadcast(inv)
            
hosts = ["127.0.0.1"]
if __name__ == "__main__":
    import blockchain

    logging.basicConfig(format='%(name)s - %(message)s', level=logging.DEBUG)
    chain = blockchain.BlockChain()
    server = BitcoinServer(hosts=hosts, chain=chain)
    server.serve_forever()
        
