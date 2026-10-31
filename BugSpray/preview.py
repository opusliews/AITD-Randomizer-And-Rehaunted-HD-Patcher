"""Preview images of the Bug Spray assets (AnimExport/render_preview.py drawing, engine
posing): the can on its own, and each character's held body through the spray animation
(side and front views). Output: out/preview_*.png"""
import sys
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "AnimExport"), str(HERE.parent / "Patcher")]
import spray_assets as S, aitd_model as M, gamedata
from render_preview import draw
from export_gltf import load_palette

out = HERE / "out"; out.mkdir(exist_ok=True)
pal = load_palette()
for k, rgb in enumerate(S.YELLOW_RAMP_RGB):          # the seed's palette (spray.palette_pak)
    pal[S.YELLOW_RAMP_AT + k] = [c / 255 for c in rgb]
can = M.parse_body(S.can_body())
pts = [tuple(v * 6 for v in p) for p in M.pose(can)] if False else [tuple(c * 6 for c in v) for v in can.verts]
cv2.imwrite(str(out / "preview_can.png"), np.hstack([draw(can, pts, pal, "side"), draw(can, pts, pal, "front")]))
for who, pak, apak in (("edward", "LISTBODY.PAK", "LISTANIM.PAK"), ("emily", "LISTBOD2.PAK", "LISTANI2.PAK")):
    held = M.parse_body(S.held_body(gamedata.pak_entries(pak)[12]))
    an = M.parse_anim(S.spray_anim(gamedata.pak_entries(apak)[4], **S.POSE[apak]))
    rows = []
    for view in ("side", "front"):
        rows.append(np.hstack([draw(held, M.pose(held, f.groups), pal, view, size=300) for f in an.frames[:4]]))
    cv2.imwrite(str(out / f"preview_{who}.png"), np.vstack(rows))
print("written", sorted(p.name for p in out.glob("preview_*.png")))
