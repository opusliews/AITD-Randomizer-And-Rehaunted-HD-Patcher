"""Logic audit (2026-10-27): can the player walk between every doorway of a room?

Floor grid per room (step 50) from rooms.json:
- the room's floor = inside a camera cover polygon of the room (camera_cover.py; the engine
  picks cameras from these, so they mark where the player can be);
- rooms with type-3 floor blocks (caves): a cell needs a block under it; its top (y1) is the
  floor height there; elsewhere the floor is y = 0;
- blocked when a hard-collision box overlaps the player's box at that floor height:
  x/z +-R, y floor-1777..floor (body 12), open intervals as FITD AsmCheckListCol; every hard
  type blocks (anim.cpp);
- deadly scene zones (DEADLY) block: the engine tests the player's position point (GereDec);
- cells inside a type-0/10 scene zone are exits (the engine changes room there);
- neighbours with floors more than MAX_STEP apart are not connected (flagged, not assumed).
Actors (doors, furniture objects, monsters) are not modelled.
Output: room_walk.txt, one line per room: the walkable areas and the exits each one reaches."""
import json, sys
from collections import deque
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import camera_cover as CC
ROOMS = HERE.parents[1] / "ResearchRun" / "TrackRooms" / "datasets" / "rooms.json"
DEADLY = {(1, 1, 3): "corridor hole (LIFE 38)"}     # (floor, room, scene zone id)
STEP, BODY, MAX_STEP = 50, 1777, 300
COVER_MARGIN = 400                  # cover polygons stop short of doorways: allow this much beyond


def analyse(r, R, cover, debug=False):
    hard, scene = r["hard_collision_zones"], r["scene_zones"]
    polys = cover.get(r["room"], [])
    if not polys:
        return None
    xs = [x for p in polys for x, _ in p] + [z["x1"] for z in scene] + [z["x2"] for z in scene]
    zs = [z for p in polys for _, z in p] + [z["z1"] for z in scene] + [z["z2"] for z in scene]
    x0, z0 = min(xs) // STEP * STEP, min(zs) // STEP * STEP
    x0, z0 = x0 - COVER_MARGIN, z0 - COVER_MARGIN
    nx, nz = (max(xs) - x0) // STEP + 2 + COVER_MARGIN // STEP, (max(zs) - z0) // STEP + 2 + COVER_MARGIN // STEP
    blocks = [h for h in hard if h["type"] == 3]
    exits = [z for z in scene if z["type"] in (0, 10)]
    deadly = [z for z in scene if (r["floor"], r["room"], z["zone_id"]) in DEADLY]
    covered = [[CC.inside(polys, x0 + i * STEP, z0 + k * STEP) for k in range(nz)] for i in range(nx)]
    near = [[False] * nz for _ in range(nx)]     # within COVER_MARGIN of a cover polygon
    m = COVER_MARGIN // STEP
    q = deque((i, k, 0) for i in range(nx) for k in range(nz) if covered[i][k])
    for i, k, _ in q:
        near[i][k] = True
    while q:
        a, b, dist = q.popleft()
        if dist == m:
            continue
        for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c, d = a + da, b + db
            if 0 <= c < nx and 0 <= d < nz and not near[c][d]:
                near[c][d] = True; q.append((c, d, dist + 1))
    fy = [[None] * nz for _ in range(nx)]        # floor height of a walkable cell
    exit_of = {}
    for i in range(nx):
        x = x0 + i * STEP
        for k in range(nz):
            z = z0 + k * STEP
            if blocks:
                under = [b["y1"] for b in blocks if b["x1"] <= x <= b["x2"] and b["z1"] <= z <= b["z2"]]
                if not under:
                    continue
                y = min(under)
            else:
                y = 0
            if any(h["x1"] < x + R and x - R < h["x2"] and h["z1"] < z + R and z - R < h["z2"]
                   and h["y1"] < y and y - BODY < h["y2"] for h in hard):
                continue
            ex = next((e for e in exits if e["x1"] <= x <= e["x2"] and e["z1"] <= z <= e["z2"]
                       and e["y1"] <= y <= e["y2"]), None)
            if ex is not None:
                exit_of[(i, k)] = ex
                continue
            if not near[i][k]:
                continue
            if any(d["x1"] <= x <= d["x2"] and d["z1"] <= z <= d["z2"] for d in deadly):
                continue
            fy[i][k] = y
    comp = [[-1] * nz for _ in range(nx)]
    n = 0
    for i in range(nx):
        for k in range(nz):
            if fy[i][k] is not None and comp[i][k] < 0:
                q = deque([(i, k)]); comp[i][k] = n
                while q:
                    a, b = q.popleft()
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        c, d = a + da, b + db
                        if 0 <= c < nx and 0 <= d < nz and fy[c][d] is not None and comp[c][d] < 0 \
                                and abs(fy[c][d] - fy[a][b]) <= MAX_STEP:
                            comp[c][d] = n; q.append((c, d))
                n += 1
    size = {}
    for i in range(nx):
        for k in range(nz):
            if comp[i][k] >= 0:
                size[comp[i][k]] = size.get(comp[i][k], 0) + 1
    reach = {}
    for (i, k), e in exit_of.items():
        name = f"SZ{e['zone_id']}->{'F' if e['type'] == 10 else 'R'}{e['parameter']}"
        reach.setdefault(name, set())
        for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c, d = i + da, k + db
            if 0 <= c < nx and 0 <= d < nz and comp[c][d] >= 0:
                reach[name].add(comp[c][d])
    for e in exits:
        reach.setdefault(f"SZ{e['zone_id']}->{'F' if e['type'] == 10 else 'R'}{e['parameter']}", set())
    if debug:
        return reach, size, dict(fy=fy, comp=comp, x0=x0, z0=z0, nx=nx, nz=nz, blocks=blocks, hard=hard)
    return reach, size


def main(widths=(300, 150), floors=None, write=True):
    rooms = json.loads(ROOMS.read_text(encoding="utf-8"))
    covers = {}
    out = []
    for R in widths:
        out.append(f"== player half-width {R}, max floor step {MAX_STEP}")
        for r in rooms:
            if floors is not None and r["floor"] not in floors:
                continue
            if r["floor"] not in covers:
                covers[r["floor"]] = CC.covers(r["floor"])
            res = analyse(r, R, covers[r["floor"]])
            if res is None:
                out.append(f"--    F{r['floor']}:R{r['room']}: no camera cover (not a playable room)")
                continue
            reach, size = res
            # ok when one area touches every doorway (tiny pockets beside doorways are ignored)
            areas = sorted({c for cs in reach.values() for c in cs}, key=lambda c: -size[c])
            main_area = next((c for c in areas if all(c in cs for cs in reach.values())), None)
            if main_area is not None:
                out.append(f"ok    F{r['floor']}:R{r['room']}: one area ({size[main_area]} cells) reaches "
                           + ", ".join(sorted(reach)))
                continue
            groups = {}
            for e, cs in reach.items():
                big = [c for c in cs if size[c] >= 100] or sorted(cs, key=lambda c: -size[c])[:1]
                groups.setdefault(tuple(sorted(big)), []).append(e)
            out.append(f"SPLIT F{r['floor']}:R{r['room']}: " + " | ".join(
                f"{'+'.join(f'a{c}({size[c]})' for c in k) if k else 'UNREACHED'}: {', '.join(sorted(v))}"
                for k, v in groups.items()))
    text = "\n".join(out) + "\n"
    if write:
        (HERE / "room_walk.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
