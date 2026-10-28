"""AITD1 randomizer generator, v1 (work-order step 4, part 1: the core).

  python generate.py --seed 1234 [--out DIR] [--vanilla-copy]

What v1 shuffles (only mechanisms proven in play):
  search slots (PoC B), containers and locked containers, inventory
  containers, the vase breakage, monster drops (PoC D/E) and the hidden
  library book (H:117). Contact slots and direct pickups keep their vanilla
  items (their visible world models need the pickup-slot design first), and so
  do their event hooks. Every slot keeps its vanilla conditions (Rule:
  `RandomizerPlan.md` "Slot conditions stay vanilla") and its item count.

Fill: assumed fill driven by the seed checker (Generated/Logic/logic_check.py).
  Progression items (every item the logic names) are placed one by one in a
  random order; each goes into a random empty position that is reachable when
  every progression item not yet placed is assumed owned. The remaining items
  fill the remaining positions at random. Items placed by `put_at` (monster
  drops, breakage) must have a world model. The finished placement is checked
  again with a full sweep; a failure is retried with the next sub-seed and is
  never written.

Output (DIR, default Generated/Seeds/seed_<n>):
  patchset/LISTLIFE.PAK + manifest.json   in-place operand retargeting, each
                                          site checked against its vanilla word;
                                          each patched script re-decoded with the
                                          same instructions and unchanged flow
  seed_<n>.scn                            TatouScenario scenario using the patch set
  placement.json                          slot -> items (the checker's input format)
  spoiler.md                              slot table and the playthrough spheres
  --vanilla-copy: Generated/VanillaTest/Seed_<n> (GOG game copy + LISTLIFE.PAK,
                  DOSBox-X config and launcher; the GOG exe is not modified)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import struct
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent
sys.path.insert(0, str(GEN / "Patcher"))
sys.path.insert(0, str(GEN / "Logic"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L            # noqa: E402
import aitd_objets as O          # noqa: E402
from aitd_pak import read_pak, write_pak   # noqa: E402
import logic_check as C          # noqa: E402
import locked_doors               # noqa: E402
import gamedata                   # noqa: E402
sys.path.insert(0, str(GEN / "BugSpray"))
import spray as SPRAY             # noqa: E402  (the Bug Spray item, every randomized seed)

SRC = gamedata.source_dir()      # ResearchRun/SourceCopy, or the player's game folder (the app)
CAT = GEN / "Patcher" / "catalog"
ROOT = GEN.parent
VERSION = "v20 (2026-10-28)"   # spray sound (sample 101); v19: boss needs the lighter
PART2_FAMILIES = {"container", "locked_container", "inventory_container", "breakage",
                  "monster_drop", "extra_search"}
PUT_AT_FAMILIES = {"breakage", "monster_drop", "enemy_drop"}
MAX_PER_LOCATION = 2       # user rule 2026-10-15: every location holds 0, 1 or 2 items
FALLBACK_MAX = 3           # user fallback rule 2026-10-15: cap 3 when the positions run out
# 1-item locations that can grow to 2 (script growth). Inventory containers stay at 1:
# they rename themselves "empty" once the first item is taken, losing a declined second one.
# Slots left vanilla (never shuffled; their vanilla item stays out of the pool):
#   H:117  the library's secret one-sided spot (debug OBJ 75, LIFE 117, book 76): searching works
#          from one side only, behind a bookcase that otherwise says "Nothing important" -
#          too confusing for a shuffled item (user, 2026-10-16).
SLOT_EXCLUDED = {"H:117"}
EXTRA_SPOT_EXCLUDED = {"F3:R12:HC10", "F3:R12:HC15"}   # Dining Room: share one search branch with the table HC14 (user-excluded); kept out by user decision 2026-10-16
GROWABLE_FAMILIES = {"search", "container", "locked_container", "extra_search",
                     "breakage", "monster_drop"}
# Non-progression items kept first when a seed has fewer positions than items:
# 1 = firearms, ammunition, healing; 2 = melee weapons; everything else (lore) = 3.
JUNK_TIER = {3: 1, 18: 1, 101: 1, 103: 1, 48: 1, 95: 1, 167: 1,
             111: 2, 112: 2, 172: 2, 173: 2}
DUD = 2                    # OBJ 2 "Actions" is always held: found 2 is a no-op and object(2) = 1,
                           # so a position pointed at it is empty ("Nothing important!")
EVENT_LABEL = {"lamp_lit": "the lamp can be lit", "jug_filled": "the jug can be filled with water",
               "knight_dead": "the knight can be defeated", "pirate_dead": "the pirate can be defeated",
               "ghosts_dead": "the ghosts can be banished", "medusas_dead": "the medusas can be defeated",
               "boss_defeated": "Pregzt can be defeated (goal)",
               "spiders_sprayed": "the Garden spiders can be sprayed"}


STATE_WORDS = ("empty", "broken", "wet")
FAMILY_LABEL = {"search": "Search", "container": "Container", "locked_container": "Locked container",
                "inventory_container": "Inside an item", "breakage": "Breaks open",
                "monster_drop": "Monster drop", "extra_search": "Search (hidden)",
                "enemy_drop": "Enemy drop", "extra_spot": "Search (extra spot)", "world": "In plain sight"}
# Option Shuffle Visible Items: names of the touch locations (contact zones use the user's zone names)
WORLD_DESC = {"P:17": "Floor", "P:25": "Against the wall", "P:96": "Floor", "P:148": "Floor",
              "P:205": "Wedge by the barrels"}


def friendly_names(objs, key_names=False):
    """Item -> player-facing name: the name shown on pickup, plus the game's own title rename
    (books, parchments, keys...) in quotes when it differs, e.g. 'A Parchment ("The Sacrificial
    Dagger")'. With the Show Key Names option keys show only their real name. Overrides from
    Generated/Logic/item_names.json."""
    import aitd_text as X
    txt = X.entries(read_pak(SRC / "ENGLISH.PAK").entries[0].data)
    lives = [L.decode(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
    owner = {o["found_life"]: i for i, o in enumerate(objs) if o["found_life"] != -1}
    title = {}
    for n, ins in enumerate(lives):
        for i in ins:
            if i.name == "found_name":
                tgt = i.obj if i.obj is not None else owner.get(n)
                text = txt.get(i.args[0], b"").decode("cp437", "replace").strip()
                if tgt is not None and text and not any(w in text.lower() for w in STATE_WORDS):
                    title.setdefault(tgt, text)
    out = {}
    for i, o in enumerate(objs):
        base = txt.get(o["found_name"], b"").decode("cp437", "replace").strip()
        t = title.get(i)
        if not base:
            out[i] = t or f"object {i}"
        elif t and t != base and not (key_names and base.lower() == "a key"):
            out[i] = f'{base} ("{t}")'     # the name on pickup, then the title once read/used
        else:
            out[i] = t or base
    over = json.loads((GEN / "Logic" / "item_names.json").read_text(encoding="utf-8"))
    for k, v in over.items():
        if not k.startswith("_"):
            out[int(k)] = v["name"]
    return out


def location_labels():
    """Region/room id -> player-facing label (Generated/Logic/location_names.json)."""
    d = json.loads((GEN / "Logic" / "location_names.json").read_text(encoding="utf-8"))

    def label(rid):
        if rid is None:
            return None
        floor = rid.split("/")[0]
        region = d["regions"].get(rid, d["regions"].get(floor)) if rid in d["regions"] else d["regions"].get(floor)
        alias = d["rooms"].get(rid, {}).get("same_as")      # e.g. 1/6 = the Storage Closet 1/0
        if alias:
            return label(alias)
        room = d["rooms"].get(rid, {}).get("name")
        if region and room and room != region:
            return f"{region} – {room}"
        return room or region or rid
    return label


def load_slots():
    """Shuffleable slots: id, family, life, vanilla items, item sites, region."""
    out = []
    for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]:
        if s["mechanism"] != "search":
            continue
        out.append({"id": s["slot_id"], "family": "search", "items": [i["obj"] for i in s["items"]],
                    "sites": {i["obj"]: [dict(x, life=s["life"]) for x in i["sites"]] for i in s["items"]}})
    for s in json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["slots"]:
        if s["family"] not in PART2_FAMILIES or s["slot_id"] in SLOT_EXCLUDED:
            continue
        out.append({"id": s["slot_id"], "family": s["family"], "items": list(s["items"]),
                    "sites": {int(k): [dict(x, life=x.get("life", s["life"])) for x in v]
                              for k, v in s["item_sites"].items()}})
    for x in out:
        x["min"] = 1 if x["family"] in PUT_AT_FAMILIES else 0   # put_at cannot be emptied
    set_cap(out, MAX_PER_LOCATION)
    return out


def VIS_MECH():
    sys.path.insert(0, str(GEN / "VisibleItems"))
    import mechanics
    return mechanics


def world_slots():
    """Option Shuffle Visible Items (user, 2026-10-16): the logic's contact and touch slots, one
    position per world location, exactly one item each (Generated/VisibleItems/placement.py).
    The hook altar is one location with a contact zone (F6:R6:HC81) and a touch pickup (P:232):
    P:232 becomes an empty alias, so the logic gives the altar's item once. `sites` (the contact
    zones' found operands) are for verify_seed.py; the patch itself is VisibleItems/mechanics.py."""
    sys.path.insert(0, str(GEN / "VisibleItems"))
    import placement as VIS
    contact = {s["slot_id"]: {i["obj"]: [dict(x, life=x.get("life", s.get("life"))) for x in i["sites"]]
                              for i in s["items"]}
               for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]
               if s["mechanism"] == "contact"}
    by_slot = defaultdict(list)
    for sp in VIS.world_spots():
        by_slot[sp["slot_id"]].append(sp)
    out = []
    for sid, sps in by_slot.items():
        items = [sp["vanilla_item"] for sp in sps]
        out.append({"id": sid, "family": "world", "items": items, "world": [sp["id"] for sp in sps],
                    "sites": {i: contact.get(sid, {}).get(i, []) for i in items},
                    "positions": len(items), "cap": len(items), "min": len(items)})
    out.append({"id": "P:232", "family": "world", "items": [], "world": [], "sites": {},
                "positions": 0, "cap": 0, "min": 0})
    return out


def set_cap(slots, max_per):
    """Positions and cap of every slot for a per-location maximum (2, or 3 as the fallback).
    Growable locations grow to the maximum; vanilla multi-item spots keep their positions;
    new places (extra spots, enemy drops) hold up to the maximum."""
    for x in slots:
        if x["family"] == "world":            # exactly one item per world location
            continue
        if x["family"] in ("extra_spot", "enemy_drop"):
            x["positions"] = x["cap"] = max_per
            continue
        grows = len(x["items"]) < max_per and x["family"] in GROWABLE_FAMILIES
        x["positions"] = max_per if grows else len(x["items"])
        x["cap"] = min(x["positions"], max_per)


def extra_spot_slots(rng, count, lives):
    """Many Search Places: `count` random usable empty zones become search spots (1-2 items).
    Only zones whose branch has the standard search shape (search checks + one message) and that
    the user annotated "Empty searchable area" are eligible; the two Dining Room zones run the
    table logic and are left out."""
    zones = json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["optional_empty_zones"]
    ok = []
    for z in zones:
        if not z["usable"] or z["zone_id"] in EXTRA_SPOT_EXCLUDED:
            continue
        # only zones the user confirmed as search spots in the inspector review; a valid
        # "nothing important" branch alone is not enough (F0:R0:HC17/HC23 and F2:R0:HC17/HC23
        # answer a search but are not real spots; user, 2026-10-16)
        if not (z.get("user_note") or "").strip().startswith("Empty searchable area"):
            continue
        branch = find_zone_branch(lives[z["controller_life"]], z["parameter"])
        if branch:
            ok.append(z)
    rng.shuffle(ok)
    out = []
    for z in sorted(ok[:count], key=lambda z: z["zone_id"]):
        fl, rm = z["zone_id"].split(":")[:2]
        out.append({"id": z["zone_id"], "family": "extra_spot", "items": [], "sites": {},
                    "life": z["controller_life"], "parameter": z["parameter"],
                    "region": f"{fl[1:]}/{rm[1:]}",
                    "positions": MAX_PER_LOCATION, "cap": MAX_PER_LOCATION, "min": 1})
    return out


def bare(ins) -> str:
    """Instruction text without a leading jump label ("L196: switch ..." -> "switch ...")."""
    return re.sub(r"^L\w+: ", "", L.format_instr(ins))


def find_zone_branch(instrs, param):
    """(kind, index) of the hard_col case/multi_case holding `param`, if its body is the
    standard empty-search shape: if anim #2 / if end_anim #1 / message N (same exit label)."""
    in_switch = False
    for k, ins in enumerate(instrs):
        t = bare(ins)
        if ins.op == L.OP_SWITCH:
            in_switch = t == "switch obj_1.hard_col"
            continue
        if not in_switch:
            continue
        if (ins.name == "case" and ins.args[0] == param) or \
                (ins.name == "multi_case" and param in ins.args[0]):
            body = [bare(x) for x in instrs[k + 1:k + 4]]
            if len(body) == 3 and body[0].startswith("if_egal obj_1.anim #2 @") and \
                    body[1].startswith("if_egal obj_1.end_anim #1 @") and body[2].startswith("message ") and \
                    body[0].rsplit("@", 1)[1] == body[1].rsplit("@", 1)[1]:
                return ins.name, k
            return None
    return None


def enemy_drop_slots(man, rng, chance):
    """Roll each eligible enemy (independent chance); a rolled enemy carries 1-2 items."""
    out = []
    for sid, e in man.get("enemy_drop_slots", {}).items():
        if sid.startswith("_"):
            continue
        if rng.random() * 100 < chance:
            out.append({"id": sid, "family": "enemy_drop", "enemy": e["enemy"], "items": [],
                        "sites": {}, "positions": MAX_PER_LOCATION, "cap": MAX_PER_LOCATION, "min": 1})
    return out


def progression_items(man, world_slots):
    text = json.dumps(man)
    items = {int(n) for n in re.findall(r"item:(\d+)", text)}
    for s in world_slots:
        items |= {int(n) for n in re.findall(r"item:(\d+)", s["requires"])}
    return items


def fill(rng, slots, prog, has_body, world, pool):
    """Assumed fill with per-location caps. Returns (placement, omitted junk, reason)."""
    nodes, edges, wslots, events, man = world
    family = {x["id"]: x["family"] for x in slots}
    cap = {x["id"]: x["cap"] for x in slots}
    placement = {x["id"]: [None] * x["positions"] for x in slots}
    count = lambda sid: sum(i is not None for i in placement[sid])
    fits = lambda sid, item: family[sid] not in PUT_AT_FAMILIES or has_body(item)

    def put(sid, item):
        k = placement[sid].index(None)
        placement[sid][k] = item

    order = [i for i in pool if i in prog]
    rng.shuffle(order)
    # Junk in priority tiers: if capacity runs out, lore goes before equipment.
    tiers = [[i for i in pool if i not in prog and JUNK_TIER.get(i, 3) == t] for t in (1, 2, 3)]
    for t in tiers:
        rng.shuffle(t)
    junk = tiers[0] + tiers[1] + tiers[2]
    needy = lambda sid: count(sid) < next(x["min"] for x in slots if x["id"] == sid)
    for n, item in enumerate(order):
        ok, st, spheres, got = C.sweep(nodes, edges, wslots, events, man, placement, set(order[n + 1:]))
        free = [x["id"] for x in slots if x["id"] in got and count(x["id"]) < cap[x["id"]]
                and fits(x["id"], item)]
        if not free:
            return None, [], f"no reachable position for item {item}"
        # Keep the minimums satisfiable: when the items still to place only just cover the
        # unmet minimums, this item must go to a location that still needs one.
        unmet = sum(max(0, x["min"] - count(x["id"])) for x in slots)
        remaining = len(order) - n + len(junk)
        if remaining <= unmet and any(needy(f) for f in free):
            free = [f for f in free if needy(f)]
        put(rng.choice(free), item)
    for x in slots:                                   # minimums first (put_at slots)
        while count(x["id"]) < x["min"]:
            pick = next((j for j in junk if fits(x["id"], j)), None)
            if pick is None:
                return None, [], f"not enough items for the minimum of {x['id']}"
            junk.remove(pick)
            put(x["id"], pick)
    while junk:                                       # then random free capacity
        free = [x["id"] for x in slots if count(x["id"]) < cap[x["id"]] and fits(x["id"], junk[0])]
        if not free:
            break
        put(rng.choice(free), junk.pop(0))
    return placement, junk, ""


_OWNERS = None


def life_owners_map(lives):
    """object -> every LIFE it can run (slot_catalog2.life_owners)."""
    global _OWNERS
    if _OWNERS is None:
        import slot_catalog2
        objs = O.load(SRC / "OBJETS.ITD")
        by = defaultdict(set)
        for life, objs_ in slot_catalog2.life_owners(lives, objs).items():
            for o in objs_:
                by[o].add(life)
        _OWNERS = by
    return _OWNERS


def enemy_death_sites(lives, enemy):
    """(life, instruction offset) of every `delete ENEMY` in the enemy's own scripts."""
    owners = life_owners_map(lives)
    return [(n, i.offset) for n in sorted(owners.get(enemy, ())) for i in lives[n]
            if i.name == "delete" and i.args[0] == enemy]


def patch(slots, placement, key_names_objs=None, doors=None, visible=None, saber_broken=False,
          whole_mirrors=False, glow_objs=None, spray=None):
    entries = [bytearray(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
    # base patch for every seed (vanilla flaw): the broken vase drops its contents at the player
    vase_report = [VIS_MECH().vase_contents_at_player(entries), VIS_MECH().vase_breaks_at_feet(entries)]
    # base patch for every seed (vanilla flaws), on the untouched scripts: LIFE 522 grows only at
    # its end and LIFE 550 keeps its size, so every later edit's offsets stay valid
    cellar_report = cellar_tunnel_fixes(entries)
    vis_report = None
    if visible is not None:
        # Shuffle Visible Items first, on the untouched scripts: its patches use vanilla offsets and
        # keep every script's size (word patches) or append new scripts, so the growth and extra-spot
        # edits below still work on top (VisibleItems/mechanics.py)
        sys.path.insert(0, str(GEN / "VisibleItems"))
        import mechanics as VIS_M
        assignment, displaced, vis_objs = visible
        vis_report = VIS_M.apply(entries, vis_objs, assignment, displaced)
    touched = defaultdict(set)
    originals = {}
    growth = []                       # (slot, its placement, items added beyond the vanilla positions)
    for s in slots:
        if s["family"] in ("enemy_drop", "extra_spot", "world"):
            continue                  # built below (world locations: VisibleItems/mechanics.py)
        extras = [i for i in placement[s["id"]][len(s["items"]):] if i is not None]
        if extras:
            growth.append((s, placement[s["id"]], extras))
        for k, old in enumerate(s["items"]):
            new = placement[s["id"]][k]
            for site in s["sites"][old]:
                if new is None and site["kind"] == "target":
                    continue          # obj_X.found_weight: keep the vanilla target, never touch OBJ 2
                if new is None and s["family"] in PUT_AT_FAMILIES:
                    raise SystemExit(f"{s['id']}: a put_at position cannot be emptied")
                new_word = DUD if new is None else new
                life = site["life"]
                originals.setdefault(life, bytes(entries[life]))
                word = struct.unpack_from("<h", entries[life], site["offset"])[0]
                if word != old:
                    raise SystemExit(f"{s['id']}: LIFE {life} @{site['offset']}: expected {old}, found {word}")
                struct.pack_into("<h", entries[life], site["offset"], new_word)
                touched[life].add(site["offset"])
    report = {}
    for life, before in originals.items():
        after = bytes(entries[life])
        diff = {i for i in range(0, len(before), 2) if before[i:i + 2] != after[i:i + 2]}
        a, b = L.decode(before), L.decode(after)
        same = len(a) == len(b) and all(x.op == y.op and x.offset == y.offset and x.size() == y.size()
                                        for x, y in zip(a, b))
        flow = L.check_patch(a, b)
        ok = same and flow.ok and not flow.changed_flow and diff <= touched[life]
        report[life] = {"ok": ok, "words_changed": len(diff), "sha256": hashlib.sha256(after).hexdigest()}
        if not ok:
            raise SystemExit(f"LIFE {life}: verification failed {report[life]}")
    # Growth: items beyond a location's vanilla positions (up to the cap, 2 or 3).
    #   1-item search/container shape "if_egal object(A) #0 @Lmsg / found A / ... / goto / Lmsg:
    #   message" becomes the PoC A pattern: offer all items when any is untaken, else the
    #   message (one declared flow change: the check now jumps to the offer);
    #   2-item cascade (vanilla "A untaken: found A, found B / else B untaken: found B / else
    #   message"): every "found B" is followed by the new items, and a branch "a new item is
    #   untaken: found them" goes in front of the message (the jumps to the message are the
    #   declared flow changes);
    #   put_at shape: more "put_at X self" right after the first (pure insertion).
    by_life = defaultdict(list)
    for s, got, extras in growth:
        words = [[x for x in s["sites"][item] if x["kind"] == "word"] for item in s["items"]]
        n_van = len(s["items"])
        if s["family"] in PUT_AT_FAMILIES:
            if n_van != 1:
                raise SystemExit(f"{s['id']}: growth of a {n_van}-item put_at location")
            for site in words[0]:                  # every death branch (the knight has two scripts)
                by_life[site["life"]].append(("put_at", s, site["at"], extras))
        elif n_van == 1:
            site = words[0][0]                     # the single found of the 1-item shape
            by_life[site["life"]].append(("offer", s, site["at"], [got[0]] + extras))
        else:
            last = s["items"][-1]
            checks = [x for x in s["sites"][last] if x["kind"] == "expr_arg"]
            if len(checks) != 1 or len({x["life"] for x in s["sites"][last]}) != 1:
                raise SystemExit(f"{s['id']}: unexpected cascade shape for growth")
            by_life[checks[0]["life"]].append(
                ("cascade", s, checks[0]["at"], (got[n_van - 1], [x["at"] for x in words[-1]], extras)))
    for life, ops in by_life.items():
        before = L.decode(bytes(entries[life]))
        offs = [i.offset for i in before]
        lines = L.format_script(before).splitlines()
        line_at = {int(l.rsplit("; @", 1)[1]): n for n, l in enumerate(lines) if "; @" in l}
        intended = set()
        edits = {}                         # line index -> replacement lines

        def edit(n, new_lines, sid):
            if n in edits:
                raise SystemExit(f"{sid}: LIFE {life} line {n} edited twice by growth")
            edits[n] = new_lines

        for n_op, (kind, s, at, data) in enumerate(ops):
            ins = before[offs.index(at)]
            if kind == "put_at":
                n = line_at[at]
                edit(n, [lines[n]] + [f"put_at {x} {ins.args[1]}" for x in data], s["id"])
                continue
            if kind == "offer":
                items = data
                chk = before[offs.index(at) - 1]
                text = bare(chk)
                if not (chk.name == "if_egal" and text.startswith(f"if_egal object({items[0]}) #0 @")):
                    raise SystemExit(f"{s['id']}: unexpected shape before found: {text}")
                lab = f"Lgrow{n_op}"
                n_chk, n_found = line_at[chk.offset], line_at[at]
                head = lines[n_chk].split("    ; @")[0]
                prefix = head.split(": ")[0] + ": " if head.startswith("L") and ": " in head else ""
                msg = text.rsplit("@", 1)[1]
                edit(n_chk, [f"{prefix}if_egal object({items[0]}) #1 @{lab}    ; @{chk.offset}"]
                     + [f"if_egal object({x}) #1 @{lab}" for x in items[1:]] + [f"goto @{msg}"], s["id"])
                edit(n_found, [f"{lab}: {lines[n_found]}"] + [f"found {x}" for x in items[1:]], s["id"])
                intended.add(chk.offset)
                continue
            # cascade
            cur_last, found_ats, extras = data
            text = bare(ins)
            if not (ins.name == "if_egal" and text.startswith(f"if_egal object({cur_last}) #0 @")):
                raise SystemExit(f"{s['id']}: unexpected cascade check: {text}")
            msg_lab = text.rsplit("@", 1)[1]
            k = offs.index(at)
            exit_ins = next((x for x in before[k + 1:] if x.name == "goto"), None)
            n_msg = next((n for n, l in enumerate(lines) if l.startswith(f"{msg_lab}: ")), None)
            if exit_ins is None or n_msg is None:
                raise SystemExit(f"{s['id']}: cascade without exit or message")
            msg_line = lines[n_msg][len(msg_lab) + 2:]
            if not msg_line.startswith("message "):
                raise SystemExit(f"{s['id']}: cascade ends in {msg_line!r}, not a message")
            exit_lab = bare(exit_ins).rsplit("@", 1)[1]
            for fa in found_ats:
                if bare(before[offs.index(fa)]) != f"found {cur_last}":
                    raise SystemExit(f"{s['id']}: expected found {cur_last} at @{fa}")
                n = line_at[fa]
                edit(n, [lines[n]] + [f"found {x}" for x in extras], s["id"])
            offer, new_msg = f"Lcasc{n_op}", f"Lcascm{n_op}"
            edit(n_msg, [f"{msg_lab}: if_egal object({extras[0]}) #1 @{offer}"]
                 + [f"if_egal object({x}) #1 @{offer}" for x in extras[1:]]
                 + [f"goto @{new_msg}", f"{offer}: found {extras[0]}"] + [f"found {x}" for x in extras[1:]]
                 + [f"goto @{exit_lab}", f"{new_msg}: {msg_line}"], s["id"])
            intended |= {x.offset for x in before if x.jump() and x.jump().label == msg_lab}
            msg_off = int(msg_line.rsplit("; @", 1)[1])
            intended.add(before[offs.index(msg_off) - 1].offset)
        out_lines = []
        for n, line in enumerate(lines):
            out_lines += edits.get(n, [line])
        patched = L.parse_script("\n".join(out_lines) + "\n")
        chk_r = L.check_text_patch(before, patched, intended)
        data = L.encode(patched)
        L.decode(data)
        if not chk_r.ok or chk_r.removed:
            raise SystemExit(f"LIFE {life}: growth failed the flow check: "
                             f"unexpected={chk_r.unexpected_flow} backward={chk_r.new_backward} "
                             f"removed={chk_r.removed}\n" + "\n".join(out_lines))
        entries[life] = bytearray(data)
        report[life] = dict(report.get(life, {}), ok=True, grown=len(ops),
                            sha256=hashlib.sha256(data).hexdigest())
    # Many Search Places: an empty zone gets an award block (PoC A pattern).
    #   own case: checks inserted before its message, offer after it (pure insertion);
    #   shared multi_case: a new "case P" in front of it (taking over its label), the
    #   value removed from the shared list (one declared flow change at the multi_case).
    spot_by_life = defaultdict(list)
    for s in slots:
        if s["family"] == "extra_spot":
            items = [i for i in placement[s["id"]] if i is not None]
            if items:
                spot_by_life[s["life"]].append((s, items))
    for life, ops in spot_by_life.items():
        before = L.decode(bytes(entries[life]))
        lines = L.format_script(before).splitlines()
        line_at = {int(l.rsplit("; @", 1)[1]): n for n, l in enumerate(lines) if "; @" in l}
        intended = set()
        edits = defaultdict(list)          # line index -> lines inserted BEFORE it
        repl = {}                          # line index -> replacement line
        blocks = defaultdict(list)         # multi_case line -> new case blocks (in order)
        for n_op, (s, items) in enumerate(ops):
            kind, k = find_zone_branch(before, s["parameter"])
            exit_lab = bare(before[k + 1]).rsplit("@", 1)[1]
            msg = bare(before[k + 3])
            offer = f"Lspot{n_op}"
            checks = [f"if_egal object({i}) #1 @{offer}" for i in items]
            founds = [f"{offer}: found {items[0]}"] + [f"found {i}" for i in items[1:]]
            if kind == "case":
                n_msg = line_at[before[k + 3].offset]
                edits[n_msg] += checks
                edits[n_msg + 1] += [f"goto @{exit_lab}"] + founds
            else:
                blocks[line_at[before[k].offset]].append(
                    (s["parameter"], [f"if_egal obj_1.anim #2 @{exit_lab}", f"if_egal obj_1.end_anim #1 @{exit_lab}"]
                     + checks + [msg, f"goto @{exit_lab}"] + founds + [f"goto @{exit_lab}"]))
        for n_mc, cases in blocks.items():
            line = lines[n_mc]
            head, _, off = line.partition("    ; @")
            label, _, instr = head.partition(": ") if head.startswith("L") and ": " in head else ("", "", head)
            mc = next(x for x in before if x.offset == int(off))
            taken = {p for p, _ in cases}
            keep = [v for v in mc.args[0] if v not in taken] or [-2]   # -2 never matches hard_col
            target = instr.rsplit("@", 1)[1]
            # chain: new case j falls through to new case j+1, the last one to the multi_case
            labels = [f"Lnc{n_mc}_{j}" for j in range(len(cases))] + [f"Lmc{n_mc}"]
            if label:                       # instructions that jumped to the multi_case now reach case 0
                labels[0] = label
                intended |= {x.offset for x in before if x.jump() and x.jump().label == label}
            prev = before[[x.offset for x in before].index(mc.offset) - 1]
            intended.add(prev.offset)       # the instruction before (e.g. the switch) now falls into case 0
            new = []
            for j, (param, body) in enumerate(cases):
                new.append(f"{labels[j]}: case {param} @{labels[j + 1]}" if (j or label) else
                           f"case {param} @{labels[j + 1]}")
                new += body
            edits[n_mc] += new
            repl[n_mc] = f"Lmc{n_mc}: multi_case [{','.join(map(str, keep))}] @{target}    ; @{off}"
            intended.add(mc.offset)
        out_lines = []
        for n, line in enumerate(lines):
            out_lines += edits.get(n, [])
            out_lines.append(repl.get(n, line))
        patched = L.parse_script("\n".join(out_lines) + "\n")
        chk_r = L.check_text_patch(before, patched, intended)
        data = L.encode(patched)
        L.decode(data)
        if not chk_r.ok or chk_r.removed:
            raise SystemExit(f"LIFE {life}: extra search spot failed the flow check: "
                             f"unexpected={[before[o].offset for o in chk_r.unexpected_flow]} "
                             f"backward={chk_r.new_backward} removed={chk_r.removed}\n" + "\n".join(out_lines))
        entries[life] = bytearray(data)
        report[life] = dict(report.get(life, {}), ok=True, extra_spots=len(ops),
                            sha256=hashlib.sha256(data).hexdigest())
    report[SPIDER_LIFE] = giant_spider_death(entries)    # every seed; before the drops below
    # Enemy drops: insert "put_at ITEM ENEMY" before each "delete ENEMY" (PoC E pattern).
    lives_now = [L.decode(bytes(e)) for e in entries]
    inserts = defaultdict(list)
    for s in slots:
        if s["family"] != "enemy_drop":
            continue
        items = [i for i in placement[s["id"]] if i is not None]
        for life, at in enemy_death_sites(lives_now, s["enemy"]):
            inserts[life].append((at, s["enemy"], items))
    for life, ins in inserts.items():
        before = L.decode(bytes(entries[life]))
        out_lines = []
        for line in L.format_script(before).splitlines():
            for at, enemy, items in ins:
                body = line.split("    ; @")[0]
                label, sep, instr = body.partition(": ") if body.startswith("L") and ": " in body else ("", "", body)
                if line.endswith(f"; @{at}") and instr == f"delete {enemy}":
                    new = [f"put_at {i} {enemy}" for i in items]
                    if label:                     # the label moves to the first inserted line
                        new[0] = f"{label}: {new[0]}"
                        line = f"{instr}    ; @{at}"
                    out_lines += new
            out_lines.append(line)
        patched = L.parse_script("\n".join(out_lines) + "\n")
        chk = L.check_text_patch(before, patched, set())
        data = L.encode(patched)
        L.decode(data)
        added = sum(len(x[2]) for x in ins)
        if not chk.ok or chk.added != added or chk.removed:
            raise SystemExit(f"LIFE {life}: enemy-drop insertion failed the flow check")
        entries[life] = bytearray(data)
        report[life] = dict(report.get(life, {}), ok=True, inserted_put_at=added,
                            sha256=hashlib.sha256(data).hexdigest())
    for life in range(len(entries)):        # renames skipped by emptied item branches
        moved = renames_on_empty(entries, life)
        if moved:
            report[life] = dict(report.get(life, {}), renames_on_empty=moved,
                                sha256=hashlib.sha256(bytes(entries[life])).hexdigest())
    if glow_objs is not None:             # before the appended key/lock scripts and the padding entry
        report["drop_glow"] = add_drop_glows(entries, slots, placement, glow_objs)
    report[TOILET_LIFE] = dict(report.get(TOILET_LIFE, {}), **add_toilet_message(entries))
    report[WORM_CHASE_LIFE] = worm_chase_wall_collision(entries)
    for life, r in cellar_report.items():
        report[life] = dict(report.get(life, {}), **r)
    report["vase_contents"] = vase_report
    if vis_report is not None:
        report["visible_items"] = vis_report
    if saber_broken:
        report["saber_pieces"] = break_saber_at_new_game(entries)
    if whole_mirrors:
        report[HIT_LIFE] = keep_mirrors_whole(entries)
    if spray is not None:                 # the Bug Spray's scripts (before the padding entry)
        report["bug_spray"] = SPRAY.add_scripts(L, entries, *spray)
    if doors is not None:                 # More Locked Doors: key and lock scripts are appended
        keys, key_recs, door_objs = doors
        report["locked_doors"] = locked_doors.add_scripts(L, entries, key_recs, keys, door_objs)
    elif visible is not None or report.get("drop_glow") or spray is not None:   # appended scripts need the padding entry
        entries.append(bytearray(L.encode(L.parse_script("endlife\n"))))
    if key_names_objs is not None:
        report[NEW_GAME_LIFE] = add_key_names(entries, key_names_objs)
    return write_pak([bytes(e) for e in entries]), report


def renames_on_empty(entries, life) -> list[str]:
    """A rename such as `obj_37.found_name 591` ("The chest's key", LIFE 45) sits inside the
    branch that gives the item. When the seed empties that location, the branch only finds the
    dud OBJ 2 and is never taken (object(2) is always 1), so the key kept "A Key" (user report
    2026-10-15). Copy each such rename to the start of the branch's "nothing here" message.
    Branch start = the jump target of the line before the first `found` (`if_egal object(2) #0
    @Lm`, vanilla shape, or `goto @Lm`, PoC A shape). Returns the inserted lines."""
    before = L.decode(bytes(entries[life]))
    lines = L.format_script(before).splitlines()
    body = lambda x: x.split("    ; @")[0]
    instr = lambda x: re.sub(r"^L\w+: ", "", body(x))
    inserts = {}                                    # message label -> rename lines
    for i, line in enumerate(lines):
        if not re.fullmatch(r"obj_\d+\.found_name \d+", instr(line)):
            continue
        j = i - 1
        while j >= 0 and re.fullmatch(r"obj_\d+\.found_name \d+", instr(lines[j])):
            j -= 1
        founds = []
        while j >= 0 and instr(lines[j]).startswith("found "):
            founds.append(instr(lines[j]))
            j -= 1
        if not founds or any(f != "found 2" for f in founds):
            continue
        m = re.fullmatch(r"(?:if_egal object\(2\) #[01] |goto )@(L\w+)", instr(lines[j]))
        if not m:
            continue
        target = m.group(1)
        for _ in range(8):      # vanilla chain "L300: if_egal object(2) #0 @L320" (LIFE 503): follow it
            at = next(x for x in lines if body(x).startswith(target + ": "))
            nxt = re.fullmatch(r"if_egal object\(2\) #0 @(L\w+)", instr(at))
            if not nxt:
                break
            target = nxt.group(1)
        inserts.setdefault(target, []).append(instr(line))
    if not inserts:
        return []
    out, added = [], []
    for line in lines:
        label = body(line).split(": ")[0] if re.match(r"^L\w+: ", line) else None
        if label in inserts:
            if not instr(line).startswith("message "):
                raise SystemExit(f"LIFE {life}: {label} is not a message branch: {line}")
            new = list(dict.fromkeys(inserts[label]))
            added += new
            out.append(f"{label}: {new[0]}")
            out += new[1:]
            out.append(f"{instr(line)}    ; @{line.split('    ; @')[1]}")
        else:
            out.append(line)
    patched = L.parse_script("\n".join(out) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != len(added) or chk.removed:
        raise SystemExit(f"LIFE {life}: rename-on-empty insertion failed the flow check")
    entries[life] = bytearray(data)
    return added


# ---- flavour patches, applied to every seed ---------------------------------------------
LANGUAGES = ("ENGLISH", "USA", "FRANCAIS", "ITALIANO", "ESPAGNOL", "DEUTSCH")
# Text ids: 1151-1299 new key names (More Locked Doors), 1301+ flavour (RandomizerPlan.md).
FLAVOUR_TEXTS = {1301: "Who would even think of", 1302: "doing something so disgusting?"}
TOILET_LIFE = 159          # 2nd floor Bathroom controller (OBJ 91)


def add_toilet_message(entries) -> dict:
    """Searching the 2nd floor Bathroom toilet F2:R5:HC9 (hard_col 3) shows two lines instead of
    "No Water" (an homage to Silent Hill 3; user 2026-10-16, tested in game with
    Scenarios/patch_sources/life159_toilet_message.asm). The engine stacks messages from the
    bottom in queue order, so the second line is queued first. The search also sets CVar 40
    (unused by the AITD1 engine and every script) and starts the controller's chrono; while
    CVar 40 = 1 and chrono < 3 s both lines are re-queued each frame (makeMessage restarts a
    shown message's timer), then CVar 40 is cleared.
    Applied to the seed's LIFE 159 (its HC10 cabinet branch may be patched), so the edit is
    made on the formatted script, not by pasting a listing."""
    before = L.decode(bytes(entries[TOILET_LIFE]))
    lines = L.format_script(before).splitlines()
    body = lambda x: x.split("    ; @")[0]
    instr = lambda x: re.sub(r"^L\w+: ", "", body(x))
    off = lambda x: int(x.split("    ; @")[1])
    i = next(k for k, x in enumerate(lines) if re.fullmatch(r"multi_case \[1,2,3,4\] @L\w+", instr(x)))
    label = body(lines[i]).split(": ")[0]
    target = instr(lines[i]).split("@")[1]
    intended = {off(lines[i])} | {off(x) for x in lines if x.split("    ; @")[0].endswith(f"@{label}")}
    split = [f"{label}: case 3 @Ltoilet_rest",
             f"if_egal obj_1.anim #2 @{target}",
             f"if_egal obj_1.end_anim #1 @{target}",
             "start_chrono",
             "c_var 40 #1",
             "message 1302",
             "message 1301",
             f"goto @{target}",
             f"Ltoilet_rest: multi_case [1,2,4] @{target}    ; @{off(lines[i])}"]
    lines[i:i + 1] = split
    last = lines[-1]
    if instr(last) != "endlife" or re.match(r"^L\w+: ", last):
        raise SystemExit(f"LIFE {TOILET_LIFE}: unexpected last line {last!r}")
    lines[-1:] = ["if_egal cvar(40) #1 @Ltoilet_end",
                  "if_inf chrono #3 @Ltoilet_clear",
                  "message 1302",
                  "message 1301",
                  "goto @Ltoilet_end",
                  "Ltoilet_clear: c_var 40 #0",
                  f"Ltoilet_end: endlife    ; @{off(last)}"]
    patched = L.parse_script("\n".join(lines) + "\n")
    chk = L.check_text_patch(before, patched, intended)
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.removed:
        raise SystemExit(f"LIFE {TOILET_LIFE}: toilet message failed the flow check")
    entries[TOILET_LIFE] = bytearray(data)
    return {"ok": True, "toilet_message": True, "sha256": hashlib.sha256(data).hexdigest()}


# ---- vanilla flaw fixed for every seed: the worm chase without walls ---------------------
WORM_CHASE_LIFE = 460      # worm OBJ 218, office route: waits for room 5/4, then the TRACK 20 chase
WORM_CHASE_ORIGINAL = bytes.fromhex("04001f800100ffff040007000f00030014000d00c2001f00cd010c00")
WORM_CHASE_PATCHED = bytes.fromhex("04001f800100ffff0400090036000100" "0f00030014000d00c2001f00cd010c00")


def worm_chase_wall_collision(entries) -> dict:
    """`test_col 1` in front of LIFE 460's `trackmode 3 20` (Research/WormRunaway_2026-10-26.md).
    Entering the tunnels from the cellar first runs LIFE 458 case 1 `test_col 0`; the engine
    keeps it with the worm (world flag 0x20) when it unloads, so the later office-route chase
    has no wall collision, misses OBJ 219's stop zone and walks off forever (the lure into the
    dirt tunnel then never happens). ReHaunted's lifeBugfixes.cpp applies the same 32 bytes and
    leaves an already patched LIFE 460 alone."""
    before = L.decode(bytes(entries[WORM_CHASE_LIFE]))
    if bytes(entries[WORM_CHASE_LIFE]) != WORM_CHASE_ORIGINAL:
        raise SystemExit(f"LIFE {WORM_CHASE_LIFE}: not the vanilla worm chase script")
    lines = L.format_script(before).splitlines()
    i = next(k for k, x in enumerate(lines) if x.split("    ; @")[0] == "trackmode 3 20")
    lines[i:i] = ["test_col 1"]
    patched = L.parse_script("\n".join(lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != 1 or chk.removed or data != WORM_CHASE_PATCHED:
        raise SystemExit(f"LIFE {WORM_CHASE_LIFE}: worm chase patch failed the flow check")
    entries[WORM_CHASE_LIFE] = bytearray(data)
    return {"ok": True, "worm_chase_wall_collision": True, "sha256": hashlib.sha256(data).hexdigest()}


# ---- vanilla flaws fixed for every seed: the cellar <-> tunnel passage ---------------------
# The same patches as ReHaunted's lifeBugfixes.cpp (Research/CellarTunnelTransition_4-0_5-3.md),
# so the original DOS game gets them too. ReHaunted leaves already patched data alone.
CELLAR_LIFE, ENDGAME_LIFE = 550, 522
CELLAR_WORDS = ((848, 6000, 5800, "cellar -> tunnel arrival z moved out of return zone F5:R3:SZ1"),
                (1810, 33, 172, "worm cellar placement guarded by the lure flag var_172"))
ENDGAME_INSERT_AT = 330           # LIFE 522: `var 172 #1` before the final endlife
ENDGAME_INSERT = bytes.fromhex("1300ac00ffff0100")
ENDGAME_JUMPS = ((8, 160), (20, 154))   # the two `goto 330` jump words, +4 words after the insert
TRACK_FIXES = {   # STOP moved in front of MARK 1: the player stops before the teleport
    40: (14, bytes.fromhex("040001000400020013000000000000000700"),
         bytes.fromhex("070004000100040002001300000000000000")),
    41: (14, bytes.fromhex("04000100040002000400030013000000000300000700"),
         bytes.fromhex("07000400010004000200040003001300000000030000")),
}


def cellar_tunnel_fixes(entries) -> dict:
    """LIFE 550: arrival z 6000 -> 5800 and the worm guard var_33 -> var_172 (same size; Visible
    Items edits LIFE 550 without moving offsets). LIFE 522: `var 172 #1` before the final endlife,
    both early jumps still on endlife."""
    report = {}
    life = entries[CELLAR_LIFE]
    for at, old, new, why in CELLAR_WORDS:
        word = struct.unpack_from("<H", life, at)[0]
        if word != old:
            raise SystemExit(f"LIFE {CELLAR_LIFE} @{at}: expected {old}, found {word} ({why})")
        struct.pack_into("<H", life, at, new)
    L.decode(bytes(life))
    report[CELLAR_LIFE] = {"ok": True, "cellar_tunnel_fixes": [w[3] for w in CELLAR_WORDS],
                           "sha256": hashlib.sha256(bytes(life)).hexdigest()}

    before = bytes(entries[ENDGAME_LIFE])
    if len(before) != ENDGAME_INSERT_AT + 2 or any(
            struct.unpack_from("<H", before, at)[0] != w for at, w in ENDGAME_JUMPS):
        raise SystemExit(f"LIFE {ENDGAME_LIFE}: not the vanilla endgame script")
    lines = L.format_script(L.decode(before)).splitlines()
    if not lines[-1].split("    ; @")[0].endswith("endlife") or not lines[-1].endswith(f"@{ENDGAME_INSERT_AT}"):
        raise SystemExit(f"LIFE {ENDGAME_LIFE}: unexpected last line {lines[-1]!r}")
    lines[-1:-1] = ["var 172 #1"]          # the jumps keep their label on the endlife
    patched = L.parse_script("\n".join(lines) + "\n")
    chk = L.check_text_patch(L.decode(before), patched, set())
    data = L.encode(patched)
    want = bytearray(before[:ENDGAME_INSERT_AT] + ENDGAME_INSERT + before[ENDGAME_INSERT_AT:])
    for at, w in ENDGAME_JUMPS:
        struct.pack_into("<H", want, at, w + len(ENDGAME_INSERT) // 2)
    if not chk.ok or chk.added != 1 or chk.removed or data != bytes(want):
        raise SystemExit(f"LIFE {ENDGAME_LIFE}: endgame lure flag failed the flow check")
    entries[ENDGAME_LIFE] = bytearray(data)
    report[ENDGAME_LIFE] = {"ok": True, "endgame_lure_flag": True, "sha256": hashlib.sha256(data).hexdigest()}
    return report


# ---- every seed: the giant spider dies like the other monsters ------------------------------
# OBJ 224 (5/6) dies only by falling into its hole: LIFE 471 deletes it once its room y passes
# -2000 (it walks at -4010; y grows downward). Before that delete it now gets the usual death,
# `do_real_zv / special 0 / sound #6` (the zombie's LIFE 84 @140), with the puff twice: TRACK 45
# warps it to the middle of the hole, then to the ledge spot, one `do_move` each, all in the same
# frame. An enemy drop's `put_at ITEM 224`, inserted later in front of the delete, then lands on
# that spot (user, 2026-10-27; points measured by the user in game, the hole centre being the
# middle of two edge points (-5073, 7683) and (-4952, 9805)).
SPIDER, SPIDER_LIFE, SPIDER_TRACK = 224, 471, 45
SPIDER_LIFE_ORIGINAL = bytes.fromhex("0000470006fffa0018fc000006fffa0048002c01010007002200ffff30f802002000e0000c00")
SPIDER_ROOM = 6
SPIDER_HOLE = (-5013, -4010, 8744)
SPIDER_DROP_SPOT = (-5087, -4010, 6781)
# Leash (user, 2026-10-27): the spider follows the player with no path finding, so once it
# leaves 5/6 it can get caught on walls for a minute or more (seen in the crossing 5/5), and
# it can only die in its own hole. When it is no longer in 5/6 while chasing, it walks back to
# the drop spot (TRACK 46 from the 5/5 door, TRACK 47 from the 5/10 door), then chases again.
# The ledge in 5/6 is a walled corridor at y -4010 (floor blocks, hard zones type 3) with no
# floor beyond its walls, so the walls stay on, and the walk-back follows the middle of the
# corridor: the 5/5 door opening is x -6400, z 1600..4600; the 5/10 door opening is
# z -8400, x 900..5900; the corridor runs 14 -> 19 -> 18 -> 16 -> 23 (ETAGE05 room 6 hard
# zones, Generated/ResearchRun/TrackRooms/datasets/rooms.json). Waypoints keep the spider's
# box (+-250) off every wall.
SPIDER_TRACK_FROM_5, SPIDER_TRACK_FROM_10 = 46, 47
SPIDER_PATH_FROM_5 = ((-5600, 3100), SPIDER_DROP_SPOT[::2])
SPIDER_PATH_FROM_10 = ((3400, -6900), (2400, -3900), (2400, -1400), (-5100, -1400), SPIDER_DROP_SPOT[::2])


def giant_spider_death(entries) -> dict:
    """LIFE 471: the leash in front of the fall test, and the death effect in front of
    `delete 224` (insertions; the leash's new jumps are its own)."""
    if bytes(entries[SPIDER_LIFE]) != SPIDER_LIFE_ORIGINAL:
        raise SystemExit(f"LIFE {SPIDER_LIFE}: not the vanilla giant spider script")
    before = L.decode(bytes(entries[SPIDER_LIFE]))
    lines = L.format_script(before).splitlines()
    i = next(k for k, x in enumerate(lines) if x.split("    ; @")[0].startswith("if_sup room_y "))
    leash = ["if_egal num_track #1 @Lsp_home",               # chasing (follow mode, target OBJ 1)
             "if_egal room #5 @Lsp_not5",
             f"trackmode 3 {SPIDER_TRACK_FROM_5}",
             "Lsp_not5: if_egal room #10 @Lsp_home",
             f"trackmode 3 {SPIDER_TRACK_FROM_10}",
             "Lsp_home: if_egal num_track #-1 @Lsp_fall",     # walk-back ended (TRACK END)
             "trackmode 2 1",
             "Lsp_fall: " + lines[i]]
    lines[i:i + 1] = leash
    i = next(k for k, x in enumerate(lines) if x.split("    ; @")[0] == f"delete {SPIDER}")
    death = ["do_real_zv", f"trackmode 3 {SPIDER_TRACK}", "do_move", "special 0", "do_move", "special 0", "sound #6"]
    lines[i:i] = death
    patched = L.parse_script("\n".join(lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != len(leash) - 1 + len(death) or chk.removed:
        raise SystemExit(f"LIFE {SPIDER_LIFE}: giant spider patch failed the flow check {chk}")
    entries[SPIDER_LIFE] = bytearray(data)
    return {"ok": True, "giant_spider_death": True, "giant_spider_leash": True,
            "sha256": hashlib.sha256(data).hexdigest()}


def spider_track() -> bytes:
    """TRACK 45: warp to the hole centre, warp to the drop spot, END (+ the usual [20, 2] trailer)."""
    words = [0, SPIDER_ROOM, *SPIDER_HOLE, 0, SPIDER_ROOM, *SPIDER_DROP_SPOT, 2, 20, 2]
    return struct.pack(f"<{len(words)}h", *words)


def spider_walk_back(path) -> bytes:
    """TRACK 46/47: GOTO each waypoint of 5/6 in turn, then END (the chase resumes)."""
    words = [w for x, z in path for w in (1, SPIDER_ROOM, x, z)] + [2, 20, 2]
    return struct.pack(f"<{len(words)}h", *words)


def track_fixes() -> tuple[bytes, dict]:
    """LISTTRAK.PAK with TRACK 40/41 reordered (STOP before MARK 1, lengths unchanged) and the
    giant spider's TRACK 45 appended."""
    tracks = [bytearray(e.data) for e in read_pak(SRC / "LISTTRAK.PAK").entries]
    for n, (at, old, new) in TRACK_FIXES.items():
        if bytes(tracks[n][at:at + len(old)]) != old:
            raise SystemExit(f"TRACK {n}: not the vanilla bytes at {at}")
        tracks[n][at:at + len(new)] = new
    if len(tracks) != SPIDER_TRACK:
        raise SystemExit(f"LISTTRAK.PAK: {len(tracks)} tracks, expected {SPIDER_TRACK}")
    tracks.append(bytearray(spider_track()))
    tracks.append(bytearray(spider_walk_back(SPIDER_PATH_FROM_5)))
    tracks.append(bytearray(spider_walk_back(SPIDER_PATH_FROM_10)))
    report = {str(n): "STOP before MARK 1" for n in TRACK_FIXES}
    report[str(SPIDER_TRACK)] = "new: the giant spider's death puffs (hole centre, drop spot)"
    report[str(SPIDER_TRACK_FROM_5)] = "new: the giant spider walks back from the 5/5 door"
    report[str(SPIDER_TRACK_FROM_10)] = "new: the giant spider walks back from the 5/10 door"
    return write_pak([bytes(t) for t in tracks]), report


def language_paks(extra: dict[int, str] | None = None) -> dict[str, bytes]:
    """The six language PAKs with the flavour texts (and e.g. new key names) added."""
    import aitd_text as X
    out = {}
    for lang in LANGUAGES:
        es = [e.data for e in read_pak(SRC / f"{lang}.PAK").entries]
        es[0] = X.add_entries(es[0], {**FLAVOUR_TEXTS, **(extra or {})})
        out[f"{lang}.PAK"] = write_pak(es)
    return out


NEW_GAME_LIFE = 562     # run once by OBJ 2 on the first frame of a new game


def key_renames(objs, lives, txt) -> list[tuple[int, int]]:
    """(key object, message) for every key whose scripts rename it from 'A Key' to its real
    name when it is used (found_name): 37, 53, 108, 141, 144, 163 in vanilla."""
    owner = {o["found_life"]: i for i, o in enumerate(objs) if o["found_life"] != -1}
    text = lambda m: txt.get(m, b"").decode("cp437", "replace").strip()
    out = {}
    for n, ins in enumerate(lives):
        for i in ins:
            if i.name != "found_name":
                continue
            tgt = i.obj if i.obj is not None else owner.get(n)
            if tgt is not None and text(objs[tgt]["found_name"]).lower() == "a key" \
                    and "key" in text(i.args[0]).lower():
                out.setdefault(tgt, i.args[0])
    return sorted(out.items())


SABER, SABER_BLADE = 38, 41
# Option Saber Pieces (user, 2026-10-13/17; Research/AnnotationReview_2026-10-13.md §3.2): what the
# game sets when the saber breaks (LIFE 49 @612-656), applied at new game when the seed's 50/50 roll
# says broken. Every consumer reads var_38 and the object ids, so nothing else changes; the break
# branch itself checks var_38 = 0, so the blade can never drop a second time.
SABER_BROKEN_LINES = [f"obj_{SABER}.body #42", f"obj_{SABER}.found_body 43", f"obj_{SABER}.found_name 580",
                      f"obj_{SABER}.found_weight 15", "var 38 #1", "var 39 #2"]


def break_saber_at_new_game(entries: list[bytearray]) -> dict:
    """The new-game script (LIFE 562) breaks the saber, right after 'take 2' (as Show Key Names)."""
    before = L.decode(bytes(entries[NEW_GAME_LIFE]))
    out_lines, done = [], False
    for line in L.format_script(before).splitlines():
        out_lines.append(line)
        if not done and line.split("    ; @")[0] == "take 2":
            out_lines += SABER_BROKEN_LINES
            done = True
    if not done:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: 'take 2' not found (saber pieces)")
    patched = L.parse_script("\n".join(out_lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != len(SABER_BROKEN_LINES) or chk.removed:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: saber insertion failed the flow check")
    entries[NEW_GAME_LIFE] = bytearray(data)
    return {"ok": True, "saber_broken": True, "sha256": hashlib.sha256(data).hexdigest()}


# Seed difficulty (Research/SeedDifficulty.md, user 2026-10-18): the route score is the length of
# the walkthrough planner's shortest complete route (room moves, floor changes weighted) as a
# percentage of the vanilla layout's (77). Bands from 200 seeds at the app defaults: 24 % easy,
# 48 % normal, 24 % hard, 4 % very hard.
VANILLA_SEED = 0                # seed 0: the original item layout with every fix and feature
DIFFICULTY = {"easy": (0, 59), "normal": (60, 89), "hard": (90, 119), "very-hard": (120, 1 << 30)}
DIFFICULTY_TRIES = 40           # placements rejected for their score before the seed is refused
_vanilla_cost = []


def route_score(world, placement) -> int | None:
    import walkthrough as W
    if not _vanilla_cost:                 # the original layout on an untouched world
        _vanilla_cost.append(W.Planner(*C.load_world(), {}).plan()[0])
    r = W.Planner(*world, placement).plan()
    return None if r is None else round(100 * r[0] / _vanilla_cost[0])


def difficulty_label(score: int | None) -> str:
    for name, (lo, hi) in DIFFICULTY.items():
        if score is not None and lo <= score <= hi:
            return {"very-hard": "Very hard"}.get(name, name.capitalize())
    return "unknown"


def add_drop_glows(entries: list[bytearray], slots, placement, objs: list[dict]) -> dict:
    """Option Drop Glow (Research/DropGlow.md): every monster drop that holds items (the Knight's
    and the Pirate's vanilla drops, and Enemy Drops) gets a glow object: a translucent light beam
    (model 274) put at the monster right after its last `put_at ITEM MONSTER`, in every death
    branch, with a script that deletes the glow once all of the drop's items have been taken.
    Glow records are appended to `objs`, their scripts to `entries`. Returns {glow: {...}}."""
    sys.path.insert(0, str(GEN / "DropGlow"))
    import glow
    out = {}
    for s in slots:
        if s["family"] not in ("monster_drop", "enemy_drop"):
            continue
        items = [i for i in placement[s["id"]] if i is not None]
        if not items:
            continue
        monster = s["enemy"] if s["family"] == "enemy_drop" else int(s["id"].split(":")[1])
        g = len(objs)
        rec, script = glow.glow_object(g, items)
        rec["life"] = len(entries)

        def dropped(line):                # the item of a "put_at ITEM MONSTER" line, else None
            m = re.fullmatch(rf"put_at (\d+) {monster}", re.sub(r"^L\w+: ", "", line.split("    ; @")[0]))
            return int(m.group(1)) if m else None
        sites = []
        for life in range(len(entries)):
            before = L.decode(bytes(entries[life]))
            lines = L.format_script(before).splitlines()
            runs = [n for n, line in enumerate(lines) if dropped(line) in items
                    and not (n + 1 < len(lines) and dropped(lines[n + 1]) is not None)]   # last of each run
            if not runs:
                continue
            for n in reversed(runs):
                lines.insert(n + 1, f"put_at {g} {monster}")
            patched = L.parse_script("\n".join(lines) + "\n")
            chk = L.check_text_patch(before, patched, set())
            data = L.encode(patched)
            L.decode(data)
            if not chk.ok or chk.added != len(runs) or chk.removed:
                raise SystemExit(f"LIFE {life}: drop glow insertion failed the flow check")
            entries[life] = bytearray(data)
            sites.append(life)
        if not sites:
            raise SystemExit(f"{s['id']}: no put_at of its items at monster {monster} found for the glow")
        objs.append(rec)
        entries.append(bytearray(L.encode(script)))
        out[g] = {"slot": s["id"], "monster": monster, "items": items, "life": rec["life"], "sites": sites}
    return out


HIT_LIFE = 553         # the player's hit reaction: breaks a carried mirror (54, then 55) per hit
MIRRORS = (54, 55)


def keep_mirrors_whole(entries: list[bytearray]) -> dict:
    """Option Prevent Mirrors From Breaking (Research/AnnotationReview_2026-10-13.md 1.3): a hit
    breaks one carried mirror, and a broken mirror never kills a medusa (a vanilla soft-lock).
    LIFE 553 @206/@268 tests `if_egal isfound(#54) #1`; isfound is only ever 0 or 1 (FITD and
    ReHaunted evalVar: foundFlag & 0x8000), so testing #2 skips both break branches. The same
    words are rewritten in place: size and flow unchanged."""
    before = L.decode(bytes(entries[HIT_LIFE]))
    out_lines, done = [], []
    for line in L.format_script(before).splitlines():
        for m in MIRRORS:
            old = f"if_egal isfound(#{m}) #1 "
            if old in line:
                line = line.replace(old, f"if_egal isfound(#{m}) #2 ")
                done.append(m)
        out_lines.append(line)
    if done != list(MIRRORS):
        raise SystemExit(f"LIFE {HIT_LIFE}: mirror tests not found (found {done})")
    patched = L.parse_script("\n".join(out_lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added or chk.removed or len(data) != len(entries[HIT_LIFE]):
        raise SystemExit(f"LIFE {HIT_LIFE}: mirror patch failed the flow check")
    entries[HIT_LIFE] = bytearray(data)
    return {"ok": True, "whole_mirrors": True, "sha256": hashlib.sha256(data).hexdigest()}


def add_key_names(entries: list[bytearray], objs) -> dict:
    """Option Show Key Names: the new-game script gives every key its real name at once
    (the same found_name the game runs when the key is used), right after 'take 2'."""
    import aitd_text as X
    txt = X.entries(read_pak(SRC / "ENGLISH.PAK").entries[0].data)
    renames = key_renames(objs, [L.decode(bytes(e)) for e in entries], txt)
    before = L.decode(bytes(entries[NEW_GAME_LIFE]))
    out_lines, done = [], False
    for line in L.format_script(before).splitlines():
        out_lines.append(line)
        if not done and line.split("    ; @")[0] == "take 2":
            out_lines += [f"obj_{k}.found_name {m}" for k, m in renames]
            done = True
    if not done:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: 'take 2' not found (key names)")
    patched = L.parse_script("\n".join(out_lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != len(renames) or chk.removed:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: key-name insertion failed the flow check")
    entries[NEW_GAME_LIFE] = bytearray(data)
    return {
        "ok": True, "key_names": {str(k): m for k, m in renames}, "sha256": hashlib.sha256(data).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--vanilla-copy", action="store_true")
    ap.add_argument("--attempts", type=int, default=200)
    ap.add_argument("--enemy-drops", action="store_true",
                    help="option: eligible enemies may carry items (Research/EnemyDrops_Review.md)")
    ap.add_argument("--drop-chance", type=float, default=25.0,
                    help="percent chance per eligible enemy, rolled independently (default 25)")
    ap.add_argument("--extra-spots", type=int, default=0,
                    help="option Many Search Places: this many random empty search zones become "
                         "search spots (0 = off; suggested 10; 40 eligible)")
    ap.add_argument("--locked-doors", type=float, default=0.0, metavar="CHANCE",
                    help="option More Locked Doors: percent chance per room key to lock every door "
                         "it opens (0 = off; default when on: 25)")
    ap.add_argument("--saber-pieces", action="store_true",
                    help="option Saber Pieces: 50/50 per seed, the saber starts broken and its blade is "
                         "shuffled as its own item (the coat-of-arms passage then needs both pieces)")
    ap.add_argument("--visible-items", action="store_true",
                    help="option Shuffle Visible Items: the items lying in the world (tables, floors, the "
                         "bow, the pantry key...) join the shuffle; any item can be shown at any world "
                         "location (Research/VisibleItems_Proposal.md)")
    ap.add_argument("--max-per-location", type=int, choices=(2, 3), default=None,
                    help="testing: force this per-location maximum (default: 2, and 3 only if "
                         "the items do not fit at 2)")
    ap.add_argument("--key-names", action="store_true",
                    help="option Show Key Names: every key shows its real name from the start "
                         "(vanilla: 'A Key' until used)")
    ap.add_argument("--difficulty", choices=tuple(DIFFICULTY), default=None,
                    help="only accept placements whose route score is in this band (easy < 60, normal "
                         "60-89, hard 90-119, very-hard 120+; the original layout = 100); at most "
                         f"{DIFFICULTY_TRIES} rejected placements, then the seed is refused "
                         "(Research/SeedDifficulty.md)")
    ap.add_argument("--drop-glow", action="store_true",
                    help="option Drop Glow: items dropped by monsters stand in a translucent light beam "
                         "until taken (Research/DropGlow.md)")
    ap.add_argument("--whole-mirrors", action="store_true",
                    help="option Prevent Mirrors From Breaking: being hit no longer breaks a carried "
                         "mirror (vanilla: a broken mirror can't kill a medusa, a soft-lock)")
    ap.add_argument("--check-placement", type=Path, default=None, metavar="PLACEMENT_JSON",
                    help="no fill and no output: build this seed's world (same seed and options) and "
                         "check the given placement.json against today's logic; exit 0 if the goal "
                         "is reachable (e.g. does an older seed still pass?)")
    a = ap.parse_args(argv)
    vanilla = a.seed == VANILLA_SEED
    if vanilla:
        # Seed 0 (user, 2026-10-26): the original item layout, no randomization at all; the fixes and
        # the non-random features (key names, whole mirrors, drop glow, ...) still apply
        a.enemy_drops = a.saber_pieces = a.visible_items = False
        a.extra_spots, a.locked_doors, a.difficulty = 0, 0.0, None

    world = C.load_world()
    nodes, edges, wslots, events, man = world
    slots = load_slots()
    known = {s["id"] for s in wslots}
    missing = [s["id"] for s in slots if s["id"] not in known]
    if missing:
        raise SystemExit(f"slots unknown to the logic: {missing}")
    objs = O.load(SRC / "OBJETS.ITD")
    names = {}
    for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]:
        names.update({i["obj"]: i["name"] for i in s["items"]})
    for s in json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))["slots"]:
        names.update({int(k): v for k, v in s.get("names", {}).items()})
    prog = progression_items(man, wslots)
    has_body = lambda i: objs[i]["body"] != -1
    pool = [i for x in slots for i in x["items"]]
    saber_broken = bool(a.saber_pieces) and random.Random(f"{a.seed}:saber").random() < 0.5
    if saber_broken:
        pool.append(SABER_BLADE)
        # the saber can't break any more, so the blade's vanilla source (Y:38) gives nothing
        slots = slots + [{"id": "Y:38", "family": "byproduct", "items": [], "sites": {},
                          "positions": 0, "cap": 0, "min": 0}]
        for e in edges:                       # the coat of arms takes both pieces, in either order
            if e["from"] == "3/11" and e["to"] == "5/0" and f"item:{SABER}" in e["requires"]:
                e["requires"] = e["requires"].replace(f"item:{SABER}", f"item:{SABER} & item:{SABER_BLADE}")
                e["expr"] = C.Expr(e["requires"])
    if a.visible_items:
        wl = world_slots()
        slots = slots + wl
        pool += [i for x in wl for i in x["items"]]
        # the cellar passage: whatever lies at the wedge location releases the barrels when taken
        # (mechanics.py), and it can always be taken there
        for e in edges:
            if e["from"] == "4/0" and e["to"] == "5/3" and "item:205" in e["requires"]:
                e["requires"] = e["requires"].replace("item:205", "true")
                e["expr"] = C.Expr(e["requires"])
        # the Bedroom 1 werewolf (E:87): taking whatever lies on the fireplace releases it
        # (mechanics.py retargets LIFE 138), not the notebook (Research/LogicAndChecker.md audit)
        for s in wslots:
            if s["id"] == "E:87":
                s["requires"] = "true"
                s["expr"] = C.Expr("true")
    if a.enemy_drops:          # the rolls are part of the seed, independent of fill retries
        slots = slots + enemy_drop_slots(man, random.Random(f"{a.seed}:drops"), a.drop_chance)
    spots_used = 0
    if a.extra_spots:
        # every extra spot must hold at least one item: never ask for more than the items allow
        room = len(pool) - sum(x["min"] for x in slots)
        spots_used = max(0, min(a.extra_spots, room))
        if spots_used < a.extra_spots:
            print(f"note: {a.extra_spots} extra spots requested, only {spots_used} can be filled "
                  f"({len(pool)} items for {sum(x['min'] for x in slots)} mandatory places); using {spots_used}")
        van_lives = [L.decode(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
        extra = extra_spot_slots(random.Random(f"{a.seed}:spots"), spots_used, van_lives)
        slots = slots + extra
        for x in extra:                       # the logic sees them as ordinary rooms' spots
            wslots.append({"id": x["id"], "region": x["region"], "items": [], "local": [],
                           "requires": "true", "expr": C.Expr("true")})

    doors = None
    if a.locked_doors:
        # rolled once per seed, independent of fill retries (like enemy drops)
        locked = locked_doors.roll(random.Random(f"{a.seed}:doors"), a.locked_doors)
        keys = locked_doors.plan_keys(locked, len(objs))
        key_recs = locked_doors.key_records(keys, objs)
        objs.extend(key_recs)                     # fill checks item models (has_body)
        for label, k in keys.items():
            pool.append(k["obj"])
            prog.add(k["obj"])
            for i in k["doors"]:
                pair = set(locked_doors.DOORS[i][1])
                gated = [e for e in edges if {e["from"], e["to"]} == pair]
                if len(gated) < 2:
                    raise SystemExit(f"locked door {locked_doors.DOORS[i][0]}: rooms {pair} have "
                                     f"{len(gated)} edge(s) in the logic, expected both directions")
                for e in gated:                   # locked from both sides
                    e["requires"] = f"({e['requires']}) & item:{k['obj']}"
                    e["expr"] = C.Expr(e["requires"])
        doors = (keys, key_recs, objs)

    spray = None
    if not vanilla:
        # the Bug Spray (user, 2026-10-28; BugSpray/spray.py): every randomized seed, never seed 0.
        # Appended after the keys, so key object numbers stay as before.
        spray_obj = len(objs)
        spray_rec = SPRAY.record(objs)
        objs.append(spray_rec)
        pool.append(spray_obj)
        prog.add(spray_obj)
        SPRAY.logic(edges, wslots, events, man, spray_obj, C.Expr)
        spray = (spray_obj, spray_rec)

    if a.check_placement:
        given = {k: v for k, v in json.loads(a.check_placement.read_text(encoding="utf-8")).items()
                 if not k.startswith("_")}
        unknown = sorted(set(given) - {s["id"] for s in wslots})
        if unknown:
            raise SystemExit(f"placement names slots this seed's world doesn't have: {unknown}")
        ok, st, spheres, got = C.sweep(nodes, edges, wslots, events, man, given)
        print(f"seed {a.seed}: {a.check_placement}: goal {'REACHED' if ok else 'NOT REACHED'}; "
              f"{len(st['reached'])}/{len(nodes)} regions, {len(spheres)} spheres; "
              f"unreached: {sorted(set(nodes) - st['reached'])}")
        return 0 if ok else 1

    # User fallback rule (2026-10-15): every location holds at most 2 items; only when the items
    # do not all fit (or no valid placement exists) the seed is filled again with at most 3.
    caps = (a.max_per_location,) if a.max_per_location else (MAX_PER_LOCATION, FALLBACK_MAX)
    best = None
    band = DIFFICULTY[a.difficulty] if a.difficulty else None
    difficulty_misses = 0                   # placements rejected for their score (all caps together)
    if vanilla:                             # every location keeps its own items; still logic-checked
        caps = ()
        set_cap(slots, MAX_PER_LOCATION)
        placement = {x["id"]: list(x["items"]) + [None] * (x["positions"] - len(x["items"])) for x in slots}
        ok, st, spheres, got = C.sweep(nodes, edges, wslots, events, man, placement)
        if not ok:
            print(f"seed {a.seed}: the original layout failed the logic check")
            return 1
        best = (placement, [], 0, MAX_PER_LOCATION)
    for cap_used in caps:
        set_cap(slots, cap_used)
        placement, omitted, why = None, [], ""
        for attempt in range(a.attempts):
            rng = random.Random(f"{a.seed}:{attempt}")
            placement, omitted, why = fill(rng, slots, prog, has_body, world, pool)
            if placement is None:
                continue
            ok, st, spheres, got = C.sweep(nodes, edges, wslots, events, man, placement)
            if ok and band is not None:
                score = route_score(world, placement)
                if score is None or not band[0] <= score <= band[1]:
                    difficulty_misses += 1
                    placement, why = None, f"difficulty: score {score} is not {a.difficulty}"
                    if difficulty_misses >= DIFFICULTY_TRIES:
                        break
                    continue
            if ok:
                break
            placement, why = None, "final check failed"
        if difficulty_misses >= DIFFICULTY_TRIES and placement is None:
            break
        if placement is not None and (best is None or len(omitted) < len(best[1])):
            best = (placement, omitted, attempt, cap_used)
        if placement is not None and not omitted:
            break
    if best is None:
        if difficulty_misses >= DIFFICULTY_TRIES:
            print(f"seed {a.seed}: no {a.difficulty} placement in {DIFFICULTY_TRIES} tries; "
                  f"try another seed number or settings")
        else:
            print(f"seed {a.seed}: no valid placement after {a.attempts} attempts per cap ({why})")
        return 1
    placement, omitted, attempt, cap_used = best
    set_cap(slots, cap_used)
    score = route_score(world, placement)
    level = "Vanilla" if vanilla else difficulty_label(score)

    out = a.out or (GEN / "Seeds" / f"seed_{a.seed}")
    (out / "patchset").mkdir(parents=True, exist_ok=True)
    for old in (out / "patchset").iterdir():  # a rerun into the same folder: install.py copies every
        if old.is_file():                     # PAK/ITD there, so no file of other options may remain
            old.unlink()
    visible = None
    if a.visible_items:
        assignment = {w: placement[s["id"]][k] for s in slots if s["family"] == "world"
                      for k, w in enumerate(s["world"])}
        displaced = {i for s in slots if s["family"] == "world" for i in s["items"]} - set(assignment.values())
        visible = (assignment, displaced, objs)
    pak, report = patch(slots, placement, objs if a.key_names else None, doors, visible, saber_broken,
                        a.whole_mirrors, objs if a.drop_glow else None, spray)
    (out / "patchset" / "LISTLIFE.PAK").write_bytes(pak)
    src_hash = hashlib.sha256((SRC / "LISTLIFE.PAK").read_bytes()).hexdigest()
    files = {"LISTLIFE.PAK": {"source_sha256": src_hash, "sha256": hashlib.sha256(pak).hexdigest()}}
    trak, report["tracks"] = track_fixes()            # every seed: the cellar <-> tunnel walks
    (out / "patchset" / "LISTTRAK.PAK").write_bytes(trak)
    files["LISTTRAK.PAK"] = {"source_sha256": hashlib.sha256((SRC / "LISTTRAK.PAK").read_bytes()).hexdigest(),
                             "sha256": hashlib.sha256(trak).hexdigest()}
    key_texts = {k["text"]: label for label, k in doors[0].items()} if doors else {}
    if spray:                                            # the Bug Spray's name and message
        key_texts.update(SPRAY.TEXTS)
        for name, data in SPRAY.anim_paks().items():     # Edward's and Emily's spray animation
            (out / "patchset" / name).write_bytes(data)
            files[name] = {"source_sha256": hashlib.sha256((SRC / name).read_bytes()).hexdigest(),
                           "sha256": hashlib.sha256(data).hexdigest()}
        samp = SPRAY.sample_pak()                         # the spray sound (sample 101)
        (out / "patchset" / "LISTSAMP.PAK").write_bytes(samp)
        files["LISTSAMP.PAK"] = {"source_sha256": hashlib.sha256((SRC / "LISTSAMP.PAK").read_bytes()).hexdigest(),
                                 "sha256": hashlib.sha256(samp).hexdigest()}
    glows = report.get("drop_glow") or {}
    if doors or a.visible_items or glows:                # new key records, door leaves, moved items, glows
        objets = O.write_objets(objs, 400)
        (out / "patchset" / "OBJETS.ITD").write_bytes(objets)
        files["OBJETS.ITD"] = {"source_sha256": hashlib.sha256((SRC / "OBJETS.ITD").read_bytes()).hexdigest(),
                               "sha256": hashlib.sha256(objets).hexdigest(), "objects": len(objs)}
    if a.visible_items or glows or spray:                # the randomizer's models (cover, arrow, glow, spray)
        for name, data in VIS_MECH().listbodies().items():   # Edward's and Emily's model files
            (out / "patchset" / name).write_bytes(data)
            files[name] = {"source_sha256": hashlib.sha256((SRC / name).read_bytes()).hexdigest(),
                           "sha256": hashlib.sha256(data).hexdigest()}
    for name, data in language_paks(key_texts).items():  # flavour texts + new key names
        (out / "patchset" / name).write_bytes(data)
        files[name] = {"source_sha256": hashlib.sha256((SRC / name).read_bytes()).hexdigest(),
                       "sha256": hashlib.sha256(data).hexdigest()}
    (out / "patchset" / "manifest.json").write_text(json.dumps({
        "tool": f"Generated/Generator/generate.py {VERSION}", "seed": a.seed, "attempt": attempt,
        "options": {"vanilla_layout": vanilla,
                    "enemy_drops": a.enemy_drops, "drop_chance": a.drop_chance if a.enemy_drops else None,
                    "extra_spots": a.extra_spots, "key_names": a.key_names,
                    "locked_doors": a.locked_doors or None, "visible_items": a.visible_items,
                    "saber_pieces": a.saber_pieces, "whole_mirrors": a.whole_mirrors,
                    "drop_glow": a.drop_glow,
                    "max_per_location": cap_used,
                    **({"forced_max_per_location": a.max_per_location} if a.max_per_location else {})},
        "omitted_items": omitted, "saber_broken": saber_broken,
        "difficulty": {"score": score, "label": level, "requested": a.difficulty},
        "files": files, "texts": {str(k): v for k, v in {**FLAVOUR_TEXTS, **key_texts}.items()},
        "scripts": report}, indent=1), encoding="utf-8")
    (out / "placement.json").write_text(json.dumps(
        {k: [i for i in v if i is not None] for k, v in placement.items()}, indent=1), encoding="utf-8")
    import zone_table                     # TatouScenario F8 zone colours (green = item inside)
    zone_table.write_seed(out)
    (out / f"seed_{a.seed}.scn").write_text(
        f"# Randomizer seed {a.seed} ({VERSION}): logic-checked, see spoiler.md.\n"
        f"# Copy this file and the patchset folder (as patchsets/seed_{a.seed}) to the exe's scenarios folder.\n"
        f"name Randomizer seed {a.seed}\npatchset patchsets/seed_{a.seed}\n", encoding="utf-8")

    nice = friendly_names(objs, a.key_names)
    if doors:
        nice.update({k["obj"]: label for label, k in doors[0].items()})
    if spray:
        nice[spray[0]] = SPRAY.TEXTS[SPRAY.TEXT_NAME]
    label = location_labels()
    fmt = lambda xs: ", ".join(nice.get(x, f"object {x}") for x in xs if x is not None) or "nothing"
    region = {s["id"]: s["region"] for s in wslots}
    container_of = {"I:46": 46, "I:94": 94, "I:181": 181}
    special = {"M:82": "dropped by the Knight", "M:149": "dropped by the Pirate",
               "B:56": "inside the vase (break it)", "Y:38": "when the saber breaks",
               "H:117": "hidden: works from one side only, so search it from both sides"}
    # the user's descriptions of search zones and containers (Generated/Logic/zone_descriptions.json)
    desc = {k: v for k, v in json.loads((GEN / "Logic" / "zone_descriptions.json").read_text(
        encoding="utf-8")).items() if not k.startswith("_")}
    desc.update(WORLD_DESC)
    desc_of = lambda sid: desc.get({"H:117": "F2:R0:HC18"}.get(sid, sid))

    enemies = json.loads((GEN / "Logic" / "enemy_names.json").read_text(encoding="utf-8"))
    for x in slots:
        if x["family"] == "enemy_drop":
            e = enemies[str(x["enemy"])]
            region[x["id"]] = e["location"]
            # "how": what makes a trigger-spawned enemy appear, or how a special one dies
            special[x["id"]] = f"dropped by the {e['name']}" + (f" ({e['how']})" if e.get("how") else "")

    def where(sid):
        extra = special.get(sid)
        if region.get(sid) is None:
            c = container_of.get(sid)
            return f"inside {nice.get(c, 'an item')}" if c else (extra or "in the inventory")
        place = label(region[sid]) + (f" – {desc_of(sid)}" if desc_of(sid) else "")
        return f"{place}, {extra}" if extra else place
    lines = [f"# Spoiler, seed {a.seed} ({VERSION})", "",
             f"Logic-checked: the goal is reachable (checker sweep). Fill attempt {attempt}.", "",
             f"Difficulty: **{level}** (score {score}; the original game's item layout = 100. The score is "
             "the length of the shortest route through the seed's puzzle chain).", "",
             ("Seed 0: the original item layout, nothing is shuffled; only the fixes and the options "
              "below apply." if vanilla else
              "Shuffled: search slots, containers, inventory containers, vase breakage, monster drops, "
              "the hidden library book. "
              + ("Visible items: everything lying in the world is shuffled too (any item can be shown at any "
                 "world location; each holds exactly one). " if a.visible_items else
                 "Contact slots and floor pickups are vanilla. ") +
              f"At most {cap_used} items per location; an empty search spot says \"Nothing important!\"."),
             "" if not a.extra_spots else f"Option: {a.extra_spots} extra search spots (empty in vanilla).",
             "" if not a.whole_mirrors else "Option: mirrors don't break when you are hit.",
             "" if not a.key_names else "Option: keys show their real names from the start (vanilla: \"A Key\" until used).",
             "" if not a.saber_pieces else (
                 "Option Saber Pieces: this seed's saber **starts broken**; its blade is a separate item (see the "
                 "table). The coat of arms in Jeremy's study takes both pieces, in either order."
                 if saber_broken else "Option Saber Pieces: this seed rolled a **whole** saber (50/50)."),
             "" if not a.enemy_drops else
             f"Option: enemies can drop items ({a.drop_chance:g}% per eligible enemy). Drops land where "
             "the enemy dies, which may be off camera: walk over the spot.", "",
             "| Location | How | Now gives | Vanilla item | Slot id |", "|---|---|---|---|---|"]
    for s in sorted(slots, key=lambda s: (where(s["id"]) or "", s["id"])):
        if not s["positions"] and not s["items"]:
            continue                      # empty aliases: P:232 (the altar's touch side), Y:38 (broken saber)
        lines.append(f"| {where(s['id'])} | {FAMILY_LABEL.get(s['family'], s['family'])} | "
                     f"**{fmt(placement[s['id']])}** | {fmt(s['items'])} | {s['id']} |")
    if omitted:
        lines += ["", f"Not in this seed (no room left): {fmt(omitted)}."]
    if doors:
        where_key = {i: sid for sid, v in placement.items() for i in v if i is not None}
        lines += ["", "## Locked doors", "",
                  f"Option More Locked Doors ({a.locked_doors:g}% per room key): these doors are locked "
                  "from both sides until opened with their key (select the key, then use it at the door).", "",
                  "| Door | Key | Key location |", "|---|---|---|"]
        for klabel, k in doors[0].items():
            sid = where_key.get(k["obj"])
            for i in k["doors"]:
                a_, b_ = locked_doors.DOORS[i][1]
                lines.append(f"| {label(a_)} ↔ {label(b_)} | {klabel} | "
                             f"{where(sid) if sid else 'not placed'} |")
    lines += ["", "## Playthrough (spheres)", ""]
    for k, sp in enumerate(spheres):
        bits = []
        if sp["regions"]:
            bits.append("new areas: " + ", ".join(dict.fromkeys(label(r) for r in sp["regions"])))
        if sp["events"]:
            bits.append("**" + ", ".join(EVENT_LABEL.get(e, e) for e in sp["events"]) + "**")
        if sp["slots"]:
            bits.append("; ".join(f"{fmt(x['items'])} ({where(x['slot'])})" for x in sp["slots"] if x["items"]))
        lines.append(f"{k}. " + " — ".join(bits))
    import walkthrough as W
    planner = W.Planner(nodes, edges, wslots, events, man, placement)
    walk = planner.plan()
    if walk is None:
        raise SystemExit(f"seed {a.seed}: the walkthrough planner found no route (the checker did)")
    words = json.loads((GEN / "Logic" / "walkthrough_text.json").read_text(encoding="utf-8"))["useful_words"]
    lines += [""] + W.render(planner, walk, nice, label, {x["id"]: x["family"] for x in slots},
                             special, container_of, words, desc_of)
    (out / "spoiler.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if a.vanilla_copy:
        dst = GEN / "VanillaTest" / f"Seed_{a.seed}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ROOT / "OriginalGame" / "INDARK", dst / "INDARK")
        for name in ("LISTLIFE.PAK", "LISTTRAK.PAK"):   # scripts only: the copy keeps the vanilla exe
            shutil.copy2(out / "patchset" / name, dst / "INDARK" / name)
        conf = (GEN / "VanillaTest" / "T1.conf").read_text(encoding="utf-8")
        conf = conf.replace("VanillaTest\\T1", f"VanillaTest\\Seed_{a.seed}")
        (GEN / "VanillaTest" / f"Seed_{a.seed}.conf").write_text(conf, encoding="utf-8")
        (GEN / "VanillaTest" / f"run_Seed_{a.seed}.bat").write_text(
            '@echo off\r\n"C:\\Tools\\DOSBox-X\\bin\\x64\\Release\\dosbox-x.exe" -conf "%~dp0'
            f'Seed_{a.seed}.conf"\r\n', encoding="utf-8")

    # independent check (verify_seed.py): every patched script must award exactly the placed
    # items. Added 2026-10-16 after a seed passed the generator's own checks but not this one.
    # In-process since 2026-10-17 (the patcher app is one frozen exe); verify_seed imports this
    # module by name, so run as a script it checks with a second, freshly loaded copy.
    import verify_seed
    bad, chk_lines = verify_seed.verify(out)
    if bad:
        print("\n".join(chk_lines))
        print(f"seed {a.seed}: REJECTED by verify_seed.py (the patched scripts do not match the placement)")
        return 1
    placed = sum(i is not None for v in placement.values() for i in v)
    spots = [x["id"] for x in slots if x["family"] == "extra_spot"]
    drops = [x["id"] for x in slots if x["family"] == "enemy_drop"]
    print(f"seed {a.seed}: {placed} items placed in {len(slots)} locations ({len(drops)} enemy drops), "
          f"{len(spots)} extra search spots, {len(omitted)} left out, attempt {attempt}, {len(spheres)} spheres, "
          f"{len(report)} scripts patched and verified, difficulty {level} ({score}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
