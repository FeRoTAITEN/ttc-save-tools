# Privacy review of `saves/`

The saves were created from a real console save, so they were scanned for personal identifiers in every file (raw bytes, decrypted snapshots, the decompressed `IntegralServer.dat` table), in these forms: decimal string, lowercase/uppercase hex string, little-endian and big-endian int64, and inside longer strings.

## Found

| Identifier | Where | Action |
|---|---|---|
| PSN account id (64-bit) | `*_game_save_data.gm`: as the file name, as the `account_id` string, ~33 times inside item-name strings, once as int64 and once inside a stage key; `IntegralServer.dat`: same table plus the server `userID` record; `City.bin`: tens of thousands of int64 (`network_psn_name`) and `PnxUserID_<hex>` keys; snapshots: ~80 int64 and 2 hex strings each | Replaced everywhere by a neutral id (decimal `1000000000000000000`, hex `0de0b6b3a7640000`, same field lengths) with `tools/retarget_ids.py`. All checksums recomputed (GSv crc32, zlib blob, City.bin doc/blob crc + lookup3, snapshot Blowfish + md5 names, City.bin snapshot names). Re-scan: 0 occurrences left. Files re-verified (see `TESTS.md`). The `.gm` file was renamed to `1000000000000000000_game_save_data.gm`. |
| Online id / user name | `player_name` = `UNKNOWN` in the profile; no online id string found | none needed |
| Numeric user id, console id | not present in any file | none |
| `sce_sys/` (`param.sfo` account fields, `keystone`, icons) | outside the decrypted data | removed, never published (`.gitignore` blocks `sce_sys/`) |
| Town names | no free-text town name in the saves; only game profile names | none |

## Left unchanged (decide)

- `43904d43`: the town save id (folder name `TOWN-43904d43-01`, first field of `IntegralServer.dat`, 6 occurrences in `City.bin`). It looks like a save/town id, not an account id, and the game expects it to match the folder. Kept as is; it might still be derived from the original account.
- Stage key suffix `:f2d14e5f` (after the account id in stage keys). Unknown meaning; kept.
- In-game progress data (stats, positions, timestamps) is the original player's progress by nature.
- The anonymized saves have not been tested on a console; if the game rejects them, run `retarget_ids.py` with your own account id.

Decision: the town id 43904d43 and the stage-key suffix f2d14e5f are kept as is.
