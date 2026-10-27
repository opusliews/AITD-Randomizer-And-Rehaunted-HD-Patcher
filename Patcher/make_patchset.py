"""Build a patch-set folder (replacement game files) for TatouScenario.

  python make_patchset.py OUTDIR --life 8=edits/life8.asm --intended 8=54
                                 [--track 40=edits/track40.trk] [--force]
                                 [--new-life new.asm ...] [--objets edits.json]
                                 [--text 1151="Key to ..."]

- Starts from the read-only working copies (Generated/ResearchRun/SourceCopy),
  or from another patch set's LISTLIFE.PAK with --base (layered patch sets).
- Each --life N=FILE replaces LIFE N with the assembled listing. The listing
  is checked against the original with aitd_life.check_text_patch: control
  flow may change only at the --intended byte offsets of that script, and no
  new backward branch is allowed. A failed check aborts unless --force.
- Each --new-life FILE appends a brand-new LIFE script, in order, from the
  first free index (563 in vanilla). New scripts must decode cleanly and
  have no backward branch. One padding script (`endlife`) follows them, so
  every new index is below the engine's file count (PAK_getNumFiles returns
  one less than the number of entries).
- --objets FILE (JSON) edits OBJETS.ITD from the vanilla copy:
    {"set":    {"29": {"life": 564}},
     "append": [{"clone": 37, "found_name": 1151, "found_life": 563}]}
  Appended records take the next object numbers (292 in vanilla); at most
  300 objects in total (save format). Every life / found_life / floor_life
  must name an existing LIFE script, every found_name an existing text.
- Each --text ID=TEXT adds a text entry to every language PAK (ENGLISH,
  USA, FRANCAIS, ITALIANO, ESPAGNOL, DEUTSCH), with the same (English) text,
  so no language lacks the id.
- Writes OUTDIR/LISTLIFE.PAK, LISTTRAK.PAK, OBJETS.ITD and language PAKs as
  needed (PAK entries stored raw) plus OUTDIR/manifest.json (source hashes,
  changed entries, check reports).

A scenario loads the folder with `patchset <folder>`; the game files on disk
are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
import aitd_track as T         # noqa: E402
import aitd_objets as O        # noqa: E402
import aitd_text as X          # noqa: E402
from aitd_pak import read_pak, write_pak   # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "ResearchRun" / "SourceCopy"
LANGUAGES = ("ENGLISH", "USA", "FRANCAIS", "ITALIANO", "ESPAGNOL", "DEUTSCH")
PADDING_LIFE = "endlife\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pairs(values: list[str]) -> dict[int, str]:
    out = {}
    for v in values:
        key, _, val = v.partition("=")
        out[int(key)] = val
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--life", action="append", default=[], help="N=listing.asm")
    ap.add_argument("--intended", action="append", default=[], help="N=offset[,offset...]")
    ap.add_argument("--track", action="append", default=[], help="N=listing.trk")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--new-life", action="append", default=[], type=Path, help="append a new LIFE script")
    ap.add_argument("--objets", type=Path, help="JSON edits of OBJETS.ITD")
    ap.add_argument("--text", action="append", default=[], help="ID=TEXT, added to every language PAK")
    ap.add_argument("--max-objects", type=int, default=O.MAX_OBJECTS,
                    help="object limit of the target engine (300 unless its table was raised)")
    ap.add_argument("--base", type=Path, help="start from this LISTLIFE.PAK (e.g. another patch set) "
                    "instead of the vanilla working copy; listings are checked against it")
    a = ap.parse_args()

    manifest = {"tool": "Generated/Patcher/make_patchset.py", "files": {}, "life": {}, "track": {}}
    a.outdir.mkdir(parents=True, exist_ok=True)
    intended = {n: {int(x) for x in v.split(",") if x} for n, v in pairs(a.intended).items()}
    failed = False

    life_count = len(read_pak((a.base or SOURCE / "LISTLIFE.PAK")).entries)
    if a.life or a.new_life:
        base = a.base or SOURCE / "LISTLIFE.PAK"
        src = base.read_bytes()
        entries = [e.data for e in read_pak(base).entries]
        manifest["life_base"] = str(base)
        for n, listing in sorted(pairs(a.life).items()):
            original = L.decode(entries[n])
            patched = L.parse_script(Path(listing).read_text(encoding="utf-8"))
            report = L.check_text_patch(original, patched, intended.get(n, set()))
            data = L.encode(patched)
            L.decode(data)
            manifest["life"][n] = {
                "listing": str(listing), "original_bytes": len(entries[n]), "patched_bytes": len(data),
                "added_instructions": report.added, "intended_offsets": sorted(intended.get(n, set())),
                "flow_changed_at": [original[o].offset for o in report.changed_flow],
                "undeclared_flow_changes": [original[o].offset for o in report.unexpected_flow],
                "removed": [original[o].offset for o in report.removed],
                "new_backward_branches": [str(b) for b in report.new_backward],
                "ok": report.ok, "sha256": sha(data)}
            print(f"LIFE {n}: {len(entries[n])} -> {len(data)} bytes, +{report.added} instructions, "
                  f"{'OK' if report.ok else 'REJECTED'}")
            if not report.ok:
                failed = True
                for k in ("undeclared_flow_changes", "new_backward_branches"):
                    if manifest["life"][n][k]:
                        print(f"  {k}: {manifest['life'][n][k]}")
            entries[n] = data
        for listing in a.new_life:
            n = len(entries)
            instrs = L.parse_script(listing.read_text(encoding="utf-8"))
            data = L.encode(instrs)
            L.decode(data)
            back = L.backward_branches(instrs)
            manifest["life"][n] = {"listing": str(listing), "new": True, "patched_bytes": len(data),
                                   "new_backward_branches": [str(b) for b in back],
                                   "ok": not back, "sha256": sha(data)}
            print(f"LIFE {n} (new): {len(data)} bytes, {'OK' if not back else 'REJECTED (backward branch)'}")
            failed |= bool(back)
            entries.append(data)
        if a.new_life:
            entries.append(L.encode(L.parse_script(PADDING_LIFE)))
            manifest["life_padding_entry"] = len(entries) - 1
        life_count = len(entries)
        if failed and not a.force:
            print("not written (use --force to write anyway)")
            return 1
        out = write_pak(entries)
        (a.outdir / "LISTLIFE.PAK").write_bytes(out)
        manifest["files"]["LISTLIFE.PAK"] = {"source_sha256": sha(src), "sha256": sha(out)}

    if a.track:
        src = (SOURCE / "LISTTRAK.PAK").read_bytes()
        entries = [e.data for e in read_pak(SOURCE / "LISTTRAK.PAK").entries]
        for n, listing in sorted(pairs(a.track).items()):
            data = T.encode(T.parse_track(Path(listing).read_text(encoding="utf-8")))
            T.decode(data)
            manifest["track"][n] = {"listing": str(listing), "original_bytes": len(entries[n]),
                                    "patched_bytes": len(data), "sha256": sha(data)}
            print(f"TRACK {n}: {len(entries[n])} -> {len(data)} bytes")
            entries[n] = data
        out = write_pak(entries)
        (a.outdir / "LISTTRAK.PAK").write_bytes(out)
        manifest["files"]["LISTTRAK.PAK"] = {"source_sha256": sha(src), "sha256": sha(out)}

    texts = {}
    for t in a.text:
        key, _, val = t.partition("=")
        texts[int(key)] = val
    if texts:
        manifest["text"] = {str(k): v for k, v in sorted(texts.items())}
        for lang in LANGUAGES:
            path = SOURCE / f"{lang}.PAK"
            src = path.read_bytes()
            entries = [e.data for e in read_pak(path).entries]
            entries[0] = X.add_entries(entries[0], texts)
            out = write_pak(entries)
            (a.outdir / f"{lang}.PAK").write_bytes(out)
            manifest["files"][f"{lang}.PAK"] = {"source_sha256": sha(src), "sha256": sha(out)}
        print(f"text: {len(texts)} entries added to {len(LANGUAGES)} language PAKs")

    if a.objets:
        spec = json.loads(a.objets.read_text(encoding="utf-8"))
        src = (SOURCE / "OBJETS.ITD").read_bytes()
        objects = O.read_objets(src)
        known_text = set(X.entries(read_pak(SOURCE / "ENGLISH.PAK").entries[0].data)) | set(texts)
        changed = {}
        for k, fields in spec.get("set", {}).items():
            objects[int(k)].update(fields)
            changed[int(k)] = fields
        for rec in spec.get("append", []):
            rec = dict(rec)
            repeat = rec.pop("repeat", 1)
            for _ in range(repeat - 1):
                clone = dict(objects[rec["clone"]]) if "clone" in rec else {f: 0 for f in O.FIELDS}
                clone.update({k: v for k, v in rec.items() if k != "clone"})
                changed[len(objects)] = rec
                objects.append(clone)
            new = dict(objects[rec.pop("clone")]) if "clone" in rec else {f: 0 for f in O.FIELDS}
            new.update(rec)
            changed[len(objects)] = rec
            objects.append(new)
        errors = []
        for i in changed:
            o = objects[i]
            for f in ("life", "found_life", "floor_life"):
                if o[f] != -1 and not 0 <= o[f] < life_count:
                    errors.append(f"OBJ {i}: {f} {o[f]} does not exist ({life_count} LIFE scripts)")
            if o["found_name"] != -1 and o["found_name"] not in known_text:
                errors.append(f"OBJ {i}: found_name {o['found_name']} is not a text id")
        if errors:
            print("\n".join(errors))
            return 1
        out = O.write_objets(objects, a.max_objects)
        (a.outdir / "OBJETS.ITD").write_bytes(out)
        manifest["files"]["OBJETS.ITD"] = {"source_sha256": sha(src), "sha256": sha(out)}
        manifest["objets"] = {"spec": str(a.objets), "count": len(objects),
                              "changed": {str(k): v for k, v in sorted(changed.items())}}
        print(f"OBJETS.ITD: {len(objects)} objects, {len(changed)} changed or added")

    (a.outdir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"patch set written to {a.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
