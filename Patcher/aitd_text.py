"""AITD1 language text (entry 0 of ENGLISH.PAK and the other language PAKs).

Grammar, from the engine parser (ReHaunted FitdLib/main.cpp `allocTextes`,
same as FITD): a byte stream of `@<decimal id>:<text>` entries; the text runs
until the first byte below 0x20 (the files use CR LF), and byte 0x1A ends the
stream (DEUTSCH.PAK has no 0x1A; it ends at the data end). Lookup is by id (`getTextFromIdx`), at most NUM_MAX_TEXT_ENTRY = 1000
entries. Vanilla ENGLISH.PAK entry 0 has 204 entries, ids 1..1150.

The text is kept as raw bytes so the round trip is exact. New entries are
inserted before the 0x1A end marker in the vanilla `@id:text\r\n` form.
"""
from __future__ import annotations

import re

MAX_ENTRIES = 1000
END = b"\x1a"
_ENTRY = re.compile(rb"@(\d+):([\x20-\xff]*)")


def entries(data: bytes) -> dict[int, bytes]:
    body = data.split(END, 1)[0]
    return {int(m.group(1)): m.group(2) for m in _ENTRY.finditer(body)}


def add_entries(data: bytes, new: dict[int, str]) -> bytes:
    existing = entries(data)
    clash = sorted(set(new) & set(existing))
    if clash:
        raise ValueError(f"text ids already used: {clash}")
    if len(existing) + len(new) > MAX_ENTRIES:
        raise ValueError(f"{len(existing) + len(new)} text entries: the engine reads at most {MAX_ENTRIES}")
    end = data.find(END)
    if end < 0:
        end = len(data)    # DEUTSCH.PAK has no 0x1A marker; the parser stops at the data end
    if not data[:end].endswith(b"\r\n"):
        raise ValueError("last entry does not end with CR LF")
    added = bytearray()
    for i, text in sorted(new.items()):
        raw = text.encode("ascii")  # game font mapping of other bytes not checked
        if any(b < 0x20 for b in raw) or b"@" in raw:
            raise ValueError(f"text {i}: control characters or '@' are not allowed")
        added += b"@%d:%s\r\n" % (i, raw)
    return data[:end] + bytes(added) + data[end:]
