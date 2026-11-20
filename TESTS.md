# Test results

Run on the decrypted saves in `saves/` (Python 3, pycryptodome 3.23). Every file re-encodes byte-identically and all checksums verify.

## `python tools/ttc.py verify saves`

```
saves\Game01\1000000000000000000_game_save_data.gm [gm]
  GSv parse + re-encode identical    OK
  GSv crc32                          OK
  lookup3 trailer                    OK
saves\Game01\IntegralServer.dat [integral]
  decode + re-encode identical       OK
  inner GSv crc32                    OK
  inner GSv re-encode identical      OK
  lookup3 trailer                    OK
saves\Game01\local_save_data.gm [gm]
  GSv parse + re-encode identical    OK
  GSv crc32                          OK
  lookup3 trailer                    OK
saves\TOWN-43904d43-01\City.bin [city]
  8811 docs: doc crc, blob crc       OK
  lookup3 trailer                    OK
saves\TOWN-43904d43-01\Snapshots\369ecb494c7f9603cb71093a40c48a26.dat [snapshot]
  Blowfish round trip + GSv crc      OK
  GSv re-encode identical            OK
  renumber identical                 OK
  whole file re-assembles identical  OK
  md5(file) == file name             OK
saves\TOWN-43904d43-01\Snapshots\4f0c496ef8850f2c97f30f8069509e69.dat [snapshot]
  Blowfish round trip + GSv crc      OK
  GSv re-encode identical            OK
  renumber identical                 OK
  whole file re-assembles identical  OK
  md5(file) == file name             OK
saves\TOWN-43904d43-01\Snapshots\5b6c332bed185c78bda10e7e620dded2.dat [snapshot]
  Blowfish round trip + GSv crc      OK
  GSv re-encode identical            OK
  renumber identical                 OK
  whole file re-assembles identical  OK
  md5(file) == file name             OK
ALL OK
```

## Per-tool self tests

```
$ python tools/gsv.py roundtrip saves/Game01/1000000000000000000_game_save_data.gm
roundtrip byte-identical: True
$ python tools/ttc_save.py roundtrip saves/Game01/IntegralServer.dat
roundtrip byte-identical: True 707588 707588
$ python tools/citycheck.py saves/TOWN-43904d43-01/City.bin
entries(blobs): 8811  doc-crc ok: True  blob-crc ok: True  trailer stored ecf8786d calc ecf8786d
PROBLEMS: none
$ python tools/snapdoc.py selftest saves/TOWN-43904d43-01/Snapshots
369ecb494c7f9603cb71093a40c48a26.dat enc True renumber True file True pad-rule True pad 4 {'objects': 4592, 'collisions': 0, 'non_monotonic': 0, 'dense': True, 'refs_ok': True}
4f0c496ef8850f2c97f30f8069509e69.dat enc True renumber True file True pad-rule True pad 5 {'objects': 4690, 'collisions': 0, 'non_monotonic': 0, 'dense': True, 'refs_ok': True}
5b6c332bed185c78bda10e7e620dded2.dat enc True renumber True file True pad-rule True pad 6 {'objects': 4788, 'collisions': 0, 'non_monotonic': 0, 'dense': True, 'refs_ok': True}
SELFTEST PASS
```

## Other checks (done once, on copies)

- `ttc.py fix-checksums` on an unmodified copy of every file and of the TOWN directory gives byte-identical files (idempotent).
- `ttc.py set` on a `.gm` leaf and on a snapshot leaf, then setting the original value back, restores the original bytes (the snapshot returns to its original md5 file name).
- `retarget_ids.py` on the original save set: 0 occurrences of the old id remain in any file (including the decompressed `IntegralServer.dat` table and decrypted snapshots); all of the checks above pass on the output.
