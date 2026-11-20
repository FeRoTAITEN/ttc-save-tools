# The Tomorrow Children: Phoenix Edition (CUSA28033) - save format and how to edit it

All numbers little-endian. crc32 = standard zlib.crc32. lookup3 = Bob Jenkins hashlittle(data, len, initval=0)
(init = 0xdeadbeef + len; eboot function 0xe6d770; test vector: hashlittle("Four score and seven years ago") = 0x17770551).

## 0) PS4 save layer
   - Game01 = 128 blocks, TOWN-43904d43-01 = 2048 blocks (64 MiB), both signed to the same PSN account.
   - Decrypt / re-encrypt with a PS4 save tool (e.g. Apollo Save Tool, or a save resigner). Then decrypt again and check the files are byte-identical.
   - Inside this layer the GAME files have no further encryption, only checksums.

## 1) GSv format (used everywhere)
   header : 'GSv\x15' | u32 size | u32 crc32(body) | body
            if the computed crc == 0xb00b1ee5 it is stored as 0xb00b1ee6 (0xb00b1ee5 means "skip").
   value  : u16 type + payload
            0 int32 | 1 float32 | 4 table | 5 string | 6 array | 7 int64 | 8 nil | 13 bytes (u32 len, often a nested GSv)
            14 = 64-byte matrix (TOWN)
   string : u32 id if seen before; first occurrence: u32 len + bytes + NUL
   table  : u32 id, u32 count, if count>0: u16 flags (bit0 uniform key type -> u16, bit1 uniform value type -> u16), pairs
   array  : u32 id, u32 len, if len>0: u16 flags (bit0 uniform type -> u16), elements
   !! IMPORTANT: string, table and array IDs share ONE running counter in file order.
      If you add a new name, renumber everything after it (`tools/gsv_renumber.py`).
      An ID collision = the game opens a fresh profile or crashes.

## 2) GAME PROFILE (Game01)
   game_save_data.gm  : GSv (size = len-16) + last 4 bytes = u32 lookup3(file[:-4])
   IntegralServer.dat : str = u32 len + bytes + NUL
       blob = char[8] "1.0" | u32 crc32(zdata) | u32 raw_len | u32 0 | u64 zlen | zdata (zlib level 9)
              | u32 crc32(blob[0:28+zlen]) | u16 0x0a0d
       zdata = the player's GSv table (mirror of game_save_data.gm)
       then the server user record, then last 4 bytes = u32 lookup3(file[:-4])
   local_save_data.gm : settings only (version/eula/gamma), do not touch.
   Rule: every value edited in game_save_data.gm must be edited the same way in the IntegralServer.dat table.
   Order: GSv crc32 -> zlib -> blob crc32 -> whole-file lookup3 last.
   The game picks between the two copies by save_counter (higher wins).

## 3) TOWN (TOWN-43904d43-01)
   City.bin : network command log (8811 GSv docs), NOT the town state.
       each entry: [GSv doc][u32 crc32(doc incl. its 12-byte header)][0d 0a], preceded by u32 blob_len = len(doc)+6
       file header lists the 3 snapshot names (32-char md5 at 0x21f7 / 0x2228 / 0x2259)
       last 4 bytes = u32 lookup3(file[:-4])
       Order: GSv crc -> blob crc -> lookup3 last.
   Snapshots (3 files, the real town state):
       Blowfish-CBC   key = 7&78fJ4d   IV = Z%)kj<4w
       decrypted: 20-byte header (u32 10, u32 idx, u64 stamp, u32) | one GSv doc (town state) | terrain chunks ("chikei")
       file name = md5(encrypted file). After an edit: encrypt -> md5 -> rename -> update the name in City.bin -> City.bin lookup3.
       Apply the same edit to all 3 snapshots.

## 4) Lessons
   - Town levels (propaganda/technology/culture) are recomputed at load from the building list, not stored.
   - Power = electric_storage per generator (float32: largest exact value 99,999,992).
   - Monuments: build_monument flag (0 none, 1 requested, 2 building, 3 finished). Flag 3 without an object
     = unlocked but no model. A model needs an object record; roads are not saved, the game draws them only while building.
     Population monuments built by the game also apply city_policy effects (house capacity).
   - Avoid INT32_MAX (2,147,483,647) and other boundary values.
   - Trophies unlock on in-game events; a raised counter makes them unlock the first time you do the action.

## 5) Workflow
   decrypt -> edit -> renumber IDs (if names added) -> crc32 -> zlib/blob -> lookup3 -> (TOWN: Blowfish + md5 + City.bin)
   -> Create Save -> decrypt again and compare -> USB -> console.
   Back up first, and test one change at a time.

Tools: see README.md (`tools/ttc.py` wraps gsv.py, ttc_save.py, snapdoc.py, citycheck.py, lookup3.py).
