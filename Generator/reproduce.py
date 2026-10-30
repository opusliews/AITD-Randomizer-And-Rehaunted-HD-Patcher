"""Rebuild a player's randomized game from an F7 capture (bug reports).

The AITD Randomizer edition of ReHaunted keeps only the F7 state capture of the
scenario tester. A capture is a TatouScenario .scn file: the player's position,
inventory, VARS/CVARS and OBJETS changes against the new-game state. Its header
also copies the install marker (AITD_Randomizer.json, written by install.py):
seed, generator version, options and the installed files' hashes.

This tool:
  1. reads the marker from the capture header;
  2. regenerates the seed with generate.py (same seed and options; the generator
     is deterministic for a given version);
  3. checks the regenerated LISTLIFE.PAK hash against the hash installed on the
     player's machine (an exact match means the same game);
  4. writes OUT/<capture>.scn plus OUT/patchsets/seed_<N>/ for TatouScenario.
     Copy both into the TatouScenario exe's scenarios folder and load the .scn
     (or start TatouScenario with it): the game restarts on the seed and is put in
     the captured state.

The game-start scenario of a seed is just its patchset (seed_<N>.scn in the
regenerated folder, also written to OUT): the capture already holds everything
else, as differences from that start.

Usage: python reproduce.py capture_YYYYMMDD_HHMMSS.scn [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def read_marker(lines: list[str]) -> dict | None:
    try:
        a = lines.index("# randomizer-marker-begin")
        b = lines.index("# randomizer-marker-end")
    except ValueError:
        return None
    return json.loads("\n".join(l[3:] if l.startswith("#| ") else l[2:] for l in lines[a + 1:b]))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path)
    ap.add_argument("--out", type=Path, help="default Generated/Scenarios/repro/<capture name>")
    a = ap.parse_args()

    text = a.capture.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    marker = read_marker(lines)
    if marker is None:
        print("no randomizer marker in the capture: the game folder had no seed installed "
              "(vanilla game, or installed by hand). Load the capture as it is.")
        return 1
    seed, opts = marker.get("seed"), marker.get("options") or {}
    if seed is None:
        print("the marker has no seed number")
        return 1
    print(f"seed {seed}, installed {marker.get('installed')} by {marker.get('generator')}")
    print(f"options {json.dumps(opts)}")

    import generate                      # same folder; only for VERSION
    current = f"Generated/Generator/generate.py {generate.VERSION}"
    if marker.get("generator") and marker["generator"] != current:
        print(f"WARNING: captured with '{marker['generator']}', this is '{current}'. Another generator "
              "version can place items differently; the hash check below decides.")

    out = a.out or GEN / "Scenarios" / "repro" / a.capture.stem
    seed_dir = GEN / "Seeds" / "repro" / f"{a.capture.stem}_seed_{seed}"
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "generate.py"), "--seed", str(seed),
           "--out", str(seed_dir)]
    if opts.get("enemy_drops"):
        cmd += ["--enemy-drops", "--drop-chance", str(opts.get("drop_chance", 25.0))]
    if opts.get("extra_spots"):
        cmd += ["--extra-spots", str(opts["extra_spots"])]
    if opts.get("key_names"):
        cmd += ["--key-names"]
    if opts.get("locked_doors"):
        cmd += ["--locked-doors", str(opts["locked_doors"])]
    if opts.get("saber_pieces"):
        cmd += ["--saber-pieces"]
    if opts.get("visible_items"):
        cmd += ["--visible-items"]
    if opts.get("deadly_smoke"):
        cmd += ["--deadly-smoke"]
    if opts.get("forced_max_per_location"):          # test seeds only; normal seeds pick 2 or 3 themselves
        cmd += ["--max-per-location", str(opts["forced_max_per_location"])]
    print("regenerating:", " ".join(cmd[1:]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr)
        print("generation failed")
        return 1
    manifest = json.loads((seed_dir / "patchset" / "manifest.json").read_text(encoding="utf-8"))

    ok = True
    for name, rec in (marker.get("files") or {}).items():
        mine = seed_dir / "patchset" / name
        if not mine.exists():
            continue                      # e.g. the ReHaunted config the installer edited
        match = sha(mine) == rec.get("after")
        ok &= match
        print(f"  {name}: {'MATCH' if match else 'DIFFERENT'} (player {str(rec.get('after'))[:16]}, "
              f"regenerated {sha(mine)[:16]})")
    if marker.get("attempt") is not None and marker["attempt"] != manifest.get("attempt"):
        print(f"  fill attempt differs: player {marker['attempt']}, regenerated {manifest.get('attempt')}")
    if not ok:
        print("NOT REPRODUCED: the regenerated files differ from the player's. Check out the generator "
              "version named above and rerun. Scenario written anyway, for inspection only.")

    # the scenario: the capture's own commands, with the regenerated patchset
    out.mkdir(parents=True, exist_ok=True)
    pdir = out / "patchsets" / f"seed_{seed}"
    if pdir.exists():
        shutil.rmtree(pdir)
    shutil.copytree(seed_dir / "patchset", pdir)
    body = [l for l in lines if not l.startswith("#| ") and not l.startswith("# randomizer-marker-")
            and not l.strip().startswith("patchset ")]
    at = next((i + 1 for i, l in enumerate(body) if l.startswith("name ")), 0)
    body[at:at] = ["", f"patchset patchsets/seed_{seed}"]
    head = [f"# Reproduction of {a.capture.name}: seed {seed}, options {json.dumps(opts)}",
            f"# Regenerated by Generated/Generator/reproduce.py with {current}: "
            + ("files MATCH the player's." if ok else "files DIFFER from the player's (not the same game)."),
            f"# Spoiler: {seed_dir / 'spoiler.md'}"]
    (out / a.capture.name).write_text("\n".join(head + body) + "\n", encoding="utf-8")
    (out / f"seed_{seed}_start.scn").write_text(
        f"# Game start of seed {seed} (options {json.dumps(opts)}).\n"
        f"name Randomizer seed {seed} start\npatchset patchsets/seed_{seed}\n", encoding="utf-8")
    print(f"wrote {out / a.capture.name} and {out / f'seed_{seed}_start.scn'} (+ patchsets/seed_{seed})")
    print("copy the contents of that folder into the TatouScenario exe's scenarios folder")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
