"""Render keyframes of an AITD1 body + animation to a PNG strip (engine posing, flat polygons).

Usage: python render_preview.py --body 12 --anim 254 --out preview.png [--view side|front|both]
Views: engine x right / y down; "front" looks along +z (from in front of a model facing -z),
"side" looks along +x. Bone labels show which group is which.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Patcher"))
import gamedata
from aitd_model import parse_body, parse_anim, pose
from export_gltf import load_palette, bone_names


def draw(body, pts, pal, view, size=360, label=False, names=None):
    img = np.full((size, size, 3), 235, np.uint8)
    P = np.array(pts, float)
    if view == "front":   # screen x = engine x, depth = z
        sx, sy, depth = P[:, 0], P[:, 1], P[:, 2]
    else:                 # side: screen x = engine z, depth = -x
        sx, sy, depth = P[:, 2], P[:, 1], -P[:, 0]
    k = size / 2200.0
    X = (sx * k + size / 2); Y = (sy * k + size * 0.92)
    polys = []
    for p in body.prims:
        if p.type in (1, 8, 9, 10) and len(p.points) >= 3:
            polys.append((np.mean(depth[p.points]), p))
    for _, p in sorted(polys, key=lambda t: -t[0]):           # far first
        c = (pal[p.color][::-1] * 255).astype(int).tolist()
        cv2.fillPoly(img, [np.stack([X[p.points], Y[p.points]], 1).astype(np.int32)], c, cv2.LINE_AA)
    for p in body.prims:
        if p.type == 0:
            a, b = p.points
            cv2.line(img, (int(X[a]), int(Y[a])), (int(X[b]), int(Y[b])), (0, 0, 0), 1, cv2.LINE_AA)
    if label:
        for gi, g in enumerate(body.groups):
            if gi < 2: continue
            b = g.base
            cv2.circle(img, (int(X[b]), int(Y[b])), 3, (0, 0, 255), -1)
            cv2.putText(img, names[gi].split("_", 1)[1], (int(X[b]) + 4, int(Y[b]) - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.33, (0, 0, 160), 1, cv2.LINE_AA)
    cv2.putText(img, view, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", type=int, default=12); ap.add_argument("--anim", type=int, default=-1)
    ap.add_argument("--body-pak", default="LISTBODY.PAK"); ap.add_argument("--anim-pak", default="LISTANIM.PAK")
    ap.add_argument("--view", default="both"); ap.add_argument("--labels", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    body = parse_body(gamedata.pak_entries(a.body_pak)[a.body]); pal = load_palette(); names = bone_names(body)
    n = len(body.groups)
    frames = [("rest", [(0, (0, 0, 0))] * n)]
    if a.anim >= 0:
        an = parse_anim(gamedata.pak_entries(a.anim_pak)[a.anim])
        frames = [(f"key {i} ({f.time}t)", [(0, (0, 0, 0))] + list(f.groups[1:n])) for i, f in enumerate(an.frames)]
    views = ["front", "side"] if a.view == "both" else [a.view]
    rows = []
    for v in views:
        tiles = []
        for title, st in frames:
            t = draw(body, pose(body, st), pal, v, label=a.labels, names=names)
            cv2.putText(t, title, (6, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
            tiles.append(t)
        rows.append(np.hstack(tiles))
    cv2.imwrite(a.out, np.vstack(rows))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
