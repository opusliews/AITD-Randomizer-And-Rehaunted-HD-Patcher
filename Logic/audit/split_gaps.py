"""Logic audit helper: for rooms that room_walk.py reports as split, the narrowest gap between
each pair of walkable areas and what fills it (no floor block = water/chasm, or a wall box),
and for unreached exits whether any floor block touches the exit."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import room_walk as W, camera_cover as CC


def report(f, rr, R=300):
    rooms = json.loads(W.ROOMS.read_text(encoding="utf-8"))
    r = next(r for r in rooms if r["floor"] == f and r["room"] == rr)
    reach, size, g = W.analyse(r, R, CC.covers(f), debug=True)
    fy, comp, x0, z0, nx, nz = g["fy"], g["comp"], g["x0"], g["z0"], g["nx"], g["nz"]
    big = sorted(c for c in size if size[c] >= 100)
    cells = {c: [(i, k) for i in range(nx) for k in range(nz) if comp[i][k] == c] for c in big}
    lines = [f"F{f}:R{rr}: areas {[(c, size[c]) for c in big]}  exits {dict((e, sorted(v)) for e, v in reach.items())}"]
    for c in big:
        ys = [fy[i][k] for i, k in cells[c]]
        xs = [x0 + i * W.STEP for i, _ in cells[c]]; zs = [z0 + k * W.STEP for _, k in cells[c]]
        lines.append(f"   a{c}: floor y {min(ys)}..{max(ys)}, x {min(xs)}..{max(xs)}, z {min(zs)}..{max(zs)}")
    for a in big:
        for b in big:
            if a < b:
                d, (i, k), (j, l) = min(((abs(i - j) + abs(k - l)) * W.STEP, (i, k), (j, l))
                                        for i, k in cells[a][::3] for j, l in cells[b][::3])
                x, z = x0 + (i + j) // 2 * W.STEP, z0 + (k + l) // 2 * W.STEP
                under = [h["y1"] for h in g["blocks"] if h["x1"] <= x <= h["x2"] and h["z1"] <= z <= h["z2"]]
                walls = [h["zone_id"] for h in g["hard"] if h["type"] != 3 and h["x1"] <= x <= h["x2"] and h["z1"] <= z <= h["z2"]]
                lines.append(f"   a{a}<->a{b}: gap ~{d} around ({x},{z}); floor block there: {under or 'NONE'}; "
                             f"wall boxes: {walls or 'none'}; edge heights {fy[i][k]} / {fy[j][l]}")
    for e, v in reach.items():
        if not v:
            ex = next(z for z in r["scene_zones"] if f"SZ{z['zone_id']}" == e.split("->")[0])
            under = [h["y1"] for h in g["blocks"] if h["x1"] < ex["x2"] and ex["x1"] < h["x2"] and h["z1"] < ex["z2"] and ex["z1"] < h["z2"]]
            lines.append(f"   {e} UNREACHED: exit x {ex['x1']}..{ex['x2']} y {ex['y1']}..{ex['y2']} z {ex['z1']}..{ex['z2']}; "
                         f"floor blocks touching it (tops): {under or 'NONE'}")
    return "\n".join(lines)


if __name__ == "__main__":
    out = "\n".join(report(f, r) for f, r in ((5, 0), (5, 2), (5, 7), (5, 8), (5, 10), (6, 6)))
    (HERE / "split_gaps.txt").write_text(out + "\n", encoding="utf-8")
    print(out)
