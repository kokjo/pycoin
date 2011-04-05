import collections

import status
import msgs

try:
    requestq = status.state.requestq
except:
    requestq = collections.deque()
    status.state.requestq = requestq

# No point maintaining this beyond
failed_requests = collections.defaultdict(set)

def add(iv):
    requestq.appendleft(iv)

def add_lots(ivs):
    requestq.extendleft(ivs)

def pop(ip):
    "Return a suitable request iv for this ip, None otherwise"
    otherlist = []
    while len(requestq):
        if ip in failed_requests[requestq[-1]]:
            # We didn't get this last time we asked, let's not try again
            otherlist.append(requestq.pop())
        else:
            iv = requestq.pop()
            requestq.extend(reversed(otherlist))
            return iv
    return None

def no_reply(ip, iv, failed):
    """We didn't get a reply to our getblocks for this. If failed is True,
       it was due to a timeout (they probably don't have it) rather than an
       unrelated connection shutdown"""
    requestq.append(iv)
    if failed:
        failed_requests[iv].add(ip)
