import eventlet
import eventlet.debug
#eventlet.debug.spew()
DB_HOME = "./db"
DB_KILL_ON_DEADLOCK = False

import scriptindexer
TX_CHECK_SCRIPTS = False

NETWORK_NODES = ["127.0.0.1", "192.168.1.11"]

NEW_TX_HOOKS = [scriptindexer.index_script]

BLOCK_CONFIRM_HOOKS = []
BLOCK_REVERT_HOOKS = []

