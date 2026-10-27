"""Visible items: world locations and how any item is posed at any of them (2026-10-16).

Research/VisibleItems_Proposal.md. Evidence (check_origin.py): 66 of the 68 pool models have
their lowest point at the origin (BODY y2 = 0; y grows downward); the arrows (+30), dagger 78
(+20) and the first-aid cases (+10) reach below it. Vanilla world items stand with y = the
top of the hard-collision block under them, except deliberate poses (leaning/hanging keys,
the leaning bow) and supports without collision (talisman, hook, soup).

Rules:
  * height: origin y = spot surface - BODY y2 (the model's bottom on the surface);
  * pose: the "dropped" pose (alpha = gamma = 0; the game drops every item that way), turned
    to the spot's beta;
  * leaning / hanging spots (bow, Ballroom mantel key, Pantry nail key): long, thin items (and
    keys at the key spots) stand up like the spot's own item: same angles when their long axis
    matches, else a quarter turn about Y first; leaning ones share the spot item's bottom,
    hanging ones its top (user, 2026-10-16). Any other item sits on the surface below (mantel,
    cabinet top, floor under the bow) in the dropped pose;
  * clipping: on a surface with a known supporting block, the item is moved so its footprint
    stays on the block (centred when it is bigger than the block).
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "Generated" / "Patcher" / "catalog"
sys.path.insert(0, str(ROOT / "Generated" / "Patcher"))
import gamedata                   # noqa: E402  the original game files (project copy, or the player's)

KEY_MODELS = {37, 53, 108, 141, 144, 163}     # vanilla keys (new door keys clone 37/53/108/141/163)
POKER_LOCATION = (2, 10, -1637, 0, -549)       # user, 2026-10-16 (noclip): floor left of the fireplace
LEAN_SPOTS = {25, 144, 86}                      # spots named by their vanilla item; 86 = Bedroom 1
                                                # mantel (user, 2026-10-17: flat there it can barely be seen)
# items that lean/hang like long ones although their model isn't long and thin, with the axis that
# stands up. The Old Indian Cover (OBJ 5): its vanilla world model (body 18) is a small folded heap
# that looks mangled and dark stood up (vis_109) and bad lying down (user, 2026-10-17), so it gets
# a new model (below) and leans with it.
LEANABLE: dict[int, str] = {5: "z"}
# open, one-sided models (a sheet seen from above): stood up, their top must face the room, which
# is the opposite roll of the closed long items (user test 2026-10-17, Rug8.png: the rug stood with
# its back to the camera and only slivers were drawn)
FLIP_ROLL = {5}
# The cover's world model is replaced (user, 2026-10-17: "it's a bad model"): its inventory model
# (body 19, a detailed rug) scaled to 0.7 becomes a new model COVER_BODY appended to LISTBODY.PAK
# (scale_body.py; mechanics.listbody). With it the cover is leanable again.
# Round 6 (user test 2026-10-17): 0.7 looked too big and dark/see-through (no HD texture map: see
# scale_body solid). Solid at 0.5 looked fine on a table and the floor (References/visibility/
# Rug6.png, Rug7.png), "a third of that" -> 1/6 of the inventory model (about 430 x 600).
COVER, COVER_BODY, COVER_SOURCE_BODY = 5, 272, 19
# then "increase the size by half" (user, 2026-10-17) -> 1/4; the model is also made plain (not
# jointed) so ReHaunted draws no constant shadow (scale_body._strip_single_group)
CUSTOM_BODIES = {272: (19, 1 / 4),                         # new model -> (vanilla source, scale)
                 273: (162, "cross"),                     # the cross arrow (scale_body.cross_body)
                 274: (None, "glow")}                     # the drop glow beam (DropGlow/glow_body.py)
# Arrows placed at a world location show the cross arrow (two fins at 90 degrees, readable from any
# side); picked up, their found-life switches back to the plain arrow, so drops and throws look
# vanilla (user idea, 2026-10-17; mechanics.py).
ARROW_BODY, CROSS_ARROW_BODY = 162, 273


def custom_body(body: int) -> bytes | None:
    """Raw data of a model the randomizer adds (not in the extracted vanilla LISTBODY)."""
    if body in CUSTOM_BODIES:
        import scale_body
        src, factor = CUSTOM_BODIES[body]
        if factor == "glow":
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DropGlow"))
            import glow_body
            return glow_body.glow_body()
        raw = gamedata.body(src)
        if factor == "cross":
            return scale_body.cross_body(raw)
        return scale_body.scale_body(raw, factor, solid=True)
    return None
HANG_SPOTS = {163}


# The object fields used here, read from OBJETS.ITD under the names of References/AITD_objects.csv
# (identical for all 292 objects, checked 2026-10-17; the CSV leaves -1 blank).
OBJECT_FIELDS = {"body_id": "body", "initial_floor": "stage", "initial_room": "room", "x": "x", "y": "y",
                 "z": "z", "initial_alpha": "alpha", "initial_beta": "beta", "initial_gamma": "gamma"}


def objects() -> dict[int, dict]:
    import aitd_objets as O
    return {i: {"obj_id": i, **{k: o[v] for k, v in OBJECT_FIELDS.items()}}
            for i, o in enumerate(O.load(gamedata.source_dir() / "OBJETS.ITD"))}


def zones() -> list[dict]:
    """Hard-collision boxes from the ETAGE files, as the rows of References/AITD_zones.csv (all
    1169 CSV rows identical, checked 2026-10-17; the files also have room F3:R14, absent there)."""
    return gamedata.hard_collisions()


def body_box(body: int) -> tuple[int, int, int, int, int, int]:
    data = custom_body(body) or gamedata.body(body)
    return struct.unpack_from("<6h", data, 2)


def box(z):
    return tuple(int(z[k]) for k in ("x1", "x2", "y1", "y2", "z1", "z2"))


def support_block(zs, floor, room, x, y, z):
    """(top y, zone, box) of the highest hard-collision block under (x, z) at or below y."""
    best = None
    for zn in zs:
        if zn["zone_kind"] != "hard_collision" or zn["floor_id"] != str(floor) or zn["room_id"] != str(room):
            continue
        b = box(zn)
        if b[0] <= x <= b[1] and b[4] <= z <= b[5] and b[2] >= y - 50:
            if best is None or b[2] < best[0]:
                best = (b[2], zn["zone_id"], b)
    return best


def world_spots() -> list[dict]:
    """Every world location (one item each): contact items (the zone gives them) and touch
    pickups. Named by the vanilla item; the poker (no vanilla model) gets the user's spot."""
    objs, zs = objects(), zones()
    spots = []
    contact = [s for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]
               if s["mechanism"] == "contact"]
    touch = [s for s in json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["slots"]
             if s["family"] == "direct_pickup"]
    seen = set()
    for kind, slot_id, item in [("contact", s["slot_id"], i["obj"]) for s in contact for i in s["items"]] + \
                               [("touch", s["slot_id"], s["items"][0]) for s in touch]:
        if item in seen:                  # the hook: contact zone and touch pickup at one spot
            continue
        seen.add(item)
        r = objs[item]
        if item == 120:
            f, rm, x, y, z = POKER_LOCATION
            a, b, g = 0, 0, 0
        else:
            f, rm, x, y, z = (int(r[k]) for k in ("initial_floor", "initial_room", "x", "y", "z"))
            a, b, g = (int(r[k]) for k in ("initial_alpha", "initial_beta", "initial_gamma"))
        spot = {"id": f"W:{item}", "vanilla_item": item, "slot_id": slot_id, "mechanism": kind,
                "floor": f, "room": rm, "x": x, "y": y, "z": z, "alpha": a, "beta": b, "gamma": g,
                "kind": "lean" if item in LEAN_SPOTS else "hang" if item in HANG_SPOTS else
                        "ground" if y == 0 else "surface"}
        sup = support_block(zs, f, rm, x, y, z)
        spot["support_y"] = sup[0] if sup else 0              # under a lean/hang pose, or the floor
        spot["support_zone"] = sup[1] if sup else None
        # the block's area is used against clipping only when the item really stands on it
        spot["clamp_box"] = list(sup[2]) if sup and abs(sup[0] - y) <= 10 and spot["kind"] in ("surface", "lean") else None
        spots.append(spot)
    return spots


def rot_order(body: int) -> str:
    """The engine's rotation order for a model (ReHaunted renderer.cpp): plain models go through
    RotateNuage, Y (beta) then Z (gamma) then X (alpha); jointed (INFO_ANIM) models put the angles
    into group 0 and rotate it with RotateList, Y then X then Z. With alpha = 0 both agree."""
    data = custom_body(body) or gamedata.body(body)
    return "YXZ" if struct.unpack_from("<H", data, 0)[0] & 2 else "YZX"


def _rot(pt, alpha, beta, gamma, order="YZX"):
    """The engine's rotation of a model point (cosTable is a sine table)."""
    x, y, z = pt
    sin = lambda a: math.sin(2 * math.pi * (a % 1024) / 1024)
    cos = lambda a: math.cos(2 * math.pi * (a % 1024) / 1024)
    for axis in order:
        if axis == "Y" and beta % 1024:
            x, z = x * cos(beta) - z * sin(beta), x * sin(beta) + z * cos(beta)
        elif axis == "X" and alpha % 1024:
            y, z = y * cos(alpha) - z * sin(alpha), y * sin(alpha) + z * cos(alpha)
        elif axis == "Z" and gamma % 1024:
            x, y = x * cos(gamma) - y * sin(gamma), x * sin(gamma) + y * cos(gamma)
    return x, y, z


def turn_vertical(alpha: int, beta: int, gamma: int, quarter: int, order: str = "YZX") -> tuple[int, int, int]:
    """Angles (in quarter turns of 256) for the pose (alpha, beta, gamma) followed by `quarter`
    quarter turns about the WORLD vertical axis. The engine turns about Y before it rolls, so
    changing beta alone turns a stood-up item about a horizontal axis (user test 2026-10-17,
    vis_154); this searches the 64 quarter-turn combinations for the one with the same effect."""
    import math
    def apply(pt, a, b, g):
        return _rot(pt, a, b, g, order)
    def turn_y(pt):
        x, y, z = pt
        for _ in range(quarter % 4):
            x, z = -z, x                      # about the vertical axis (sign: one direction)
        return x, y, z
    basis = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    want = [turn_y(apply(v, alpha, beta, gamma)) for v in basis]
    for a in range(0, 1024, 256):
        for b in range(0, 1024, 256):
            for g in range(0, 1024, 256):
                got = [apply(v, a, b, g) for v in basis]
                if all(math.dist(u, w) < 1e-6 for u, w in zip(got, want)):
                    return a, b, g
    raise ValueError("no quarter-turn combination found")


def turn_about(alpha: int, beta: int, gamma: int, axis: tuple, quarter: int, order: str = "YZX") -> tuple[int, int, int]:
    """Angles (quarter turns) for the pose followed by `quarter` quarter turns about a WORLD axis
    (a unit vector along x, y or z), e.g. the axis a stood-up sheet faces, to turn it within its
    own plane (portrait -> landscape; user test 2026-10-17)."""
    import math
    ax = [round(c) for c in axis]
    if sorted(map(abs, ax)) != [0, 0, 1]:
        raise ValueError(f"axis {axis} is not a world axis")
    def turn(pt):
        x, y, z = pt
        for _ in range(quarter % 4):
            if ax[0]:
                y, z = -z * ax[0], y * ax[0]
            elif ax[1]:
                x, z = -z * ax[1], x * ax[1]
            else:
                x, y = -y * ax[2], x * ax[2]
        return x, y, z
    basis = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    want = [turn(_rot(v, alpha, beta, gamma, order)) for v in basis]
    for a in range(0, 1024, 256):
        for b in range(0, 1024, 256):
            for g in range(0, 1024, 256):
                got = [_rot(v, a, b, g, order) for v in basis]
                if all(math.dist(u, w) < 1e-6 for u, w in zip(got, want)):
                    return a, b, g
    raise ValueError("no quarter-turn combination found")


def rotated_y(body: int, alpha: int, beta: int, gamma: int) -> tuple[float, float]:
    """(top, bottom) of the model after rotation (y grows downward)."""
    x1, x2, y1, y2, z1, z2 = body_box(body)
    order = rot_order(body)
    ys = [_rot((x, y, z), alpha, beta, gamma, order)[1] for x in (x1, x2) for y in (y1, y2) for z in (z1, z2)]
    return min(ys), max(ys)


def long_axis(body: int, strict: bool = True) -> str | None:
    """'x' or 'z' for a long, thin model (longest side >= 300 and >= 3x the other two; user,
    2026-10-16: rifle, sword, saber, arrows, poker, bow, daggers, knives). strict=False: just
    the longer horizontal axis (the keys of the key spots)."""
    x1, x2, y1, y2, z1, z2 = body_box(body)
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    axis, length = ("x", dx) if dx >= dz else ("z", dz)
    if not strict:
        return axis
    others = [dy, dz if axis == "x" else dx]
    return axis if length >= 300 and all(3 * o <= length for o in others) else None


# Poses approved one by one in game (user, 2026-10-17): (item, location) -> alpha, beta, gamma, y.
# They win over the rules (a one-sided sheet's facing can't be read from the data).
FIXED_POSES = {
    (5, "W:25"): (256, 512, 512, -475),     # rug at the bow spot: test 174
    (5, "W:86"): (0, 256, 768, -1625),      # rug on the Bedroom 1 mantel: test 157
    (5, "W:144"): (0, 256, 768, -1525),     # rug on the Ballroom mantel: test 178
    (5, "W:13"): (0, 256, 0, -925),         # rug on the Attic table, turned 90 degrees: test 179
}


def key_bodies(objs: dict) -> set[int]:
    """Models of the vanilla keys (the More Locked Doors keys are clones of them)."""
    return {int(objs[k]["body_id"]) for k in KEY_MODELS}


def pose(item: int, spot: dict, objs: dict | None = None, body: int | None = None) -> dict:
    """Position and angles of `item` at `spot` (the rules in the module docstring). `body`: the
    item's model when it is not in the object catalog (new door keys); else read from it."""
    objs = objs or objects()
    if (item, spot["id"]) in FIXED_POSES:
        a, b, g, y = FIXED_POSES[(item, spot["id"])]
        return {"x": spot["x"], "y": y, "z": spot["z"], "alpha": a, "beta": b, "gamma": g,
                "rule": "fixed pose approved in game"}
    if body is None:
        body = COVER_BODY if item == COVER else int(objs[item]["body_id"])
    x1, x2, y1, y2, z1, z2 = body_box(body)
    x, z = spot["x"], spot["z"]
    beta = spot["beta"]
    if spot["kind"] in ("lean", "hang"):
        if item == spot["vanilla_item"]:
            return {"x": x, "y": spot["y"], "z": z, "alpha": spot["alpha"], "beta": beta, "gamma": spot["gamma"],
                    "rule": "the spot's own vanilla pose"}
        # Long, thin items (and keys at the key spots) take the spot item's orientation (user,
        # 2026-10-16): the same angles when their long axis matches the spot item's, else a
        # quarter turn more about Y first (the engine turns about Y before rolling). Height:
        # leaning items share the spot item's bottom, hanging items its top (the nail).
        spot_body = int(objs[spot["vanilla_item"]]["body_id"])
        mine = LEANABLE.get(item) or long_axis(body) or (
            long_axis(body, strict=False) if body in key_bodies(objs) and spot["vanilla_item"] in KEY_MODELS else None)
        if mine:
            theirs = long_axis(spot_body, strict=False)
            s_top, s_bottom = rotated_y(spot_body, spot["alpha"], beta, spot["gamma"])
            x1s, x2s, y1s, y2s, z1s, z2s = body_box(spot_body)
            if spot["kind"] == "lean" and (s_bottom - s_top) < max(x2s - x1s, z2s - z1s):
                # the spot's own item is not upright (the Ballroom mantel key lies on its edge,
                # long side horizontal): long items stand upright on the surface below, like the
                # bow (user test 2026-10-17: vis_34-36 "not leaning")
                # roll 256, not the bow's 768: this spot faces the other way (beta 512), and 768
                # stood every item on its wrong end (user test 2026-10-17: vis_89-98 upside down)
                b = (beta + (256 if mine == "z" else 0)) % 1024
                # the roll that stands items right way up depends on the spot's facing: beta 0 (bow
                # spot, Bedroom 1 mantel) 768, beta 512 (Ballroom) 256 (user tests 05, 99-108)
                g = (768 - beta) % 1024
                if item in FLIP_ROLL:
                    g = (g + 512) % 1024
                top, bottom = rotated_y(body, 0, b, g)
                return {"x": x, "y": round(spot["support_y"] - bottom), "z": z, "alpha": 0, "beta": b,
                        "gamma": g, "rule": "stood upright on the surface below, like the bow"
                        + (" (rolled to face the room)" if item in FLIP_ROLL else "")}
            b = (beta + (256 if mine != theirs else 0)) % 1024
            a, g = spot["alpha"], spot["gamma"]
            if item in FLIP_ROLL:
                g = (g + 512) % 1024                 # the opposite roll: top faces the room
            top, bottom = rotated_y(body, a, b, g)
            if spot["kind"] == "hang":
                yy = round(spot["y"] + s_top - top)
                rule = "stood up like the spot's item, hanging from the same top (nail)"
            else:
                yy = round(spot["y"] + s_bottom - bottom)
                rule = "stood up like the spot's item, on the same bottom"
            return {"x": x, "y": yy, "z": z, "alpha": a, "beta": b, "gamma": g, "rule": rule}
    surface = spot["y"] if spot["kind"] in ("surface", "ground") else spot["support_y"]
    rule = "dropped pose on the surface" if spot["kind"] in ("surface", "ground") else            "dropped pose on the surface below the lean/hang spot"
    if spot["clamp_box"]:
        bx1, bx2, _, _, bz1, bz2 = spot["clamp_box"]
        hx, hz = max(abs(x1), abs(x2)), max(abs(z1), abs(z2))
        if (beta // 256) % 2:                                 # quarter turn: footprint axes swap
            hx, hz = hz, hx
        x = _fit(x, bx1, bx2, hx)
        z = _fit(z, bz1, bz2, hz)
        if (x, z) != (spot["x"], spot["z"]):
            rule += f", moved onto the block ({spot['support_zone']})"
    return {"x": x, "y": surface - y2, "z": z, "alpha": 0, "beta": beta, "gamma": 0, "rule": rule}


def _fit(v, lo, hi, half):
    if hi - lo <= 2 * half:
        return (lo + hi) // 2
    return min(max(v, lo + half), hi - half)


if __name__ == "__main__":
    for s in world_spots():
        print(s["id"], s["kind"], s["mechanism"], s["floor"], s["room"], s["x"], s["y"], s["z"],
              "support", s["support_y"], s["support_zone"], "clamp", s["clamp_box"])
