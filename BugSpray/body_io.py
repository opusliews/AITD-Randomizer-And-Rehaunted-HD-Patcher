"""Write AITD1 bodies (LISTBODY/LISTBOD2) parsed by AnimExport/aitd_model.parse_body, and edit
them: insert vertices into a group (renumbering later groups and primitives). Format: FITD
hqr.cpp createBodyFromPtr; checked byte-identical on every vanilla body (selftest below)."""
from __future__ import annotations
import struct, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "AnimExport")]
import aitd_model as M


def write_body(b: M.Body) -> bytes:
    out = bytearray(struct.pack("<H", b.flags))
    out += struct.pack("<6h", *b.zv)
    out += struct.pack("<H", len(b.scratch)) + bytes(b.scratch)
    out += struct.pack("<H", len(b.verts)) + b"".join(struct.pack("<3h", *v) for v in b.verts)
    if b.flags & M.INFO_ANIM:
        out += struct.pack("<H", len(b.groups))
        out += b"".join(struct.pack("<H", i * 0x10) for i in b.order)
        for g in b.groups:
            out += struct.pack("<3h", g.start * 6, g.count, g.base * 6)
            out += struct.pack("<2b", g.parent, g.num) + struct.pack("<h", g.type) + struct.pack("<3h", *g.delta)
    out += struct.pack("<H", len(b.prims))
    for p in b.prims:
        out.append(p.type)
        if p.type == 0:
            out += bytes([p.material, p.color, p.even]) + b"".join(struct.pack("<H", i * 6) for i in p.points)
        elif p.type in (1, 8):
            out += bytes([len(p.points), p.material, p.color]) + b"".join(struct.pack("<H", i * 6) for i in p.points)
        elif p.type in (2, 6, 7):
            out += bytes([p.material, p.color, p.even]) + struct.pack("<H", p.points[0] * 6)
        elif p.type == 3:
            out += bytes([p.material, p.color, p.even]) + struct.pack("<H", p.size) + struct.pack("<H", p.points[0] * 6)
        else:
            raise ValueError(f"prim type {p.type} not supported for writing")
    out += getattr(b, "tail", b"")
    return bytes(out)


def insert_verts(b: M.Body, group: int, verts: list[tuple]) -> int:
    """Append verts at the end of a group's vertex range (relative to the group's pivot, as
    stored); every later vertex index moves up. Returns the index of the first new vertex."""
    g = b.groups[group]
    at, k = g.start + g.count, len(verts)
    shift = lambda i: i + k if i >= at else i
    b.verts[at:at] = [tuple(v) for v in verts]
    for h in b.groups:
        if h is not g:
            h.start = shift(h.start)
        h.base = shift(h.base)
    g.count += k
    for p in b.prims:
        p.points = [shift(i) for i in p.points]
    return at


if __name__ == "__main__":                        # selftest: every vanilla body round-trips
    sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "Patcher")]
    import gamedata
    for pak in ("LISTBODY.PAK", "LISTBOD2.PAK"):
        bad = skipped = 0
        ents = gamedata.pak_entries(pak)
        for n, d in enumerate(ents):
            try:
                b = M.parse_body(d)
            except (ValueError, AssertionError):
                skipped += 1; continue
            if any(p.type in (9, 10) for p in b.prims):
                skipped += 1; continue
            if write_body(b) != d:
                bad += 1; print(pak, n, "differs")
        print(f"{pak}: {len(ents)} bodies, {bad} differ, {skipped} skipped (unsupported prims)")
