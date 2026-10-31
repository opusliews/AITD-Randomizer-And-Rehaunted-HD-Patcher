"""Evidence for the placement rule (2026-10-16): is an item model's origin its bottom?
For every item of the combined pool: the BODY bounding box (y grows downward in AITD), and
for vanilla world items the top (y1) of the hard-collision block under their x/z."""
import csv
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Generated" / "Generator"))
import generate as G  # noqa: E402

BODY = ROOT / "Generated" / "ResearchRun" / "PakInventory" / "extracted" / "LISTBODY"
rows = {int(r["obj_id"]): r for r in csv.DictReader(open(ROOT / "References" / "AITD_objects.csv", encoding="utf-8", errors="replace"))}
zones = list(csv.DictReader(open(ROOT / "References" / "AITD_zones.csv", encoding="utf-8", errors="replace")))
VISIBLE = [13, 56, 86, 83, 102, 107, 110, 120, 121, 123, 144, 125, 163, 171, 199, 182, 232, 17, 25, 96, 148, 205]


def bounds(body):
    d = (BODY / f"{body:08d}.dat").read_bytes()
    return struct.unpack_from("<6h", d, 2)


def support(f, r, x, y, z):
    """Top of the highest block under (x, z) that is at or below y (hard collision only)."""
    best = None
    for zn in zones:
        if zn["zone_kind"] != "hard_collision" or zn["floor_id"] != str(f) or zn["room_id"] != str(r):
            continue
        x1, x2, y1, y2, z1, z2 = (int(zn[k]) for k in ("x1", "x2", "y1", "y2", "z1", "z2"))
        if x1 <= x <= x2 and z1 <= z <= z2 and y1 >= y - 50:
            if best is None or y1 < best[0]:
                best = (y1, zn["zone_id"])
    return best


def main():
    pool = sorted({i for s in G.load_slots() for i in s["items"]} | set(VISIBLE))
    out = []
    for i in pool:
        r = rows[i]
        x1, x2, y1, y2, z1, z2 = bounds(int(r["body_id"]))
        line = (f"{i:4} {r['known_name'][:24]:24} body {r['body_id']:>3} y {y1:5}..{y2:5} "
                f"x {x1:5}..{x2:5} z {z1:5}..{z2:5} ang {r['initial_alpha']},{r['initial_beta']},{r['initial_gamma']}")
        if i in VISIBLE and r["initial_floor"].strip():
            f, rm, x, y, z = (int(r[k]) for k in ("initial_floor", "initial_room", "x", "y", "z"))
            s = support(f, rm, x, y, z)
            line += f" | at y {y}, support {s}"
        out.append(line)
    print("\n".join(out))


if __name__ == "__main__":
    main()
