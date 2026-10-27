"""Assembles search_hint.asm with MASM (MSVC Build Tools ml.exe, OMF output) and prints its bytes
as the hex string that vanilla_exe.py embeds (SEARCH_HINT_CODE), so players need no assembler.

  python build_search_hint.py [ML_EXE]

Checks: one segment; no fixups (offsets are written as `label - start`); no 386 encodings in
the listing (0F xx near jumps, 66/67 prefixes); the embedded copy in vanilla_exe.py is identical.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ML = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x86\ml.exe"


def ledata(obj: bytes) -> bytes:
    """The code bytes of the single segment (LEDATA records, 0xA0)."""
    out = bytearray()
    i = 0
    while i < len(obj):
        rtype, length = obj[i], struct.unpack_from("<H", obj, i + 1)[0]
        body = obj[i + 3:i + 3 + length - 1]
        if rtype in (0x9C, 0x9D):
            sys.exit("FIXUPP record: use label - start constants, not offset label")
        if rtype == 0xA0:
            seg, off = body[0], struct.unpack_from("<H", body, 1)[0]
            assert seg == 1, "one segment expected"
            data = body[3:]
            out[len(out):off + len(data)] = bytes(off + len(data) - len(out))
            out[off:off + len(data)] = data
        i += 3 + length
    return bytes(out)


def build(ml: str = ML) -> bytes:
    with tempfile.TemporaryDirectory() as t:
        obj, lst = Path(t) / "h.obj", Path(t) / "h.lst"
        r = subprocess.run([ml, "/nologo", "/c", "/omf", f"/Fl{lst}", f"/Fo{obj}",
                            str(HERE / "search_hint.asm")], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        bad = [l for l in lst.read_text(errors="replace").splitlines()
               if re.match(r"^ [0-9A-F]{4}  (0F|66|67)\b", l)]
        if bad:
            sys.exit("386 encodings:\n" + "\n".join(bad))
        return ledata(obj.read_bytes())


if __name__ == "__main__":
    code = build(*sys.argv[1:])
    print(code.hex())
    sys.path.insert(0, str(HERE.parent))
    import vanilla_exe
    print("vanilla_exe.SEARCH_HINT_CODE", "matches" if vanilla_exe.SEARCH_HINT_CODE == code else "DIFFERS",
          f"({len(code)} bytes)")
