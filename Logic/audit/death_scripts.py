"""Logic audit (2026-10-27): every LIFE script that can kill the player or end the game, and
which objects run it (floor/room). Output: death_scripts.txt next to this file.
Death = player switched to LIFE 39 (the death script, AnnotationReview), `game_over`, or a
script that assigns another LIFE to OBJ 1 (listed for review)."""
import re, sys
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
            users.setdefault(o[k], []).append(f"OBJ {i} (F{o['stage']}:R{o['room']}, {k})")
# LIFE n -> LIFEs it switches to (life X / obj_N.life X), to follow chains
out = []
for n, d in enumerate(van):
    lines = L.format_script(L.decode(d)).splitlines()
    hits = [l.strip() for l in lines if re.search(r"obj_1\.life \d+|game_over|^\s*life 39\b|obj_1\.life_mode", l)]
    if hits:
        out.append(f"LIFE {n}  run by: {', '.join(users.get(n, ['(assigned by scripts)']))}")
        out += [f"    {h}" for h in hits]
text = "\n".join(out) + "\n"
(HERE / "death_scripts.txt").write_text(text, encoding="utf-8")
print(text)
