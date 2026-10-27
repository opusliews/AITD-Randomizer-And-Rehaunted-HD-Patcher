"""Visual test batches for visible items (2026-10-16; user's quick-succession idea).

For every room with world locations, 3 scenarios: each puts a differently shaped item at every
location of the room (V1 big/tall, V2 long, V3 small/flat; V3 at touch spots also checks that a
small item can be touched and picked up), moves the location's vanilla item away, and puts the
player in the room at a safe point near the locations. Poses come from placement.py. Writes
Generated/Scenarios/visible/*.scn and CHECKLIST.md (one line per scenario for the user's notes).

Player point (automatic, as in memory 'player placement checks'): inside the room (walls hit in
all four directions), outside every hard-collision box (+250), outside the room's type-0 scene
(room-change) zones, >= 400 from contact zones (type 9), >= 700 from every placed object with a
model (monsters, ghosts, furniture actors), 800-1600 from the room's locations, on floor y 0.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placement as P  # noqa: E402

OUT = P.ROOT / "Generated" / "Scenarios" / "visible"


def named_objects() -> dict[int, dict]:
    """P.objects() plus the item names of References/AITD_objects.csv (project annotation, for the
    scenario comments only)."""
    import csv
    names = {int(r["obj_id"]): r["known_name"] for r in csv.DictReader(
        open(P.ROOT / "References" / "AITD_objects.csv", encoding="utf-8", errors="replace"))}
    return {i: {**o, "known_name": names.get(i, "")} for i, o in P.objects().items()}

# item classes (vanilla object ids); the order is the preference within a class
BIG = [123, 171, 96, 56, 167, 13, 83, 16, 205, 268, 46, 5]
LONG = [81, 3, 38, 120, 26, 78, 25, 111, 172, 232]
SMALL = [37, 101, 15, 121, 54, 199, 125, 12, 109, 110, 148]
CLASSES = [("V1 big/tall", BIG), ("V2 long", LONG), ("V3 small/flat", SMALL)]
LAMP_DARK_ROOMS = {(2, 0), (2, 6)}         # dark rooms (logic): the player gets the lit lamp


def room_name(f, r):
    import json
    d = json.loads((P.ROOT / "Generated" / "Logic" / "location_names.json").read_text(encoding="utf-8"))
    v = d.get("rooms", d).get(f"{f}/{r}", {})
    return v.get("name", f"{f}/{r}") if isinstance(v, dict) else str(v)


def player_point(f, r, spots, objs, zs, used_objs):
    hard, scene, contact = [], [], []
    for z in zs:
        if z["floor_id"] != str(f) or z["room_id"] != str(r):
            continue
        b = P.box(z)
        if z["zone_kind"] == "hard_collision":
            hard.append((b, z["type"]))
            if z["type"] == "9":
                contact.append(b)
        elif z["zone_kind"] == "scene" and z["type"] == "0":   # room-change zones (the caverns' type-9 scene zones are not)
            scene.append(b)
    things = []
    for i, o in objs.items():
        if o["initial_floor"] == str(f) and o["initial_room"] == str(r) and o["body_id"].strip() not in ("", "-1") \
                and i not in used_objs and i != 1:
            things.append((int(o["x"]), int(o["z"])))

    def inside(b, x, z, m=0):
        return b[0] - m <= x <= b[1] + m and b[4] - m <= z <= b[5] + m

    def dist_box(b, x, z):
        dx = max(b[0] - x, 0, x - b[1])
        dz = max(b[4] - z, 0, z - b[5])
        return math.hypot(dx, dz)

    def walled(x, z):
        walls = [b for b, t in hard if t in ("0", "1") and b[2] <= -2000]   # full-height blocks
        hits = [any(b[4] <= z <= b[5] and b[1] < x for b in walls), any(b[4] <= z <= b[5] and b[0] > x for b in walls),
                any(b[0] <= x <= b[1] and b[5] < z for b in walls), any(b[0] <= x <= b[1] and b[4] > z for b in walls)]
        return all(hits)

    best = None
    xs = [s["x"] for s in spots]
    zs_ = [s["z"] for s in spots]
    for gx in range(min(xs) - 2000, max(xs) + 2001, 100):
        for gz in range(min(zs_) - 2000, max(zs_) + 2001, 100):
            if any(inside(b, gx, gz, 250) for b, _ in hard) or any(inside(b, gx, gz, 100) for b in scene):
                continue
            if any(dist_box(b, gx, gz) < 400 for b in contact):
                continue
            if any(math.hypot(gx - tx, gz - tz) < 700 for tx, tz in things):
                continue
            d = [math.hypot(gx - s["x"], gz - s["z"]) for s in spots]
            if min(d) < 800 or max(d) > 1600 and min(d) > 1600:
                continue
            if not walled(gx, gz):
                continue
            score = abs(min(d) - 1100) + 0.2 * (max(d) - min(d))
            if best is None or score < best[0]:
                best = (score, gx, gz)
    return None if best is None else (best[1], best[2])


# Later rounds (user, 2026-10-17: tested scenarios never change; new and replacement tests are
# appended after the highest number). Each round: (title, note for superseded tests, [(location, item)]).
# Retired (user, 2026-10-17: obsolete tests deleted; also round 13 / 173 and its stray rebuild 180): rounds 8-9 / 141-153 (smaller rug, superseded by round 10); round 2 (89-98, upside down), round 4
# (109-118, vanilla cover model), rounds 5-7 (119-140, earlier rug models); also 34-36 and 61-69 of
# the first batch. Numbers are never reused: new rounds go after the highest remaining one... and
# after 150 at least.
RETIRED_UP_TO = 180
ROUNDS = [
    ("Round 3 (2026-10-17): Ballroom mantel, the same items turned right way up",
     "Replaces round 2 (89-98: correct but upside down): the Ballroom spot faces the other way from the bow "
     "spot, so the roll is 256, not 768.",
     [("W:144", i) for i in (3, 25, 26, 38, 78, 81, 111, 120, 172, 37)]),
    ("Round 10 (2026-10-17): the rug 1.5x bigger (1/4 of the inventory model), no shadow; Bedroom 1 mantel leanable",
     "Replaces all rug tests 144-153 (deleted). Patch set vis_cover_model4: model 272 = the rug at 1/4, plain "
     "(not jointed), so no constant ReHaunted shadow. The bow spot and the Bedroom 1 mantel come in two variants "
     "(the quarter turn / the side facing the room): note which one looks right. Then long items on the "
     "Bedroom 1 mantel, now a leaning spot.",
     [("W:25", 5, ["obj 5 beta 512"]), ("W:25", 5, ["obj 5 beta 0"]),
      ("W:86", 5), ("W:86", 5, ["obj 5 gamma 768", "obj 5 y -1625"]),
      ("W:144", 5), ("W:163", 5), ("W:13", 5), ("W:107", 5), ("W:171", 5), ("W:96", 5), ("W:148", 5), ("W:120", 5),
      ("W:86", 3), ("W:86", 81), ("W:86", 120)],
     {"patchset": "../patchsets/vis_cover_model4", "commands": ["obj 5 body 272"], "body": 272}),
    ("Round 14 (2026-10-17): 173 spun 180 degrees within its own plane",
     "173 was perfect (user); then spun 180 degrees about its face axis: same face toward the camera, "
     "upside down (placement.turn_about).",
     [("W:25", 5, ["obj 5 alpha 256", "obj 5 beta 512", "obj 5 gamma 512", "obj 5 y -475"])],
     {"patchset": "../patchsets/vis_cover_model4", "commands": ["obj 5 body 272"], "body": 272}),
    ("Round 15 (2026-10-17): long items on the Bedroom 1 mantel (redone), the rug turned at the Ballroom and Attic",
     "175-177 replace 166-168 (deleted: a builder bug posed them with the rug's model, so they lay flat). "
     "178: the Ballroom rug (158) spun 180 degrees within its plane. 179: the Attic table rug (160) turned 90 "
     "degrees on its flat axis.",
     [("W:86", 3), ("W:86", 81), ("W:86", 120),
      ("W:144", 5, ["obj 5 alpha 0", "obj 5 beta 256", "obj 5 gamma 768", "obj 5 y -1525"]),
      ("W:13", 5, ["obj 5 beta 256"])],
     {"patchset": "../patchsets/vis_cover_model4", "commands": ["obj 5 body 272"], "body": 272}),
    ("Round 16 (2026-10-17): the cross arrow (two fins at 90 degrees) at world locations",
     "User idea: arrows are too thin to see from some sides, so an arrow placed by the randomizer at a world "
     "location shows a model made of the arrow plus a copy turned 90 degrees about its long axis (model 273). "
     "Picked up, its found-life switches it back to the plain arrow: at the Drawing Room floor (touch), pick it "
     "up, drop it and check it is the thin vanilla arrow again. Patch set vis_cross_arrow.",
     [("W:13", 26), ("W:148", 26), ("W:25", 26), ("W:163", 26), ("W:86", 26), ("W:120", 26)],
     {"patchset": "../patchsets/vis_cross_arrow", "commands": ["obj 26 body 273"], "bodies": {26: 273}}),
]


def append_rounds():
    """Writes the rounds not written yet: new numbers after the highest existing scenario, rows
    appended to CHECKLIST.md. Existing scenario files are never rewritten."""
    objs, zs = named_objects(), P.zones()
    spots = {s["id"]: s for s in P.world_spots()}
    check = OUT / "CHECKLIST.md"
    text = check.read_text(encoding="utf-8")
    n = max([RETIRED_UP_TO] + [int(f.name.split("_")[1]) for f in OUT.glob("vis_*.scn")])
    for title, note, tests, *extra in ROUNDS:
        extra = extra[0] if extra else {}
        if f"## {title}" in text:
            continue
        rows = ["", f"## {title}", "", note, "", "| Scenario | Room | Location → test item (rule) | Notes |",
                "|---|---|---|---|"]
        for sid, item, *after in tests:
            after = after[0] if after else []
            s = spots[sid]
            f, r = s["floor"], s["room"]
            body_override = extra.get("bodies", {}).get(item) or (extra.get("body") if item == P.COVER else None)
            p = P.pose(item, s, objs, body=body_override)
            pt = player_point(f, r, [s], objs, zs, {item, s["vanilla_item"]})
            n += 1
            nm = objs[item]["known_name"] or f"OBJ {item}"
            name = f"vis_{n:02d}_{room_name(f, r).replace(' ', '_')}_{s['kind']}_{nm.split()[-1]}"
            flags = 128 if s["mechanism"] == "touch" else 0
            body = [f"# Visible items, {title.split(':')[0]}, test {n:02d}: {room_name(f, r)} ({f}/{r}), {s['id']} "
                    f"({s['kind']}, {s['mechanism']}).",
                    f"#   OBJ {item} {nm} at ({p['x']}, {p['y']}, {p['z']}), angles "
                    f"{p['alpha']}/{p['beta']}/{p['gamma']}: {p['rule']}",
                    f"# Player at ({pt[0]}, 0, {pt[1]}): automatic safe point.",
                    f"name Visible items {n:02d}: {nm} at the {room_name(f, r)} {s['kind']} spot"]
            if extra.get("patchset"):
                body.append(f"patchset {extra['patchset']}")
            body += extra.get("commands", [])
            body += [f"remove {s['vanilla_item']}",
                    f"obj {item} stage {f}", f"obj {item} room {r}", f"obj {item} x {p['x']}", f"obj {item} y {p['y']}",
                    f"obj {item} z {p['z']}", f"obj {item} alpha {p['alpha']}", f"obj {item} beta {p['beta']}",
                    f"obj {item} gamma {p['gamma']}", f"obj {item} flags {flags}"] + after + [
                    f"player {f} {r} {pt[0]} 0 {pt[1]}"]
            if after:
                body.insert(2, f"# Variant: {'; '.join(after)}")
            path = OUT / f"{name}.scn"
            if path.exists():
                raise SystemExit(f"{path.name} exists: scenarios are never rewritten")
            path.write_text("\n".join(body) + "\n", encoding="utf-8")
            rows.append(f"| `{name}.scn` | {room_name(f, r)} | {s['id']} {s['kind']} → {nm} ({p['rule']})"
                        f"{' — variant: ' + '; '.join(after) if after else ''} | |")
        text += "\n".join(rows) + "\n"
        check.write_text(text, encoding="utf-8")
        print(f"{title}: up to {n:02d}")


def main():
    if any(OUT.glob("vis_*.scn")):
        # the first batch (01-88) is frozen once tested: only append later rounds
        append_rounds()
        return
    objs, zs = named_objects(), P.zones()
    spots = P.world_spots()
    by_room = defaultdict(list)
    for s in spots:
        by_room[(s["floor"], s["room"])].append(s)
    # locations far apart in one room (> 2000) get their own scenario set, so the player is
    # always next to what is being checked
    groups = []
    for key, room_spots in sorted(by_room.items()):
        clusters = []
        for s in room_spots:
            near = next((c for c in clusters if any(math.hypot(s["x"] - t["x"], s["z"] - t["z"]) <= 2000 for t in c)), None)
            if near is None:
                clusters.append([s])
            else:
                near.append(s)
        groups += [(key, c) for c in clusters]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.scn"):
        old.unlink()
    checklist = ["# Visible items: visual test checklist (generated by Generated/VisibleItems/build_visual_tests.py)", "",
                 "Drag each scenario onto TatouScenario (or start it with `--scenario`). For each item note: "
                 "**ok / floats / sunk / wrong pose / not visible**. Clipping and absurd sizes are fine (user, 2026-10-16).",
                 "At **touch** spots (marked *touch*), also walk into the item: it should be picked up (V3 tests small items there).",
                 "At *contact* spots, don't pick up: the zone still gives the vanilla item in these visual tests.", "",
                 "| Scenario | Room | Location → test item (rule) | Notes |", "|---|---|---|---|"]
    n = 0
    for g_index, ((f, r), room_spots) in enumerate(groups):
        vanilla = {s["vanilla_item"] for s in room_spots}
        if (f, r) in LAMP_DARK_ROOMS:
            vanilla.add(13)                       # the lamp is in the player's hand there
        for vlabel, pool in CLASSES:
            used = set()
            lines, desc = [], []
            for s in room_spots:
                # each room group starts at a different place in the class list, so the batch
                # shows many different items rather than the same three everywhere
                rot = pool[g_index % len(pool):] + pool[:g_index % len(pool)]
                if pool is SMALL and s["kind"] in ("lean", "hang") and s["vanilla_item"] in P.KEY_MODELS:
                    rot = [37] + rot                  # V3 checks a different key model in the key pose
                item = next(i for i in rot if i not in vanilla and i not in used)
                used.add(item)
                p = P.pose(item, s, objs)
                flags = 128 if s["mechanism"] == "touch" else 0
                lines += [f"obj {item} stage {f}", f"obj {item} room {r}", f"obj {item} x {p['x']}",
                          f"obj {item} y {p['y']}", f"obj {item} z {p['z']}", f"obj {item} alpha {p['alpha']}",
                          f"obj {item} beta {p['beta']}", f"obj {item} gamma {p['gamma']}", f"obj {item} flags {flags}"]
                nm = objs[item]["known_name"] or f"OBJ {item}"
                desc.append((s, item, nm, p))
            pt = player_point(f, r, room_spots, objs, zs, used | vanilla)
            if pt is None:
                print(f"room {f}/{r}: no safe player point found")
                continue
            n += 1
            name = f"vis_{n:02d}_{room_name(f, r).replace(' ', '_').replace(chr(39), '')}_{vlabel.split()[0]}"
            head = [f"# Visible items, visual test {n:02d}: {room_name(f, r)} ({f}/{r}), {vlabel}.",
                    "# Vanilla data (no patch set). Each location's vanilla item is moved away; the test items:"]
            for s, item, nm, p in desc:
                head.append(f"#   {s['id']} ({s['kind']}, {s['mechanism']}, vanilla {objs[s['vanilla_item']]['known_name']}): "
                            f"OBJ {item} {nm} at ({p['x']}, {p['y']}, {p['z']}), angles {p['alpha']}/{p['beta']}/{p['gamma']}: {p['rule']}")
            head.append(f"# Player at ({pt[0]}, 0, {pt[1]}): automatic safe point (build_visual_tests.py docstring).")
            body = [f"name Visible items {n:02d}: {room_name(f, r)}, {vlabel}"]
            for s in room_spots:
                body.append(f"remove {s['vanilla_item']}")
            body += lines
            if (f, r) in LAMP_DARK_ROOMS:
                head.append("# Dark room: you get the lit lamp in hand (13, var 7 = 1).")
                body += ["give 13", "in_hand 13", "var 7 1"]
            if f >= 5:
                head.append("# Caverns: player flags 321 and the Jump action (LIFE 550 on a normal arrival).")
                body += ["obj 1 flags 321", "obj 2 found_flag 496"]
            body.append(f"player {f} {r} {pt[0]} 0 {pt[1]}")
            (OUT / f"{name}.scn").write_text("\n".join(head + body) + "\n", encoding="utf-8")
            cell = "<br>".join(f"{s['id']} {s['kind']}{' *touch*' if s['mechanism'] == 'touch' else ''} → {nm} ({p['rule']})"
                               for s, item, nm, p in desc)
            checklist.append(f"| `{name}.scn` | {room_name(f, r)} | {cell} | |")
    # Lean batch (user, 2026-10-16): every long, thin pool item at each lean/hang spot (bow,
    # Ballroom mantel key, Pantry nail), one per scenario; numbered after the main batch.
    LONG_ITEMS = [3, 25, 26, 38, 78, 81, 111, 120, 144, 172]   # one per model shape (27/28 = 26, 173 = 172)
    checklist += ["", "## Lean batch: long items standing like the bow / the keys", "",
                  "| Scenario | Room | Location → test item (rule) | Notes |", "|---|---|---|---|"]
    for s in [x for x in spots if x["kind"] in ("lean", "hang")]:
        f, r = s["floor"], s["room"]
        for item in LONG_ITEMS:
            if item == s["vanilla_item"]:
                continue
            p = P.pose(item, s, objs)
            pt = player_point(f, r, [s], objs, zs, {item, s["vanilla_item"]})
            n += 1
            nm = objs[item]["known_name"] or f"OBJ {item}"
            name = f"vis_{n:02d}_{room_name(f, r).replace(' ', '_')}_lean_{nm.split()[-1]}"
            flags = 128 if s["mechanism"] == "touch" else 0
            head = [f"# Visible items, lean batch {n:02d}: {room_name(f, r)} ({f}/{r}), {s['id']} ({s['kind']}, {s['mechanism']}).",
                    f"#   OBJ {item} {nm} at ({p['x']}, {p['y']}, {p['z']}), angles {p['alpha']}/{p['beta']}/{p['gamma']}: {p['rule']}",
                    "# Check: standing/hanging like the vanilla bow or key; upside down? (note which end is up)",
                    f"# Player at ({pt[0]}, 0, {pt[1]}): automatic safe point."]
            body = [f"name Visible items {n:02d}: {nm} at the {room_name(f, r)} {s['kind']} spot",
                    f"remove {s['vanilla_item']}"]
            body += [f"obj {item} stage {f}", f"obj {item} room {r}", f"obj {item} x {p['x']}", f"obj {item} y {p['y']}",
                     f"obj {item} z {p['z']}", f"obj {item} alpha {p['alpha']}", f"obj {item} beta {p['beta']}",
                     f"obj {item} gamma {p['gamma']}", f"obj {item} flags {flags}", f"player {f} {r} {pt[0]} 0 {pt[1]}"]
            (OUT / f"{name}.scn").write_text("\n".join(head + body) + "\n", encoding="utf-8")
            checklist.append(f"| `{name}.scn` | {room_name(f, r)} | {s['id']} {s['kind']}{' *touch*' if flags else ''} → {nm} ({p['rule']}) | |")
    (OUT / "CHECKLIST.md").write_text("\n".join(checklist) + "\n", encoding="utf-8")
    print(f"{n} scenarios in {OUT}")


if __name__ == "__main__":
    main()
