"""Seed checker (work-order step 3): reachability sweep over the region graph.

  python logic_check.py                    vanilla placement
  python logic_check.py --placement P.json a seed: {"slot_id": [item, ...], ...}
                                           (slots not listed keep their vanilla items)

Graph = region_graph_auto.json (rooms, room/floor edges) + logic_manual.json
(virtual nodes, reroutes, extra edges, edge requirements, events, slot rules).
Slots = catalog/search_slots.json (part 1) + catalog/acquisition_slots.json
(part 2). A slot's region is its room (or a slot_region override); its local
requirement is every `in_hand #N` in its vanilla conditions (-> item:N) plus
any slot_rules entry. Inventory containers have no region (only their item).

The sweep starts in the start region with the start items and repeats until
nothing changes: walk every edge whose requirement holds, take every item of
every reachable slot whose requirement holds, raise every event whose
requirement holds. Each round is a "sphere" (the spoiler order). A seed passes
when the goal holds at the end.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAT = HERE.parent / "Patcher" / "catalog"


class Expr:
    """Tiny parser for requirement expressions."""
    TOKEN = re.compile(r"\s*(item:\d+|event:\w+|reach:[\w/]+|true|never|[()&|])")

    def __init__(self, text: str):
        self.text = text
        self.tokens = [m.group(1) for m in self.TOKEN.finditer(text)]
        if "".join(self.tokens) != re.sub(r"\s+", "", text):
            raise ValueError(f"bad requirement: {text}")
        self.pos = 0
        self.tree = self.parse_or()

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == "|":
            self.pos += 1
            left = ("or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_atom()
        while self.peek() == "&":
            self.pos += 1
            left = ("and", left, self.parse_atom())
        return left

    def parse_atom(self):
        t = self.peek()
        self.pos += 1
        if t == "(":
            e = self.parse_or()
            self.pos += 1
            return e
        return ("atom", t)

    def ok(self, st) -> bool:
        def ev(n):
            if n[0] == "and":
                return ev(n[1]) and ev(n[2])
            if n[0] == "or":
                return ev(n[1]) or ev(n[2])
            t = n[1]
            if t == "true":
                return True
            if t == "never":
                return False
            kind, val = t.split(":", 1)
            if kind == "item":
                return int(val) in st["items"]
            if kind == "event":
                return val in st["events"]
            return val in st["reached"]
        return ev(self.tree)


def load_world():
    auto = json.loads((HERE / "region_graph_auto.json").read_text(encoding="utf-8"))
    man = json.loads((HERE / "logic_manual.json").read_text(encoding="utf-8"))
    nodes = list(auto["nodes"]) + list(man.get("virtual_nodes", {}))
    edges = [dict(e) for e in auto["edges"] if e.get("to")]
    for r in man.get("reroute", []):
        for e in edges:
            if e["zone"] == r["zone"]:
                e.update({k: r[k] for k in ("from", "to") if k in r})
    for e in edges:
        e["requires"] = "true"
    for x in man.get("extra_edges", []):
        edges.append({"from": x["from"], "to": x["to"], "zone": "manual", "kind": "manual",
                      "requires": x["requires"]})
    for rule in man.get("edge_rules", []):
        hit = [e for e in edges if e["from"] == rule["from"] and e["to"] == rule["to"]]
        if not hit:
            raise SystemExit(f"edge rule matches no edge: {rule['from']} -> {rule['to']}")
        for e in hit:
            e["requires"] = rule["requires"]
    dark = man.get("dark_rooms")
    if dark:                                  # entering a dark room needs light
        for e in edges:
            if e["to"] in dark["rooms"]:
                e["requires"] = dark["requires"] if e["requires"] == "true"                     else f"({e['requires']}) & {dark['requires']}"
    for e in edges:
        e["expr"] = Expr(e["requires"])

    slots = []
    for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]:
        fl, rm = s["slot_id"].split(":")[:2]
        reqs = sorted({int(m) for c in s["conditions"] for m in re.findall(r"in_hand #(\d+)", c)})
        slots.append({"id": s["slot_id"], "region": f"{fl[1:]}/{rm[1:]}",
                      "items": [i["obj"] for i in s["items"]], "local": [f"item:{n}" for n in reqs]})
    part2 = json.loads((CAT / "acquisition_slots.json").read_text(encoding="utf-8"))
    for s in part2["slots"]:
        loc = s.get("location")
        reqs = sorted({int(m) for c in s.get("local_requirements", []) for m in re.findall(r"in_hand #(\d+)", c)})
        slots.append({"id": s["slot_id"], "region": f"{loc['floor']}/{loc['room']}" if loc else None,
                      "items": list(s["items"]), "local": [f"item:{n}" for n in reqs],
                      "start": s["family"] == "starting_inventory"})
    for sid, e in man.get("enemy_drop_slots", {}).items():
        if not sid.startswith("_"):           # optional; empty unless a placement fills them
            slots.append({"id": sid, "region": e["region"], "items": [], "local": [],
                          "enemy_requires": e["requires"]})
    for s in slots:
        if s["id"] in man.get("slot_region", {}):
            s["region"] = man["slot_region"][s["id"]]
        extra = man.get("slot_rules", {}).get(s["id"], {}).get("requires") or s.get("enemy_requires")
        s["requires"] = " & ".join(s["local"] + ([f"({extra})"] if extra else [])) or "true"
        s["expr"] = Expr(s["requires"])
    events = {k: Expr(v["requires"]) for k, v in man["events"].items()}
    return nodes, edges, slots, events, man


def sweep(nodes, edges, slots, events, man, placement=None, assumed=()):
    """assumed: items treated as already owned (assumed fill). Placement lists
    may contain None for positions not filled yet."""
    st = {"items": set(man["start"]["items"]) | set(assumed), "events": set(),
          "reached": {man["start"]["region"]}}
    got = set()
    spheres = []
    goal = Expr(man["goal"])
    while True:
        new_nodes, new_slots, new_events = [], [], []
        changed = True
        while changed:                       # walk to the closure first
            changed = False
            for e in edges:
                if e["from"] in st["reached"] and e["to"] not in st["reached"] and e["expr"].ok(st):
                    st["reached"].add(e["to"])
                    new_nodes.append(e["to"])
                    changed = True
            for name, ex in events.items():
                if name not in st["events"] and ex.ok(st):
                    st["events"].add(name)
                    new_events.append(name)
                    changed = True
        for s in slots:
            if s["id"] in got or s.get("start"):
                continue
            if (s["region"] is None or s["region"] in st["reached"]) and s["expr"].ok(st):
                got.add(s["id"])
                items = placement.get(s["id"], s["items"]) if placement else s["items"]
                new_slots.append((s["id"], [i for i in items if i is not None]))
        if not (new_nodes or new_slots or new_events):
            break
        for _, items in new_slots:
            st["items"].update(items)
        spheres.append({"regions": new_nodes, "events": new_events,
                        "slots": [{"slot": sid, "items": it} for sid, it in new_slots]})
    return goal.ok(st), st, spheres, got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--placement", type=Path)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    nodes, edges, slots, events, man = load_world()
    placement = json.loads(a.placement.read_text(encoding="utf-8")) if a.placement else None
    if placement:
        placement = {k: v for k, v in placement.items() if not k.startswith("_")}
        known = {x["id"] for x in slots}
        empty = {z["zone_id"]: z for z in json.loads((CAT / "acquisition_slots.json").read_text(
            encoding="utf-8"))["optional_empty_zones"]}
        for sid in placement:
            if sid in known:
                continue
            if sid not in empty or not empty[sid]["usable"]:
                raise SystemExit(f"placement names an unknown or unusable slot: {sid}")
            fl, rm = sid.split(":")[:2]       # a "Many Search Places" zone (PoC A pattern)
            slots.append({"id": sid, "region": f"{fl[1:]}/{rm[1:]}", "items": [], "local": [],
                          "requires": "true", "expr": Expr("true")})
    ok, st, spheres, got = sweep(nodes, edges, slots, events, man, placement)
    for k, sp in enumerate(spheres):
        parts = []
        if sp["regions"]:
            parts.append("rooms " + " ".join(sp["regions"]))
        if sp["events"]:
            parts.append("events " + " ".join(sp["events"]))
        if sp["slots"]:
            parts.append("slots " + " ".join(f"{x['slot']}{x['items']}" for x in sp["slots"]))
        print(f"sphere {k}: " + "; ".join(parts))
    unreached = [n for n in nodes if n not in st["reached"]]
    missed = [s["id"] for s in slots if s["id"] not in got and not s.get("start")]
    print(f"\nGOAL {'REACHED' if ok else 'NOT REACHED'}; rooms {len(st['reached'])}/{len(nodes)}; "
          f"slots {len(got)}/{sum(not s.get('start') for s in slots)}; events {sorted(st['events'])}")
    print("unreached rooms:", unreached)
    print("unobtained slots:", missed)
    if a.report:
        a.report.write_text(json.dumps({"goal": ok, "spheres": spheres, "unreached": unreached,
                                        "unobtained": missed}, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
