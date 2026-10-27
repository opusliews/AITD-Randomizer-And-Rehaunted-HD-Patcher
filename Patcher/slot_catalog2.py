"""Location-slot catalog, part 2: every other way an item enters play.

  python slot_catalog2.py    -> catalog/acquisition_slots.json, catalog/acquisition_slots.csv

Part 1 (slot_catalog.py, catalog/search_slots.json) covers the type-9 search
and contact branches of the room controllers. Part 2 enumerates, from the raw
LIFE scripts and OBJETS.ITD, every remaining instruction or flag that puts an
item into the inventory or the world, and classifies it:

  container            a world object the player opens (posrel/anim test), then `found`
  locked_container     the same, gated by a key in hand (`in_hand #K`) and a var
  inventory_container  an item's found-LIFE, action 64 ("open"): `found X`, then the
                       container is renamed/reweighted
  breakage             an object's LIFE that releases an item when it breaks (`put_at X self`)
  monster_drop         a monster's death branch: `put_at X self`
  direct_pickup        a world object with AF_FOUNDABLE (0x80) in OBJETS.ITD: walk into it
  starting_inventory   `take X` in the new-game setup (LIFE 562)
  extra_search         a hard_col branch in a controller other than the room's main one

Not slots, but recorded for the logic file:
  item_use_placements  an item's found-LIFE `put`/`put_at`/`drop` when used (puzzles:
                       the item leaves the inventory and goes into the world)
  item_returns         `found` that gives a used item back (gramophone records)
  optional_empty_zones type-9 zones whose branch only shows a message, with the
                       parameter-sharing check (PoC A pattern, "Many Search Places")

Every `found` in the game must be in part 1 or part 2 (checked), and every
direct pickup is checked against the independent LifeDISA-derived
Generated/ResearchRun/ObjectVars/output/item_evidence.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
import aitd_objets as O        # noqa: E402
from aitd_pak import read_pak  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "ResearchRun"
SRC = RUN / "SourceCopy"
OUT = HERE / "catalog"
REFS = HERE.parents[1] / "References"

OP = L.OPCODE_BY_NAME
ACQ = {"found", "take", "put_at", "put", "drop"}
ITEM_FIELDS = {"object", "isfound", "thrown"}
AF_FOUNDABLE = 0x80


def life_owners(lives, objs):
    """life -> {object: roles}; follows `life N` / `obj_X.life N` from every start life."""
    owners = defaultdict(lambda: defaultdict(set))
    work = []
    for i, o in enumerate(objs):
        for field, role in (("life", "life"), ("floor_life", "floor"), ("found_life", "found")):
            if o[field] != -1:
                owners[o[field]][i].add(role)
                work.append((o[field], i))
    seen = set()
    while work:
        life, obj = work.pop()
        if (life, obj) in seen:
            continue
        seen.add((life, obj))
        for ins in lives[life]:
            if ins.op == OP["life"] and 0 <= ins.args[0] < len(lives):
                tgt = ins.obj if ins.obj is not None else obj
                owners[ins.args[0]][tgt].add("life")
                work.append((ins.args[0], tgt))
    return owners


def item_sites(instrs, item):
    """Every operand naming `item` as an object in a script."""
    out = []
    for ins in instrs:
        for s in L.operand_sites(ins):
            if s.value != item:
                continue
            if (s.kind == "word" and ins.name in ("found", "take", "put_at", "put", "drop")
                    and s.detail.endswith("#0")) or s.kind == "target" \
                    or (s.kind == "expr_arg" and s.detail in ITEM_FIELDS) \
                    or (s.kind == "const" and s.detail == "isfound"):
                out.append({"offset": s.offset, "kind": s.kind, "detail": s.detail,
                            "instruction": L.format_instr(ins), "at": ins.offset})
    return out


def conditions_before(instrs, k):
    """Conditional branches before instruction k (text), as local requirements."""
    out = []
    for ins in instrs[:k]:
        if ins.jump() and ins.op not in (L.OP_GOTO, L.OP_CASE, L.OP_MULTI_CASE):
            out.append(f"@{ins.offset} {L.format_instr(ins)}")
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    lives = [L.decode(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
    objs = O.load(SRC / "OBJETS.ITD")
    names = {int(r["object_id"]): r["found_name_text"] for r in
             csv.DictReader(open(RUN / "ObjectVars" / "output" / "item_evidence.csv", encoding="utf-8"))}
    owners = life_owners(lives, objs)
    part1 = json.loads((OUT / "search_slots.json").read_text(encoding="utf-8"))["slots"]
    covered = defaultdict(list)
    for s in part1:
        covered[s["life"]].append((s["branch_bytes"][0], s["branch_bytes"][1] or 1 << 30))

    def where(obj):
        o = objs[obj]
        return None if o["stage"] == -1 else {"floor": o["stage"], "room": o["room"]}

    slots, uses, returns, uncovered = [], [], [], []
    for n, instrs in enumerate(lives):
        own = owners.get(n, {})
        roles = {r for rs in own.values() for r in rs}
        for k, ins in enumerate(instrs):
            if ins.name not in ACQ:
                continue
            if ins.name == "found" and any(a <= ins.offset < b for a, b in covered.get(n, [])):
                continue
            base = {"life": n, "at": ins.offset, "instruction": L.format_instr(ins),
                    "owners": sorted(own), "owner_roles": sorted(roles)}
            if ins.name == "drop" and ins.args[0].kind == "var":
                base["note"] = "the player's own drop (LIFE 11, item in var_9)"
                uses.append(dict(base, kind="player_drop"))
                continue
            if ins.name == "take":
                item = ins.args[0]
                slots.append(dict(base, slot_id=f"S:{item}", family="starting_inventory",
                                  location=None, items=[item]))
                continue
            if ins.name == "put":
                item = ins.args[0]
                uses.append(dict(base, kind="put", item=item,
                                 to={"floor": ins.args[5], "room": ins.args[4],
                                     "x": ins.args[1], "y": ins.args[2], "z": ins.args[3]}))
                continue
            if ins.name == "drop":
                uses.append(dict(base, kind="drop_at", item=None, onto=ins.args[0].value))
                continue
            if ins.name == "put_at":
                item, at = ins.args
                owner = sorted(own)[0] if own else None
                if "found" in roles and owner == item:
                    uses.append(dict(base, kind="put_at", item=item, onto=at))
                elif "found" in roles and at == 1:
                    # an item's found-LIFE drops another item at the player (saber -> blade)
                    slots.append(dict(base, slot_id=f"Y:{owner}", family="item_byproduct",
                                      location=None, source_obj=owner, items=[item]))
                elif at == owner:
                    fam = "breakage" if any("isfound" in L.format_instr(i) for i in instrs[:k])                         else "monster_drop"
                    sid = f"{'B' if fam == 'breakage' else 'M'}:{owner}"
                    prev = next((x for x in slots if x["slot_id"] == sid), None)
                    if prev:
                        prev.setdefault("also", []).append({"life": n, "at": ins.offset})
                    else:
                        slots.append(dict(base, slot_id=sid, family=fam, location=where(owner),
                                          source_obj=owner, items=[item]))
                else:
                    slots.append(dict(base, slot_id=f"X:{n}@{ins.offset}", family="unclassified_put_at",
                                      location=where(owner) if owner is not None else None, items=[item]))
                continue
            # found outside part 1
            item = ins.args[0]
            owner = sorted(own)[0] if own else None
            text = "\n".join(L.format_instr(i) for i in instrs)
            if "found" in roles and objs[owner]["found_name"] != -1:
                if any(i.name == "case" and i.args[0] == 64 for i in instrs[:k]):
                    fam, loc = "inventory_container", None
                    sid = f"I:{owner}"
                else:
                    returns.append(dict(base, item=item))
                    continue
            elif "obj_1.hard_col" in text and objs[owner]["body"] == -1:
                fam, loc, sid = "extra_search", where(owner), f"H:{n}"
            else:
                locked = any(i.name in ("if_egal", "if_different") and "in_hand" in L.format_instr(i)
                             for i in instrs[:k])
                fam = "locked_container" if locked else "container"
                loc, sid = where(owner), f"C:{owner}"
            prev = next((s for s in slots if s["slot_id"] == sid), None)
            if prev:
                if item not in prev["items"]:
                    prev["items"].append(item)
                continue
            slots.append(dict(base, slot_id=sid, family=fam, location=loc, source_obj=owner, items=[item]))

    # Direct pickups (OBJETS flags) and the independent cross-check.
    for i, o in enumerate(objs):
        if o["flags"] & AF_FOUNDABLE:
            slots.append({"slot_id": f"P:{i}", "family": "direct_pickup", "location": where(i),
                          "source_obj": i, "items": [i], "life": None, "at": None,
                          "instruction": f"OBJETS flags {o['flags']:#x}", "owners": [], "owner_roles": []})

    # Per-slot details: item operand sites (what a shuffle retargets) and local requirements.
    for s in slots:
        if s["life"] is None:
            for it in s["items"]:
                s.setdefault("item_sites", {})[str(it)] = []
            s["local_requirements"] = []
            s["names"] = {str(it): names.get(it, "") for it in s["items"]}
            continue
        instrs = lives[s["life"]]
        s["item_sites"] = {str(it): item_sites(instrs, it) for it in s["items"]}
        for extra in s.get("also", []):       # the same slot in another LIFE (knight 131/132)
            for it in s["items"]:
                s["item_sites"][str(it)] += [dict(x, life=extra["life"]) for x in item_sites(lives[extra["life"]], it)]
        k = next(i for i, x in enumerate(instrs) if x.offset == s["at"])
        s["local_requirements"] = conditions_before(instrs, k)
        s["names"] = {str(it): names.get(it, "") for it in s["items"]}

    # Optional empty zones: type-9 "message" zones, with the sharing check.
    zrows = list(csv.DictReader(open(RUN / "Tools" / "type9_zone_rewards.csv", encoding="utf-8")))
    notes = {r["zone_id"]: r["description"] for r in
             csv.DictReader(open(REFS / "AITD_zones.csv", encoding="utf-8", errors="replace"))}
    NOTHING = {'"nothing_important!"', '"nothing_important_in_this_bookcase!"'}
    EXCLUDE_WORDS = ("cannot be used", "can't give", "don't allow", "prevent", "kills you",
                     "must confirm", "no randomized")
    # hard_col parameters handled by the extra controllers (F2:R0 LIFE 117: parameter 6)
    extra_params = set()
    for s in slots:
        if s["family"] == "extra_search" and s["location"]:
            for ins in lives[s["life"]]:
                f = L.format_instr(ins)
                if f.startswith("if_egal obj_1.hard_col #"):
                    extra_params.add((s["location"]["floor"], s["location"]["room"], ins.args[1].value))

    def zone_reason(r):
        note = notes.get(r["zone_id"], "").lower()
        fl, rm = (int(x[1:]) for x in r["zone_id"].split(":")[:2])
        if r["messages"] not in NOTHING:
            return f"message {r['messages'] or 'none'}"
        if any(w in note for w in EXCLUDE_WORDS):
            return "excluded by user note"
        if (fl, rm, int(r["parameter"])) in extra_params:
            return "parameter also handled by an extra controller (item slot)"
        return ""
    group = defaultdict(list)
    for r in zrows:
        group[(r["controller_life"], r["parameter"])].append(r)
    empty = []
    for r in zrows:
        if r["mechanism"] != "message":
            continue
        own = zone_reason(r)
        mates = [m for m in group[(r["controller_life"], r["parameter"])] if m is not r]
        bad = [m["zone_id"] for m in mates if m["mechanism"] != "message" or zone_reason(m)]
        reason = own or (f"parameter shared with {', '.join(bad)}" if bad else "")
        empty.append({"zone_id": r["zone_id"], "parameter": int(r["parameter"]),
                      "controller_life": int(r["controller_life"]) if r["controller_life"] else None,
                      "shares_parameter_with": [m["zone_id"] for m in mates],
                      "messages": r["messages"], "usable": not reason, "reason": reason,
                      "user_note": notes.get(r["zone_id"], "")})

    # Cross-checks.
    problems = []
    every_found = [(n, i.offset, i.args[0]) for n, ins in enumerate(lives) for i in ins if i.name == "found"]
    in_slots = {(s["life"], it) for s in slots for it in s["items"]} | \
               {(r["life"], r["item"]) for r in returns}
    for n, off, item in every_found:
        if not any(a <= off < b for a, b in covered.get(n, [])) and (n, item) not in in_slots:
            problems.append(f"found {item} at LIFE {n} @{off} not catalogued")
    ev = {int(r["object_id"]): r for r in
          csv.DictReader(open(RUN / "ObjectVars" / "output" / "item_evidence.csv", encoding="utf-8"))}
    for n, off, item in every_found:
        scripts = {int(x) for x in ev.get(item, {}).get("explicit_found_scripts", "").replace("|", ";").split(";") if x}
        if n not in scripts:
            problems.append(f"found {item} at LIFE {n}: not in item_evidence explicit_found_scripts {sorted(scripts)}")
    for s in slots:
        if s["family"] == "direct_pickup":
            fl = ev.get(s["source_obj"], {}).get("decoded_flags", "")
            if "FOUNDABLE" not in fl.upper() and "0x80" not in fl and "128" not in fl:
                problems.append(f"{s['slot_id']}: item_evidence decoded_flags '{fl}' lacks FOUNDABLE")
        if s["family"] == "unclassified_put_at":
            problems.append(f"{s['slot_id']}: unclassified put_at")

    # Items with no acquisition anywhere.
    acquired = {it for s in slots for it in s["items"]} | {i["obj"] for s in part1 for i in s["items"]}
    items = [i for i, o in enumerate(objs) if o["found_name"] != -1 and o["found_life"] != -1]
    never = [i for i in items if i not in acquired]

    result = {"source": "Generated/Patcher/slot_catalog2.py", "slots": slots,
              "item_use_placements": uses, "item_returns": returns,
              "optional_empty_zones": empty, "items_without_acquisition": never,
              "cross_check_problems": problems}
    (OUT / "acquisition_slots.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    with open(OUT / "acquisition_slots.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slot_id", "family", "floor", "room", "life", "at", "items", "local_requirements"])
        for s in slots:
            loc = s["location"] or {}
            w.writerow([s["slot_id"], s["family"], loc.get("floor", ""), loc.get("room", ""),
                        s["life"] if s["life"] is not None else "", s["at"] if s["at"] is not None else "",
                        " ".join(f"{i}:{names.get(i, '')}" for i in s["items"]),
                        " | ".join(s["local_requirements"])])
    fam = defaultdict(int)
    for s in slots:
        fam[s["family"]] += 1
    print(f"{len(slots)} slots {dict(fam)}; {len(uses)} item-use placements; {len(returns)} returns; "
          f"{len(empty)} empty zones ({sum(e['usable'] for e in empty)} usable); "
          f"{len(never)} items without acquisition; cross-check problems: {len(problems)}")
    for p in problems:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
