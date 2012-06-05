import web
from blockchain import Block, Tx, _chains, get_bestblock
from utils import *

def tx_link(tx_h):
    return """<a href="/tx/%s">%s</a>""" % (h2h(tx_h), h2h(tx_h))
def blk_link(blk_h):
    return """<a href="/blockhash/%s">%s</a>""" % (h2h(blk_h), h2h(blk_h))
def chain_name(ch):
    return _chains.get(ch, "unknown")

def get_render():
    return web.template.render('templates', globals={'h2h':h2h, "chain_name":chain_name, "blk_link":blk_link, "tx_link":tx_link, "bits_to_diff":bits_to_diff})
    
class tx:        
    def GET(self, hexhash):
        h = hexhash.decode("hex")[::-1]
        tx = Tx.get_by_hash(h)
        return get_render().tx(tx)
class block:        
    def GET(self, hexhash):
        h = hexhash.decode("hex")[::-1]
        blk = Block.get_by_hash(h)
        return get_render().block(blk)
        
class blocknumber_redirect:        
    def GET(self, number):
        number = int(number)
        blk = Block.get_by_number(number)
        raise web.seeother('/blockhash/%s' % h2h(blk.hash))

class blocknumber_redirect:        
    def GET(self, number):
        number = int(number)
        blk = get_bestblock()
        raise web.seeother('/blockhash/%s' % h2h(blk.hash))


urls = (
    "/tx/(.*)", tx,
    "/blockhash/(.*)", block,
    "/blocknumber/(.*)", blocknumber_redirect,
    "/", bestblock_redirect
)
app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()
