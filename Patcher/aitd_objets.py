"""AITD1 OBJETS.ITD (world object table): read and write.

Layout, from the engine loader (ReHaunted FitdLib/main.cpp `LoadWorld`, same
as FITD): u16 count, then `count` records of 26 little-endian s16 fields
(52 bytes) in the order of FIELDS. The engine sizes its table from `count`.

Limit: 300 records. Vanilla INDARK.EXE allocates the table for exactly 300
(farmalloc 0x3CF0) and saves it as a fixed 15600-byte block; ReHaunted and
FITD save/load exactly 300 records (save.cpp, "fix for save engine").
Vanilla has 292 records. vanilla_exe.py --max-objects raises the vanilla
limit (Research/VanillaExe_Ghidra.md).
"""
from __future__ import annotations

import struct
from pathlib import Path

FIELDS = (
    "obj_index", "body", "flags", "type_zv", "found_body", "found_name", "found_flag", "found_life",
    "x", "y", "z", "alpha", "beta", "gamma", "stage", "room", "life_mode", "life", "floor_life",
    "anim", "frame", "anim_type", "anim_info", "track_mode", "track_number", "position_in_track",
)
RECORD_SIZE = 2 * len(FIELDS)
MAX_OBJECTS = 300


def read_objets(data: bytes) -> list[dict[str, int]]:
    (count,) = struct.unpack_from("<H", data, 0)
    if len(data) != 2 + count * RECORD_SIZE:
        raise ValueError(f"OBJETS.ITD: {len(data)} bytes, expected {2 + count * RECORD_SIZE} for {count} records")
    out = []
    for i in range(count):
        values = struct.unpack_from(f"<{len(FIELDS)}h", data, 2 + i * RECORD_SIZE)
        out.append(dict(zip(FIELDS, values)))
    return out


def write_objets(objects: list[dict[str, int]], max_objects: int = MAX_OBJECTS) -> bytes:
    """max_objects: 300 for unpatched engines; higher only for an engine whose
    table was raised (vanilla_exe.py --max-objects, or a fixed ReHaunted)."""
    if len(objects) > max_objects:
        raise ValueError(f"{len(objects)} objects: the target engine holds at most {max_objects}")
    out = bytearray(struct.pack("<H", len(objects)))
    for i, o in enumerate(objects):
        unknown = set(o) - set(FIELDS)
        if unknown:
            raise ValueError(f"object {i}: unknown fields {sorted(unknown)}")
        out += struct.pack(f"<{len(FIELDS)}h", *(o[f] for f in FIELDS))
    return bytes(out)


def load(path: Path | str) -> list[dict[str, int]]:
    return read_objets(Path(path).read_bytes())


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parents[1] / "ResearchRun" / "SourceCopy" / "OBJETS.ITD")
    raw = src.read_bytes()
    objs = read_objets(raw)
    same = write_objets(objs) == raw
    print(f"{src}: {len(objs)} objects, round trip {'identical' if same else 'DIFFERENT'}")
    sys.exit(0 if same else 1)
