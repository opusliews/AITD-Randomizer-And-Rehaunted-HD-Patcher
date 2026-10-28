"""Assumption register (2026-10-28): where do LIFE 533 (F5:R0) and LIFE 534 (F6:R0) soak the
player's matchboxes (121, 174), cartridges 18 and rifle ammo, and put out a lit lamp not held
in hand? Both test `obj_1.room_y > -2000` (if_sup obj_1.room_y #-2000 continues when greater).
Uses room_walk.py's floor grid (floor height = top of the type-3 block under the cell) and asks,
per room: which cells are 'wet' (floor > -2000), and can each doorway be reached from the
others on dry cells only? Output: water_check.txt."""
import json, sys
from collections import deque
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import room_walk as RW, camera_cover as CC
HERE = Path(__file__).resolve().parent
WET_ABOVE = -2000
rooms = json.loads(RW.ROOMS.read_text(encoding="utf-8"))
out = []
for fl, rm in ((5, 0), (6, 0)):
    r = next(x for x in rooms if x["floor"] == fl and x["room"] == rm)
    reach, size, g = RW.analyse(r, 150, CC.covers(fl), debug=True)
    fy, nx, nz = g["fy"], g["nx"], g["nz"]
    ys = sorted({y for col in fy for y in col if y is not None})
    wet = sum(1 for col in fy for y in col if y is not None and y > WET_ABOVE)
    dry = sum(1 for col in fy for y in col if y is not None and y <= WET_ABOVE)
    out.append(f"F{fl}:R{rm}: floor heights {ys[:12]}{' ...' if len(ys) > 12 else ''}; "
               f"wet cells {wet}, dry cells {dry}")
    # doorway cells next to walkable cells; dry-only connectivity
    comp = [[-1] * nz for _ in range(nx)]
    n = 0
    for i in range(nx):
        for k in range(nz):
            if fy[i][k] is not None and fy[i][k] <= WET_ABOVE and comp[i][k] < 0:
                q = deque([(i, k)]); comp[i][k] = n
                while q:
                    a, b = q.popleft()
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        c, d = a + da, b + db
                        if 0 <= c < nx and 0 <= d < nz and fy[c][d] is not None and fy[c][d] <= WET_ABOVE \
                                and comp[c][d] < 0 and abs(fy[c][d] - fy[a][b]) <= RW.MAX_STEP:
                            comp[c][d] = n; q.append((c, d))
                n += 1
    exits = [z for z in r["scene_zones"] if z["type"] in (0, 10)]
    for e in exits:
        name = f"SZ{e['zone_id']}->{'F' if e['type'] == 10 else 'R'}{e['parameter']}"
        cells = [(i, k) for i in range(nx) for k in range(nz)
                 if e["x1"] - RW.STEP <= g["x0"] + i * RW.STEP <= e["x2"] + RW.STEP
                 and e["z1"] - RW.STEP <= g["z0"] + k * RW.STEP <= e["z2"] + RW.STEP and fy[i][k] is not None]
        wy = sorted({fy[i][k] for i, k in cells})
        out.append(f"  {name}: y {e['y1']}..{e['y2']}; floor next to it {wy}; dry areas "
                   f"{sorted({comp[i][k] for i, k in cells if comp[i][k] >= 0})}")
text = "\n".join(out) + "\n"
(HERE / "water_check.txt").write_text(text, encoding="utf-8")
print(text)
