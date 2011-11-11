#!/usr/bin/python
import network
import threading
import blockchain
import code
import logging
logging.basicConfig(format='%(name)s - %(message)s', level=logging.INFO)

chain = blockchain.BlockChain()
server = network.BitcoinServer(hosts=["127.0.0.1"], chain=chain)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.run()

class SocketConsole(code.InteractiveConsole):
    def __init__(self, locals, socket):
        code.InteractiveConsole.__init__(self, locals)
        self._file = socket.makefile("rw")
    def raw_input(p=""):
        self._file.write(p)
        return self._file.readline()

def console_thread(s):
    d = {"chain":chain, "server":server}
    console = SocketConsole(d, s)
    console.interact()

sock  = socket.socket()
sock.bind("127.0.0.1", 7777)
sock.listen(5)
while True:
    try:
        s,a = sock.accept()
        th = threading.Thread(target=lambda : console_thread(s))
        th.run()
    except:
        break
