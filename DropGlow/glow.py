"""Drop glow objects (2026-10-17): a world object showing the glow model (glow_body.py,
GLOW_BODY in VisibleItems/placement.CUSTOM_BODIES) with a script that deletes it once all of
its items have been taken.

Record: as an item lying in the world (OBJ 13, the lamp: flags 0, life_mode 0, so its script
runs while it has an actor in the camera's room), but not foundable (found_flag 0, no found
body/name/life), so it can't be picked up, and type_zv 1 (the collision box is the model's
header box: a point above the players' heads since 2026-10-28, glow_body.BOX). The script, per item:
    if_egal isfound(#ITEM) #1 @Lend      ; not taken yet -> stop
    ...
    delete GLOW
    Lend: endlife
isfound is 1 once the item was ever taken (foundFlag & 0x8000), even if it was dropped again.
"""
from __future__ import annotations

import aitd_life as L

GLOW_BODY = 274


def glow_object(index: int, items: list[int]) -> tuple[dict, list]:
    """(OBJETS record without position or life, LIFE script) of the glow object `index`."""
    if not items:
        raise ValueError("a glow needs at least one item")
    rec = {"obj_index": -1, "body": GLOW_BODY, "flags": 0, "type_zv": 1, "found_body": -1,
           "found_name": -1, "found_flag": 0, "found_life": -1, "x": 0, "y": 0, "z": 0,
           "alpha": 0, "beta": 0, "gamma": 0, "stage": -1, "room": -1, "life_mode": 0, "life": -1,
           "floor_life": -1, "anim": -1, "frame": 0, "anim_type": 0, "anim_info": -1,
           "track_mode": 0, "track_number": -1, "position_in_track": 0}
    lines = [f"if_egal isfound(#{i}) #1 @Lend" for i in items] + [f"delete {index}", "Lend: endlife"]
    return rec, L.parse_script("\n".join(lines) + "\n")
