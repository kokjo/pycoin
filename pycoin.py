#!/usr/bin/python
import network
import threading
import blockchain
import code
import logging
import socket
import sys

#logging.basicConfig(format='%(name)s - %(message)s', level=logging.INFO)

chain = blockchain.BlockChain()
server = network.BitcoinServer(hosts=["127.0.0.1"], chain=chain)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.daemon = True
server_thread.start()        

def console():
    d = {"chain":chain, "server":server}
    console = code.InteractiveConsole(d)
    console.interact()
    
console_thread = threading.Thread(target=console)
console_thread.daemon = True
console_thread.start()

console_thread.join()

