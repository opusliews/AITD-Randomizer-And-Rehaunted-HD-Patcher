"""Assumption register (2026-10-28): every edge of the base logic whose way back is missing or
needs something different (the sweep is monotonic, so a one-way passage could trap a player).
Output: one_way_edges.txt."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import logic_check as C
nodes, edges, slots, events, man = C.load_world()
by = {}
for e in edges:
    by.setdefault((e["from"], e["to"]), set()).add(e["requires"])
out = []
for (a, b), reqs in sorted(by.items()):
    back = by.get((b, a))
    if back != reqs:
        out.append(f"{a:5} -> {b:5} {sorted(reqs)}   back: {sorted(back) if back else 'NONE'}")
(HERE / "one_way_edges.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))

# the bridge (5/0 -> 5/1) is the only edge with no way back: can a player with NO items and no
# events walk home from 5/1? (doors in the caves are not lockable by More Locked Doors)
st = {"items": set(), "events": set(), "reached": {"5/1"}}
changed = True
while changed:
    changed = False
    for e in edges:
        if e["from"] in st["reached"] and e["to"] not in st["reached"] and e["expr"].ok(st):
            st["reached"].add(e["to"]); changed = True
line = f"\nfrom 5/1 with nothing: reaches 3/5 {'3/5' in st['reached']}, 0/0 {'0/0' in st['reached']}; {sorted(st['reached'])}"
with open(HERE / "one_way_edges.txt", "a", encoding="utf-8") as f:
    f.write(line + "\n")
print(line)
