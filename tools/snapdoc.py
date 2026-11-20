#!/usr/bin/env python3
"""Snapshot doc (GSv inside a decrypted town snapshot .dat) re-serialiser, final8 2026-11-17.

Reader = gparse.Dec2 (external string dictionary refs '<G%d>' = len with bit31, table/array back references =
an id already seen, type 14 = 64 raw bytes). This module adds:
  enc(node)       exact inverse of Dec2 (typed values, uniform key/value types, back refs as id only)
  renumber(root)  one id counter in encode order like the game writer (gsv_renumber.py): new string text ->
                  next id, repeated text -> back reference to the first id; every table/array -> next id;
                  a table/array back reference -> the new id of the object it pointed to.
  load(path)/save(bytes, doc) whole .dat: Blowfish CBC decrypt, header 0x14 bytes, doc at 0x14 (GSv size/crc32),
                  the rest of the payload (terrain etc.) copied verbatim after the doc, zero padding to 8 bytes.
Selftest: python snapdoc.py selftest DIR  -> parse + enc + renumber byte-identical for every snapshot.
"""
import os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gparse, snap  # noqa: E402
from gsv import Node, INT, FLOAT, VEC3, TABLE, STR, ARRAY, I64, NIL, COLOR, BYTES  # noqa: E402


def enc(n, typed=True, out=None):
    out = bytearray() if out is None else out
    if typed:
        out += struct.pack('<H', n.t)
    t = n.t
    if t == INT: out += struct.pack('<i', n.v)
    elif t == FLOAT: out += struct.pack('<f', n.v)
    elif t == VEC3: out += struct.pack('<3f', *n.v)
    elif t == I64: out += struct.pack('<q', n.v)
    elif t == NIL: pass
    elif t == COLOR: out += n.v
    elif t == BYTES: out += struct.pack('<I', len(n.v)) + n.v
    elif t == 14: out += n.v
    elif t == STR:
        out += struct.pack('<I', n.sid)
        if n.new:
            if n.v.startswith('<G') and n.v.endswith('>') and n.v[2:-1].isdigit():
                out += struct.pack('<I', 0x80000000 | int(n.v[2:-1]))
            else:
                raw = n.v.encode('utf-8', 'surrogateescape')
                out += struct.pack('<I', len(raw)) + raw + b'\0'
    elif t in (TABLE, ARRAY):
        out += struct.pack('<I', n.tid)
        if n.kt == 'ref':
            return out
        out += struct.pack('<I', len(n.v))
        if n.v:
            out += struct.pack('<H', n.flags)
            if t == TABLE:
                if n.kt is not None: out += struct.pack('<H', n.kt)
                if n.vt is not None: out += struct.pack('<H', n.vt)
                for k, v in n.v:
                    enc(k, n.kt is None, out); enc(v, n.vt is None, out)
            else:
                if n.vt is not None: out += struct.pack('<H', n.vt)
                for v in n.v:
                    enc(v, n.vt is None, out)
    else:
        raise ValueError('type %r' % t)
    return out


def renumber(root):
    nxt = [1]; seen = {}; objmap = {}

    def w(n):
        if n.t == STR:
            if n.v in seen:
                n.sid, n.new = seen[n.v], False
            else:
                n.sid, n.new = nxt[0], True; seen[n.v] = nxt[0]; nxt[0] += 1
        elif n.t in (TABLE, ARRAY):
            if n.kt == 'ref':
                n.tid = objmap[n.tid]; return
            old = n.tid; n.tid = nxt[0]; nxt[0] += 1
            if old is not None:  # None = object added by an edit (nothing can reference it)
                assert old not in objmap, ('duplicate object id', old)
                objmap[old] = n.tid
            for x in n.v:
                if n.t == TABLE: w(x[0]); w(x[1])
                else: w(x)
    w(root)
    return nxt[0] - 1


def stats(root):
    order = []; S = set(); T = set(); refs_ok = [True]

    def w(n):
        if n.t == STR and n.new:
            order.append(n.sid); S.add(n.sid)
        elif n.t in (TABLE, ARRAY):
            if n.kt == 'ref':
                refs_ok[0] &= n.tid in T; return
            order.append(n.tid); T.add(n.tid)
            for x in n.v:
                if n.t == TABLE: w(x[0]); w(x[1])
                else: w(x)
    w(root)
    ids = S | T
    return {'objects': len(order), 'collisions': len(S & T),
            'non_monotonic': sum(1 for a, b in zip(order, order[1:]) if b != a + 1),
            'dense': ids == set(range(1, len(order) + 1)) and len(ids) == len(order), 'refs_ok': refs_ok[0]}


def doc_bytes(root):
    body = bytes(enc(root))
    return b'GSv\x15' + struct.pack('<II', len(body), zlib.crc32(body) & 0xffffffff) + body


def load(path):
    e = open(path, 'rb').read(); p = snap.dec(e)
    assert snap.enc(p) == e and p[0x14:0x18] == b'GSv\x15'
    size = struct.unpack_from('<I', p, 0x18)[0]
    assert struct.unpack_from('<I', p, 0x1c)[0] == zlib.crc32(p[0x20:0x20 + size]) & 0xffffffff
    root = gparse.parse(p[0x14:0x14 + 12 + size])
    rest = p[0x20 + size:]
    body = rest.rstrip(b'\0')
    return dict(enc=e, plain=p, head=p[:0x14], root=root, size=size, rest=rest, body=body, pad=len(rest) - len(body))


def assemble(head, doc, body, pad=None):
    """pad=None: zero padding to the next multiple of 8 with at least 1 zero (base files: 5..7 zeros)."""
    p = head + doc + body
    if pad is None:
        pad = (-len(p)) % 8 or 8
    p += b'\0' * pad
    assert len(p) % 8 == 0
    return p


def selftest(d):
    ok = True
    for f in sorted(os.listdir(d)):
        s = load(os.path.join(d, f))
        doc = s['plain'][0x14:0x20 + s['size']]
        a = doc_bytes(s['root']) == doc
        st0 = stats(s['root'])
        renumber(s['root'])
        b = doc_bytes(s['root']) == doc
        c = snap.enc(assemble(s['head'], doc_bytes(s['root']), s['body'], s['pad'])) == s['enc']
        c2 = assemble(s['head'], doc, s['body']) == s['plain']
        print(f, 'enc', a, 'renumber', b, 'file', c, 'pad-rule', c2, 'pad', s['pad'], st0)
        ok &= a and b and c and c2
    return ok


if __name__ == '__main__':
    if sys.argv[1] == 'selftest':
        r = True
        for d in sys.argv[2:]:
            r &= selftest(d)
        print('SELFTEST', 'PASS' if r else 'FAIL'); sys.exit(0 if r else 1)
