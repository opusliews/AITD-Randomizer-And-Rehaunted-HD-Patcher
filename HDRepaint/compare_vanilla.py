"""Overlay vanilla AITD1 camera frames on user-painted 4x HD backgrounds.

Usage: python compare_vanilla.py <OriginalGame dir> <HD png>... --out <dir>
Writes <name>_vanilla_x4.png and <name>_edges.png (vanilla edges in red on the HD image).
"""
import argparse, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Patcher"))
from aitd_pak import read_pak

ap = argparse.ArgumentParser()
ap.add_argument("game"); ap.add_argument("images", nargs="+"); ap.add_argument("--out", required=True)
a = ap.parse_args()
game = Path(a.game); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
pal = read_pak(game / "ITD_RESS.PAK").entries[3].data[:768]
pal = np.frombuffer(pal, np.uint8).reshape(256, 3).astype(np.int32)
if pal.max() < 64: pal = pal * 4
for img in a.images:
    p = Path(img); stem = p.stem               # CAMERA00_002
    pakname, idx = stem.split("_"); idx = int(idx)
    raw = read_pak(game / f"{pakname}.PAK").entries[idx].data
    px = np.frombuffer(raw[-64000:] if len(raw) != 64000 else raw, np.uint8).reshape(200, 320)
    van = pal[px][:, :, ::-1].astype(np.uint8)
    hd = cv2.imread(str(p))
    h, w = hd.shape[:2]
    big = cv2.resize(van, (w, h), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(out / f"{stem}_vanilla_up.png"), big)
    e = cv2.Canny(cv2.cvtColor(cv2.resize(van, (w, h), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2GRAY), 40, 110)
    ov = hd.copy(); ov[e > 0] = (0, 0, 255)
    cv2.imwrite(str(out / f"{stem}_edges.png"), ov)
    print(stem, hd.shape, "entry bytes", len(raw))
