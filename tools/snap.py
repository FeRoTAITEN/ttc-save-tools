"""Blowfish-CBC layer of TOWN snapshot files (needs pycryptodome)."""
from Crypto.Cipher import Blowfish
K = b'7&78fJ4d'
IV = b'Z%)kj<4w'


def dec(b): return Blowfish.new(K, Blowfish.MODE_CBC, IV).decrypt(b)
def enc(b): return Blowfish.new(K, Blowfish.MODE_CBC, IV).encrypt(b)
