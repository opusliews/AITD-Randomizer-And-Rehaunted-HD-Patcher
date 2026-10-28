"""Bug Spray assets (user design 2026-10-28, Research/BugSpray.md; References/spray_can.png).

- can_body(): the world/inventory model, a plain AITD1 body standing on the floor: a stacked
  cylinder in yellow/green bands (Y G Y G Y), a narrower green cap and a black nozzle sticking
  out sideways.
- held_body(player): a player body (Edward LISTBODY 12 or Emily LISTBOD2 12) with the same can
  in the right hand: its vertices go into the hand.R group (13), so they follow the hand. The can
  is placed from the hand's own vertices (centre = the hand's mean vertex, nozzle along the
  hand), so one function serves both skeletons. Used only while spraying (body swap, as the
  vanilla drinking body 268).
- spray_anim(idle): the spraying animation built from the player's idle (anim 4) frame 0: right
  arm raised forward to about 45 degrees below horizontal, elbow slightly bent, head and chest
  tilted down, then small spraying motions of the hand and forearm, then back to the idle pose.
  17 groups (the held body has no prop bones). 25 ticks per second.

Palette (ITD_RESS entry 3): no saturated yellow exists; 0x0E (255,255,135) is the only clear
yellow, 0xD6 (75,95,35) the most saturated green, 0x6F near-black. Material 0 = flat.
Angles: 1024 = 360 degrees; negative x swings an arm forward (drinking anim 277: upper arm
-202, forearm -190); positive x tilts the head down (idle anim 4 frame 1: head +60).
"""
from __future__ import annotations
import copy, math, struct, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "AnimExport")]
import aitd_model as M
import body_io as B

YELLOW, GREEN, BLACK = 0x0E, 0xD6, 0x6F
SIDES = 8
RADIUS, HEIGHT = 42, 200               # mm-like engine units; the player is about 1777 tall
BANDS = (YELLOW, GREEN, YELLOW, GREEN, YELLOW)
CAP_R, CAP_H = 22, 34
NOZZLE = (10, 46)                      # half-width, length
HAND_GROUP = 13                        # hand.R in the 17-group player skeleton
DEG = 1024 / 360


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def can_mesh(origin, axis, side):
    """Vertices and polygons (colour, vertex list) of the can: bottom centre at origin, top
    along axis, nozzle pointing along side. Faces wound like vanilla visible faces
    ((p1-p0) x (p2-p0) points into the model)."""
    axis, side = _norm(axis), _norm(side)
    u = side
    w = _norm(_cross(axis, u))
    pt = lambda t, r, ang: tuple(origin[i] + axis[i] * t + r * (math.cos(ang) * u[i] + math.sin(ang) * w[i])
                                 for i in range(3))
    verts, polys = [], []

    def ring(t, r):
        base = len(verts)
        verts.extend(pt(t, r, 2 * math.pi * k / SIDES) for k in range(SIDES))
        return base

    def tube(t0, t1, r, colour):
        a, b = ring(t0, r), ring(t1, r)
        for k in range(SIDES):
            polys.append((colour, [a + k, a + (k + 1) % SIDES, b + (k + 1) % SIDES, b + k]))
        return a, b

    band_h = HEIGHT / len(BANDS)
    first = None
    for i, c in enumerate(BANDS):
        a, b = tube(i * band_h, (i + 1) * band_h, RADIUS, c)
        first = a if first is None else first
    polys.append((YELLOW, [first + k for k in range(SIDES)]))            # bottom
    top = ring(HEIGHT, RADIUS)
    polys.append((YELLOW, [top + k for k in range(SIDES)]))              # top
    ca, cb = tube(HEIGHT, HEIGHT + CAP_H, CAP_R, GREEN)
    polys.append((GREEN, [cb + k for k in range(SIDES)]))
    # nozzle: a box from the cap's side outwards along `side`
    h, ln = NOZZLE
    c0 = tuple(origin[i] + axis[i] * (HEIGHT + CAP_H * 0.6) for i in range(3))
    corners = []
    for s in (CAP_R * 0.5, CAP_R * 0.5 + ln):
        for da, dw in ((-h, -h), (h, -h), (h, h), (-h, h)):
            corners.append(tuple(c0[i] + u[i] * s + axis[i] * da + w[i] * dw for i in range(3)))
    nb = len(verts); verts.extend(corners)
    q = lambda *ix: [nb + i for i in ix]
    for f in (q(0, 1, 2, 3), q(4, 5, 6, 7), q(0, 1, 5, 4), q(1, 2, 6, 5), q(2, 3, 7, 6), q(3, 0, 4, 7)):
        polys.append((BLACK, f))
    centre = tuple(origin[i] + axis[i] * HEIGHT / 2 for i in range(3))
    out = []
    for colour, f in polys:                                   # vanilla winding
        p = [verts[i] for i in f]
        n = _cross(tuple(p[1][i] - p[0][i] for i in range(3)), tuple(p[2][i] - p[0][i] for i in range(3)))
        mid = tuple(sum(c[i] for c in p) / len(p) for i in range(3))
        inward = tuple(centre[i] - mid[i] for i in range(3))
        if sum(n[i] * inward[i] for i in range(3)) < 0:
            f = f[::-1]
        out.append((colour, f))
    return [tuple(round(c) for c in v) for v in verts], out


INVENTORY_SCALE = 10      # user (DOS test T14, 2026-10-28): 1:1 was tiny in the inventory; vanilla
                          # inventory models are 2400-4000 units, 6-25x their world models


def can_body(scale: int = 1) -> bytes:
    """Standing on the floor (y negative = up), nozzle towards -z. scale 1: the world model;
    INVENTORY_SCALE: the inventory / pickup-screen model (found_body)."""
    verts, polys = can_mesh((0, 0, 0), (0, -1, 0), (0, 0, -1))
    verts = [tuple(c * scale for c in v) for v in verts]
    ys = [v[1] for v in verts]
    zv = tuple(c * scale for c in (-RADIUS, RADIUS)) + (min(ys), 0) + tuple(
        c * scale for c in (-RADIUS - NOZZLE[1], RADIUS))
    out = bytearray(struct.pack("<H", 0)) + struct.pack("<6h", *zv) + struct.pack("<H", 0)
    out += struct.pack("<H", len(verts)) + b"".join(struct.pack("<3h", *v) for v in verts)
    out += struct.pack("<H", len(polys))
    for colour, f in polys:
        out += bytes([1, len(f), 0, colour]) + b"".join(struct.pack("<H", 6 * i) for i in f)
    return bytes(out)


def held_body(player: bytes) -> bytes:
    """The player body with the can in the right hand (hand.R group 13). Hand vertices are
    stored relative to the group's pivot (the wrist), so the can is built in that frame:
    centre at the hand's mean vertex, can axis across the hand pointing forward (-z, made
    perpendicular to the hand), nozzle along the hand (away from the wrist)."""
    b = M.parse_body(player)
    g = b.groups[HAND_GROUP]
    hand = b.verts[g.start:g.start + g.count]
    mid = tuple(sum(v[i] for v in hand) / len(hand) for i in range(3))
    along = _norm(mid)                                        # wrist -> hand
    fwd = (0.0, 0.0, -1.0)
    d = sum(fwd[i] * along[i] for i in range(3))
    axis = _norm(tuple(fwd[i] - d * along[i] for i in range(3)))
    origin = tuple(mid[i] - axis[i] * HEIGHT / 2 for i in range(3))   # the hand grips the middle
    verts, polys = can_mesh(origin, axis, along)
    at = B.insert_verts(b, HAND_GROUP, verts)
    for colour, f in polys:
        b.prims.append(M.Prim(1, 0, colour, [at + i for i in f]))
    return B.write_body(b)


# Per character (picked from rendered candidates, out/pose_candidates*.png, 2026-10-28): the arm
# raised to about 45 degrees to the floor, elbow slightly bent. Emily's idle already bends the
# forearm forward by about 66 degrees (LISTANI2 anim 4: 836), so her forearm angle undoes most of it.
POSE = {"LISTANIM.PAK": dict(arm=-45.0, fore=-20.0), "LISTANI2.PAK": dict(arm=-45.0, fore=46.0)}


SLOWDOWN = 2              # user (DOS test T14, 2026-10-28): the arm motion at half speed (6.4 s)


def spray_anim(idle: bytes, arm=-45.0, fore=-20.0, head=30.0, chest=8.0) -> bytes:
    """Spraying, from the idle animation's frame 0 (17 groups kept). Angles in degrees:
    arm = upper arm, fore = forearm (negative = forward), head/chest (positive = down)."""
    base = M.parse_anim(idle)
    rest = [(t, tuple(d)) for t, d in base.frames[0].groups[:17]]

    def frame(time, arm=0.0, fore=0.0, hand=(0.0, 0.0), head=0.0, chest=0.0):
        g = list(rest)
        def put(i, dx=0.0, dz=0.0):
            t, (x, y, z) = g[i]
            g[i] = (0, ((x + round(dx * DEG)) & 0x3FF, y, (z + round(dz * DEG)) & 0x3FF))
        put(11, arm); put(12, fore); put(13, hand[0], hand[1]); put(7, head); put(6, chest)
        return M.Frame(time * SLOWDOWN, (0, 0, 0), g)

    frames = [frame(12, arm, fore, (0, 0), head, chest),       # raise (0.5 s at SLOWDOWN 1)
              frame(6, arm, fore, (0, 0), head, chest)]        # settle
    for k in range(6):                                         # spraying motions (about 2 s at 1)
        s = 1 if k % 2 == 0 else -1
        frames.append(frame(8, arm + 2 * s, fore + 3 * s, (6 * s, 4 * s), head, chest))
    frames.append(frame(14, 0, 0, (0, 0), 0, 0))               # back to rest
    return M.write_anim(M.Anim(frames, 17))


if __name__ == "__main__":
    import hashlib
    sys.path[:0] = [str(HERE.parent / "Patcher")]
    import gamedata
    print("can body", len(can_body()), "bytes", hashlib.sha256(can_body()).hexdigest()[:12])
    for pak, apak in (("LISTBODY.PAK", "LISTANIM.PAK"), ("LISTBOD2.PAK", "LISTANI2.PAK")):
        hb = held_body(gamedata.pak_entries(pak)[12])
        an = spray_anim(gamedata.pak_entries(apak)[4], **POSE[apak])
        print(pak, "held body", len(hb), "bytes;", apak, "spray anim", len(an), "bytes",
              len(M.parse_anim(an).frames), "frames", sum(f.time for f in M.parse_anim(an).frames), "ticks")
