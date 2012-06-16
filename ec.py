import ecdsa
_p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2FL
_r = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141L
_b = 0x0000000000000000000000000000000000000000000000000000000000000007L
_a = 0x0000000000000000000000000000000000000000000000000000000000000000L
_Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798L	
_Gy = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8L	
curve_secp256k1 = ecdsa.ellipticcurve.CurveFp( _p, _a, _b )
generator_secp256k1 = ecdsa.ellipticcurve.Point( curve_secp256k1, _Gx, _Gy, _r )	
oid_secp256k1 = (1,3,132,0,10)	
SECP256k1 = ecdsa.curves.Curve("SECP256k1", curve_secp256k1, generator_secp256k1, oid_secp256k1 )

def load_pubkey(keystr):
    return ecdsa.VerifyingKey.from_string(keystr[1:], curve=SECP256k1)

def load_privkey(keystr):
    return ecdsa.SigningKey.from_string(keystr, curve=SECP256k1)

def generate():
    privatkey = ecdsa.SigningKey.generate(curve=SECP256k1)
    publickey = privatkey.get_verifying_key()
    return privatkey.to_string(), "\x04"+publickey.to_string()
    
def load_sig(signature):
    return signature[:-1], ord(signature[-1:])

def verify_sig(s, h, k):
    key = load_pubkey(k)
    return key.verify_digest(s, h, sigdecode=ecdsa.util.sigdecode_der)
