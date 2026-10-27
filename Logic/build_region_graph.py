"""Region graph, automatic layer (work-order step 3).

  python build_region_graph.py   -> region_graph_auto.json, region_graph_review.csv

Nodes are rooms (floor:room) from the ETAGE room data
(Generated/ResearchRun/TrackRooms/datasets/rooms.json).

Edges, all extracted from game data:
  room     type-0 scene zones (room change inside a floor; the engine moves
           any actor whose point enters the zone to the zone's room;
           TrackRooms/datasets/room_transitions.csv)
  floor    type-10 scene zones: the engine switches the player to its floor
           LIFE (OBJ 1 floor_life = LIFE 550) with HARD_DEC = zone parameter.
           LIFE 550 `switch hard_dec` case P either runs `changeroom` itself
           and/or starts a stairs TRACK (`trackmode 3 T`); the `switch
           num_track` case T then runs `changeroom` (possibly per track
           `mark`). The destination is the last player changeroom on that path.

Doors on edges: every object whose LIFE (any LIFE it can run) shows
"It's locked!" (message 101) or tests `in_hand` before opening is a gating
candidate. It is attached to the room's edge zone nearest to it, with the
requirement read from its scripts (in_hand items, var tests). These
attachments are INFERRED and listed for review; the hand-written layer
(logic_manual.json) confirms or overrides them.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "Patcher"))
import aitd_life as L          # noqa: E402
import aitd_objets as O        # noqa: E402
from aitd_pak import read_pak  # noqa: E402

RUN = HERE.parent / "ResearchRun"
DATA = RUN / "TrackRooms" / "datasets"
SRC = RUN / "SourceCopy"
FLOOR_LIFE = 550


def node(f, r):
    return f"{f}/{r}"


def case_blocks(instrs, switch_text):
    """{case value: [instructions]} of the first `switch` whose text matches."""
    idx = L.label_index(instrs)
    out = {}
    k0 = next(k for k, i in enumerate(instrs) if L.format_instr(i) == switch_text)
    k = k0 + 1
    while k < len(instrs) and instrs[k].op in (L.OP_CASE, L.OP_MULTI_CASE):
        ins = instrs[k]
        end = idx[ins.jump().label]
        vals = [ins.args[0]] if ins.op == L.OP_CASE else list(ins.args[0])
        for v in vals:
            out[v] = instrs[k + 1:end]
        k = end
    return out


def player_changerooms(block):
    """(floor, room, x, y, z, guard text) of every player changeroom in a block."""
    out, guard = [], []
    for ins in block:
        t = L.format_instr(ins)
        if ins.name in ("if_egal", "if_different", "switch", "case"):
            guard.append(t)
        if ins.name == "changeroom" and ins.obj is None:
            out.append((*ins.args[:5], "; ".join(guard[-2:])))
    return out


def main() -> int:
    rooms = json.loads((DATA / "rooms.json").read_text(encoding="utf-8"))
    nodes = sorted({node(r["floor"], r["room"]) for r in rooms},
                   key=lambda s: tuple(map(int, s.split("/"))))
    zones = list(csv.DictReader(open(DATA / "room_zones.csv", encoding="utf-8")))
    lives = [L.decode(e.data) for e in read_pak(SRC / "LISTLIFE.PAK").entries]
    objs = O.load(SRC / "OBJETS.ITD")

    edges = []
    # Room edges (type-0 scene zones).
    for z in zones:
        if z["kind"] == "scene" and z["type"] == "0":
            edges.append({"from": node(z["floor"], z["room"]), "to": node(z["floor"], z["parameter"]),
                          "kind": "room", "zone": f"F{z['floor']}:R{z['room']}:SZ{z['zone_id']}",
                          "evidence": "type-0 scene zone"})

    # Floor edges (type-10 scene zones -> LIFE 550).
    l550 = lives[FLOOR_LIFE]
    by_dec = case_blocks(l550, "switch hard_dec")
    by_track = case_blocks(l550, "switch num_track")
    for z in zones:
        if not (z["kind"] == "scene" and z["type"] == "10"):
            continue
        p = int(z["parameter"])
        block = by_dec.get(p, [])
        direct = player_changerooms(block)
        tracks = [i.args[1] for i in block if i.name == "trackmode" and i.args[0] == 3]
        via = player_changerooms(by_track.get(tracks[0], [])) if tracks else []
        dests = via or direct
        cond = [L.format_instr(i) for i in block if i.name in ("if_egal", "if_different")]
        base = {"from": node(z["floor"], z["room"]), "kind": "floor",
                "zone": f"F{z['floor']}:R{z['room']}:SZ{z['zone_id']}", "parameter": p,
                "track": tracks[0] if tracks else None, "conditions": cond,
                "evidence": f"type-10 zone -> LIFE 550 hard_dec {p}"
                            + (f" -> track {tracks[0]}" if tracks else "")}
        if not dests:
            edges.append(dict(base, to=None, note="no player changeroom on this path"))
        for d in {(d[0], d[1]): d for d in dests}.values():
            edges.append(dict(base, to=node(d[0], d[1]), arrival=list(d[2:5]),
                              guard=d[5] or None, ambiguous=len({(x[0], x[1]) for x in dests}) > 1))

    # Gating candidates: objects whose LIFE shows message 101 or tests in_hand.
    owners = defaultdict(set)
    work = [(o["life"], i) for i, o in enumerate(objs) if o["life"] != -1]
    seen = set()
    while work:
        life, obj = work.pop()
        if (life, obj) in seen or not 0 <= life < len(lives):
            continue
        seen.add((life, obj))
        owners[obj].add(life)
        for ins in lives[life]:
            if ins.name == "life" and ins.obj is None:
                work.append((ins.args[0], obj))
            elif ins.name == "life" and ins.obj is not None:
                work.append((ins.args[0], ins.obj))
    gates = []
    for obj, ls in owners.items():
        o = objs[obj]
        if o["stage"] == -1:
            continue
        texts = [(n, [L.format_instr(i) for i in lives[n]]) for n in sorted(ls)]
        if not any("message 101" in t or "in_hand #" in t for _, tl in texts for t in tl):
            continue
        items = sorted({int(t.split("in_hand #")[1].split()[0]) for _, tl in texts for t in tl
                        if "in_hand #" in t and t.split("in_hand #")[1].split()[0].lstrip("-").isdigit()})
        varz = sorted({t.split("var_")[1].split()[0] for _, tl in texts for t in tl
                       if t.startswith(("if_egal var_", "if_different var_"))}, key=int)
        f, r = o["stage"], o["room"]
        cand = [z for z in zones if z["kind"] == "scene" and z["type"] in ("0", "10")
                and int(z["floor"]) == f and int(z["room"]) == r]

        def dist(z):
            cx = (int(z["x1"]) + int(z["x2"])) / 2
            cz = (int(z["z1"]) + int(z["z2"])) / 2
            return ((cx - o["x"]) ** 2 + (cz - o["z"]) ** 2) ** 0.5
        cand.sort(key=dist)
        near = cand[0] if cand else None
        gates.append({"obj": obj, "room": node(f, r), "pos": [o["x"], o["y"], o["z"]], "body": o["body"],
                      "lives": sorted(ls), "in_hand_items": items, "var_tests": varz,
                      "nearest_edge_zone": f"F{f}:R{r}:SZ{near['zone_id']}" if near else None,
                      "nearest_edge_to": (node(f, near["parameter"]) if near and near["type"] == "0"
                                          else f"floor zone p{near['parameter']}" if near else None),
                      "distance": round(dist(near)) if near else None,
                      "status": "inferred"})

    out = {"source": "Generated/Logic/build_region_graph.py", "nodes": nodes, "edges": edges,
           "gate_candidates": sorted(gates, key=lambda g: g["obj"])}
    (HERE / "region_graph_auto.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    with open(HERE / "region_graph_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "from", "to", "zone", "detail"])
        for e in edges:
            w.writerow([e["kind"], e["from"], e.get("to"), e["zone"], e["evidence"] +
                        (f"; guard {e['guard']}" if e.get("guard") else "") +
                        ("; AMBIGUOUS" if e.get("ambiguous") else "")])
        for g in out["gate_candidates"]:
            w.writerow(["gate?", g["room"], g["nearest_edge_to"], g["nearest_edge_zone"],
                        f"OBJ {g['obj']} lives {g['lives']} in_hand {g['in_hand_items']} vars {g['var_tests']} "
                        f"dist {g['distance']}"])
    fe = [e for e in edges if e["kind"] == "floor"]
    print(f"{len(nodes)} rooms, {len(edges) - len(fe)} room edges, {len(fe)} floor edges, "
          f"{len(gates)} gate candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
