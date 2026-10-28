"""Assumption register (2026-10-28): for every item the logic requires, every LIFE line that
deletes it, moves it (put/put_at/drop), changes its found flags/weight, or throws it.
Output: consumption_scan.txt. Read with life_dump.txt (dump_life.py)."""
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
man = json.loads((HERE.parent / "logic_manual.json").read_text(encoding="utf-8"))
items = sorted({int(n) for n in re.findall(r"item:(\d+)", json.dumps(man))} | {2, 38, 41, 110, 232, 268})
dump = (HERE / "life_dump.txt").read_text(encoding="utf-8").splitlines()
out, life = [], None
for ln in dump:
    if ln.startswith("===== LIFE"):
        life = ln
        continue
    s = ln.strip().split(";")[0].strip()
    for n in items:
        pats = [rf"^delete {n}$", rf"^put {n} ", rf"^put_at {n} ", rf"^drop #?{n}\b",
                rf"^obj_{n}\.found_(flag|weight)\b", rf"^obj_1\.throw \d+ \d+ \d+ {n} ", rf"^take {n}$"]
        if any(re.search(p, s) for p in pats):
            out.append(f"item {n:3}: {s:40} | {life[6:].split('  run by')[0]}  ({life.split('run by: ')[1][:90]})")
out.sort(key=lambda x: int(x.split(":")[0][5:]))
(HERE / "consumption_scan.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
