#!/usr/bin/env python3
"""Rewrite the PSN account id inside a decrypted TTC save set and recompute every checksum.

The account id appears as: 19-digit decimal string, 16-digit lowercase hex string (also as 'PnxUserID_<hex>'),
and a little-endian int64. All forms have fixed length, so the files keep their structure; GSv crc32, zlib blob,
City.bin crcs, snapshot Blowfish + md5 names and lookup3 trailers are rebuilt.

  retarget_ids.py --from-dec 1000000000000000000 --to-dec <your 19-digit id> GAME01_DIR TOWN_DIR OUT_DIR
Writes OUT_DIR/Game01/ and OUT_DIR/<TOWN dir name>/ . The .gm file is renamed to <to-dec>_game_save_data.gm.
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookup3, ttc_save, citycheck, snap  # noqa: E401,E402


def make_pairs(a, b):
    ia, ib = int(a), int(b)
    assert len(a) == len(b) == 19 and a.isdigit() and b.isdigit(), "ids must be 19-digit decimals"
    return [(a.encode(), b.encode()), (('%016x' % ia).encode(), ('%016x' % ib).encode()),
            (struct.pack('<q', ia), struct.pack('<q', ib)), (struct.pack('<Q', ia), struct.pack('<Q', ib))]


def patch(d, pairs):
    n = 0
    for o, nw in pairs:
        n += d.count(o)
        d = d.replace(o, nw)
    return d, n


def left(d, pairs):
    return sum(d.count(o) for o, _ in pairs)


def do_game(src, dst, pairs, a, b):
    os.makedirs(dst, exist_ok=True)
    for f in sorted(os.listdir(src)):
        d = open(os.path.join(src, f), 'rb').read()
        if f.endswith('.gm'):
            d, n = patch(d, pairs)
            d = lookup3.fix(ttc_save.gsv_fix(d))
            f = f.replace(a, b)
        elif f == 'IntegralServer.dat':
            fl = ttc_save.decode(d)
            assert ttc_save.encode(fl) == d, 'IntegralServer roundtrip failed'
            n = 0
            fl['local_gsv'], k = patch(fl['local_gsv'], pairs)
            n += k
            fl['local_gsv'] = ttc_save.gsv_fix(fl['local_gsv'])
            for key in ('userID', 'transferringSnapshotHash'):
                s, k = patch(fl[key].encode(), pairs)
                fl[key] = s.decode()
                n += k
            for key in ('blob_tail', 'rest'):
                fl[key], k = patch(fl[key], pairs)
                n += k
            d = lookup3.fix(ttc_save.encode(fl))
            ttc_save.decode(d)
        else:
            n = 0
        print('Game01/%s: %d replaced, %d left' % (f, n, left(d, pairs)))
        open(os.path.join(dst, f), 'wb').write(d)


def do_town(src, dst, pairs):
    os.makedirs(os.path.join(dst, 'Snapshots'), exist_ok=True)
    city = open(os.path.join(src, 'City.bin'), 'rb').read()
    city, n = patch(city, pairs)
    for f in sorted(os.listdir(os.path.join(src, 'Snapshots'))):
        e = open(os.path.join(src, 'Snapshots', f), 'rb').read()
        p, k = patch(snap.dec(e), pairs)
        p = bytearray(p)
        assert p[0x14:0x18] == b'GSv\x15'
        size = struct.unpack_from('<I', p, 0x18)[0]
        struct.pack_into('<I', p, 0x1c, zlib.crc32(bytes(p[0x20:0x20 + size])) & 0xffffffff)
        e2 = snap.enc(bytes(p))
        name = hashlib.md5(e2).hexdigest()
        assert city.count(f[:-4].encode()) >= 1
        city = city.replace(f[:-4].encode(), name.encode())
        open(os.path.join(dst, 'Snapshots', name + '.dat'), 'wb').write(e2)
        print('Snapshots/%s -> %s.dat: %d replaced, %d left' % (f, name, k, left(snap.dec(e2), pairs)))
    city = bytes(citycheck.fix(bytearray(city)))
    es, pr = citycheck.verify(city, False)
    print('City.bin: %d replaced, %d left, entries %d, problems %s' % (n, left(city, pairs), len(es), pr or 'none'))
    open(os.path.join(dst, 'City.bin'), 'wb').write(city)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from-dec', required=True)
    ap.add_argument('--to-dec', required=True)
    ap.add_argument('game_dir')
    ap.add_argument('town_dir')
    ap.add_argument('out_dir')
    a = ap.parse_args()
    pairs = make_pairs(a.from_dec, a.to_dec)
    do_game(a.game_dir, os.path.join(a.out_dir, 'Game01'), pairs, a.from_dec, a.to_dec)
    do_town(a.town_dir, os.path.join(a.out_dir, os.path.basename(os.path.normpath(a.town_dir))), pairs)


if __name__ == '__main__':
    main()
