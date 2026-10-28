"""Logic audit (2026-10-27): every door-like LIFE script (opens/closes with posrel and door
anims) and every condition it tests besides the standard ones. Standard door script (LIFE 22):
col_by player, var_24 == 0 (global), its own open-state var. Output door_conditions.txt."""
import re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "Patcher")]
import aitd_life as L, aitd_objets as O, gamedata

van = gamedata.pak_entries("LISTLIFE.PAK")
objs = O.load(gamedata.source_dir() / "OBJETS.ITD")
out = []
for i, o in enumerate(objs):
    n = o["life"]
    if n < 0:
        continue
    lines = [l.strip() for l in L.format_script(L.decode(van[n])).splitlines()]
    text = "\n".join(lines)
    if "posrel(1)" not in text or not re.search(r"anim_(repeat|once) (2[6-9]|30)\b", text):
        continue
    conds = []
    for l in lines:
        m = re.search(r"if_(egal|different|sup|inf|sup_egal|inf_egal) (\S+) (\S+)", l)
        if not m:
            continue
        a = m.group(2)
        if a in ("col_by", "obj_1.anim", "obj_1.end_anim", "var_24", "posrel(1)"):
            continue
        conds.append(f"{m.group(1)} {a} {m.group(3)}")
    state = [c for c in conds if re.fullmatch(r"egal var_\d+ #0", c)]
    extra = [c for c in conds if c not in state[:1]]
    out.append(f"OBJ {i:3d} F{o['stage']}:R{o['room']} LIFE {n}: " + ("; ".join(extra) if extra else "standard"))
text = "\n".join(out) + "\n"
(HERE / "door_conditions.txt").write_text(text, encoding="utf-8")
print(text)
