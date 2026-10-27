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
COLOR = 0xB0             # palette bank 11 (grey ramp), lightest shade c3c3b3 (white, user 2026-10-18; was 0x70 gold)
MATERIAL_TRANS = 2
BOX = (-1, 1, 4000, 4001, -1, 1)     # x1 x2 y1 y2 z1 z2: unreachable, below the floor


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


def glow_body(height: int = HEIGHT, bottom: int = BOTTOM, top: int = TOP, color: int = COLOR) -> bytes:
    ring = lambda r, y: [(round(r * math.cos(2 * math.pi * k / SIDES)), y,
                          round(r * math.sin(2 * math.pi * k / SIDES))) for k in range(SIDES)]
    verts = ring(bottom, 0) + ring(top, -height)              # 0..SIDES-1 floor, SIDES.. top
    centre = (0, -height / 2, 0)
    faces = [[k, (k + 1) % SIDES, SIDES + (k + 1) % SIDES, SIDES + k] for k in range(SIDES)]
    faces += [list(range(SIDES)), list(range(SIDES, 2 * SIDES))]   # floor and top caps
    polys = [_wound(f, verts, centre) for f in faces]
    out = bytearray(struct.pack("<H", 0))                 # flags: plain model
    out += struct.pack("<6h", *BOX)
    out += struct.pack("<H", 0)                           # no scratch bytes
    out += struct.pack("<H", len(verts)) + b"".join(struct.pack("<3h", *v) for v in verts)
    out += struct.pack("<H", len(polys))
    for p in polys:                                       # poly: type 1, n, material, colour, offsets
        out += bytes([1, len(p), MATERIAL_TRANS, color]) + b"".join(struct.pack("<H", 6 * i) for i in p)
    return bytes(out)


if __name__ == "__main__":
    import hashlib
    d = glow_body()
    print(len(d), "bytes", hashlib.sha256(d).hexdigest())
