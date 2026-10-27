"""Mechanics tests for visible items (2026-10-17): one hand-picked patch set (vanilla data + only
the visible-items mechanics, VisibleItems/mechanics.py) and one scenario per behaviour, the player
next to the location. Writes Generated/Scenarios/patchsets/vis_mechanics/ and
Generated/Scenarios/visible_mech/*.scn + CHECKLIST.md."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\Projects\AITD\Generated\Patcher")
import aitd_life as L  # noqa: E402
import aitd_objets as O  # noqa: E402
from aitd_pak import read_pak, write_pak  # noqa: E402
import build_visual_tests as BV  # noqa: E402
import mechanics as M  # noqa: E402
import placement as P  # noqa: E402

SRC = Path(r"C:\Projects\AITD\OriginalGame\INDARK")
SCN = P.ROOT / "Generated" / "Scenarios"
PATCHSET = SCN / "patchsets" / "vis_mechanics"
OUT = SCN / "visible_mech"

ASSIGNMENT = {"W:13": 110, "W:110": 13, "W:205": 37, "W:86": 205, "W:56": 171, "W:171": 56,
              "W:148": 101, "W:25": 81, "W:163": 3}
TESTS = [
    ("W:13", [], "Attic table: the Talisman lies there and CHIMES (positional). Take it: you get the Talisman; "
                 "the chime stops once taken."),
    ("W:110", [], "Ritual Chamber table: the Oil Lamp lies there; NO chime in this room. Take it: you get the lamp."),
    ("W:205", [], "Cellar wedge spot (touch): a small Key lies there. Walk into it: you get the key, and the "
                  "BARRELS ROLL (they hit hard: step aside). Re-enter the room later: they don't roll again."),
    ("W:86", [], "Bedroom 1 mantel: the wedge Block lies there. Take it: the werewolf comes (as with the notebook). "
                 "Later, the block does not roll the cellar barrels."),
    ("W:56", [], "Master Bedroom bedside table: the Pot of Soup. Take it: the werewolf jumps in through the window "
                 "after a moment (as with the vase)."),
    ("W:171", [], "Kitchen fireplace: the Vase. Take it, throw it anywhere (here or in another room): it breaks and "
                  "drops the Dresser's Key (its vanilla contents)."),
    ("W:148", [], "Drawing Room floor (touch): Some Bullets. Walk into them: you get the bullets."),
    ("W:25", [], "Storage Closet bow spot (touch): the Sword stands like the bow. Walk into it: you get the sword."),
    ("W:163", [], "Pantry nail: the Rifle hangs from the nail. Take it: you get the rifle."),
]


def main():
    entries = [bytearray(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
    objs = O.read_objets((SRC / "OBJETS.ITD").read_bytes())
    placed = set(ASSIGNMENT.values())
    displaced = {int(k[2:]) for k in ASSIGNMENT} - placed
    report = M.apply(entries, objs, ASSIGNMENT, displaced)
    entries.append(bytearray(L.encode(L.parse_script("endlife\n"))))     # padding (appended scripts)
    PATCHSET.mkdir(parents=True, exist_ok=True)
    (PATCHSET / "LISTLIFE.PAK").write_bytes(write_pak([bytes(e) for e in entries]))
    (PATCHSET / "OBJETS.ITD").write_bytes(O.write_objets(objs, 400))
    for name, data in M.listbodies().items():                  # the cover's new model (272), Edward + Emily
        (PATCHSET / name).write_bytes(data)
    (PATCHSET / "manifest.json").write_text(json.dumps({"tool": "Generated/VisibleItems/build_mechanics_tests.py",
                                                        "assignment": ASSIGNMENT, "displaced": sorted(displaced),
                                                        "report": report}, indent=1), encoding="utf-8")
    csv_objs, zs = P.objects(), P.zones()
    spots = {s["id"]: s for s in P.world_spots()}
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.scn"):
        old.unlink()
    check = ["# Visible items: mechanics test checklist (Generated/VisibleItems/build_mechanics_tests.py)", "",
             "Patch set `patchsets/vis_mechanics` (vanilla data + only the visible-items mechanics). Note: "
             "**ok / what happened**.", "", "| Scenario | What to do and expect | Notes |", "|---|---|---|"]
    n = 0
    for sid, give, expect in TESTS:
        s = spots[sid]
        f, r = s["floor"], s["room"]
        pt = BV.player_point(f, r, [s], csv_objs, zs, {ASSIGNMENT[sid], s["vanilla_item"]})
        n += 1
        name = f"mech_{n:02d}_{BV.room_name(f, r).replace(' ', '_')}"
        lines = [f"# Visible items, mechanics test {n:02d}: {BV.room_name(f, r)} ({f}/{r}), location {sid}.",
                 f"# {expect}", f"# Player at ({pt[0]}, 0, {pt[1]}): automatic safe point.",
                 f"name Visible items mechanics {n:02d}: {BV.room_name(f, r)}", "patchset ../patchsets/vis_mechanics"]
        lines += [f"give {g}" for g in give]
        lines.append(f"player {f} {r} {pt[0]} 0 {pt[1]}")
        (OUT / f"{name}.scn").write_text("\n".join(lines) + "\n", encoding="utf-8")
        check.append(f"| `{name}.scn` | {expect} | |")
    # path 2: back up the tunnel into the cellar with the wedge-spot item still there
    n += 1
    name = f"mech_{n:02d}_Tunnel_return"
    expect = ("Start in the tunnel (5/3) at the cellar-side arrival point. Walk north into the climb: you come up "
              "into the cellar, the BARRELS ROLL, and you are offered the wedge-spot item (the small key) instead of "
              "it being destroyed.")
    (OUT / f"{name}.scn").write_text("\n".join([
        f"# Visible items, mechanics test {n:02d}: tunnel return (LIFE 550 path 2). {expect}",
        "# Player at (-300, -4010, 5800): the patched cellar->tunnel arrival point (CellarTunnelTransition_4-0_5-3.md),",
        "# clear of every wall and 190 units outside the return zone F5:R3:SZ1. Caverns: player flags 321, Jump action.",
        f"name Visible items mechanics {n:02d}: tunnel return", "patchset ../patchsets/vis_mechanics",
        "obj 1 flags 321", "obj 2 found_flag 496", "player 5 3 -300 -4010 5800"]) + "\n", encoding="utf-8")
    check.append(f"| `{name}.scn` | {expect} | |")
    check.append("| (any) | Save after taking an item, load: the item stays in the inventory, the location stays "
                 "empty, nothing rolls or spawns twice. | |")
    (OUT / "CHECKLIST.md").write_text("\n".join(check) + "\n", encoding="utf-8")
    print(f"{n} scenarios; patch set {PATCHSET}")


if __name__ == "__main__":
    main()
