"""Seed-level logic tests: each JSON is a placement plus the generator arguments of its seed
("_args") and the expected result ("_expect": "pass"/"fail"). generate.py --check-placement
builds that seed's world (locked doors, drops, spots...) and checks the placement against
today's logic.  python Generated/Logic/tests_seed/run.py"""
import json, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Generator"))
import generate as G

bad = 0
for f in sorted(HERE.glob("*.json")):
    t = json.loads(f.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        rc = G.main(t["_args"] + ["--out", tmp, "--check-placement", str(f)])
    got = "pass" if rc == 0 else "fail"
    ok = got == t["_expect"]
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'} {f.name}: expected {t['_expect']}, got {got}")
print(f"{bad} failure(s)")
sys.exit(1 if bad else 0)
