"""Camera cover zones per room (AITD1: ETAGE0x.PAK entry 1; FITD floor.cpp loadFloor and
main.cpp isInPoly/findBestCamera). A camera lists the rooms it views; for each, polygons in that
room's coordinates / 10 where the player is "covered" by the camera. The union over all cameras
is where the player can stand in the room. covers(floor) -> {room: [[(x, z), ...], ...]} in
room units (x10 applied)."""
import struct, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "Patcher")]
import gamedata


def covers(floor: int) -> dict[int, list[list[tuple[int, int]]]]:
    raw = gamedata.pak_entries(f"ETAGE{floor:02d}.PAK")[1]
    n, last = 0, 0                                      # FITD: entries while the offsets increase
    while n < struct.unpack_from("<I", raw, 0)[0] // 4:
        o = struct.unpack_from("<I", raw, n * 4)[0]
        if o <= last:
            break
        last, n = o, n + 1
    out: dict[int, list] = {}
    for i in range(n):
        off = struct.unpack_from("<I", raw, i * 4)[0]
        if off + 0x14 > len(raw):                       # FITD: offset < raw size, else no camera
            continue
        nview = struct.unpack_from("<H", raw, off + 0x12)[0]
        p = off + 0x14
        for _ in range(nview):
            room, _mask, cover = struct.unpack_from("<hHH", raw, p)
            p += 12                                     # AITD1: idx, mask, cover, light x/y/z
            q = off + cover
            nz = struct.unpack_from("<H", raw, q)[0]; q += 2
            for _ in range(nz):
                npts = struct.unpack_from("<H", raw, q)[0]; q += 2
                pts = [struct.unpack_from("<hh", raw, q + 4 * j) for j in range(npts)]
                q += 4 * npts
                out.setdefault(room, []).append([(x * 10, z * 10) for x, z in pts])
    return out


def inside(polys, x, z) -> bool:
    for poly in polys:                                  # even-odd ray test
        c = False
        for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
            if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
                c = not c
        if c:
            return True
    return False


if __name__ == "__main__":
    for f in range(8):
        try:
            c = covers(f)
        except Exception as e:
            print(f, "error", e); continue
        print(f"floor {f}: rooms {sorted(c)} polys {sum(len(v) for v in c.values())}")
