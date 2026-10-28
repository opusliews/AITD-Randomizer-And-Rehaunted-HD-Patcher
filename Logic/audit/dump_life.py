"""Dump every vanilla LIFE script (formatted) to life_dump.txt, with the objects that run it.
Used by the 2026-10-28 assumption register (Research/LogicAssumptions.md)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "Patcher")]
import aitd_life as L, aitd_objets as O, gamedata

van = gamedata.pak_entries("LISTLIFE.PAK")
objs = O.load(gamedata.source_dir() / "OBJETS.ITD")
users = {}
for i, o in enumerate(objs):
    for k in ("life", "floor_life"):
        if o[k] >= 0:
            users.setdefault(o[k], []).append(f"OBJ {i} '{o.get('name', '')}' (F{o['stage']}:R{o['room']}, {k})")
out = []
for n, d in enumerate(van):
    out.append(f"===== LIFE {n}  run by: {', '.join(users.get(n, ['(assigned by scripts)']))}")
    out.append(L.format_script(L.decode(d)))
(HERE / "life_dump.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print(len(van), "scripts")
