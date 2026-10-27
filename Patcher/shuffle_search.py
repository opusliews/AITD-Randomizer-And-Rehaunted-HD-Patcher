"""PoC B: shuffle the items of all search slots, driven by the slot catalog.

  python shuffle_search.py --seed 42 OUTDIR

- Pool: every item position of the catalog's "search" slots (34 positions in
  21 slots). Contact slots keep their items (Rule 1).
- The items are permuted with the seed; each slot keeps its number of items.
- Patching is in place: every catalog site that names an awarded item (`found X`,
  `object(X)`, `isfound(#X)`, `obj_X.` targets) is rewritten from the original
  item to the new one, after checking the original word. No code is added.
- Every patched script is re-decoded and must be instruction-for-instruction
  identical to the original except at catalog sites, with unchanged control
  flow (check_patch with nothing intended).
- Writes OUTDIR/LISTLIFE.PAK (raw entries), manifest.json and spoiler.md.

This is a mechanics proof of concept: no logic is applied, so a seed may be
unbeatable. Slot side effects stay with the slot (the mirror spot still needs
the dresser key; searching the garden spot still wakes the spiders).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
from aitd_pak import read_pak, write_pak   # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE.parent / "ResearchRun" / "SourceCopy" / "LISTLIFE.PAK"
ZONE_NOTES = ROOT / "References" / "AITD_zones.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--seed", type=int, required=True)
    a = ap.parse_args()

    catalog = json.loads((HERE / "catalog" / "search_slots.json").read_text(encoding="utf-8"))
    if catalog["cross_check_problems"]:
        print("catalog has cross-check problems; rebuild it first")
        return 1
    slots = [s for s in catalog["slots"] if s["mechanism"] == "search"]
    names = {i["obj"]: i["name"] for s in catalog["slots"] for i in s["items"]}

    positions = [(s["slot_id"], i["obj"]) for s in slots for i in s["items"]]
    pool = [obj for _, obj in positions]
    if len(set(pool)) != len(pool):
        print("an item appears in two search positions; refusing")
        return 1
    rng = random.Random(a.seed)
    shuffled = pool[:]
    rng.shuffle(shuffled)
    new_item = {pos: obj for pos, obj in zip(positions, shuffled)}

    src = SOURCE.read_bytes()
    entries = [bytearray(e.data) for e in read_pak(SOURCE).entries]
    originals = {s["life"]: bytes(entries[s["life"]]) for s in slots}
    patched_sites = defaultdict(set)
    for s in slots:
        data = entries[s["life"]]
        for item in s["items"]:
            target = new_item[(s["slot_id"], item["obj"])]
            for site in item["sites"]:
                found = struct.unpack_from("<h", data, site["offset"])[0]
                if found != item["obj"]:
                    print(f"LIFE {s['life']} @{site['offset']}: expected {item['obj']}, found {found}")
                    return 1
                struct.pack_into("<h", data, site["offset"], target)
                patched_sites[s["life"]].add(site["offset"])

    # Verify: same instructions and flow, operands differ only at catalog sites.
    report = {}
    for life, before in originals.items():
        after = bytes(entries[life])
        diff = {i for i in range(0, len(before), 2) if before[i:i + 2] != after[i:i + 2]}
        orig_i, new_i = L.decode(before), L.decode(after)
        same_shape = len(orig_i) == len(new_i) and all(
            x.op == y.op and x.offset == y.offset and x.size() == y.size() for x, y in zip(orig_i, new_i))
        flow = L.check_patch(orig_i, new_i)
        ok = same_shape and flow.ok and not flow.changed_flow and diff <= patched_sites[life]
        report[life] = {"ok": ok, "words_changed": len(diff), "sha256": hashlib.sha256(after).hexdigest()}
        if not ok:
            print(f"LIFE {life}: verification failed {report[life]}")
            return 1

    a.outdir.mkdir(parents=True, exist_ok=True)
    out = write_pak([bytes(e) for e in entries])
    (a.outdir / "LISTLIFE.PAK").write_bytes(out)

    notes = {}
    if ZONE_NOTES.exists():
        for r in csv.DictReader(open(ZONE_NOTES, encoding="utf-8", errors="replace")):
            text = "".join(c for c in r.get("description", "") if 32 <= ord(c) < 127 or c.isspace())
            notes[r["zone_id"]] = " ".join(text.split()).replace("|", "/")[:90]
    lines = [f"# Search shuffle, seed {a.seed}", "",
             "No logic applied (mechanics PoC). One search offers all items of a spot.", "",
             "| Search spot | Vanilla item(s) | Now gives | Note (your zone description) |", "|---|---|---|---|"]
    mapping = []
    for s in slots:
        old = [i["obj"] for i in s["items"]]
        new = [new_item[(s["slot_id"], o)] for o in old]
        mapping.append({"slot": s["slot_id"], "life": s["life"], "vanilla": old, "now": new})
        fmt = lambda xs: ", ".join(f"{names[x]} ({x})" for x in xs)
        lines.append(f"| {s['slot_id']} | {fmt(old)} | **{fmt(new)}** | {notes.get(s['zones'][0], '')} |")
    (a.outdir / "spoiler.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (a.outdir / "manifest.json").write_text(json.dumps({
        "tool": "Generated/Patcher/shuffle_search.py", "seed": a.seed,
        "catalog": "Generated/Patcher/catalog/search_slots.json",
        "files": {"LISTLIFE.PAK": {"source_sha256": hashlib.sha256(src).hexdigest(),
                                   "sha256": hashlib.sha256(out).hexdigest()}},
        "mapping": mapping, "scripts": report}, indent=1), encoding="utf-8")
    moved = sum(1 for p in positions if new_item[p] != p[1])
    print(f"seed {a.seed}: {len(positions)} positions in {len(slots)} slots, {moved} items moved, "
          f"{len(report)} scripts patched and verified -> {a.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
