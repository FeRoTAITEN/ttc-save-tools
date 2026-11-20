#!/usr/bin/env python3
"""The Tomorrow Children (CUSA28033, Phoenix) save decoder/encoder. No network.

Files (decrypted savedata0, outer PS4 layer already removed):
  Game01/savedata0/IntegralServer.dat   local "IntegralServer" state (wallet lives here)
  Game01/savedata0/*.gm                 "GSv" GameMonkey tables (crc32 header)

IntegralServer.dat layout (all little-endian; str = u32 len + bytes + NUL):
  u32 version (0x76) | u32 id (0x43904d43, = TOWN-43904d43 folder) | u32 1 | u32 2
  str local-user key ("PnxLocalUserID_LocalUser") | u32 1 | u32 blob_size | blob[blob_size]
     blob = char[8] "1.0" | u32 crc32(zdata) | u32 raw_len | u32 0 | u64 zlen
            | zdata (zlib level 9, raw = GSv table of the local user)
            | u32 crc32(blob[0 : 28+zlen]) | u16 0x0a0d
  server user record:
     str userID | u64 lastSentCommandIndex | str transferringSnapshotHash
     u32 total_paid_dollar | u32 wallet_list_length | u32 total_free_dollar
     u32 continuous_playing_days | u32 bonus_list_length
     u32 n_entitlements | n x char[8]
  rest (game-param JSON blobs, info, ...) kept as opaque bytes. The file is not truncated
  on save, so stale bytes of older saves follow the live data; they are kept verbatim.

Usage:
  ttc_save.py decode FILE                 print fields (IntegralServer.dat or .gm)
  ttc_save.py roundtrip FILE              decode -> encode, must be byte-identical
  ttc_save.py set FILE OUT --free N [--paid N]
  ttc_save.py gm-fix FILE OUT             recompute the GSv crc32 (body only; .gm 4-byte trailer kept)
"""
import argparse
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling lookup3.py (also under python -I)

GSV_MAGIC = b"GSv\x15"


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


class R:
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def u(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.o)
        self.o += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def raw(self, n):
        b = self.d[self.o:self.o + n]
        if len(b) != n:
            raise ValueError("truncated at 0x%x" % self.o)
        self.o += n
        return b

    def s(self):
        n = self.u("I")
        b = self.raw(n)
        if self.raw(1) != b"\0":
            raise ValueError("string not NUL-terminated at 0x%x" % self.o)
        return b.decode("utf-8")


def wstr(s):
    b = s.encode("utf-8")
    return struct.pack("<I", len(b)) + b + b"\0"


# ---------------------------------------------------------------- GSv (.gm)
def gsv_check(b):
    """GSv: 'GSv\\x15' | u32 size | u32 crc32(b[12:12+size]) | body.
    Embedded (IntegralServer local user): size = len-12. On-disk .gm: size = len-16, followed
    by a 4-byte trailer of unknown meaning (not crc32 of the file; kept verbatim)."""
    if b[:4] != GSV_MAGIC:
        raise ValueError("not GSv")
    size, h = struct.unpack_from("<II", b, 4)
    return {"size": size, "trailer": len(b) - 12 - size, "crc_ok": h == crc(b[12:12 + size])}


def gsv_fix(b):
    b = bytearray(b)
    size = struct.unpack_from("<I", b, 4)[0]
    struct.pack_into("<I", b, 8, crc(bytes(b[12:12 + size])))
    return bytes(b)


# ---------------------------------------------------------------- IntegralServer.dat
USER_U32 = ["total_paid_dollar", "wallet_list_length", "total_free_dollar",
            "continuous_playing_days", "bonus_list_length"]


def decode(d):
    r = R(d)
    f = {}
    f["version"], f["id"], f["h2"], f["h3"] = r.u("IIII")
    f["local_key"] = r.s()
    f["local_count"] = r.u("I")
    if f["local_count"] != 1:
        raise ValueError("local_count %d not supported" % f["local_count"])
    bsize = r.u("I")
    b0 = r.o
    f["blob_tag"] = r.raw(8)
    zcrc, rawlen, f["blob_pad"], zlen = r.u("IIIQ")
    z = r.raw(zlen)
    if crc(z) != zcrc:
        raise ValueError("zdata crc mismatch")
    raw = zlib.decompress(z)
    if len(raw) != rawlen:
        raise ValueError("raw length mismatch")
    bcrc = r.u("I")
    if bcrc != crc(d[b0:b0 + 28 + zlen]):
        raise ValueError("blob crc mismatch")
    f["blob_tail"] = r.raw(b0 + bsize - r.o)
    f["local_gsv"] = raw
    f["local_z"] = z  # kept to prove the re-compression is identical
    f["userID"] = r.s()
    f["lastSentCommandIndex"] = r.u("Q")
    f["transferringSnapshotHash"] = r.s()
    for k in USER_U32:
        f[k] = r.u("I")
    n = r.u("I")
    f["entitlements"] = [r.raw(8) for _ in range(n)]
    f["rest"] = d[r.o:]
    f["_wallet_off"] = r.o - 8 * n - 4 - 4 * len(USER_U32)
    return f


def encode(f):
    raw = f["local_gsv"]
    z = zlib.compress(raw, 9)
    blob = f["blob_tag"] + struct.pack("<IIIQ", crc(z), len(raw), f["blob_pad"], len(z)) + z
    blob += struct.pack("<I", crc(blob)) + f["blob_tail"]
    out = struct.pack("<IIII", f["version"], f["id"], f["h2"], f["h3"])
    out += wstr(f["local_key"]) + struct.pack("<II", f["local_count"], len(blob)) + blob
    out += wstr(f["userID"]) + struct.pack("<Q", f["lastSentCommandIndex"])
    out += wstr(f["transferringSnapshotHash"])
    out += struct.pack("<5I", *[f[k] for k in USER_U32])
    out += struct.pack("<I", len(f["entitlements"])) + b"".join(f["entitlements"])
    return out + f["rest"]


def show(f):
    g = gsv_check(f["local_gsv"])
    print("version 0x%x id 0x%08x local_key %s" % (f["version"], f["id"], f["local_key"]))
    print("local user GSv: %d bytes, crc ok=%s, zlib recompress identical=%s"
          % (len(f["local_gsv"]), g["crc_ok"], zlib.compress(f["local_gsv"], 9) == f["local_z"]))
    for k in ["userID", "lastSentCommandIndex", "transferringSnapshotHash"] + USER_U32:
        print("%-26s %s" % (k, f[k]))
    print("%-26s %s" % ("entitlements", [e.rstrip(b"\0").decode() for e in f["entitlements"]]))
    print("wallet u32 block at file offset 0x%x (total_free_dollar at 0x%x)"
          % (f["_wallet_off"], f["_wallet_off"] + 8))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("decode", "roundtrip"):
        sp.add_parser(c).add_argument("file")
    p = sp.add_parser("set")
    p.add_argument("file"); p.add_argument("out")
    p.add_argument("--free", type=int); p.add_argument("--paid", type=int)
    p = sp.add_parser("gm-fix")
    p.add_argument("file"); p.add_argument("out")
    a = ap.parse_args()
    d = open(a.file, "rb").read()
    if a.cmd == "gm-fix":
        from lookup3 import fix as trailer_fix  # noqa: PLC0415  (.gm 4-byte trailer = lookup3 of the file body)
        out = trailer_fix(gsv_fix(d))
        open(a.out, "wb").write(out); print(gsv_check(out)); return 0
    if d[:4] == GSV_MAGIC:
        print(gsv_check(d)); return 0
    f = decode(d)
    if a.cmd == "decode":
        show(f)
    elif a.cmd == "roundtrip":
        e = encode(f)
        ok = e == d
        print("roundtrip byte-identical:", ok, len(e), len(d))
        return 0 if ok else 1
    elif a.cmd == "set":
        if a.free is not None:
            if not 0 <= a.free <= 0x7FFFFFFF:
                raise SystemExit("value out of range")
            f["total_free_dollar"] = a.free
        if a.paid is not None:
            f["total_paid_dollar"] = a.paid
        # The game verifies the whole file: last 4 bytes = lookup3 hashlittle(file[:-4], 0) (eboot 0xe6d770,
        # checked by loader 0xe7cd10; mismatch => SAVE_DATA_ERROR_FILE_CORRUPT). Recompute it after any edit.
        from lookup3 import fix as trailer_fix  # noqa: PLC0415
        e = trailer_fix(encode(f))
        open(a.out, "wb").write(e)
        g = decode(e)
        print("written", a.out, "total_free_dollar", g["total_free_dollar"],
              "total_paid_dollar", g["total_paid_dollar"], "size", len(e), "(orig %d)" % len(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
