"""Batch test of the generator fill (no files written).

  python batch.py --seeds 500 [--report batch_report.json]

For every seed: run the same fill as generate.py, check the result with an
independent full sweep, and collect statistics:
  - failures (no valid placement within the attempt limit) and retries;
  - spheres per seed (how long the playthrough chain is);
  - per progression item: how often it lands in each slot (bias check), and
    how often it lands in its vanilla slot;
  - per slot: how often it receives a progression item.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as G   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--attempts", type=int, default=200)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--enemy-drops", action="store_true")
    ap.add_argument("--drop-chance", type=float, default=25.0)
    ap.add_argument("--extra-spots", type=int, default=0)
    a = ap.parse_args()

    world = G.C.load_world()
    nodes, edges, wslots, events, man = world
    slots = G.load_slots()
    objs = G.O.load(G.SRC / "OBJETS.ITD")
    prog = G.progression_items(man, wslots)
    has_body = lambda i: objs[i]["body"] != -1
    vanilla_slot = {i: s["id"] for s in slots for i in s["items"]}
    pool = [i for x in slots for i in x["items"]]
    base_slots = slots
    van_lives = [G.L.decode(e.data) for e in G.read_pak(G.SRC / "LISTLIFE.PAK").entries]
    omitted_count = Counter()
    pool_prog = sorted(prog & set(vanilla_slot))

    fails, retries, sphere_counts = [], Counter(), Counter()
    where = defaultdict(Counter)
    slot_prog = Counter()
    why_retry = Counter()
    for seed in range(a.seeds):
        placement = None
        slots = base_slots + (G.enemy_drop_slots(man, random.Random(f"{seed}:drops"), a.drop_chance)
                              if a.enemy_drops else [])
        wslots_seed = list(wslots)
        if a.extra_spots:
            room = len(pool) - sum(x["min"] for x in slots)
            extra = G.extra_spot_slots(random.Random(f"{seed}:spots"), max(0, min(a.extra_spots, room)), van_lives)
            slots = slots + extra
            wslots_seed += [{"id": x["id"], "region": x["region"], "items": [], "local": [],
                             "requires": "true", "expr": G.C.Expr("true")} for x in extra]
        world = (nodes, edges, wslots_seed, events, man)
        for attempt in range(a.attempts):
            rng = random.Random(f"{seed}:{attempt}")
            placement, omitted, why = G.fill(rng, slots, prog, has_body, world, pool)
            if placement is None:
                why_retry[why.split(" for item")[0]] += 1
                continue
            ok, st, spheres, got = G.C.sweep(nodes, edges, wslots_seed, events, man, placement)
            if ok:
                break
            why_retry["final check failed"] += 1
            placement = None
        if placement is None:
            fails.append(seed)
            continue
        retries[attempt] += 1
        omitted_count[len(omitted)] += 1
        sphere_counts[len(spheres)] += 1
        for sid, items in placement.items():
            for i in items:
                if i is None:
                    continue
                if i in prog:
                    where[i][sid] += 1
                    slot_prog[sid] += 1

    ok = a.seeds - len(fails)
    print(f"{a.seeds} seeds: {ok} valid, {len(fails)} failed {fails[:10]}")
    print(f"attempts needed: {dict(sorted(retries.items()))}; retry reasons: {dict(why_retry)}")
    print(f"spheres per seed: {dict(sorted(sphere_counts.items()))}")
    print(f"items left out per seed: {dict(sorted(omitted_count.items()))}")
    print(f"\nprogression items ({len(pool_prog)}): share in vanilla slot, distinct slots used, top slot share")
    for i in pool_prog:
        c = where[i]
        top, n = c.most_common(1)[0] if c else ("-", 0)
        print(f"  {i:>4}: vanilla {c[vanilla_slot[i]] / max(ok, 1):5.1%}  slots {len(c):>2}  "
              f"top {top} {n / max(ok, 1):5.1%}")
    print(f"\nslots never receiving progression: {[s['id'] for s in slots if not slot_prog[s['id']]]}")
    if a.report:
        a.report.write_text(json.dumps({"seeds": a.seeds, "failed": fails, "attempts": retries,
                                        "retry_reasons": why_retry, "spheres": sphere_counts,
                                        "item_slots": {str(i): dict(where[i]) for i in pool_prog},
                                        "slot_progression": dict(slot_prog)}, indent=1), encoding="utf-8")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
