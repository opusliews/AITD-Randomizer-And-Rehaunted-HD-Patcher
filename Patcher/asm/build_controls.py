"""Assembles controls.asm with MASM (ml.exe, OMF) and prints what vanilla_exe.py embeds:
the code bytes (CONTROLS_CODE), the hook entry offsets (labels entry_*) and the offsets of the
segment words that need relocation entries (labels reloc_*), so players need no assembler.

  python build_controls.py [ML_EXE] [--write]   (--write updates the copy in vanilla_exe.py)

Checks (as build_search_hint.py): one segment, no fixups, no 386 encodings; and that the copy
embedded in vanilla_exe.py is identical.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_search_hint import ML, ledata  # noqa: E402


def build(ml: str = ML) -> tuple[bytes, dict[str, int], list[int]]:
    with tempfile.TemporaryDirectory() as t:
        obj, lst = Path(t) / "c.obj", Path(t) / "c.lst"
        r = subprocess.run([ml, "/nologo", "/c", "/omf", "/Sa", f"/Fl{lst}", f"/Fo{obj}",
                            str(HERE / "controls.asm")], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        listing = lst.read_text(errors="replace")
        bad = [l for l in listing.splitlines() if re.match(r"^ [0-9A-F]{4}  (0F|66|67)\b", l)]
        if bad:
            sys.exit("386 encodings:\n" + "\n".join(bad))
        code = ledata(obj.read_bytes())
    labels = {}
    for m in re.finditer(r"^((?:entry|reloc)_\w+)\s*[. ]*\s+L Near\s+([0-9A-F]{4})", listing, re.M):
        labels[m.group(1)] = int(m.group(2), 16)
    entries = {k[len("entry_"):]: v for k, v in labels.items() if k.startswith("entry_")}
    relocs = sorted(v for k, v in labels.items() if k.startswith("reloc_"))
    if len(entries) != 8 or not relocs:
        sys.exit(f"labels not found in the listing: {labels}")
    for o in relocs:                                   # each must follow a far jmp/call opcode
        if code[o - 3] not in (0xEA, 0x9A):
            sys.exit(f"reloc at {o:#x} does not follow a far jump/call")
    return code, entries, relocs


def write_embedded(code: bytes, entries: dict, relocs: list) -> None:
    """Replaces CONTROLS_CODE / CONTROLS_ENTRIES / CONTROLS_RELOCS in vanilla_exe.py."""
    p = HERE.parent / "vanilla_exe.py"
    s = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in s else "\n"
    s = s.replace("\r\n", "\n")
    h = code.hex()
    lines = "\n".join(f'    "{h[i:i + 96]}"' for i in range(0, len(h), 96))
    s, n1 = re.subn(r'CONTROLS_CODE = bytes\.fromhex\(\n(?:    "[0-9a-f]+"\n?)+\)',
                    lambda m: f"CONTROLS_CODE = bytes.fromhex(\n{lines})", s)
    s, n2 = re.subn(r"CONTROLS_ENTRIES = \{[^}]*\}", lambda m: f"CONTROLS_ENTRIES = {entries!r}", s)
    s, n3 = re.subn(r"CONTROLS_RELOCS = \[[^\]]*\]", lambda m: f"CONTROLS_RELOCS = {relocs!r}", s)
    assert n1 == n2 == n3 == 1, (n1, n2, n3)
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--write"]
    code, entries, relocs = build(*args)
    if "--write" in sys.argv:
        write_embedded(code, entries, relocs)
    print("CONTROLS_CODE =", code.hex())
    print("CONTROLS_ENTRIES =", entries)
    print("CONTROLS_RELOCS =", relocs)
    sys.path.insert(0, str(HERE.parent))
    import vanilla_exe
    same = (getattr(vanilla_exe, "CONTROLS_CODE", None) == code and vanilla_exe.CONTROLS_ENTRIES == entries
            and vanilla_exe.CONTROLS_RELOCS == relocs)
    print("vanilla_exe copy", "matches" if same else "DIFFERS", f"({len(code)} bytes, {len(relocs)} relocations)")
