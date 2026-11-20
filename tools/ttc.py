#!/usr/bin/env python3
"""ttc.py - one CLI for The Tomorrow Children: Phoenix Edition (CUSA28033) decrypted saves.

  ttc.py verify PATH...            check parse + byte-identical re-encode + every checksum
  ttc.py fix-checksums PATH [-o OUT]   recompute checksums of one file (see below for TOWN dirs)
  ttc.py dump FILE [--grep TEXT]   print every leaf as 'path type value'
  ttc.py set FILE PATH VALUE [-o OUT]  change one int/float/string leaf (path as printed by dump)

PATH = a file or a directory (searched recursively). File kinds, detected by name/content:
  *.gm                 GSv table + lookup3 trailer
  IntegralServer.dat   zlib'd mirror of the GSv table + server record + lookup3 trailer
  City.bin             TOWN command log (GSv docs with crc32 + lookup3 trailer)
  Snapshots/*.dat      TOWN state: Blowfish-CBC, header, GSv doc, terrain
fix-checksums on a TOWN directory (the one that holds City.bin) fixes all snapshots (GSv crc, Blowfish, new md5
file names), writes the new names into City.bin and recomputes City.bin. On a single file it rewrites that file
(or OUT). Edit all 3 snapshots the same way, they are all loaded.
Needs Python 3 and pycryptodome (snapshots only): pip install pycryptodome
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsv, lookup3, ttc_save, citycheck  # noqa: E401,E402


def kind(path, d):
    n = os.path.basename(path)
    if n.endswith('.gm'):
        return 'gm'
    if n == 'IntegralServer.dat':
        return 'integral'
    if n == 'City.bin':
        return 'city'
    if n.endswith('.dat') and os.path.basename(os.path.dirname(path)) == 'Snapshots':
        return 'snapshot'
    raise SystemExit('unknown file kind: ' + path)


def files(paths):
    for p in paths:
        if os.path.isdir(p):
            for r, _, fs in sorted(os.walk(p)):
                for f in sorted(fs):
                    if f.endswith(('.gm', '.bin', '.dat')):
                        yield os.path.join(r, f)
        else:
            yield p


def ok(label, cond, res):
    res.append(cond)
    print('  %-34s %s' % (label, 'OK' if cond else 'FAIL'))


def verify_file(p):
    d = open(p, 'rb').read()
    k = kind(p, d)
    print('%s [%s]' % (p, k))
    res = []
    if k == 'gm':
        root, tr = gsv.parse(d)
        ok('GSv parse + re-encode identical', gsv.build(root, tr) == d, res)
        sz = struct.unpack_from('<I', d, 4)[0]
        ok('GSv crc32', struct.unpack_from('<I', d, 8)[0] == zlib.crc32(d[12:12 + sz]) & 0xffffffff, res)
        ok('lookup3 trailer', lookup3.trailer_ok(d), res)
    elif k == 'integral':
        f = ttc_save.decode(d)
        ok('decode + re-encode identical', ttc_save.encode(f) == d, res)
        ok('inner GSv crc32', ttc_save.gsv_check(f['local_gsv'])['crc_ok'], res)
        root, tr = gsv.parse(f['local_gsv'])
        ok('inner GSv re-encode identical', gsv.build(root, tr) == f['local_gsv'], res)
        ok('lookup3 trailer', lookup3.trailer_ok(d), res)
    elif k == 'city':
        es, pr = citycheck.verify(d, False)
        ok('%d docs: doc crc, blob crc' % len(es), not [x for x in pr if x[0] != 'trailer'], res)
        ok('lookup3 trailer', not [x for x in pr if x[0] == 'trailer'], res)
    else:
        import snapdoc
        s = snapdoc.load(p)
        doc = s['plain'][0x14:0x20 + s['size']]
        ok('Blowfish round trip + GSv crc', True, res)
        ok('GSv re-encode identical', snapdoc.doc_bytes(s['root']) == doc, res)
        snapdoc.renumber(s['root'])
        ok('renumber identical', snapdoc.doc_bytes(s['root']) == doc, res)
        import snap
        ok('whole file re-assembles identical',
           snap.enc(snapdoc.assemble(s['head'], doc, s['body'], s['pad'])) == s['enc'], res)
        ok('md5(file) == file name', hashlib.md5(d).hexdigest() == os.path.basename(p)[:-4], res)
    return all(res)


def fix_file(p, out):
    d = open(p, 'rb').read()
    k = kind(p, d)
    if k == 'gm':
        e = lookup3.fix(ttc_save.gsv_fix(d))
    elif k == 'integral':
        f = ttc_save.decode(d)
        f['local_gsv'] = ttc_save.gsv_fix(f['local_gsv'])
        e = lookup3.fix(ttc_save.encode(f))
    elif k == 'city':
        e = bytes(citycheck.fix(bytearray(d)))
    else:
        raise SystemExit('fix a snapshot through its TOWN directory (the folder holding City.bin)')
    open(out or p, 'wb').write(e)
    print('fixed', out or p)


def fix_town(dr):
    import snap
    cp = os.path.join(dr, 'City.bin')
    city = open(cp, 'rb').read()
    sd = os.path.join(dr, 'Snapshots')
    for f in sorted(os.listdir(sd)):
        p = os.path.join(sd, f)
        pl = bytearray(snap.dec(open(p, 'rb').read()))
        size = struct.unpack_from('<I', pl, 0x18)[0]
        struct.pack_into('<I', pl, 0x1c, zlib.crc32(bytes(pl[0x20:0x20 + size])) & 0xffffffff)
        e = snap.enc(bytes(pl))
        name = hashlib.md5(e).hexdigest()
        city = city.replace(f[:-4].encode(), name.encode())
        os.remove(p)
        open(os.path.join(sd, name + '.dat'), 'wb').write(e)
        print('snapshot', f, '->', name + '.dat')
    open(cp, 'wb').write(bytes(citycheck.fix(bytearray(city))))
    print('City.bin fixed')


def load_tree(p):
    d = open(p, 'rb').read()
    k = kind(p, d)
    if k == 'gm':
        root, tr = gsv.parse(d)
        return k, root, (tr, None)
    if k == 'integral':
        f = ttc_save.decode(d)
        root, tr = gsv.parse(f['local_gsv'])
        return k, root, (tr, f)
    if k == 'snapshot':
        import snapdoc
        s = snapdoc.load(p)
        return k, s['root'], (None, s)
    raise SystemExit('dump/set support .gm, IntegralServer.dat and Snapshots/*.dat')


def cmd_dump(a):
    k, root, _ = load_tree(a.file)
    tn = {0: 'i', 1: 'f', 2: 'v3', 13: 'b', 5: 's', 7: 'q', 8: 'nil', 9: 'c8'}
    for p, n in gsv.walk(root):
        v = n.v
        if isinstance(v, (bytes, bytearray)):
            v = '<%d bytes>' % len(v)
        elif isinstance(v, str) and len(v) > 80:
            v = v[:80] + '...'
        line = '%-70s %s %r' % (p, tn.get(n.t, n.t), v)
        if not a.grep or a.grep in line:
            print(line)


def cmd_set(a):
    k, root, (tr, ctx) = load_tree(a.file)
    hit = [n for p, n in gsv.walk(root) if p == a.path]
    if len(hit) != 1:
        raise SystemExit('path not found (or not unique): ' + a.path)
    n = hit[0]
    if n.t == gsv.INT:
        n.v = int(a.value)
        if abs(n.v) == 2147483647:
            print('warning: INT32_MAX tends to break the game')
    elif n.t == gsv.FLOAT:
        n.v = float(a.value)
    elif n.t == gsv.STR:
        n.v = a.value
    else:
        raise SystemExit('only int/float/string leaves can be set')
    out = a.output or a.file
    if k == 'gm':
        e = lookup3.fix(gsv.build(root, tr))
    elif k == 'integral':
        ctx['local_gsv'] = gsv.build(root, tr)
        e = lookup3.fix(ttc_save.encode(ctx))
        print('note: also apply the same edit to the .gm (the game uses the copy with the higher save_counter)')
    else:
        import snapdoc, snap
        e = snap.enc(snapdoc.assemble(ctx['head'], snapdoc.doc_bytes(root), ctx['body'], ctx['pad']))
        name = hashlib.md5(e).hexdigest() + '.dat'
        out = a.output or os.path.join(os.path.dirname(a.file), name)
        print('snapshot is now', name, '- run: ttc.py fix-checksums <TOWN dir> after editing all 3 snapshots')
        if not a.output and out != a.file:
            os.remove(a.file)
    open(out, 'wb').write(e)
    print('written', out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('verify').add_argument('paths', nargs='+')
    p = sp.add_parser('fix-checksums')
    p.add_argument('path')
    p.add_argument('-o', '--output')
    p = sp.add_parser('dump')
    p.add_argument('file')
    p.add_argument('--grep')
    p = sp.add_parser('set')
    p.add_argument('file')
    p.add_argument('path')
    p.add_argument('value')
    p.add_argument('-o', '--output')
    a = ap.parse_args()
    if a.cmd == 'verify':
        good = all([verify_file(f) for f in files(a.paths)])
        print('ALL OK' if good else 'FAILED')
        return 0 if good else 1
    if a.cmd == 'fix-checksums':
        if os.path.isdir(a.path):
            fix_town(a.path)
        else:
            fix_file(a.path, a.output)
    elif a.cmd == 'dump':
        cmd_dump(a)
    else:
        cmd_set(a)
    return 0


if __name__ == '__main__':
    sys.exit(main())
