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
        #print msg.tojson()
        self.outbuf += msgs.Header.serialize(msg)
    
    def init(self):
        try:
            peer_addr = self.socket.getpeername() 
        except:
            self.close("never connected")
        self.peer_address = msgs.Address.make(peer_addr[0], peer_addr[1])
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
            if len(self.inbuf) >= 20:
                try:
                    self.hdr,self.inbuf = msgs.Header(self.inbuf[:20]), self.inbuf[20:]
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
    
    def on_init(self):
        self.sendmsg(msgs.Version.make(sender=self.server.address, reciever=self.peer_address))
    
    def on_close(self, reason):
        pass
            
    def handle_version(self, msg):
        if msg.version < 31900:
            self.close("to low version %d" % msg.version)
        self.sendmsg(msgs.Verack.make())
        
    def handle_verack(self, msg):
        self.active = True
        self.server.node_connected(self)
        
    def handle_addr(self, msg):
        self.server.handle_addr(self, msg)
    def handle_inv(self, msg):
        self.sendmsg(msgs.Getdata.make(msg.objs))
    def handle_tx(self, msg):
        self.server.handle_tx(self, msg)

class BitcoinServer:
    def __init__(self, listen_sock=None, hosts=[], txs={}, blocks={}):
        self.nodes = []
        self.txs = txs
        self.blocks = blocks
        if listen_sock:
            self.listeners = [listen_sock]
        else:
            self.listeners = []
        self.addrs = set()
        self.timers = timerq.Timerq()
        self.address = msgs.Address.make("127.0.0.1",8333)
        for h in map(lambda h: (h, 8333), hosts):
            self.check_host(h) 
            
    def serve_forever(self):
        while self.nodes:
            want_write = filter(lambda n: n.want_write(), self.nodes)
            read, write, _ = select.select(self.nodes+self.listeners, want_write, [], self.timers.wait_for())
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
                    
    def broadcast(self, msg):
        for node in self.nodes:
            node.sendmsg(msg)
            
    def check_tx(self, node, tx_hash):
        if tx_hash not in self.txs:
            pass
            
    def sendrandom(self, msg):
        random.choice(filter(lambda n: n.active, self.nodes)).sendmsg(msg)
        
    def check_block(self, node, block_hash):
        if block_hash not in self.blocks:
            print "missing block:%s fetching" % block_hash[::-1].encode("hex")
            msg = msgs.Getdata.make([msgs.InvVect.make(msgs.TYPE_BLOCK, block_hash)])
            self.sendrandom(msg)
            
    def handle_block(self, node, msg):
        if msg.block.hash not in self.blocks:
            aux = msgs.BlockAux.make(msg)
            self.blocks[aux.block.hash] = aux.tobinary()
            self.blocks.sync()
            self.check_block(node, aux.block.prev)
            for tx in msg.txs:
                self.handle_tx(node, tx)
            print "block: %s" % msg.block.hash[::-1].encode("hex")

    def handle_tx(self, node, msg):
        if msg.hash not in self.txs:
            self.txs[msg.hash] = msg.tobinary()
            self.txs.sync()
            for tx_in in msg.inputs:
                 self.check_tx(node, tx_in.outpoint.tx)
            out_sum = sum(map(lambda x: x.amount, msg.outputs))
            #print "tx: %s - %d" % (msg.hash[::-1].encode("hex"), out_sum)
            
            inv = msgs.Inv.make([msgs.InvVect.make(msgs.TYPE_TX, msg.hash)])
            self.broadcast(inv)
            
hosts = ["127.0.0.1", "2.107.239.140", "46.4.121.102", "67.164.37.225", "66.94.195.139", "24.99.68.115", "24.253.68.233", "50.89.218.105"]
if __name__ == "__main__":
    txs = bsddb.btopen("tx.db")
    blocks = bsddb.btopen("block.db")
    server = BitcoinServer(hosts=hosts, txs=txs, blocks=blocks)
    server.serve_forever()
        
