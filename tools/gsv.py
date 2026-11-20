#!/usr/bin/env python3
"""GSv ('GSv\\x15') table codec for The Tomorrow Children save files (*.gm, IntegralServer local user table).

Format (reverse-engineered from save files, little-endian):
  header: 'GSv\\x15' | u32 size | u32 crc32(body[0:size]) | body | (on-disk .gm: 4-byte trailer kept verbatim)
  body  : one typed value = u16 type + payload
  types : 0 int32 | 1 float32 | 2 vec3 (3x float32) | 4 table | 5 string | 6 array | 7 int64 | 8 nil | 9 color (8 raw bytes) | 13 bytes (u32 len + raw; often an embedded GSv blob)
  string: u32 id; if the id is new in this blob: u32 len + bytes + NUL (later uses are the id only)
  table : u32 id | u32 count | if count: u16 flags (bit0 key type uniform, bit1 value type uniform)
          [u16 ktype if bit0] [u16 vtype if bit1] then count x (key, value); a non-uniform side is u16 type + payload
  array : u32 id | u32 len | if len: u16 flags (bit0 element type uniform) [u16 etype] then len elements
Decode gives a tree of Node objects that remember the byte offset of every scalar, so a field can be patched in place
(same size) and the crc recomputed; encode() re-serialises the whole tree (round trip must be byte-identical).

Usage:
  gsv.py dump FILE [--gm]          print path = value (FILE = .gm or IntegralServer.dat -> local user table)
  gsv.py roundtrip FILE
"""
import struct
import sys
import zlib

MAGIC = b"GSv\x15"
INT, FLOAT, VEC3, TABLE, STR, ARRAY, I64, NIL, COLOR, BYTES = 0, 1, 2, 4, 5, 6, 7, 8, 9, 13


class Node:
    __slots__ = ("t", "v", "off", "sid", "new", "tid", "flags", "kt", "vt")

    def __init__(self, t, v=None, off=None):
        self.t, self.v, self.off = t, v, off
        self.sid = self.new = self.tid = self.flags = self.kt = self.vt = None

    def key(self):
        return self.v if self.t in (STR, INT) else repr(self.v)


class Dec:
    def __init__(self, b, base=0):
        self.b, self.o, self.strs, self.base = b, 0, {}, base

    def u(self, f):
        v = struct.unpack_from("<" + f, self.b, self.o)[0]
        self.o += struct.calcsize("<" + f)
        return v

    def val(self, t=None):
        if t is None:
            t = self.u("H")
        n = Node(t, off=self.o + self.base)
        if t == INT:
            n.v = self.u("i")
        elif t == FLOAT:
            n.v = self.u("f")
        elif t == VEC3:
            n.v = tuple(self.u("f") for _ in range(3))
        elif t == I64:
            n.v = self.u("q")
        elif t == NIL:
            pass
        elif t == COLOR:
            n.v = bytes(self.b[self.o:self.o + 8])
            self.o += 8
        elif t == BYTES:
            ln = self.u("I")
            n.v = self.b[self.o:self.o + ln]
            self.o += ln
        elif t == STR:
            n.sid = self.u("I")
            if n.sid in self.strs:
                n.v, n.new = self.strs[n.sid], False
            else:
                ln = self.u("I")
                raw = self.b[self.o:self.o + ln]
                if self.b[self.o + ln] != 0:
                    raise ValueError("string not NUL-terminated at 0x%x" % self.o)
                self.o += ln + 1
                n.v = raw.decode("utf-8", "surrogateescape")
                n.new = True
                self.strs[n.sid] = n.v
        elif t in (TABLE, ARRAY):
            n.tid = self.u("I")
            cnt = self.u("I")
            n.v = []
            if cnt:
                n.flags = self.u("H")
                if t == TABLE:
                    if n.flags & ~3:
                        raise ValueError("table flags 0x%x at 0x%x" % (n.flags, self.o))
                    n.kt = self.u("H") if n.flags & 1 else None
                    n.vt = self.u("H") if n.flags & 2 else None
                    for _ in range(cnt):
                        k = self.val(n.kt)
                        n.v.append((k, self.val(n.vt)))
                else:
                    if n.flags & ~1:
                        raise ValueError("array flags 0x%x at 0x%x" % (n.flags, self.o))
                    n.vt = self.u("H") if n.flags & 1 else None
                    for _ in range(cnt):
                        n.v.append(self.val(n.vt))
        else:
            raise ValueError("unknown type %d at 0x%x" % (t, self.o - 2 + self.base))
        return n


def enc(n, typed=True, out=None):
    out = bytearray() if out is None else out
    if typed:
        out += struct.pack("<H", n.t)
    t = n.t
    if t == INT:
        out += struct.pack("<i", n.v)
    elif t == FLOAT:
        out += struct.pack("<f", n.v)
    elif t == VEC3:
        out += struct.pack("<3f", *n.v)
    elif t == I64:
        out += struct.pack("<q", n.v)
    elif t == COLOR:
        out += n.v
    elif t == BYTES:
        out += struct.pack("<I", len(n.v)) + n.v
    elif t == STR:
        out += struct.pack("<I", n.sid)
        if n.new:
            raw = n.v.encode("utf-8", "surrogateescape")
            out += struct.pack("<I", len(raw)) + raw + b"\0"
    elif t in (TABLE, ARRAY):
        out += struct.pack("<II", n.tid, len(n.v))
        if n.v:
            out += struct.pack("<H", n.flags)
            if t == TABLE:
                if n.kt is not None:
                    out += struct.pack("<H", n.kt)
                if n.vt is not None:
                    out += struct.pack("<H", n.vt)
                for k, v in n.v:
                    enc(k, n.kt is None, out)
                    enc(v, n.vt is None, out)
            else:
                if n.vt is not None:
                    out += struct.pack("<H", n.vt)
                for v in n.v:
                    enc(v, n.vt is None, out)
    return out


def parse(b):
    """b = whole GSv blob. Returns (root Node, trailer bytes)."""
    if b[:4] != MAGIC:
        raise ValueError("not GSv")
    size, h = struct.unpack_from("<II", b, 4)
    if h != zlib.crc32(b[12:12 + size]) & 0xFFFFFFFF:
        raise ValueError("GSv crc mismatch")
    d = Dec(b[12:12 + size], 12)
    root = d.val()
    if d.o != size:
        raise ValueError("trailing body bytes: parsed %d of %d" % (d.o, size))
    return root, b[12 + size:]


def build(root, trailer):
    body = bytes(enc(root))
    return MAGIC + struct.pack("<II", len(body), zlib.crc32(body) & 0xFFFFFFFF) + body + trailer


def walk(n, path=""):
    """Yield (path, node) for every scalar; embedded GSv blobs (BYTES or STR starting with GSv) are walked too."""
    if n.t == TABLE:
        for k, v in n.v:
            yield from walk(v, path + "." + str(k.key()))
    elif n.t == ARRAY:
        for i, v in enumerate(n.v):
            yield from walk(v, "%s[%d]" % (path, i))
    else:
        yield path, n


def items(n):
    return {k.key(): v for k, v in n.v} if n.t == TABLE else {}


def get(n, *path):
    for p in path:
        n = items(n)[p] if isinstance(p, str) else n.v[p]
    return n


def main():
    cmd, fn = sys.argv[1], sys.argv[2]
    b = open(fn, "rb").read()
    if b[:4] != MAGIC:
        sys.path.insert(0, __import__("os").path.dirname(__file__))
        import ttc_save
        b = ttc_save.decode(b)["local_gsv"]
    root, tr = parse(b)
    if cmd == "roundtrip":
        ok = build(root, tr) == b
        print("roundtrip byte-identical:", ok)
        return 0 if ok else 1
    for p, n in walk(root):
        v = n.v
        if isinstance(v, (bytes, bytearray)):
            v = "<%d bytes%s>" % (len(v), " GSv" if v[:4] == MAGIC else "")
        elif isinstance(v, str) and len(v) > 80:
            v = v[:80] + "..."
        print("%-70s %s %r" % (p, {0: "i", 1: "f", 2: "v3", 13: "b", 5: "s", 7: "q", 8: "nil", 9: "c8"}.get(n.t, n.t), v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
