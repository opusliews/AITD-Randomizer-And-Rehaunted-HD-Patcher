"""Look test of the drop glow (2026-10-17): key 37 lies on the attic floor at the spot of
Scenarios/attic_placed_items.scn (2600 0 -1548, 600 units west of the start) with a glow
object around it. The glow's script deletes the glow once the key has been taken.

  python build_glow_test.py

Writes
  Generated/VanillaTest/T8/            OriginalGame/INDARK copy + the patched files (exe untouched)
  Generated/VanillaTest/T8.conf, run_T8.bat
  Generated/Scenarios/patchsets/glow_poc/ + Scenarios/glow_poc.scn   (ReHaunted TatouScenario)

Patched files: OBJETS.ITD (key 37 placed, glow record appended), LISTLIFE.PAK (the glow
script appended, then the padding entry), LISTBODY.PAK / LISTBOD2.PAK (the randomizer's models,
glow included, VisibleItems/mechanics.listbody).
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent
ROOT = GEN.parent
for d in ("Patcher", "VisibleItems", "DropGlow"):
    sys.path.insert(0, str(GEN / d))
import aitd_life as L            # noqa: E402
import aitd_objets as O          # noqa: E402
import gamedata                  # noqa: E402
import glow                      # noqa: E402
import mechanics                 # noqa: E402
from aitd_pak import read_pak, write_pak   # noqa: E402

KEY, AT = 37, (0, 0, 2600, 0, -1548)      # stage room x y z


def patched_files() -> dict[str, bytes]:
    src = gamedata.source_dir()
    objs = O.load(src / "OBJETS.ITD")
    objs[KEY].update(stage=AT[0], room=AT[1], x=AT[2], y=AT[3], z=AT[4])
    objs[KEY]["flags"] |= 0x80      # touch pickup (AF_FOUNDABLE), as put_at sets it (FITD PutAtObjet)
    entries = [bytearray(e.data) for e in read_pak(src / "LISTLIFE.PAK").entries]
    rec, script = glow.glow_object(len(objs), [KEY])
    rec.update(stage=AT[0], room=AT[1], x=AT[2], y=AT[3], z=AT[4])
    rec["life"] = len(entries)
    objs.append(rec)
    entries.append(bytearray(L.encode(script)))
    entries.append(bytearray(L.encode(L.parse_script("endlife\n"))))   # padding (one entry fewer is read)
    files = {"OBJETS.ITD": O.write_objets(objs), "LISTLIFE.PAK": write_pak([bytes(e) for e in entries])}
    files.update(mechanics.listbodies())
    return files


def main():
    files = patched_files()
    dst = GEN / "VanillaTest" / "T8"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(ROOT / "OriginalGame" / "INDARK", dst / "INDARK")
    pset = GEN / "Scenarios" / "patchsets" / "glow_poc"
    if pset.exists():
        shutil.rmtree(pset)
    pset.mkdir(parents=True)
    for name, data in files.items():
        (dst / "INDARK" / name).write_bytes(data)
        (pset / name).write_bytes(data)
        print(f"{name:13} {hashlib.sha256(data).hexdigest()}")
    conf = (GEN / "VanillaTest" / "T7.conf").read_text(encoding="utf-8").replace("VanillaTest\\T7", "VanillaTest\\T8")
    conf = conf.replace("output=opengl", "output=surface")    # opengl renders black inside the VM
    (GEN / "VanillaTest" / "T8.conf").write_text(conf, encoding="utf-8")
    (GEN / "VanillaTest" / "run_T8.bat").write_text(
        '@echo off\r\n"C:\\Tools\\DOSBox-X\\bin\\x64\\Release\\dosbox-x.exe" -conf "%~dp0T8.conf"\r\n',
        encoding="utf-8")
    (GEN / "Scenarios" / "glow_poc.scn").write_text(
        "# TEST:   Drop glow look test: key 37 on the attic floor inside a translucent gold beam.\n"
        "# EXPECT: The beam is see-through, never blocks, and disappears once the key is taken.\n"
        "name Drop glow PoC\npatchset patchsets/glow_poc\n", encoding="utf-8")


if __name__ == "__main__":
    main()
