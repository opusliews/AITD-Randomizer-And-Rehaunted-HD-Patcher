# AITD1 patch engine (work-order step 1: assembler)

Python 3.14, standard library only. The portable Python ignores the working
directory and `PYTHONPATH` (`._pth` file), so every script adds its own folder
to `sys.path`; import these modules from scripts placed in this folder or do
the same.

| File | Contents |
|---|---|
| `aitd_pak.py` | PAK reader (raw, implode, deflate) and writer (raw entries). |
| `aitd_life.py` | LIFE instruction set, decoder, encoder, text assembler, label-based relocation, control-flow checks (`check_patch`, `check_text_patch`). |
| `aitd_track.py` | TRACK instruction set, decoder, encoder, text form. |
| `lifeasm.py` | Command line: `disasm`, `disasm-track`, `dump`, `asm`, `check`. |
| `aitd_objets.py` | OBJETS.ITD reader/writer (26 s16 fields per record; at most 300 objects, the save-format limit). `python aitd_objets.py` checks the round trip. |
| `aitd_text.py` | Language text (entry 0 of the language PAKs): parse `@id:text` entries and append new ones. |
| `vanilla_exe.py` | Binary patches for the GOG `INDARK.EXE` (hash-checked, original bytes checked): `--max-objects N`. Evidence: `Research/VanillaExe_Ghidra.md`. |
| `make_patchset.py` | Builds a patch-set folder (from vanilla, or layered on another patch set with `--base`) (replacement `LISTLIFE.PAK` / `LISTTRAK.PAK`, all entries raw, plus `manifest.json`) from edited listings. Every LIFE edit is flow-checked; a failed check aborts unless `--force`. |
| `slot_catalog.py` | Slot catalog part 1: every type-9 search/contact slot with its item operand sites → `catalog/search_slots.json` / `.csv`. Cross-checked against `type9_zone_rewards.csv`. |
| `slot_catalog2.py` | Slot catalog part 2: containers, inventory containers, breakage, monster drops, direct pickups, the extra F2:R0 search slot, item-use placements, item returns, optional empty zones → `catalog/acquisition_slots.json` / `.csv` (`Research/SlotCatalog_Part2.md`). |
| `shuffle_search.py` | PoC B: seeded shuffle of all search-slot items by in-place operand retargeting → patch set with `spoiler.md`. |
| `verify_assembler.py` | Verification suite (21 checks); `--report verify_report.json`. |
| `verify_report.json` | Last full report, including the (empty) list of vanilla backward branches. |

Format details and evidence: `Research/LifeAssembler.md`.

## Text form (LIFE)

```text
if_egal posrel(1) #4 @L82    ; @36
sound #3    ; @48
if_egal object(15) #0 @L74    ; @54
found 15    ; @66
goto @L78    ; @70
L74: message 100    ; @74
```

- `#5` constant, `var_12` variable, `field` / `obj_3.field` (field of this object / of OBJ 3), `posrel(1)`, `object(15)`, `isfound(#13)`, `cvar(36)`, `rand(10)`, `dist(1)`, `thrown(5)`, `test_zv_end_anim(a,f)`.
- `obj_N.mnemonic ...` runs the instruction on OBJ N.
- `@label` for branches. `[1,2,3]` for `multi_case` values.
- `; @N` is the original byte offset. Keep it on unchanged lines; `check` uses it to tell original instructions from new ones.

## Typical use

```powershell
python lifeasm.py disasm 8 > life8.asm      # edit life8.asm
python lifeasm.py check 8 life8.asm --intended 70 -o life8.bin
python verify_assembler.py                   # after any change to the modules
```

## Patch sets for TatouScenario

```powershell
python make_patchset.py ..\Scenarios\patchsets\life8_second_item `
    --life 8=..\Scenarios\patch_sources\life8_second_item.asm --intended 8=54
```

New scripts, objects and text (PoC C):

```powershell
python make_patchset.py OUTDIR --new-life key_found.asm --new-life door_locked.asm `
    --objets edits.json --text "1151=Key to the Bathroom (3rd Floor)"
```

`edits.json`: `{"set": {"29": {"life": 564}}, "append": [{"clone": 37, "found_name": 1151, "found_life": 563}]}`. New LIFE scripts get the next free numbers (563, 564, ...) in the order given; new objects the next free object numbers (292, ...).

Load the folder from a scenario with `patchset <folder>` (see `ReHaunted/SCENARIO_TESTING.md`). Source listings live in `Generated/Scenarios/patch_sources/`, built folders in `Generated/Scenarios/patchsets/`; copy both the `.scn` and its folder to the exe's `scenarios\` folder.

## Rules enforced by `check`

- Original instructions may change their control flow only at declared `--intended` offsets.
- No new backward branch. The vanilla scripts have none, so any branch to itself or an earlier instruction is new and could create a loop the original game never runs.
- The result must re-decode cleanly; branch distances must fit 16 bits.
