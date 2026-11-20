#!/usr/bin/env python3
"""Independent City.bin integrity model for TTC CUSA28033 (written 2026-11-16, derived from eboot + data).

Checksums (code evidence in notes/FINDINGS.md entry 2026-11-16):
  T  whole-file trailer: u32 LE = lookup3 hashlittle(file[:-4], initval 0)   (eboot fn 0xe7cd10 -> 0xe6d770)
  D  per GSv document: 'GSv\x15' u32 size u32 crc32(body[size])             (eboot 0xcb8f80 + VerifyCrc 0xe79b80)
  B  per entry blob: blob = doc + u32 crc32(doc, whole doc incl. 12-byte header) + 0d 0a   (writer 0xb085a0, plain crc32)
     preceded by u32 blob_len = len(doc)+6.
crc32 = zlib crc32. Reader-side stream crc maps a result of 0xb00b1ee5 to 0xb00b1ee6 and treats a stored 0xb00b1ee5 as 'skip'.
"""
import struct, zlib, re, sys

M32 = 0xffffffff
def rot(x, k): return ((x << k) | (x >> (32 - k))) & M32

def hashlittle(data, initval=0):
    n = len(data)
    a = b = c = (0xdeadbeef + n + initval) & M32
    i = 0
    def mix(a, b, c):
        a = (a - c) & M32; a ^= rot(c, 4);  c = (c + b) & M32
        b = (b - a) & M32; b ^= rot(a, 6);  a = (a + c) & M32
        c = (c - b) & M32; c ^= rot(b, 8);  b = (b + a) & M32
        a = (a - c) & M32; a ^= rot(c, 16); c = (c + b) & M32
        b = (b - a) & M32; b ^= rot(a, 19); a = (a + c) & M32
        c = (c - b) & M32; c ^= rot(b, 4);  b = (b + a) & M32
        return a, b, c
    unpack = struct.Struct('<III').unpack_from
    while n - i > 12:
        x, y, z = unpack(data, i)
        a = (a + x) & M32; b = (b + y) & M32; c = (c + z) & M32
        a, b, c = mix(a, b, c)
        i += 12
    rem = data[i:] + b'\0' * 12
    if n - i == 0:
        return c
    x, y, z = struct.unpack_from('<III', rem, 0)
    a = (a + x) & M32; b = (b + y) & M32; c = (c + z) & M32
    # final
    c ^= b; c = (c - rot(b, 14)) & M32
    a ^= c; a = (a - rot(c, 11)) & M32
    b ^= a; b = (b - rot(a, 25)) & M32
    c ^= b; c = (c - rot(b, 16)) & M32
    a ^= c; a = (a - rot(c, 4)) & M32
    b ^= a; b = (b - rot(a, 14)) & M32
    c ^= b; c = (c - rot(b, 24)) & M32
    return c

def crc32(b): return zlib.crc32(b) & M32

def entries(d):
    """Return list of dicts for every GSv-doc blob: off (doc start), size, blob_len_off."""
    out = []
    for m in re.finditer(b'GSv\x15', d):
        o = m.start()
        if o < 4: continue
        size, c = struct.unpack_from('<II', d, o + 4)
        if o + 12 + size + 6 > len(d): continue
        if struct.unpack_from('<I', d, o - 4)[0] != size + 12 + 6: continue
        if d[o + 12 + size + 4:o + 12 + size + 6] != b'\r\n': continue
        out.append(dict(off=o, size=size, end=o + 12 + size))
    return out

def verify(d, verbose=True):
    problems = []
    es = entries(d)
    for e in es:
        o, size, end = e['off'], e['size'], e['end']
        stored_doc = struct.unpack_from('<I', d, o + 8)[0]
        if stored_doc != crc32(d[o + 12:end]): problems.append(('doc-crc', o))
        stored_blob = struct.unpack_from('<I', d, end)[0]
        if stored_blob != crc32(d[o:end]): problems.append(('blob-crc', o))
    stored_t = struct.unpack_from('<I', d, len(d) - 4)[0]
    calc_t = hashlittle(d[:-4])
    if stored_t != calc_t: problems.append(('trailer', len(d) - 4, hex(stored_t), hex(calc_t)))
    if verbose:
        print('entries(blobs):', len(es), ' doc-crc ok:', sum(1 for p in problems if p[0] == 'doc-crc') == 0,
              ' blob-crc ok:', sum(1 for p in problems if p[0] == 'blob-crc') == 0, ' trailer stored %08x calc %08x' % (stored_t, calc_t))
    return es, problems

def fix(b):
    """Recompute all checksums in-place on bytearray b: doc crc, blob crc, trailer."""
    d = bytes(b)
    for e in entries(d):
        o, end = e['off'], e['end']
        struct.pack_into('<I', b, o + 8, crc32(bytes(b[o + 12:end])))
        struct.pack_into('<I', b, end, crc32(bytes(b[o:end])))
    struct.pack_into('<I', b, len(b) - 4, hashlittle(bytes(b[:-4])))
    return b

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    es, pr = verify(d)
    print('PROBLEMS:', pr[:10] if pr else 'none')
    sys.exit(1 if pr else 0)
