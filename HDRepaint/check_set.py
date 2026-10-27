"""Check a folder of HD repaints against every vanilla AITD1 camera.

Usage: python check_set.py <OriginalGame dir> <image dir>
For each camera in CAMERA##.PAK: is there a <PAK>_<idx>.png, is it 1280x800, and does it line up
with the vanilla frame (shift found by phase correlation of the image shrunk to 320x200 against
the vanilla frame, and the edge correlation at zero shift). Also lists files with no camera.
"""
import sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Patcher"))
from aitd_pak import read_pak

game, imgdir = Path(sys.argv[1]), Path(sys.argv[2])
pal = np.frombuffer(read_pak(game / "ITD_RESS.PAK").entries[3].data[:768], np.uint8).reshape(256, 3).astype(np.int32)
if pal.max() < 64: pal = pal * 4
expected, problems = set(), []
for pak in sorted(game.glob("CAMERA*.PAK")):
    for idx, e in enumerate(read_pak(pak).entries):
        raw = e.data
        if len(raw) < 64000:
            continue
        name = f"{pak.stem.upper()}_{idx:03d}"; expected.add(name)
        f = imgdir / f"{name}.png"
        if not f.exists():
            problems.append(f"{name}: MISSING"); continue
        hd = cv2.imread(str(f))
        h, w = hd.shape[:2]
        px = np.frombuffer(raw[-64000:], np.uint8).reshape(200, 320)
        van = cv2.cvtColor(pal[px][:, :, ::-1].astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
        small = cv2.cvtColor(cv2.resize(hd, (320, 200), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        win = cv2.createHanningWindow((320, 200), cv2.CV_32F)
        (dx, dy), resp = cv2.phaseCorrelate(van, small, win)
        ev = cv2.Canny(van.astype(np.uint8), 40, 110).astype(np.float32)
        es = cv2.Canny(small.astype(np.uint8), 40, 110).astype(np.float32)
        ev = cv2.GaussianBlur(ev, (5, 5), 1.5); es = cv2.GaussianBlur(es, (5, 5), 1.5)
        corr = float(np.corrcoef(ev.ravel(), es.ravel())[0, 1])
        flag = []
        if (w, h) != (1280, 800): flag.append(f"size {w}x{h}")
        if resp > 0.1 and max(abs(dx), abs(dy)) > 1.0: flag.append(f"shifted {dx:+.1f},{dy:+.1f} vanilla px")
        if corr < 0.15: flag.append("low edge match, check by eye")
        print(f"{name}  {w}x{h}  shift {dx:+5.1f},{dy:+5.1f} (resp {resp:.2f})  edge corr {corr:.2f}  {'; '.join(flag)}")
        if flag: problems.append(f"{name}: {'; '.join(flag)}")
extra = sorted(p.stem for p in imgdir.glob("*.png") if p.stem.upper() not in expected)
print("\n== Summary ==")
print(f"{len(expected)} vanilla cameras")
for p in problems: print(" ", p)
for x in extra: print(f"  {x}.png: no such vanilla camera (name?)")
