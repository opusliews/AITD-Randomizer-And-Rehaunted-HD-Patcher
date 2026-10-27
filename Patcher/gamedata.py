"""Where the generator reads the original game files from.

Inside the project: the read-only working copy Generated/ResearchRun/SourceCopy.
The patcher app (Generated/App) sets AITD_RANDO_DATA to the player's own game
folder (checked against the known GOG hashes first, install.check_game_data), so
the app ships no game data. Models are read from the PAK itself; inside the
project that gives the same bytes as ResearchRun/PakInventory/extracted/LISTBODY.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "ResearchRun" / "SourceCopy"


def source_dir() -> Path:
    return Path(os.environ.get("AITD_RANDO_DATA") or DEFAULT)


@lru_cache(maxsize=None)
def _paks(where: str, name: str) -> tuple[bytes, ...]:
    from aitd_pak import read_pak
    return tuple(bytes(e.data) for e in read_pak(Path(where) / name).entries)


def pak_entries(name: str) -> list[bytes]:
    return list(_paks(str(source_dir()), name))


def body(n: int) -> bytes:
    """Edward's model n (LISTBODY.PAK entry n)."""
    return _paks(str(source_dir()), "LISTBODY.PAK")[n]


def hard_collisions() -> list[dict]:
    """Every room's hard-collision boxes, as the rows of References/AITD_zones.csv (zone_kind
    hard_collision; numbers as strings). ETAGEnn.PAK entry 0 holds the rooms: a table of u32
    offsets, read up to first offset / 4 entries and only while an offset is inside the data
    (FITD room.cpp getNumberOfRoom); in each room u16 @0 points to the hard-collision list, a
    u16 count then 16-byte records x1 x2 y1 y2 z1 z2 (s16), parameter, type (u16)
    (FITD floor.cpp loadFloor)."""
    import struct
    rows = []
    for floor in range(8):
        data = _paks(str(source_dir()), f"ETAGE{floor:02d}.PAK")[0]
        offsets = []
        for i in range(struct.unpack_from("<I", data, 0)[0] // 4):
            off = struct.unpack_from("<I", data, i * 4)[0]
            if off > len(data):
                break
            offsets.append(off)
        for room, r in enumerate(offsets):
            p = r + struct.unpack_from("<H", data, r)[0]
            for j in range(struct.unpack_from("<H", data, p)[0]):
                x1, x2, y1, y2, z1, z2, param, typ = struct.unpack_from("<6h2H", data, p + 2 + 16 * j)
                rows.append({"zone_id": f"F{floor}:R{room}:HC{j}", "floor_id": str(floor), "room_id": str(room),
                             "zone_kind": "hard_collision", "zone_index": str(j), "type": str(typ),
                             "parameter": str(param), "x1": str(x1), "x2": str(x2), "y1": str(y1),
                             "y2": str(y2), "z1": str(z1), "z2": str(z2)})
    return rows
