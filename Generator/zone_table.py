"""Search-zone tables for TatouScenario's F8 inspector colours (user request, 2026-10-15).

Text format, one zone per line:  <zone key> <tag> [item ...]
  zone key  F<floor>:R<room>:HC<index>, the inspector's own key (hard-collision zone index)
  tag       seed      the zone's items in this seed (randomized run)
            vanilla   the zone's items in the original game
            possible  empty in vanilla, but a seed can put items there (Many Search Places)

TatouScenario (scenarioTester.cpp, scenarioZoneColor):
  * a loaded patch set with search_zones.txt = randomized run: GREEN while any listed item is
    still in its spot (world object foundFlag & 0xC000 == 0, the game's own object() test),
    else the default red;
  * otherwise (vanilla, or a patch set without the file) scenarios/search_zones_vanilla.txt:
    GREEN while a vanilla item is still in its spot, ORANGE for vanilla zones already emptied
    and for "possible" zones, red for the rest.

  python zone_table.py vanilla OUT.txt      write the vanilla table
  python zone_table.py seed SEED_DIR        write SEED_DIR/patchset/search_zones.txt from placement.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent
CAT = GEN / "Patcher" / "catalog"
ZONE = re.compile(r"^F\d+:R\d+:HC\d+$")
# Slots whose id is not their zone key. H:117 (hidden book 76, LIFE 117 hard_col #6) is the
# library bookcase F2:R0:HC18, searched from the north side (user-verified in game 2026-10-15).
SLOT_ZONE = {"H:117": "F2:R0:HC18"}


def container_objects() -> dict[str, int]:
    """Container slots (C:N) -> the world object whose script gives the items when it is opened
    (e.g. C:45 = bathroom cabinet door OBJ 45, LIFE 54)."""
    out = {}
    for s in json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["slots"]:
        if s["family"] in ("container", "locked_container") and s.get("owners"):
            out[s["slot_id"]] = s["owners"][0]
    return out


def zone_of(slot_id: str) -> str | None:
    """Table key: the zone key for search zones, OBJ<n> for containers (inspector object label)."""
    if ZONE.match(slot_id):
        return slot_id
    if slot_id in container_objects():
        return f"OBJ{container_objects()[slot_id]}"
    return SLOT_ZONE.get(slot_id)


def vanilla_zones() -> dict[str, list[int]]:
    zones: dict[str, list[int]] = {}
    for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]:
        zones.setdefault(s["slot_id"], []).extend(i["obj"] for i in s["items"])
    for s in json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["slots"]:
        z = zone_of(s["slot_id"])
        if z and not ZONE.match(s["slot_id"]):
            zones.setdefault(z, []).extend(s["items"])
    return zones


def vanilla_table() -> list[str]:
    zones = vanilla_zones()
    sys.path.insert(0, str(HERE))
    import generate as G
    from aitd_pak import read_pak
    import random
    lives = [G.L.decode(e.data) for e in read_pak(G.SRC / "LISTLIFE.PAK").entries]
    possible = [x["id"] for x in G.extra_spot_slots(random.Random(0), 10 ** 6, lives)]
    lines = ["# search zones, vanilla game (Generated/Generator/zone_table.py)"]
    lines += [f"{z} vanilla " + " ".join(map(str, items)) for z, items in sorted(zones.items())]
    lines += [f"{z} possible" for z in sorted(possible) if z not in zones]
    return lines


def seed_table(seed_dir: Path) -> list[str]:
    """Vanilla zones, overridden by the seed's placement (zones it does not shuffle, such as
    contact spots, keep their vanilla items)."""
    placement = json.loads((seed_dir / "placement.json").read_text(encoding="utf-8"))
    zones = vanilla_zones()
    for sid in placement:
        if zone_of(sid):
            zones[zone_of(sid)] = []
    for sid, items in placement.items():
        z = zone_of(sid)
        if z:
            zones[z].extend(i for i in items if i is not None and i != 2)
    lines = [f"# search zones, {seed_dir.name} (Generated/Generator/zone_table.py)"]
    return lines + [f"{z} seed " + " ".join(map(str, items)) for z, items in sorted(zones.items())]


def write_seed(seed_dir: Path) -> Path:
    out = seed_dir / "patchset" / "search_zones.txt"
    out.write_text("\n".join(seed_table(seed_dir)) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "vanilla":
        Path(sys.argv[2]).write_text("\n".join(vanilla_table()) + "\n", encoding="utf-8")
    elif len(sys.argv) == 3 and sys.argv[1] == "seed":
        print(write_seed(Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
