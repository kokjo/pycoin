import time
import heapq
import traceback
import logging
LOG = logging.getLogger("pycoin.timerq")
class Timerq:
    def __init__(self, waittime=10):
        self._timers = []
        self.waittime = 10
    
    def add_event(self, timeout, func):
        LOG.debug("new event %s - timeout %d", func.__name__, timeout)
        return self.add_event_abs(timeout + time.time(), func)
    
    def add_event_abs(self, when, func):
        heapq.heappush(self._timers, (when, func))
        return (when, func)
        
    def cancel_event(self, event):
        self._timers.remove(event)
        
    def do_events(self):
        while self._timers and self._timers[0][0] < time.time():
            event = heapq.heappop(self._timers)
            LOG.debug("running func %s", event[1].__name__)
            event[1]()
            
    def wait_for(self):
        if not self._timers:
            return self.waittime
        elif self._timers[0][0] < time.time():
            return 0
        else:
            return self._timers[0][0] - time.time() 
