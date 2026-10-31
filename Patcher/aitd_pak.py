"""AITD1 PAK archives: read (raw / implode / deflate) and write (raw).

Layout, from the engine loader (ReHaunted FitdLib/pak.cpp `loadPak`,
`PAK_getNumFiles`, `readPakInfo`; same as FITD):

    u32 0                      (always 0 in the AITD1 CD files)
    u32 offset[N]              entry offsets; offset[0] == 4 * (N + 1)
    entry: u32 additional_descriptor_size  (0 = none; else skip size-4 bytes)
           u32 disc_size, u32 uncompressed_size,
           u8  compression (0 raw, 1 implode, 4 deflate), u8 info5 (implode flags),
           u16 name_length, name bytes, data

Note: the engine's PAK_getNumFiles returns offset[0]/4 - 2 (N - 1), one less
than the number of entries; the last entry is still loadable by index.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PakEntry:
    data: bytes                    # decompressed content
    compression: int = 0
    info5: int = 0
    name: bytes = b""
    descriptor: bytes = b""        # additional descriptor block (rare; kept verbatim)
    stored: bytes = b""            # on-disc bytes (compressed form) as read


@dataclass
class Pak:
    entries: list[PakEntry] = field(default_factory=list)
    header_word: int = 0


# --------------------------------------------------------------------------
# PKWARE "implode" decompression (PAK compression 1). Port of the semantics of
# PAK_explode (UnPAK by C. Voila, based on M. Adler's explode.c). Codes are
# canonical Huffman codes read with inverted bits, first bit = code MSB.
# --------------------------------------------------------------------------
_CPLEN2 = list(range(2, 66))
_CPLEN3 = list(range(3, 67))
_EXTRA = [0] * 63 + [8]
_CPDIST4 = [1 + 64 * i for i in range(64)]
_CPDIST8 = [1 + 128 * i for i in range(64)]


class _Bits:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.buf = 0
        self.count = 0

    def byte(self) -> int:
        if self.pos < len(self.data):
            v = self.data[self.pos]
            self.pos += 1
            return v
        return 0

    def bits(self, n: int) -> int:
        while self.count < n:
            self.buf |= self.byte() << self.count
            self.count += 8
        v = self.buf & ((1 << n) - 1)
        self.buf >>= n
        self.count -= n
        return v


def _read_tree(src: _Bits, n: int) -> list[int]:
    # Byte stream (not bit stream): count-1, then (codes-1)<<4 | (bits-1).
    lengths: list[int] = []
    pairs = src.byte() + 1
    for _ in range(pairs):
        b = src.byte()
        lengths += [(b & 0x0F) + 1] * (((b & 0xF0) >> 4) + 1)
    if len(lengths) != n:
        raise ValueError(f"implode tree has {len(lengths)} lengths, expected {n}")
    return lengths


def _build_decoder(lengths: list[int]) -> dict[tuple[int, int], int]:
    table: dict[tuple[int, int], int] = {}
    code = 0
    for length in range(1, 17):
        for value, l in enumerate(lengths):
            if l == length:
                table[(length, code)] = value
                code += 1
        code <<= 1
    return table


def _decode(src: _Bits, table: dict[tuple[int, int], int]) -> int:
    code = 0
    for length in range(1, 17):
        code = (code << 1) | ((~src.bits(1)) & 1)
        v = table.get((length, code))
        if v is not None:
            return v
    raise ValueError("invalid implode code")


def explode(data: bytes, size: int, flags: int) -> bytes:
    src = _Bits(data)
    if flags & 4:
        lit = _build_decoder(_read_tree(src, 256))
        cplen = _CPLEN3
    else:
        lit = None
        cplen = _CPLEN2
    length_t = _build_decoder(_read_tree(src, 64))
    dist_t = _build_decoder(_read_tree(src, 64))
    low_bits, cpdist = (7, _CPDIST8) if flags & 2 else (6, _CPDIST4)

    out = bytearray()
    while len(out) < size:
        if src.bits(1):
            out.append(_decode(src, lit) if lit else src.bits(8))
        else:
            dist = src.bits(low_bits)
            dist += cpdist[_decode(src, dist_t)]
            idx = _decode(src, length_t)
            n = cplen[idx]
            if _EXTRA[idx]:
                n += src.bits(8)
            for _ in range(n):
                p = len(out) - dist
                out.append(out[p] if p >= 0 else 0)   # before the start reads zeros
    return bytes(out[:size])


# --------------------------------------------------------------------------
def read_pak(path: Path | str) -> Pak:
    raw = Path(path).read_bytes()
    header_word, first = struct.unpack_from("<II", raw, 0)
    count = first // 4 - 1
    offsets = list(struct.unpack_from(f"<{count}I", raw, 4))
    pak = Pak(header_word=header_word)
    for off in offsets:
        p = off
        (desc_size,) = struct.unpack_from("<I", raw, p)
        descriptor = b""
        if desc_size:
            descriptor = raw[p + 4:p + desc_size]
            p += desc_size
        else:
            p += 4
        disc, unc, comp, info5, name_len = struct.unpack_from("<IIBBH", raw, p)
        p += 12
        name = raw[p:p + name_len]
        p += name_len
        stored = raw[p:p + disc]
        if comp == 0:
            data = stored
        elif comp == 1:
            data = explode(stored, unc, info5)
        elif comp == 4:
            data = zlib.decompressobj(-15).decompress(stored)[:unc]
        else:
            raise ValueError(f"{path}: unknown compression {comp} at offset {off}")
        pak.entries.append(PakEntry(data, comp, info5, name, descriptor, stored))
    return pak


def write_pak(entries: list[bytes], header_word: int = 0) -> bytes:
    """Build a PAK with every entry stored uncompressed (compression 0)."""
    count = len(entries)
    out = bytearray(struct.pack("<I", header_word))
    out += b"\0" * (4 * count)
    for i, data in enumerate(entries):
        struct.pack_into("<I", out, 4 + 4 * i, len(out))
        out += struct.pack("<IIIBBH", 0, len(data), len(data), 0, 0, 0)
        out += data
    return bytes(out)


def rebuild_pak(raw: bytes, replace: dict[int, bytes]) -> bytes:
    """Rebuild the PAK file `raw` with the entries in `replace` stored uncompressed; every other
    entry keeps its on-disc block byte for byte (from its offset to the next one: compressed
    entries are followed by bytes outside disc_size). With nothing replaced the result equals
    `raw`."""
    header_word, first = struct.unpack_from("<II", raw, 0)
    count = first // 4 - 1
    offsets = list(struct.unpack_from(f"<{count}I", raw, 4)) + [len(raw)]
    out = bytearray(raw[:first])
    for i in range(count):
        struct.pack_into("<I", out, 4 + 4 * i, len(out))
        if i in replace:
            data = replace[i]
            out += struct.pack("<IIIBBH", 0, len(data), len(data), 0, 0, 0) + data
        else:
            out += raw[offsets[i]:offsets[i + 1]]
    return bytes(out)
