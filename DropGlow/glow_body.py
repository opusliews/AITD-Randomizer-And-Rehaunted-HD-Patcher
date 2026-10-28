"""The drop glow: a translucent light beam model for items dropped by monsters (user idea
2026-10-14, Research/Handoff_Step4_2026-10-13.md "drop glow"; started 2026-10-17).

Model (plain AITD1 BODY, format as scale_body.py / ReHaunted hqr.cpp createBodyFromPtr):
a closed tube, SIDES-sided, tapering from radius BOTTOM at the floor to TOP at HEIGHT, capped
at both ends, every face pointing outwards. Every polygon uses material 2 ("trans"): the
engines draw it see-through (ReHaunted rendererBGFX: a 50 % blend of the palette colour; the
lamp's lit glass and halo, body 10, use the same material in the original game).

A closed convex shape covers each screen pixel with exactly one front face; ReHaunted culls the
back faces of transparent polygons (BGFX_STATE_CULL_CCW), so the blend is applied once. The
first version (four crossed planes drawn from both sides) stacked up to eight 50 % layers in
the middle and looked thick in ReHaunted (user, 2026-10-18). Faces are wound as the vanilla
models' visible faces: (p1-p0) x (p2-p0) points into the model (bodies 8, 9, 47: 38/47, 101/147,
79/98 faces; the rest are concave parts).

The header box is the model's collision box when the object uses type_zv 1 (FITD/ReHaunted
GiveZVObjet copies it). It is put below the floor (y > 0 is down), so the glow never touches
the player or anything else and never takes one of an actor's three collision slots.
"""
from __future__ import annotations

import math
import struct

HEIGHT = 2800            # the player is about 2000 tall (y negative = up); 1400 at first, doubled (user 2026-10-18)
BOTTOM = 220             # radius at the floor
TOP = 60                 # radius at the top
SIDES = 8
# Crimson since 2026-10-28 (user: the grey beam barely showed in DOS, which recolours the background
# into the polygon's palette bank, so grey over a grey floor changes nothing). 0x50 = cb3353, the
# start of bank 5 (crimson ramp cb3353..27000f). It must be a bank start: DOS adds the background
# pixel's shade (0..15) to it, so the first try, 0x51, overflowed into bank 6 on the darkest pixels
# and showed light blue dots (user, References/Halo2.png). The Talisman (body 124) uses 0x50 too,
# so the ReHaunted edition tells the glow by its model number. Was 0xB0 grey (2026-10-18), 0x70 gold.
COLOR = 0x50
MATERIAL_TRANS = 2
# Optional solid outline: line primitives (type 0, material 0, as in 178 vanilla bodies) along the
# 8 vertical edges and both rings. Tried in 0x50 on 2026-10-28 and removed the same day (user: "the
# outline is too much"); glow_body(line_color=0x50) still builds it.
LINE_COLOR = None
MATERIAL_FLAT = 0
# Collision and draw-order box (x1 x2 y1 y2 z1 z2). DOS sorts actors by height band first, the band
# of the box's middle y (FITD actorList.cpp sortCompareFunction: ((mid - 2000) / 2000) * 2000); the
# old box below the floor (y 4000..4001) put the glow in its own band, drawn before everything, so
# doors and the player always covered it (user 2026-10-28). This box's middle (-1985) is in the
# players' band (-2000), so the glow is sorted by distance like any object. It is a point above the
# players' heads (Edward's box tops out at -1777, Emily's at -1761), so it never touches them.
BOX = (-1, 1, -1990, -1980, -1, 1)
# Spinning (user 2026-10-28: "rotate it as is, no stripes"): the body has one bone (INFO_ANIM) and
# the glow plays spin_anim() on repeat (DropGlow/glow.py). Four keyframes a quarter turn apart; the
# engine interpolates group angles the short way round (FITD anim.cpp PatchInterAngle: a step of
# 0x100 goes forward, and the loop from 0x300 back to keyframe 0 is +0x100 too), so the beam turns
# evenly. Angle units: 0x400 = a full turn; time in timer ticks (60 per second in DOS).
INFO_TRI, INFO_ANIM = 1, 2
SCRATCH = 10             # animation scratch bytes, as in all 107 animated vanilla bodies
SPIN_TICKS = 60          # per quarter turn: one turn in 4 s


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _wound(face: list[int], verts, centre) -> list[int]:
    """The face's vertex order with (p1-p0) x (p2-p0) pointing into the model (vanilla winding)."""
    p = [verts[i] for i in face]
    n = _cross(_sub(p[1], p[0]), _sub(p[2], p[0]))
    mid = tuple(sum(c) / len(p) for c in zip(*p))
    out = _sub(mid, centre)
    return face if sum(x * y for x, y in zip(n, out)) < 0 else face[::-1]


def glow_body(height: int = HEIGHT, bottom: int = BOTTOM, top: int = TOP, color: int = COLOR,
              line_color: int | None = LINE_COLOR) -> bytes:
    ring = lambda r, y: [(round(r * math.cos(2 * math.pi * k / SIDES)), y,
                          round(r * math.sin(2 * math.pi * k / SIDES))) for k in range(SIDES)]
    verts = ring(bottom, 0) + ring(top, -height)              # 0..SIDES-1 floor, SIDES.. top
    centre = (0, -height / 2, 0)
    faces = [[k, (k + 1) % SIDES, SIDES + (k + 1) % SIDES, SIDES + k] for k in range(SIDES)]
    faces += [list(range(SIDES)), list(range(SIDES, 2 * SIDES))]   # floor and top caps
    polys = [[i + 1 for i in _wound(f, verts, centre)] for f in faces]
    verts = [(0, 0, 0)] + verts                           # vertex 0: the pivot on the beam's axis
    out = bytearray(struct.pack("<H", INFO_TRI | INFO_ANIM))   # as the 107 animated vanilla bodies
    out += struct.pack("<6h", *BOX)
    # The animation scratch area: every animated vanilla body has 10 zero bytes here (static ones
    # none); the engine keeps the animation's state in it (FITD anim.cpp: the keyframe start time at
    # +4). The first spinning build had none, and the game froze (user, DOS, 2026-10-28).
    out += struct.pack("<H", SCRATCH) + bytes(SCRATCH)
    out += struct.pack("<H", len(verts)) + b"".join(struct.pack("<3h", *v) for v in verts)
    # Two groups (records: start*6, count, pivot vertex*6, parent, number, type 0 = rotation,
    # angles). The engine turns the root group by the object's own angles, not the animation's
    # (FITD AnimNuage; AnimExport/aitd_model.pose), so the root holds only the pivot and the beam
    # is its child, group 1, which spin_anim() turns around y.
    out += struct.pack("<H", 2) + struct.pack("<2H", 0, 0x10)   # 2 groups; order 0, 1 (offset / 0x10)
    out += struct.pack("<3h", 0, 1, 0) + struct.pack("<2b", -1, 0) + struct.pack("<h3h", 0, 0, 0, 0)
    out += struct.pack("<3h", 6, len(verts) - 1, 0) + struct.pack("<2b", 0, 1) + struct.pack("<h3h", 0, 0, 0, 0)
    lines = [] if line_color is None else (
        [(k, SIDES + k) for k in range(SIDES)]                                 # vertical edges
        + [(k, (k + 1) % SIDES) for k in range(SIDES)]                         # floor ring
        + [(SIDES + k, SIDES + (k + 1) % SIDES) for k in range(SIDES)])        # top ring
    out += struct.pack("<H", len(polys) + len(lines))
    for p in polys:                                       # poly: type 1, n, material, colour, offsets
        out += bytes([1, len(p), MATERIAL_TRANS, color]) + b"".join(struct.pack("<H", 6 * i) for i in p)
    for a, b in lines:                                    # line: type 0, material, colour, pad, 2 offsets
        out += bytes([0, MATERIAL_FLAT, line_color, 0]) + struct.pack("<2H", 6 * (a + 1), 6 * (b + 1))
    return bytes(out)


def spin_anim(ticks: int = SPIN_TICKS) -> bytes:
    """The glow's animation (2 groups: the root stays, group 1 = the beam): a full turn around y
    in four quarter-turn keyframes. Format as AnimExport/aitd_model.write_anim: frames, groups;
    per frame time + step, then per group type (0 = rotation) and angles (x, y, z)."""
    out = bytearray(struct.pack("<HH", 4, 2))
    for k in range(4):
        out += struct.pack("<H3h", ticks, 0, 0, 0) + struct.pack("<4h", 0, 0, 0, 0)
        out += struct.pack("<4h", 0, 0, 0x100 * k, 0)
    return bytes(out)


if __name__ == "__main__":
    import hashlib
    d, a = glow_body(), spin_anim()
    print(len(d), "bytes", hashlib.sha256(d).hexdigest())
    print("spin anim", len(a), "bytes", hashlib.sha256(a).hexdigest())
