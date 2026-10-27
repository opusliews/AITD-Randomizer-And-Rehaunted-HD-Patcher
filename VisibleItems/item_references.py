"""Every LIFE reference to the visible items (2026-10-17): which operands a world location's
patch must retarget (the location's own pickup and its events) and which belong to the item
(its found-life, its use elsewhere). Prints one line per reference."""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Projects\AITD\Generated\Patcher")
import aitd_life as L  # noqa: E402
import aitd_objets as O  # noqa: E402
import aitd_pak as P  # noqa: E402

G = Path(r"C:\Projects\AITD\OriginalGame\INDARK")
VISIBLE = [13, 56, 86, 83, 102, 107, 110, 120, 121, 123, 144, 125, 163, 171, 199, 182, 232, 17, 25, 96, 148, 205]


def main():
    pak = P.read_pak(G / "LISTLIFE.PAK")
    objs = O.read_objets((G / "OBJETS.ITD").read_bytes())
    owners = {}
    for i, o in enumerate(objs):
        for k in ("life", "found_life"):
            if o[k] >= 0:
                owners.setdefault(o[k], []).append(f"{i}.{k}")
    for item in VISIBLE:
        pats = [rf"\bobject\({item}\)", rf"isfound\(#{item}\)", rf"\bobj_{item}\.", rf"in_hand #{item}\b",
                rf"\bfound {item}\b", rf"\bput_at {item}\b", rf"#{item}\b", rf"\b{item} (?:\d|-)"]
        print(f"=== OBJ {item} (found_life {objs[item]['found_life']}, life {objs[item]['life']})")
        for n, e in enumerate(pak.entries):
            for line in L.format_script(L.decode(bytes(e.data))).splitlines():
                body = line.split("    ; @")[0]
                if any(re.search(p, body) for p in pats[:6]) or (re.search(pats[6], body) and "sound" not in body
                                                                and "message" not in body):
                    print(f"  LIFE {n:3} [{','.join(owners.get(n, []))}] {line.strip()}")


if __name__ == "__main__":
    main()
