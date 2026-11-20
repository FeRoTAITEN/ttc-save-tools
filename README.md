# ttc-save-tools

Save-editing tools, format notes and ready-made decrypted saves for **The Tomorrow Children: Phoenix Edition** (PS4, CUSA28033).

Python 3 standard library only. `pycryptodome` is needed only for the TOWN snapshots (Blowfish): `pip install pycryptodome`.

## Contents

| Path | What |
|---|---|
| `tools/ttc.py` | One CLI: `verify`, `fix-checksums`, `dump`, `set` |
| `tools/gsv.py`, `gsv_renumber.py`, `gparse.py` | GSv table codec, id renumbering, tolerant parser for TOWN docs |
| `tools/ttc_save.py` | Game01: `IntegralServer.dat` and `.gm` checksums, wallet fields |
| `tools/snapdoc.py`, `snap.py` | TOWN snapshots (Blowfish-CBC + GSv doc) |
| `tools/citycheck.py` | `City.bin` verify / fix |
| `tools/lookup3.py` | Bob Jenkins lookup3 (whole-file trailer used by the game) |
| `tools/retarget_ids.py` | Rewrite the account id inside a save set and rebuild all checksums |
| `docs/FORMAT.md` | File formats and editing workflow |
| `saves/` | Decrypted Game01 and TOWN saves (see below) |
| `TESTS.md`, `PRIVACY.md` | Round-trip results; what was removed or anonymized in `saves/` |

## The saves

`saves/Game01` (game profile) and `saves/TOWN-43904d43-01` (town), both decrypted (no PS4 encryption layer).

- Profile: maxed stats and levels, all missions completed, wallet/resources filled.
- Town: maxed town values and power, plus monument objects added for every monument that has an unlock condition (the game's own population monuments 03, 04, 16-20 are left to the game); the monument counter is set to 20 of 23.
- Known limits: monuments 21-23 are not built (no condition/circular requirements); the added monuments have no connecting roads (roads are only drawn by the game while a monument is under construction and are not saved).
- Account id fields inside the files were replaced by a neutral id (see `PRIVACY.md`). They have not been console-tested in that anonymized form.

## Import to your console

**Easiest: the encrypted release zip.** Download `TTC-maxed-save-PS4.zip` from the Releases page. It holds the two saves already encrypted in USB layout (`PS4/SAVEDATA/0de0b6b3a7640000/CUSA28033/{Game01,Game01.bin,TOWN-43904d43-01,TOWN-43904d43-01.bin}`) for the neutral account id `0de0b6b3a7640000`. Import them into Save Wizard or Apollo Save Tool, resign them to your own account, then copy the result from USB to the console. Back up your own saves first.

**Manual route (decrypted files):**

1. Create or locate the two save slots on your PS4: Game01 = 128 blocks, TOWN-43904d43-01 = 2048 blocks (play the game once so both exist).
2. If the game does not accept the save, rewrite the ids to your own PSN account id (19-digit decimal; you can read it from your own decrypted `.gm` file name):
   `python tools/retarget_ids.py --from-dec 1000000000000000000 --to-dec <YOUR_ID> saves/Game01 saves/TOWN-43904d43-01 out/`
3. Put the decrypted files in a save tool that can import them and re-sign for your account: Apollo Save Tool (decrypt/encrypt, "import decrypted files") or any PS4 save resigner. Replace the contents of the save, do not rename files.
4. Back up your original saves first. Test Game01 first, then TOWN.

## Tools

```
python tools/ttc.py verify saves                       # parse + byte-identical re-encode + all checksums
python tools/ttc.py dump FILE --grep stat              # list every value as path / type / value
python tools/ttc.py set FILE .save_counter 4000        # change one int/float/string leaf
python tools/ttc.py fix-checksums saves/Game01/IntegralServer.dat
python tools/ttc.py fix-checksums saves/TOWN-43904d43-01   # snapshots + City.bin (new md5 names)
```

After editing a value in `*_game_save_data.gm`, apply the same edit to `IntegralServer.dat` (the game uses the copy with the higher `save_counter`). Edit all 3 TOWN snapshots identically. Details in `docs/FORMAT.md`.

## Disclaimer

For personal use on your own saves. Back up before changing anything. Using modified saves can get your account flagged or banned if you play online; keep them for offline play. This project is unofficial and not affiliated with or endorsed by Sony Interactive Entertainment, Q-Games, or any rights holder. It contains no game files.
