#!/usr/bin/env python3
"""Re-assign GSv object ids exactly like the game's writer does.

Why (2026-11-16, final5 root cause): the game's GSv reader keeps ONE id -> object map for strings, tables and
arrays (1.49 eboot readers at 0xc76953/0xc76fb3/0xc77623, same code as 1.28 0xcb6620/0xcb5870/0xcb54f0: read u32 id,
look it up in the shared rb-tree at [state+0x40]; a hit = back-reference, the body is NOT read). Genuine files use one
counter in serialization order (ids 1..N, dense, monotonic, no string/table overlap). Our older item edits gave new
strings ids above the old maximum, so 77 table ids collided with string ids -> the reader takes a table as a
back-reference to a string, skips its body and desyncs -> the whole user data is rejected -> fresh profile.

renumber(root) rewrites every id in place: counter from 1 in encode order (table: key then value; array: elements);
a string whose text was already written becomes a back-reference to that id; every table/array gets a new id.
Identity on every genuine save (checked by --selftest).

Usage: gsv_renumber.py check FILE...      print id stats (collisions / non-monotonic / gaps)
       gsv_renumber.py selftest FILE...   renumber must be byte-identical on genuine files
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsv  # noqa: E402


def renumber(root):
    nxt = [1]
    seen = {}

    def w(n):
        if n.t == gsv.STR:
            if n.v in seen:
                n.sid, n.new = seen[n.v], False
            else:
                n.sid, n.new = nxt[0], True
                seen[n.v] = nxt[0]
                nxt[0] += 1
        elif n.t in (gsv.TABLE, gsv.ARRAY):
            n.tid = nxt[0]
            nxt[0] += 1
            for x in n.v:
                if n.t == gsv.TABLE:
                    w(x[0])
                    w(x[1])
                else:
                    w(x)
    w(root)
    return nxt[0] - 1


def stats(root):
    order, S, T = [], {}, set()

    def w(n):
        if n.t == gsv.STR and n.new:
            order.append(n.sid)
            S[n.sid] = n.v
        elif n.t in (gsv.TABLE, gsv.ARRAY):
            order.append(n.tid)
            T.add(n.tid)
            for x in n.v:
                if n.t == gsv.TABLE:
                    w(x[0])
                    w(x[1])
                else:
                    w(x)
    w(root)
    ids = set(S) | T
    return {"objects": len(order), "collisions": len(set(S) & T),
            "non_monotonic": sum(1 for a, b in zip(order, order[1:]) if b != a + 1),
            "dense": ids == set(range(1, len(order) + 1)) and len(ids) == len(order)}


def load_table(path):
    b = open(path, "rb").read()
    if b[:4] != gsv.MAGIC:
        import ttc_save
        b = ttc_save.decode(b)["local_gsv"]
    return b


def main():
    cmd, files = sys.argv[1], sys.argv[2:]
    bad = 0
    for f in files:
        b = load_table(f)
        root, tr = gsv.parse(b)
        if cmd == "check":
            print(f, stats(root))
        elif cmd == "selftest":
            renumber(root)
            ok = gsv.build(root, tr) == b
            bad += not ok
            print(f, "identity" if ok else "DIFFERS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
