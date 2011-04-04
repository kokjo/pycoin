import time
import heapq
import itertools

import network

_timers = []
counter = itertools.count()

def add_event(when, func):
    add_event_abs(when + time.time(), func)

def add_event_abs(when, func):
    heapq.heappush(_timers, (when, next(counter), func))

def do_events():
    while _timers and _timers[0][0] < time.time():
        try:
            heapq.heappop(_timers)[2]()
        except network.NodeDisconnected:
            pass 

def wait_for():
    if not _timers:
        return 2**32-1
    elif _timers[0][0] < time.time():
        return 0
    else:
        return _timers[0][0] - time.time()
