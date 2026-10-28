"""AITD1 body (LISTBODY/LISTBOD2) and animation (LISTANIM/LISTANI2) parsing and posing.

Follows FITD hqr.cpp createBodyFromPtr / createAnimationFromPtr and renderer.cpp
AnimNuage / RotateGroupe / RotateList (AITD1 path: no INFO_OPTIMISE).
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field

INFO_ANIM, INFO_OPTIMISE = 2, 8


@dataclass
class Group:
    start: int; count: int; base: int; parent: int; num: int
    type: int; delta: tuple


@dataclass
class Prim:
    type: int; material: int; color: int; points: list; size: int = 0; even: int = 0


@dataclass
class Body:
    flags: int; zv: tuple; scratch: bytes; verts: list
    order: list = field(default_factory=list); groups: list = field(default_factory=list)
    prims: list = field(default_factory=list)


def parse_body(b: bytes) -> Body:
    o = 0
    def rd(fmt):
        nonlocal o
        v = struct.unpack_from("<" + fmt, b, o); o += struct.calcsize("<" + fmt); return v
    flags, = rd("H"); zv = rd("6h"); n, = rd("H"); scratch = b[o:o + n]; o += n
    nv, = rd("H"); verts = [rd("3h") for _ in range(nv)]
    body = Body(flags, zv, scratch, verts)
    assert not flags & 4
    if flags & INFO_ANIM:
        assert not flags & INFO_OPTIMISE, "AITD2+ body"
        ng, = rd("H")
        body.order = [rd("H")[0] // 0x10 for _ in range(ng)]
        for _ in range(ng):
            s, c, bv = rd("3h"); par, num = rd("2b"); t, = rd("h"); d = rd("3h")
            body.groups.append(Group(s // 6, c, bv // 6, par, num, t, d))
    np_, = rd("H")
    for _ in range(np_):
        t, = rd("B")
        if t in (0,):
            m, c, e = rd("3B"); pts = [x // 6 for x in rd("2H")]; body.prims.append(Prim(t, m, c, pts, even=e))
        elif t in (1, 8):
            k, m, c = rd("3B"); body.prims.append(Prim(t, m, c, [x // 6 for x in rd(f"{k}H")]))
        elif t in (2, 6, 7):
            m, c, e = rd("3B"); body.prims.append(Prim(t, m, c, [rd("H")[0] // 6], even=e))
        elif t == 3:
            m, c, e = rd("3B"); sz, = rd("H"); body.prims.append(Prim(t, m, c, [rd("H")[0] // 6], size=sz, even=e))
        elif t in (9, 10):
            k, m, c = rd("3B"); pts = [x // 6 for x in rd(f"{k}H")]; o += 2 * k
            body.prims.append(Prim(t, m, c, pts))
        else:
            raise ValueError(f"prim type {t}")
    body.tail = b[o:]
    return body


@dataclass
class Frame:
    time: int; step: tuple; groups: list   # groups: [(type, (x,y,z))]


@dataclass
class Anim:
    frames: list; num_groups: int


def parse_anim(b: bytes) -> Anim:
    nf, ng = struct.unpack_from("<HH", b, 0); o = 4
    assert len(b) == 4 + nf * (8 + ng * 8), "AITD2+ (optimised) animation"
    frames = []
    for _ in range(nf):
        t, sx, sy, sz = struct.unpack_from("<H3h", b, o); o += 8
        gs = []
        for _ in range(ng):
            ty, x, y, z = struct.unpack_from("<4h", b, o); o += 8; gs.append((ty, (x, y, z)))
        frames.append(Frame(t, (sx, sy, sz), gs))
    return Anim(frames, ng)


def write_anim(a: Anim) -> bytes:
    out = bytearray(struct.pack("<HH", len(a.frames), a.num_groups))
    for f in a.frames:
        out += struct.pack("<H3h", f.time, *f.step)
        for ty, d in f.groups:
            out += struct.pack("<4h", ty, *d)
    return bytes(out)


# ---- exact engine posing (integer maths, as the game does) -----------------
from functools import lru_cache

@lru_cache(maxsize=1)
def cos_table():
    import re, pathlib
    src = pathlib.Path(__file__).resolve().parents[2] / "FITD" / "FitdLib" / "cosTable.cpp"
    nums = [int(x) for x in re.findall(r"-?\d+", src.read_text().split("{", 1)[1].split("}", 1)[0])]
    assert len(nums) >= 1024
    return nums[:1024]


def _rot_list(pts, idxs, rx, ry, rz):
    ct = cos_table()
    def cs(a): return ct[a & 0x3FF], ct[(a + 0x100) & 0x3FF]   # (cos-slot = sin, sin-slot = cos) as engine names
    for i in idxs:
        x, y, z = pts[i]
        if ry:
            c, s = cs(ry); tx, tz = x, z
            x = (((tx * s) - (tz * c)) >> 16) << 1; z = (((tx * c) + (tz * s)) >> 16) << 1
        if rx:
            c, s = cs(rx); ty, tz = y, z
            y = (((ty * s) - (tz * c)) >> 16) << 1; z = (((ty * c) + (tz * s)) >> 16) << 1
        if rz:
            c, s = cs(rz); tx, ty = x, y
            x = (((tx * s) - (ty * c)) >> 16) << 1; y = (((tx * c) + (ty * s)) >> 16) << 1
        pts[i] = (x, y, z)


def pose(body: Body, states=None, alpha=0, beta=0, gamma=0):
    """Vertex positions in model space, as AnimNuage computes them (AITD1 path).
    states: per-group (type, (x,y,z)); default = the body's stored states."""
    pts = [tuple(v) for v in body.verts]
    st = [(g.type, g.delta) for g in body.groups] if states is None else list(states)
    st = st + [(g.type, g.delta) for g in body.groups[len(st):]]
    st[0] = (st[0][0], (alpha, beta, gamma))
    n = len(body.groups)

    def subtree(gi):
        g = body.groups[gi]; out = list(range(g.start, g.start + g.count))
        for j in range(gi + 1, n):            # RotateGroupe scans the groups after it
            if body.groups[j].parent == g.num:
                out += subtree(j)
        return out

    for i in range(n):
        gi = body.order[i]; g = body.groups[gi]
        ty, (x, y, z) = st[gi]
        if x or y or z:
            idx = list(range(g.start, g.start + g.count))
            if ty == 0:
                _rot_list(pts, subtree(gi), x, y, z)
            elif ty == 1:
                for k in idx: p = pts[k]; pts[k] = (p[0] + x, p[1] + y, p[2] + z)
            elif ty == 2:
                for k in idx:
                    p = pts[k]; pts[k] = (int(p[0] * (x + 256) / 256), int(p[1] * (y + 256) / 256), int(p[2] * (z + 256) / 256))
    for g in body.groups:
        bx, by, bz = pts[g.base]
        for k in range(g.start, g.start + g.count):
            p = pts[k]; pts[k] = (p[0] + bx, p[1] + by, p[2] + bz)
    return pts
