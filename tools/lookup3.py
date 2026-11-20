#!/usr/bin/env python3
"""Bob Jenkins lookup3 hashlittle(key, length, initval) -- the TTC save-file trailer checksum.

eboot.elf fn 0xe6d770 (init a=b=c = 0xdeadbeef + length + initval, mix rotations 4,6,8,16,19,4) is called by the
file loader fn 0xe7cd10 with (data, filesize-4); the result must equal the file's last 4 bytes (u32 LE), otherwise
the loader returns -2 = SAVE_DATA_ERROR_FILE_CORRUPT (fn 0x10ba13c path). Applies to IntegralServer.dat and *.gm.

Usage: lookup3.py check FILE...      verify trailer
       lookup3.py fix IN OUT         recompute trailer over IN[:-4]
"""
import struct
import sys

M = 0xFFFFFFFF


def rot(x, k):
    return ((x << k) | (x >> (32 - k))) & M


def hashlittle(data: bytes, initval: int = 0) -> int:
    length = len(data)
    a = b = c = (0xDEADBEEF + length + initval) & M
    o = 0
    while length > 12:
        a = (a + struct.unpack_from("<I", data, o)[0]) & M
        b = (b + struct.unpack_from("<I", data, o + 4)[0]) & M
        c = (c + struct.unpack_from("<I", data, o + 8)[0]) & M
        # mix(a,b,c)
        a = (a - c) & M; a ^= rot(c, 4); c = (c + b) & M
        b = (b - a) & M; b ^= rot(a, 6); a = (a + c) & M
        c = (c - b) & M; c ^= rot(b, 8); b = (b + a) & M
        a = (a - c) & M; a ^= rot(c, 16); c = (c + b) & M
        b = (b - a) & M; b ^= rot(a, 19); a = (a + c) & M
        c = (c - b) & M; c ^= rot(b, 4); b = (b + a) & M
        length -= 12
        o += 12
    if length == 0:
        return c
    tail = data[o:o + length] + b"\0" * (12 - length)
    a = (a + struct.unpack_from("<I", tail, 0)[0]) & M
    b = (b + struct.unpack_from("<I", tail, 4)[0]) & M
    c = (c + struct.unpack_from("<I", tail, 8)[0]) & M
    # final(a,b,c)
    c ^= b; c = (c - rot(b, 14)) & M
    a ^= c; a = (a - rot(c, 11)) & M
    b ^= a; b = (b - rot(a, 25)) & M
    c ^= b; c = (c - rot(b, 16)) & M
    a ^= c; a = (a - rot(c, 4)) & M
    b ^= a; b = (b - rot(a, 14)) & M
    c ^= b; c = (c - rot(b, 24)) & M
    return c


def trailer_ok(d: bytes) -> bool:
    return len(d) >= 4 and hashlittle(d[:-4]) == struct.unpack("<I", d[-4:])[0]


def fix(d: bytes) -> bytes:
    return d[:-4] + struct.pack("<I", hashlittle(d[:-4]))


if __name__ == "__main__":
    if sys.argv[1] == "check":
        bad = 0
        for f in sys.argv[2:]:
            d = open(f, "rb").read()
            ok = trailer_ok(d)
            bad += not ok
            print(("OK  " if ok else "BAD ") + f, "stored=%08x calc=%08x" % (struct.unpack("<I", d[-4:])[0], hashlittle(d[:-4])))
        sys.exit(1 if bad else 0)
    if sys.argv[1] == "fix":
        open(sys.argv[3], "wb").write(fix(open(sys.argv[2], "rb").read()))
        print("fixed", sys.argv[3])
