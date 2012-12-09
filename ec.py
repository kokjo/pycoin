import ctypes
import ctypes.util

ssl = ctypes.cdll.LoadLibrary(ctypes.util.find_library('ssl') or 'libeay32')

# this specifies the curve used with ECDSA.
NID_secp256k1 = 714 # from openssl/obj_mac.h

# Thx to Sam Devlin for the ctypes magic 64-bit fix.
def check_result (val, func, args):
    if val == 0:
        raise ValueError
    else:
        return ctypes.c_void_p (val)

ssl.EC_KEY_new_by_curve_name.restype = ctypes.c_void_p
ssl.EC_KEY_new_by_curve_name.errcheck = check_result

class Key:
    def __init__(self):
        self.POINT_CONVERSION_COMPRESSED = 2
        self.POINT_CONVERSION_UNCOMPRESSED = 4
        self.k = ssl.EC_KEY_new_by_curve_name(NID_secp256k1)
        self.set_compressed(True)
        
    def __del__(self):
        if ssl:
            ssl.EC_KEY_free(self.k)
        self.k = None

    def __generate(self, secret=None):
        if secret:
            self.prikey = secret
            priv_key = ssl.BN_bin2bn(secret, 32, ssl.BN_new())
            group = ssl.EC_KEY_get0_group(self.k)
            pub_key = ssl.EC_POINT_new(group)
            ctx = ssl.BN_CTX_new()
            ssl.EC_POINT_mul(group, pub_key, priv_key, None, None, ctx)
            ssl.EC_KEY_set_private_key(self.k, priv_key)
            ssl.EC_KEY_set_public_key(self.k, pub_key)
            ssl.EC_POINT_free(pub_key)
            ssl.BN_CTX_free(ctx)
            return self.k
        else:
            return ssl.EC_KEY_generate_key(self.k)

    def __set_privkey(self, key):
        self.mb = ctypes.create_string_buffer(key)
        ssl.d2i_ECPrivateKey(ctypes.byref(self.k), ctypes.byref(ctypes.pointer(self.mb)), len(key))

    def __set_pubkey(self, key):
        self.mb = ctypes.create_string_buffer(key)
        ssl.o2i_ECPublicKey(ctypes.byref(self.k), ctypes.byref(ctypes.pointer(self.mb)), len(key))
    
    @classmethod
    def generate(cls, secret=None, compressed=True):
        key = cls()
        key.__generate(secret)
        key.set_compressed(conpressed)
        return key
    
    @classmethod
    def from_privkey(cls, keybuf):
        key = cls()
        key.__set_privkey(keybuf)
        return key
    
    @classmethod
    def from_pubkey(cls, keybuf):
        key = cls()
        key.__set_pubkey(keybuf)
        return key
    
    def get_privkey(self):
        size = ssl.i2d_ECPrivateKey(self.k, 0)
        mb_pri = ctypes.create_string_buffer(size)
        ssl.i2d_ECPrivateKey(self.k, ctypes.byref(ctypes.pointer(mb_pri)))
        return mb_pri.raw

    def get_pubkey(self):
        size = ssl.i2o_ECPublicKey(self.k, 0)
        mb = ctypes.create_string_buffer(size)
        ssl.i2o_ECPublicKey(self.k, ctypes.byref(ctypes.pointer(mb)))
        return mb.raw

    def get_secret(self):
        privkey = self.get_privkey()
        if len(privkey) == 279:
            return privkey[9:32+9]
        elif len(privkey) == 214:
            return privkey[8:32+8]
        
    def sign(self, hash):
        sig_size = ssl.ECDSA_size(self.k)
        mb_sig = ctypes.create_string_buffer(sig_size)
        sig_size0 = ctypes.POINTER(ctypes.c_int)()
        assert 1 == ssl.ECDSA_sign(0, hash, len(hash), mb_sig, ctypes.byref(sig_size0), self.k)
        return mb_sig.raw

    def verify(self, hash, sig):
        return ssl.ECDSA_verify(0, hash, len(hash), sig, len(sig), self.k) == 1

    def set_compressed(self, compressed):
        if compressed:
            form = self.POINT_CONVERSION_COMPRESSED
        else:
            form = self.POINT_CONVERSION_UNCOMPRESSED
        ssl.EC_KEY_set_conv_form(self.k, form)
        
    def get_compressed(self):
        return ssl.EC_KEY_get_conv_form(self.k) == self.POINT_CONVERSION_COMPRESSED

def load_pubkey(keystr):
    return ecdsa.VerifyingKey.from_string(keystr[1:], curve=SECP256k1)

def load_privkey(keystr):
    return ecdsa.SigningKey.from_string(keystr, curve=SECP256k1)

def generate():
    privatkey = ecdsa.SigningKey.generate(curve=SECP256k1)
    publickey = privatkey.get_verifying_key()
    return privatkey.to_string(), "\x04"+publickey.to_string()
    
def from_secret(sec):
    secret = ecdsa.ecdsa.string_to_int(sec)
    privatkey = ecdsa.SigningKey.from_secret_exponent(secret, curve=SECP256k1)
    publickey = privatkey.get_verifying_key()
    return privatkey.to_string(), "\x04"+publickey.to_string()

def load_sig(signature):
    return signature[:-1], ord(signature[-1:])

def verify_sig(s, h, k):
    key = load_pubkey(k)
    return key.verify_digest(s, h, sigdecode=ecdsa.util.sigdecode_der)
