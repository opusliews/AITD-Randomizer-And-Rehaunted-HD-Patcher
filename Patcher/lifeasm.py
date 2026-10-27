"""Command line for the AITD1 LIFE/TRACK assembler.

  python lifeasm.py disasm N                 LIFE N as text (stdout)
  python lifeasm.py disasm-track N           TRACK N as text
  python lifeasm.py dump OUTDIR              every LIFE (life_NNN.asm) and TRACK (track_NN.trk)
  python lifeasm.py asm FILE.asm -o OUT.bin  assemble a LIFE listing
  python lifeasm.py check N FILE.asm [--intended OFFSET ...]
        assemble an edited listing of LIFE N and check it against the
        original: only the instructions at the --intended byte offsets may
        change their control flow, and no new backward branch is allowed.
        Lines that keep their "; @offset" comment are original instructions;
        lines without it are new.

Reads the read-only working copy Generated/ResearchRun/SourceCopy/*.PAK
unless --pak / --track-pak is given. Text syntax: see aitd_life.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
import aitd_track as T         # noqa: E402
from aitd_pak import read_pak  # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "ResearchRun" / "SourceCopy"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["disasm", "disasm-track", "dump", "asm", "check"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--pak", type=Path, default=SOURCE / "LISTLIFE.PAK")
    ap.add_argument("--track-pak", type=Path, default=SOURCE / "LISTTRAK.PAK")
    ap.add_argument("--intended", type=int, nargs="*", default=[])
    a = ap.parse_args()

    if a.command == "disasm":
        data = read_pak(a.pak).entries[int(a.args[0])].data
        sys.stdout.write(L.format_script(L.decode(data)))
    elif a.command == "disasm-track":
        data = read_pak(a.track_pak).entries[int(a.args[0])].data
        sys.stdout.write(T.format_track(T.decode(data)))
    elif a.command == "dump":
        out = Path(a.args[0])
        out.mkdir(parents=True, exist_ok=True)
        for i, e in enumerate(read_pak(a.pak).entries):
            (out / f"life_{i:03d}.asm").write_text(L.format_script(L.decode(e.data)), encoding="utf-8")
        for i, e in enumerate(read_pak(a.track_pak).entries):
            (out / f"track_{i:02d}.trk").write_text(T.format_track(T.decode(e.data)), encoding="utf-8")
        print(f"wrote listings to {out}")
    elif a.command == "asm":
        data = L.encode(L.parse_script(Path(a.args[0]).read_text(encoding="utf-8")))
        if a.output:
            a.output.write_bytes(data)
        print(f"{len(data)} bytes")
    elif a.command == "check":
        n, path = int(a.args[0]), Path(a.args[1])
        original = L.decode(read_pak(a.pak).entries[n].data)
        patched = L.parse_script(path.read_text(encoding="utf-8"))
        report = L.check_text_patch(original, patched, set(a.intended))
        data = L.encode(patched)
        L.decode(data)    # the result must decode cleanly
        print(f"LIFE {n}: {len(original)} -> {len(patched)} instructions ({report.added} added), "
              f"{len(read_pak(a.pak).entries[n].data)} -> {len(data)} bytes")
        print(f"  flow changed at original instructions: {report.changed_flow}")
        print(f"  removed original instructions: {report.removed}")
        if report.unexpected_flow:
            print(f"  UNDECLARED flow changes (byte offsets): "
                  f"{[original[o].offset for o in report.unexpected_flow]}")
        if report.new_backward:
            print(f"  NEW BACKWARD BRANCHES (possible loops): {report.new_backward}")
        print("  OK" if report.ok else "  REJECTED")
        if report.ok and a.output:
            a.output.write_bytes(data)
        return 0 if report.ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
