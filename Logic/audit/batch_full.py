"""Batch through the real generator (generate.main: every option, verify_seed included).

  python batch_full.py generate --seeds 1-150 --preset extreme [--save DIR]
      generate every seed with the generate.py next to this tree (or the one in
      $BATCH_GENERATE_DIR, e.g. an older release checked out with git worktree); --save keeps
      each placement.json as DIR/<seed>.json
  python batch_full.py check --seeds 1-150 --preset extreme --dir DIR
      check every saved placement against this tree's logic (generate.py --check-placement)

Run each mode in its own process: old and new trees have modules with the same names.
Prints one JSON summary line."""
import argparse, contextlib, io, json, os, shutil, sys, tempfile, time
from pathlib import Path

PRESETS = {
    "extreme": ["--enemy-drops", "--drop-chance", "100", "--extra-spots", "20", "--locked-doors", "100",
                "--drop-glow", "--visible-items", "--saber-pieces", "--whole-mirrors"],
    "default": ["--enemy-drops", "--drop-chance", "25", "--extra-spots", "10", "--locked-doors", "25",
                "--drop-glow", "--visible-items", "--saber-pieces", "--whole-mirrors"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("generate", "check"))
    ap.add_argument("--seeds", default="1-150")
    ap.add_argument("--preset", default="extreme")
    ap.add_argument("--save", type=Path)
    ap.add_argument("--dir", type=Path)
    a = ap.parse_args()
    gen_dir = Path(os.environ.get("BATCH_GENERATE_DIR") or Path(__file__).resolve().parents[2] / "Generator")
    if a.mode == "check":
        gen_dir = Path(__file__).resolve().parents[2] / "Generator"
    sys.path.insert(0, str(gen_dir))
    import generate as G
    lo, hi = (int(x) for x in a.seeds.split("-"))
    args = PRESETS[a.preset]
    bad, t0 = [], time.time()
    if a.save:
        a.save.mkdir(parents=True, exist_ok=True)
    for seed in range(lo, hi + 1):
        with tempfile.TemporaryDirectory() as tmp:
            extra = (["--check-placement", str(a.dir / f"{seed}.json")] if a.mode == "check" else [])
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    rc = G.main(["--seed", str(seed), "--out", tmp] + args + extra)
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
            if rc != 0:
                bad.append(seed)
            elif a.save:
                shutil.copy(Path(tmp) / "placement.json", a.save / f"{seed}.json")
        print(f"{a.mode} {a.preset} seed {seed} ({seed - lo + 1}/{hi - lo + 1}): "
              f"{'BAD' if bad and bad[-1] == seed else 'ok'}, {round(time.time() - t0)} s", file=sys.stderr, flush=True)
    print(json.dumps({"mode": a.mode, "preset": a.preset, "seeds": f"{lo}-{hi}", "generator": str(gen_dir),
                      "failed" if a.mode == "generate" else "rejected": bad,
                      "minutes": round((time.time() - t0) / 60, 1)}))


if __name__ == "__main__":
    main()
