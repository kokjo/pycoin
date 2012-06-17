import network
import blockchain
import transactions
import msgs
import eventlet
from utils import *

class Downloader(object):
    def __init__(self, server):
        self.server = server
        self.downloading = set()
        self.oprhans = set()
        self.missing = {}
        self.want = set()
        self.invs = set()
        self.server.add_handler("inv", self.handle_inv)
        self.server.add_handler("block", self.handle_block)
        self.server.add_handler("tx", self.handle_tx)
        
        eventlet.spawn_n(self.flush_inv_thread)
        eventlet.spawn_n(self.download_blocks)
        eventlet.spawn_n(self.find_missing)
        
    def flush_inv_thread(self):
        while True:
            if self.invs:
                msg = msgs.Inv.make(self.invs)
                self.server.broadcast(msg)
                self.invs = set()
            eventlet.sleep(15)
    
    def find_missing(self):
        while True:
            for h in self.want:
                obj = msgs.InvVect.make(msgs.TYPE_BLOCK, h)
                self.download_objs([obj], self.server.sendrandom)
            eventlet.sleep(10)
            
    def download_blocks(self):
        while True:
            bestblock = blockchain.get_bestblock()
            msg = msgs.Getblocks.make([bestblock.hash])
            self.server.sendrandom(msg)
            eventlet.sleep(15)
    
    def cancel_download(self, h):
        try:
            self.downloading.remove(h)
        except KeyError:
            pass
            
    def download_objs(self, objs, sendfunc):
        objs_to_download = set()
        for obj in objs:
            if obj not in self.downloading:
                self.downloading.add(obj.hash)
                eventlet.spawn_after(5, self.cancel_download, obj.hash)
                objs_to_download.add(obj)
        sendfunc(msgs.Getdata.make(objs_to_download))
        
    def handle_inv(self, node, msg):
        objs = set()
        for obj in msg.objs:
            if obj.objtype == msgs.TYPE_TX:
                if transactions.Tx.exist(obj.hash):
                    continue
            if obj.objtype == msgs.TYPE_BLOCK:
                if blockchain.Block.exist_by_hash(obj.hash):
                    continue
            objs.add(obj)
        self.download_objs(objs, node.sendmsg)
    
    def check_missing(self, h):
        blkmsg = self.missing.pop(h, None)
        while blkmsg:
            blockchain.process_blockmsg(blkmsg)
            blkmsg = self.missing.pop(blkmsg.block.hash, None)
    
    def got_blkmsg(self, h):
        try:
            self.downloading.remove(h)
        except KeyError:
            pass
        try:
            self.want.remove(h)
        except KeyError:
            pass
    
    def handle_block(self, node, msg):
        self.got_blkmsg(msg.block.hash)
        if blockchain.Block.exist_by_hash(msg.block.hash):
            return
        if blockchain.Block.exist_by_hash(msg.block.prev):
            blockchain.process_blockmsg(msg)
            self.check_missing(msg.block.hash)
        else:
            self.missing[msg.block.prev] = msg
            self.want.add(msg.block.prev)
    
    def handle_tx(self, node, msg):
        try:
            self.downloading.remove(msg.hash)
        except KeyError:
            pass
        self.invs.add(msgs.InvVect.make(msgs.TYPE_TX, msg.hash))
        print "downloaded tx %s" % h2h(msg.hash)
        transactions.Tx.get_or_make(msg)
        
