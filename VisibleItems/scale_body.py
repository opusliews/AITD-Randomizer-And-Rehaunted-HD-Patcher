"""Scale an AITD1 BODY model (LISTBODY.PAK entry) by a factor (2026-10-17).

User request: show the Old Indian Cover in the world with its inventory model (body 19, a
detailed rug) scaled to 0.7, as a new model entry (a new number: ReHaunted's HD textures are keyed
to model numbers and polygon indexes, so reusing body 18 would map the old heap's texture onto
the new polygons; a new number has no HD texture and uses its palette colours).

Format: ReHaunted FitdLib/hqr.cpp createBodyFromPtr. Scaled: the bounding box, every vertex,
animation-group offsets (INFO_ANIM) and sphere sizes. Everything else is copied byte for byte.
"""
from __future__ import annotations

import struct

INFO_ANIM, INFO_TORTUE, INFO_OPTIMISE = 2, 4, 8


def scale_body(data: bytes, factor: float, solid: bool = False, drop_lines: bool = True) -> bytes:
    """solid: polygons with material 1 (dither) or 2 (transparent) become material 0 (plain
    colour), and line primitives are dropped. ReHaunted draws a model without an HD texture map
    from its raw data, where materials 1/2 come out dark and see-through and lines show as edges
    (user test 2026-10-17, References/visibility/Rug3.png); the inventory looked right only
    because body 19 has an HD texture map."""
    out = bytearray(data)
    s = lambda v: max(-32768, min(32767, round(v * factor)))
    flags = struct.unpack_from("<H", data, 0)[0]
    if flags & (INFO_TORTUE | INFO_OPTIMISE):
        raise ValueError(f"unsupported body flags {flags:#x}")
    for k in range(6):                                   # bounding box
        off = 2 + 2 * k
        struct.pack_into("<h", out, off, s(struct.unpack_from("<h", data, off)[0]))
    p = 14
    scratch = struct.unpack_from("<H", data, p)[0]
    p += 2 + scratch
    nv = struct.unpack_from("<H", data, p)[0]
    p += 2
    for k in range(nv * 3):                              # vertices
        struct.pack_into("<h", out, p, s(struct.unpack_from("<h", data, p)[0]))
        p += 2
    if flags & INFO_ANIM:
        ng = struct.unpack_from("<H", data, p)[0]
        p += 2 + 2 * ng                                  # group order
        for _ in range(ng):                              # start, count, base, org/num, type, delta xyz
            p += 2 + 2 + 2 + 1 + 1 + 2
            for _ in range(3):
                struct.pack_into("<h", out, p, s(struct.unpack_from("<h", data, p)[0]))
                p += 2
    npr = struct.unpack_from("<H", data, p)[0]
    prim_count_at = p
    p += 2
    prims_start = p
    kept = []                                            # (start, end) of the primitives kept
    for _ in range(npr):
        start = p
        t = data[p]
        p += 1
        if t == 0:                                       # line: material, color, even, 2 points
            p += 3 + 4
        elif t in (1, 8):                                # poly: n, material, color, n points
            n = data[p]
            p += 3 + 2 * n
        elif t in (2, 6, 7):                             # point / big point / zixel
            p += 3 + 2
        elif t == 3:                                     # sphere: material, color, even, size, point
            p += 3
            struct.pack_into("<H", out, p, max(1, round(struct.unpack_from("<H", data, p)[0] * factor)))
            p += 2 + 2
        elif t in (9, 10):                               # textured poly: n, material, color, points, uv
            n = data[p]
            p += 3 + 2 * n + 2 * n
        else:
            raise ValueError(f"unsupported primitive type {t}")
        if solid and t in (1, 8) and out[start + 2] in (1, 2):
            out[start + 2] = 0                           # poly: type, n, material, color
        if not (solid and drop_lines and t == 0):
            kept.append((start, p))
    if solid:
        body = b"".join(bytes(out[a:b]) for a, b in kept)
        out = out[:prim_count_at] + struct.pack("<H", len(kept)) + body + out[p:]
        if flags & INFO_ANIM:
            out = bytearray(_strip_single_group(bytes(out)))
    return bytes(out)


def _strip_single_group(data: bytes) -> bytes:
    """A jointed (INFO_ANIM) model with one identity group becomes a plain model: same drawing,
    but ReHaunted gives jointed models a constant shadow (main.cpp: plain objects only cast one
    while moving), which crossed the rug (user test 2026-10-17)."""
    flags = struct.unpack_from("<H", data, 0)[0]
    p = 14
    p += 2 + struct.unpack_from("<H", data, p)[0]
    p += 2 + 6 * struct.unpack_from("<H", data, p)[0]
    groups_at = p
    ng = struct.unpack_from("<H", data, p)[0]
    if ng != 1:
        raise ValueError(f"{ng} groups: only a single group can be removed")
    g = groups_at + 2 + 2
    start, count, base = struct.unpack_from("<3h", data, g)
    delta = struct.unpack_from("<3h", data, g + 10)
    if start != 0 or base != 0 or delta != (0, 0, 0):
        raise ValueError("the group is not an identity group")
    out = bytearray(data[:groups_at] + data[groups_at + 2 + 2 + 16:])
    struct.pack_into("<H", out, 0, flags & ~INFO_ANIM)
    return bytes(out)


def _parse_plain(data: bytes):
    """(flags, box, scratch bytes, vertices, primitive list) of a plain (non-jointed) model."""
    flags = struct.unpack_from("<H", data, 0)[0]
    if flags & (INFO_ANIM | INFO_TORTUE | INFO_OPTIMISE):
        raise ValueError(f"not a plain model (flags {flags:#x})")
    box = struct.unpack_from("<6h", data, 2)
    p = 14
    sc = struct.unpack_from("<H", data, p)[0]
    scratch = data[p:p + 2 + sc]
    p += 2 + sc
    nv = struct.unpack_from("<H", data, p)[0]
    p += 2
    verts = [struct.unpack_from("<3h", data, p + 6 * i) for i in range(nv)]
    p += 6 * nv
    npr = struct.unpack_from("<H", data, p)[0]
    p += 2
    prims = []                       # (type, header bytes, point offsets, tail bytes)
    for _ in range(npr):
        t = data[p]
        if t == 0:                   # type, material, color, even, p1, p2
            prims.append((t, data[p:p + 4], list(struct.unpack_from("<2H", data, p + 4)), b""))
            p += 8
        elif t in (1, 8):            # type, n, material, color, points
            n = data[p + 1]
            prims.append((t, data[p:p + 4], list(struct.unpack_from(f"<{n}H", data, p + 4)), b""))
            p += 4 + 2 * n
        elif t in (2, 6, 7):         # type, material, color, even, point
            prims.append((t, data[p:p + 4], [struct.unpack_from("<H", data, p + 4)[0]], b""))
            p += 6
        elif t == 3:                 # type, material, color, even, size, point
            prims.append((t, data[p:p + 6], [struct.unpack_from("<H", data, p + 6)[0]], b""))
            p += 8
        else:
            raise ValueError(f"unsupported primitive type {t}")
    return flags, box, scratch, verts, prims


def cross_body(data: bytes) -> bytes:
    """The model plus a copy of itself turned 90 degrees about its long (z) axis, as one plain
    model: a flat item (the arrows) then shows one of its two fins from any side, like a crossed
    sprite (user idea, 2026-10-17). Solid colours (no HD texture map), lines kept (an arrow's
    shaft may be a line)."""
    plain = scale_body(data, 1.0, solid=True, drop_lines=False)
    flags, box, scratch, verts, prims = _parse_plain(plain)
    nv = len(verts)
    turned = [(-y, x, z) for x, y, z in verts]           # 90 degrees about z
    allv = verts + turned
    xs, ys, zs = zip(*allv)
    out = bytearray(struct.pack("<H", flags))
    out += struct.pack("<6h", min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    out += scratch
    out += struct.pack("<H", len(allv)) + b"".join(struct.pack("<3h", *v) for v in allv)
    out += struct.pack("<H", 2 * len(prims))
    for shift in (0, nv * 6):
        for t, head, pts, tail in prims:
            out += head + b"".join(struct.pack("<H", q + shift) for q in pts) + tail
    return bytes(out)
