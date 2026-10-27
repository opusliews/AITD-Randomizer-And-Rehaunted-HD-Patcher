"""Spoiler walkthrough: short, direct instructions to beat a seed (user request, 2026-10-15).

The walkthrough is a simulated playthrough over the same logic as the checker
(Generated/Logic/logic_check.py):

  * an action is a location (slot) to take items from, or a logic event (light
    the lamp, kill the knight, final fight...). It is allowed only when the
    logic allows it with what the plan holds at that point, and it is reached
    by the shortest path whose doors the plan can already open (edge
    requirements; reach:X uses the rooms visited so far, conservatively);
  * distance = rooms crossed, a floor change (stairs, ladders...) counts 3;
  * 1) greedy: always the nearest allowed action that brings a progression item
    (any item named in a requirement) or an event, until the goal holds;
    2) prune: drop the step whose removal saves the most distance while the
    rest still replays and reaches the goal; repeat;
    3) re-plan nearest-first over the kept steps only, prune again, until
    stable; keep the shortest plan. Alternatives (gem OR hook) are settled by
    the pruning: the farther one is dropped first.

Monsters and real walking distances are not modelled. The final plan is
replayed step by step (every step legal when it is taken), so it cannot ask for
something that is not yet possible.
"""
from __future__ import annotations

import heapq
import json
import re
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
FLOOR_COST = 3


def atoms(text: str, kind: str) -> list[str]:
    return re.findall(kind + r":([\w/]+)", text)


class Planner:
    def __init__(self, nodes, edges, slots, events, man, placement):
        self.edges = edges
        self.out = {}
        for e in edges:
            self.out.setdefault(e["from"], []).append(e)
        self.slots = {s["id"]: s for s in slots if not s.get("start")}
        self.events = events
        self.event_text = {k: v["requires"] for k, v in man["events"].items()}
        self.man = man
        self.placement = placement
        texts = [e["requires"] for e in edges] + [s["requires"] for s in slots] + \
            list(self.event_text.values()) + [man["goal"]]
        self.prog = {int(x) for t in texts for x in atoms(t, "item")}
        self.goal_event = atoms(man["goal"], "event")[0]

    def items_of(self, sid):
        s = self.slots[sid]
        return [i for i in self.placement.get(sid, s["items"]) if i is not None]

    # ---- state -----------------------------------------------------------
    def start(self):
        return {"pos": self.man["start"]["region"], "items": set(self.man["start"]["items"]),
                "events": set(), "visited": {self.man["start"]["region"]}, "got": set()}

    def paths(self, st):
        """Dijkstra from st['pos'] over the edges usable now."""
        view = {"items": st["items"], "events": st["events"], "reached": st["visited"]}
        dist, prev = {st["pos"]: 0}, {}
        heap = [(0, st["pos"])]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist[n]:
                continue
            for e in self.out.get(n, ()):
                if not e["expr"].ok(view):
                    continue
                nd = d + (FLOOR_COST if e.get("kind") == "floor" else 1)
                if nd < dist.get(e["to"], 1 << 30):
                    dist[e["to"]], prev[e["to"]] = nd, (n, e)
                    heapq.heappush(heap, (nd, e["to"]))
        return dist, prev

    def options(self, st, dist):
        """Allowed actions now: (key, location)."""
        view = {"items": st["items"], "events": st["events"], "reached": set(dist) | st["visited"]}
        out = []
        for sid, s in self.slots.items():
            if sid in st["got"] or not s["expr"].ok(view):
                continue
            loc = st["pos"] if s["region"] is None else s["region"]
            if loc in dist:
                out.append((("slot", sid), loc))
        for name, ex in self.events.items():
            if name in st["events"] or not ex.ok(view):
                continue
            where = atoms(self.event_text[name], "reach")
            loc = where[0] if where else st["pos"]
            if loc in dist:
                out.append((("event", name), loc))
        return out

    def apply(self, st, key, loc, prev):
        path, n = [], loc
        while n != st["pos"]:
            p, e = prev[n]
            path.append(e)
            n = p
        path.reverse()
        st = {"pos": loc, "items": set(st["items"]), "events": set(st["events"]),
              "visited": st["visited"] | {e["to"] for e in path}, "got": set(st["got"])}
        if key[0] == "slot":
            st["got"].add(key[1])
            st["items"].update(self.items_of(key[1]))
        else:
            st["events"].add(key[1])
        return st, path

    def useful(self, key, st):
        if key[0] == "event":
            return True
        return any(i in self.prog and i not in st["items"] for i in self.items_of(key[1]))

    # ---- planning --------------------------------------------------------
    def greedy(self, targets=None):
        st, plan, cost = self.start(), [], 0
        while self.goal_event not in st["events"]:
            dist, prev = self.paths(st)
            opts = [(dist[loc], key[0] != "event", key, loc) for key, loc in self.options(st, dist)
                    if (key in targets if targets is not None else self.useful(key, st))]
            if not opts:
                return None
            d, _, key, loc = min(opts)
            st, _ = self.apply(st, key, loc, prev)
            plan.append(key)
            cost += d
        return plan, cost

    def replay(self, plan):
        """(cost, steps) if every step is allowed in order and the goal holds, else None."""
        st, cost, steps = self.start(), 0, []
        for key in plan:
            dist, prev = self.paths(st)
            hit = [loc for k, loc in self.options(st, dist) if k == key]
            if not hit:
                return None
            before = st
            st, path = self.apply(st, key, hit[0], prev)
            cost += dist[hit[0]]
            steps.append((key, hit[0], path, before))
        return (cost, steps) if self.goal_event in st["events"] else None

    def prune(self, plan):
        while True:
            base = self.replay(plan)[0]
            best = None
            for i in range(len(plan)):
                r = self.replay(plan[:i] + plan[i + 1:])
                if r is not None and (best is None or base - r[0] > best[0]):
                    best = (base - r[0], i)
            if best is None:
                return plan
            plan = plan[:best[1]] + plan[best[1] + 1:]

    def needed(self, plan):
        """(slot, item) pairs the plan cannot do without: the replay fails without them."""
        out = set()
        for key in plan:
            if key[0] != "slot":
                continue
            sid = key[1]
            for i in self.items_of(sid):
                saved = self.placement.get(sid)
                self.placement[sid] = [x for x in self.items_of(sid) if x != i]
                if self.replay(plan) is None:
                    out.add((sid, i))
                if saved is None:
                    del self.placement[sid]
                else:
                    self.placement[sid] = saved
        return out

    def plan(self):
        g = self.greedy()
        if g is None:
            return None
        best = self.prune(g[0])
        for _ in range(6):
            again = self.greedy(set(best))
            if again is None:
                break
            cand = self.prune(again[0])
            if self.replay(cand)[0] >= self.replay(best)[0]:
                break
            best = cand
        return self.replay(best)


def render(planner, result, names, label, family, special, container_of, useful_words,
           desc_of=lambda sid: None):
    """Markdown lines for the walkthrough section."""
    text = json.loads((GEN / "Logic" / "walkthrough_text.json").read_text(encoding="utf-8"))
    nice = lambda i: names.get(i, f"object {i}")
    cost, steps = result
    needed = planner.needed([k for k, _, _, _ in steps])
    seen_gates = set()
    lines = ["## Walkthrough (shortest route found)", "",
             "Direct instructions to beat this seed, in a short order that respects the logic: each step only "
             "needs what the earlier steps gave you. Distance counts rooms (a floor change counts 3); monsters "
             "are not taken into account. Items in **bold** are needed later; the others come with the same "
             f"location. Total route length: {cost}.", ""]
    n = 0
    last_loc = None
    for key, loc, path, before in steps:
        gates, dark = [], False
        for e in path:
            req = e["requires"]
            dark |= "event:lamp_lit" in req
            used = [nice(int(i)) for i in atoms(req, "item") if int(i) in before["items"]]
            gate = (e["from"], e["to"])
            if used and gate not in seen_gates and (e["to"], e["from"]) not in seen_gates:
                seen_gates.add(gate)
                gates.append(f"{label(e['from'])} → {label(e['to'])}: {', '.join(dict.fromkeys(used))}")
        if dark:
            gates.append("dark rooms, keep the lamp lit")
        if key[0] == "slot":
            sid = key[1]
            s = planner.slots[sid]
            items = planner.items_of(sid)
            shown = ", ".join(f"**{nice(i)}**" if (sid, i) in needed else nice(i) for i in items) or "nothing"
            fam = family.get(sid) or {"P": "direct_pickup", "C": "container"}.get(sid.split(":")[0], "")
            hand = [nice(int(i)) for i in atoms(" & ".join(s["local"]), "item")]
            if s["region"] is None:
                c = container_of.get(sid)
                what = f"Open {nice(c) if c else 'the item'} (in your inventory): {shown}"
            elif sid in special:
                sp = special[sid]
                if sp.startswith("dropped by the "):
                    sp = f"kill the {sp[len('dropped by the '):]}, it drops"
                d = desc_of(sid)
                if d and not sp.startswith("kill the "):
                    sp = f"{d}, {sp}"
                what = f"{sp[0].upper()}{sp[1:]} [{sid}]: {shown}"
            else:
                verb = {"container": "Open the container", "locked_container": "Open the locked container",
                        "extra_spot": "Search the spot", "extra_search": "Search the spot",
                        "direct_pickup": "Pick up from the floor", "world": "Take it"}.get(fam, "Search the spot")
                d = desc_of(sid)
                if d and sid not in family:
                    # a vanilla spot the seed does not shuffle: its item is often picked up by
                    # walking into it (vase, gramophone, notebook...), so no verb
                    spot = f"At the {d} ({sid})"
                elif d:                   # "Search the Bookcase (F0:R0:HC10)"
                    verb = {"container": "Open the", "locked_container": "Open the locked",
                            "direct_pickup": "Pick up from the", "world": "Take from the"}.get(fam, "Search the")
                    spot = f"{verb} {d} ({sid})"
                else:
                    spot = f"{verb} {sid}"
                what = spot + (f" with {', '.join(hand)} in hand" if hand else "") + f": {shown}"
        else:
            what = "**" + text["events"].get(key[1], {}).get("text", key[1]) + "**"
        if loc != last_loc or gates:
            n += 1
            via = f" (on the way: {'; '.join(gates)})" if gates else ""
            lines.append(f"{n}. **{label(loc)}**{via}")
            last_loc = loc
        lines.append(f"   - {what}")
    # useful extras next to the stops
    stops = {loc for _, loc, _, _ in steps}
    planned = {k[1] for k, _, _, _ in steps if k[0] == "slot"}
    extra = []
    for sid, s in planner.slots.items():
        if sid in planned or s["region"] not in stops or not s["expr"].text in ("true",):
            continue
        good = [nice(i) for i in planner.items_of(sid)
                if any(w in nice(i).split(' ("')[0].lower() for w in useful_words)]
        if good:
            extra.append(f"- {label(s['region'])}, {sid}: {', '.join(good)}")
    if extra:
        lines += ["", "Useful on the way (weapons, ammunition, healing in rooms the route already visits; "
                  "not needed to win):", ""] + sorted(extra)
    return lines
