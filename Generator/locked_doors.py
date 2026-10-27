"""Option "More Locked Doors" (mansion only): open doors become locked by new keys.

Decisions (user, ReviewResponse_Reply_2026-10-13.md Round 2 and RandomizerPlan.md; door 29's
label and the 25 % default from 2026-10-16; door 59 = Dressing Room key, 2026-10-16):
  * 24 doors or door pairs, 21 keys; keys shared per room ("Key to the Kitchen" opens every
    Kitchen door);
  * an independent lock chance per key (room), default 25 %. A rolled key locks every door it
    opens: the Dining Room's front and side entrances, both Kitchen doors and both Garden doors
    lock together (user, 2026-10-18: a seed with only the side entrance locked made the key
    worthless; until then every door was rolled on its own);
  * key models from vanilla keys 37, 53, 108, 141, 163 (not 144); key labels as listed below.

Mechanism (PoC C, passed in vanilla and ReHaunted; Research/PoC_C_NewKeyLockedDoor.md):
  * a locked door leaf gets a NEW LIFE script, a copy of its vanilla script with a key check
    inserted just before the closed-door branch (the first `switch posrel(1)`): key in hand and
    the player's "use" animation (anim 2) finished -> the door opens as in vanilla (unlock click
    first); otherwise "It's locked!" (message 101). The opening branches hand over to the
    vanilla sub-scripts, which end with `life <vanilla>`, so once opened the door runs its
    vanilla script for good. Lock state = the leaf's life number: no VARS needed, kept in saves.
    Every door leaf starts closed (its state VAR is 0 in VARS.ITD) and its vanilla script has
    the same shape (guards, state test, closed branch at the first switch posrel(1)); the
    dining/smoking room doors keep their vanilla "locked during the ghouls' dinner" rule, which
    comes before the closed branch.
  * double doors (66/67, 137/138, 152/153, 186/187) are one roll; both leaves are locked with
    the same key, and opening either opens both (the vanilla script sets the other leaf's life).
  * each rolled key is a new OBJETS record cloned from a vanilla key (model, flags, weight,
    found flag), with its own name text (1151+) and its own found-LIFE (copy of key 37's LIFE 50
    with 37 replaced). Only keys whose doors were rolled are created.
"""
from __future__ import annotations

import re

KEY_MODELS = (37, 53, 108, 141, 163)
KEY_FOUND_LIFE = 50            # key 37's found-LIFE: the template for every new key
FIRST_KEY_TEXT = 1151          # text ids 1151-1299 = new key names (RandomizerPlan.md)
LOCKED_MESSAGE = 101           # "It's locked!"

# (door leaves, rooms (engine floor/room), key label)
DOORS = [
    ((22,), ("1/0", "1/1"), "Key to the Storage Closet (3rd Floor)"),
    ((29,), ("1/1", "1/3"), "Key to the Master Bathroom (3rd Floor)"),
    ((33,), ("1/1", "1/2"), "Key to the Study (3rd Floor)"),
    ((50,), ("1/1", "1/4"), "Key to the Master Bedroom (3rd Floor)"),
    ((59,), ("1/1", "1/5"), "Key to the Dressing Room (3rd Floor)"),
    ((63,), ("1/1", "1/7"), "Key to the Stairwell (3rd Floor)"),
    ((66, 67), ("2/1", "2/0"), "Key to the Library"),
    ((84,), ("2/4", "2/3"), "Key to Bedroom 1 (2nd Floor)"),
    ((88,), ("2/2", "2/4"), "Key to the Corridor (2nd Floor)"),
    ((89,), ("2/4", "2/1"), "Key to the Gallery (2nd Floor)"),
    ((93,), ("2/4", "2/5"), "Key to the Bathroom (2nd Floor)"),
    ((100,), ("2/4", "2/6"), "Key to Bedroom 2 (2nd Floor)"),
    ((104,), ("2/1", "2/7"), "Key to Bedroom 3 (2nd Floor)"),
    ((118,), ("2/2", "2/10"), "Key to the Living Room (2nd Floor)"),
    ((137, 138), ("3/1", "3/2"), "Key to the Drawing Room (1st Floor)"),
    ((152, 153), ("3/3", "3/4"), "Key to the Garden (1st Floor)"),
    ((154,), ("3/5", "3/4"), "Key to the Garden (1st Floor)"),
    ((164,), ("3/8", "3/5"), "Key to the Kitchen (1st Floor)"),
    ((168,), ("3/8", "3/7"), "Key to the Pantry (1st Floor)"),
    ((169,), ("3/8", "3/10"), "Key to the Kitchen Closet (1st Floor)"),
    ((177,), ("3/9", "3/8"), "Key to the Kitchen (1st Floor)"),
    ((186, 187), ("3/0", "3/12"), "Key to the Dining Room (1st Floor)"),
    ((188,), ("3/9", "3/12"), "Key to the Dining Room (1st Floor)"),
    ((198,), ("3/12", "3/13"), "Key to the Smoking Room (1st Floor)"),
]


def roll(rng, chance: float) -> list[int]:
    """Indexes into DOORS that are locked in this seed: one roll per key, in the order of first
    appearance in DOORS; a locked key locks all of its doors."""
    labels = list(dict.fromkeys(label for _, _, label in DOORS))
    locked = {label for label in labels if rng.random() * 100 < chance}
    return [i for i, (_, _, label) in enumerate(DOORS) if label in locked]


def plan_keys(locked: list[int], first_obj: int) -> dict[str, dict]:
    """label -> {"obj": new object id, "text": text id, "model": vanilla key, "doors": [...]}.
    Ids follow the order of first appearance in DOORS, so a seed always numbers them alike."""
    keys: dict[str, dict] = {}
    for i in locked:
        leaves, rooms, label = DOORS[i]
        if label not in keys:
            n = len(keys)
            keys[label] = {"obj": first_obj + n, "text": FIRST_KEY_TEXT + n,
                           "model": KEY_MODELS[n % len(KEY_MODELS)], "doors": []}
        keys[label]["doors"].append(i)
    return keys


def key_records(keys: dict[str, dict], objs: list[dict]) -> list[dict]:
    """New OBJETS records (appended in key order): clones of the vanilla model key. Their
    found_life is filled in by add_scripts once the script index is known."""
    out = []
    for label, k in keys.items():
        rec = dict(objs[k["model"]])
        rec["found_name"] = k["text"]
        out.append(rec)
    return out


def key_found_script(L, entries, key_obj: int) -> list:
    """Key 37's found-LIFE (LIFE 50) with 37 replaced by the new key: pick up, use, throw."""
    text = L.format_script(L.decode(bytes(entries[KEY_FOUND_LIFE])))
    body = "\n".join(line.split("    ; @")[0] for line in text.splitlines())
    new, n = re.subn(r"(?<![\w#])#?37\b", lambda m: m.group(0).replace("37", str(key_obj)), body)
    if n != 3:      # var 9 #37, obj_1.throw 11 4 13 37 ..., in_hand 37 (as in PoC C's LIFE 563)
        raise SystemExit(f"LIFE {KEY_FOUND_LIFE}: expected 3 references to key 37, found {n}")
    return L.parse_script(new + "\n")


def locked_door_script(L, entries, vanilla_life: int, key_obj: int) -> list:
    """Copy of a door leaf's vanilla script with the key check before the closed branch."""
    lines = [x.split("    ; @")[0] for x in L.format_script(L.decode(bytes(entries[vanilla_life]))).splitlines()]
    i = next(k for k, x in enumerate(lines) if re.sub(r"^L\w+: ", "", x) == "switch posrel(1)")
    label = lines[i].split(": ")[0] + ": " if re.match(r"^L\w+: ", lines[i]) else ""
    last = lines[-1]
    end = last.split(": ")[0] if re.match(r"^L\w+: endlife$", last) else None
    if end is None:
        raise SystemExit(f"LIFE {vanilla_life}: does not end with a labelled endlife: {last!r}")
    check = [f"{label}if_egal in_hand #{key_obj} @Llocked",
             f"if_egal obj_1.anim #2 @{end}",
             f"if_egal obj_1.end_anim #1 @{end}",
             "sound #3",                                    # unlock click (vanilla locked doors)
             re.sub(r"^L\w+: ", "", lines[i])]
    lines[i:i + 1] = check
    lines += [f"Llocked: message {LOCKED_MESSAGE}", "endlife"]
    return L.parse_script("\n".join(lines) + "\n")


def add_scripts(L, entries, objs_new: list[dict], keys: dict[str, dict], door_objs: list[dict],
                padding: str = "endlife\n") -> dict:
    """Appends every key's found-LIFE and every locked leaf's lock script to `entries` (a list
    of bytearrays), sets the new records' found_life and the door leaves' life, then appends
    one padding script (the engine's file count is one less than the entry count).
    Returns a report {"keys": {...}, "doors": {...}}."""
    report = {"keys": {}, "doors": {}}
    for (label, k), rec in zip(keys.items(), objs_new):
        n = len(entries)
        instrs = key_found_script(L, entries, k["obj"])
        if L.backward_branches(instrs):
            raise SystemExit(f"key {k['obj']}: backward branch in its found-LIFE")
        data = L.encode(instrs)
        L.decode(data)
        entries.append(bytearray(data))
        rec["found_life"] = n
        report["keys"][str(k["obj"])] = {"label": label, "text": k["text"], "model": k["model"],
                                         "found_life": n}
        for i in k["doors"]:
            leaves, rooms, _ = DOORS[i]
            for leaf in leaves:
                n = len(entries)
                instrs = locked_door_script(L, entries, door_objs[leaf]["life"], k["obj"])
                if L.backward_branches(instrs):
                    raise SystemExit(f"door {leaf}: backward branch in its lock script")
                data = L.encode(instrs)
                L.decode(data)
                entries.append(bytearray(data))
                report["doors"][str(leaf)] = {"key": k["obj"], "rooms": list(rooms),
                                              "vanilla_life": door_objs[leaf]["life"], "lock_life": n}
                door_objs[leaf]["life"] = n
    entries.append(bytearray(L.encode(L.parse_script(padding))))
    return report
