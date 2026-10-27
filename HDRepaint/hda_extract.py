"""List or extract a ReHaunted .hda archive (HDBG v1/v2, as FitdLib/hdArchive.cpp reads it).

  python hda_extract.py ARCHIVE.hda                 list entries (path, size)
  python hda_extract.py ARCHIVE.hda OUTDIR [GLOB]   extract entries (optionally matching GLOB, e.g. "*CAMERA07*")

The archive is only read. Compressed v2 entries are zlib streams.
"""
import fnmatch
import struct
import sys
import zlib
from pathlib import Path

MAGIC = 0x47424448  # "HDBG"


def read_toc(f):
    magic, version, count = struct.unpack("<III", f.read(12))
    if magic != MAGIC or version not in (1, 2):
        raise SystemExit(f"not an HDBG v1/v2 archive (magic 0x{magic:08X}, version {version})")
    entries = []
    for _ in range(count):
        (n,) = struct.unpack("<H", f.read(2))
        path = f.read(n).decode("utf-8", "replace")
        offset, size = struct.unpack("<QQ", f.read(16))
        usize, flags = size, 0
        if version == 2:
            usize, flags = struct.unpack("<QI", f.read(12))
        entries.append((path, offset, size, usize, flags))
    return entries


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    with open(sys.argv[1], "rb") as f:
        entries = read_toc(f)
        if len(sys.argv) == 2:
            for path, _, size, usize, _ in sorted(entries):
                print(f"{usize:>12}  {path}")
            print(f"{len(entries)} entries")
            return
        out = Path(sys.argv[2])
        pattern = sys.argv[3] if len(sys.argv) > 3 else "*"
        n = 0
        for path, offset, size, usize, flags in entries:
            if not fnmatch.fnmatch(path.lower(), pattern.lower()):
                continue
            f.seek(offset)
            data = f.read(size)
            if flags & 1:
                data = zlib.decompress(data)
            dst = out / path.replace("\\", "/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            n += 1
        print(f"extracted {n} entries to {out}")


if __name__ == "__main__":
    main()
