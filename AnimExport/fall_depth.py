"""How far each fall animation lowers the model (shadow investigation, 2026-10-21).

For body/anim pairs from LIFE 39 (the floor-hole and other deaths), prints per keyframe
the model's lowest and highest Y (engine Y grows downwards, floor = 0) and the frame's
step (movement of the actor's position). Usage: python fall_depth.py
"""
import sys
from pathlib import Path
from aitd_model import parse_body, parse_anim, pose
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Patcher"))
import gamedata

PAIRS = [(12, 266), (15, 285), (31, 285), (193, 285), (44, 297), (45, 297), (11, 294), (12, 261)]
bodies = gamedata.pak_entries("LISTBODY.PAK")
anims = gamedata.pak_entries("LISTANIM.PAK")
for b, a in PAIRS:
    body = parse_body(bodies[b])
    anim = parse_anim(anims[a])
    rest = pose(body)
    print(f"body {b} anim {a}: {len(anim.frames)} keyframes; rest pose y {min(p[1] for p in rest)}..{max(p[1] for p in rest)}")
    total = [0, 0, 0]
    for i, f in enumerate(anim.frames):
        pts = pose(body, f.groups)
        total = [t + s for t, s in zip(total, f.step)]
        print(f"  key {i:2d} time {f.time:3d} step {f.step} (sum {tuple(total)})  "
              f"y {min(p[1] for p in pts):6d}..{max(p[1] for p in pts):6d}")
