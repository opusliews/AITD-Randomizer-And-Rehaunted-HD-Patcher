"""Location-slot catalog, part 1: search and contact slots of type-9 zones.

  python slot_catalog.py            -> catalog/search_slots.json, catalog/search_slots.csv

A slot is one hard_col branch of a room controller LIFE script: the code run
when the player touches type-9 hard-collision zones with a given parameter.
For every slot that awards items (`found X`), the catalog records:

- the zones (all type-9 zones of the room with a matching parameter) and the
  controller LIFE, case value(s) and byte range of the branch;
- the mechanism: "search" (a found runs only after the search-animation test
  `if_egal obj_1.anim #2`) or "contact" (a found runs before any such test);
- the awarded items in award order, and for each item every operand site in
  the branch that names it: `found X`, `object(X)` / `isfound(#X)` / `thrown(X)`
  reads and instructions aimed at X (`obj_X.found_weight ...`). These are the
  words a shuffle retargets;
- constants equal to an awarded item's number that are NOT item references
  (e.g. `in_hand #53` as a requirement), for review; they are never patched;
- the branch's other conditions (posrel, in_hand, vars), as text.

Branches are found exactly as the room scripts dispatch: `switch obj_1.hard_col`
followed by case / multi_case (branch = up to the case's false target), and
`if_egal obj_1.hard_col #N` (branch = up to its false target).
Cross-checked against Generated/ResearchRun/Tools/type9_zone_rewards.csv
(independent LifeDISA-text classifier).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
from aitd_pak import read_pak  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "ResearchRun"
OUT = HERE / "catalog"

HARD_COL = L.FIELD_BY_NAME["hard_col"]
ANIM = L.FIELD_BY_NAME["anim"]
OP_FOUND = L.OPCODE_BY_NAME["found"]
OP_IF_EGAL = L.OPCODE_BY_NAME["if_egal"]
ITEM_FIELDS = {"object", "isfound", "thrown"}


def is_player_field(e, code) -> bool:
    return isinstance(e, L.Expr) and e.kind == "field" and e.value == code and e.obj == 1


def branches(instrs: list[L.Instr]):
    """Yield (params, first index, end index) of every hard_col branch."""
    index = L.label_index(instrs)
    in_switch = False
    for k, ins in enumerate(instrs):
        if ins.op == L.OP_SWITCH:
            in_switch = is_player_field(ins.args[0], HARD_COL)
            continue
        if in_switch and ins.op in (L.OP_CASE, L.OP_MULTI_CASE):
            params = [ins.args[0]] if ins.op == L.OP_CASE else list(ins.args[0])
            yield params, k + 1, index[ins.jump().label]
        elif ins.op == OP_IF_EGAL and is_player_field(ins.args[0], HARD_COL) \
                and ins.args[1].kind == "const":
            yield [ins.args[1].value], k + 1, index[ins.jump().label]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    lives = [L.decode(e.data) for e in read_pak(RUN / "SourceCopy" / "LISTLIFE.PAK").entries]
    names = {int(r["object_id"]): r["found_name_text"] for r in
             csv.DictReader(open(RUN / "ObjectVars" / "output" / "objects.csv", encoding="utf-8"))}
    # (life, parameter) -> zones, from the independent classifier (room association).
    zone_rows = list(csv.DictReader(open(RUN / "Tools" / "type9_zone_rewards.csv", encoding="utf-8")))
    zones_of = defaultdict(list)
    for r in zone_rows:
        if r["controller_life"]:
            zones_of[(int(r["controller_life"]), int(r["parameter"]))].append(r)

    slots = []
    for life in sorted({k[0] for k in zones_of}):
        instrs = lives[life]
        for params, first, end in branches(instrs):
            zones = [z for p in params for z in zones_of.get((life, p), [])]
            if not zones:
                continue
            block = instrs[first:end]
            founds = [i for i in block if i.op == OP_FOUND]
            if not founds:
                continue
            items = list(dict.fromkeys(i.args[0] for i in founds))
            first_found = instrs.index(founds[0])
            search_test = any(i.op == OP_IF_EGAL and is_player_field(i.args[0], ANIM)
                              and i.args[1].kind == "const" and i.args[1].value == 2
                              for i in instrs[first:first_found])
            sites = {x: [] for x in items}
            constants = []
            conditions = []
            for ins in block:
                for s in L.operand_sites(ins):
                    if s.value not in sites:
                        continue
                    ref = {"offset": s.offset, "kind": s.kind, "detail": s.detail,
                           "instruction": L.format_instr(ins), "at": ins.offset}
                    if (s.kind == "word" and ins.op == OP_FOUND) or s.kind == "target" \
                            or (s.kind == "expr_arg" and s.detail in ITEM_FIELDS) \
                            or (s.kind == "const" and s.detail == "isfound"):
                        sites[s.value].append(ref)
                    else:
                        constants.append(ref)
                if ins.jump() and ins.op not in (L.OP_GOTO, L.OP_CASE, L.OP_MULTI_CASE):
                    conditions.append(f"@{ins.offset} {L.format_instr(ins)}")
            zone_ids = sorted({z["zone_id"] for z in zones})
            slots.append({
                "slot_id": "+".join(zone_ids),
                "zones": zone_ids,
                "life": life, "case_values": params,
                "branch_bytes": [instrs[first].offset, instrs[end].offset if end < len(instrs) else None],
                "mechanism": "search" if search_test else "contact",
                "classifier_mechanism": sorted({z["mechanism"] for z in zones}),
                "items": [{"obj": x, "name": names.get(x, ""), "sites": sites[x]} for x in items],
                "non_item_constants": constants,
                "conditions": conditions,
            })

    # Cross-check against the LifeDISA-text classifier.
    problems = []
    for s in slots:
        if [s["mechanism"]] != s["classifier_mechanism"]:
            problems.append(f"{s['slot_id']}: mechanism {s['mechanism']} vs classifier {s['classifier_mechanism']}")
        for z in s["zones"]:
            row = next(r for r in zone_rows if r["zone_id"] == z)
            theirs = {int(t.rsplit("_", 1)[1]) for t in row["found_objects"].split(";") if t}
            if theirs != {i["obj"] for i in s["items"]}:
                problems.append(f"{z}: items {sorted(i['obj'] for i in s['items'])} vs classifier {sorted(theirs)}")
    covered = {z for s in slots for z in s["zones"]}
    for r in zone_rows:
        if r["mechanism"] in ("search", "contact") and r["zone_id"] not in covered:
            problems.append(f"{r['zone_id']}: classifier says {r['mechanism']}, not in catalog")

    (OUT / "search_slots.json").write_text(json.dumps(
        {"source": "Generated/Patcher/slot_catalog.py", "slots": slots, "cross_check_problems": problems},
        indent=1), encoding="utf-8")
    with open(OUT / "search_slots.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slot_id", "mechanism", "life", "case_values", "items", "item_sites", "non_item_constants"])
        for s in slots:
            w.writerow([s["slot_id"], s["mechanism"], s["life"], " ".join(map(str, s["case_values"])),
                        " ".join(f"{i['obj']}:{i['name']}" for i in s["items"]),
                        sum(len(i["sites"]) for i in s["items"]), len(s["non_item_constants"])])
    by_mech = defaultdict(int)
    for s in slots:
        by_mech[s["mechanism"]] += 1
    print(f"{len(slots)} item slots ({dict(by_mech)}), "
          f"{sum(len(s['items']) for s in slots)} item positions; cross-check problems: {len(problems)}")
    for p in problems:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
