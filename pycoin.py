#!/usr/bin/python
import network
import SocketServer
class Pycoin(SocketServer.ThreadedTCPServer):
    daemon_threads = True
    def finish_request(request, client_address):
        

try:
    network.mainloop()
finally:
    pass
