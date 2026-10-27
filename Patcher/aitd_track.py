"""AITD1 TRACK bytecode: decoder, encoder and text form.

Opcodes and operand counts from ReHaunted FitdLib/track.cpp `processTrack`
(case 3, AITD1 numbering; `convertTrackMacro` is the identity for AITD1).
Positions in a track are word indices (`positionInTrack`). TRACK has no
branches: REPEAT restarts at word 0, END stops.

Every original AITD1 track ends with the words [20, 2] after its final END or
REPEAT. Opcode 20 (TL_CLOSE) has no interpreter case and is never reached; the
pair is kept verbatim as `trailer` (see Research/TrackRoomAnalysis.md).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

OPCODES: list[tuple[str, int | None]] = [
    ("INIT_COOR", 4),   # 0  room, x, y, z (warp)
    ("GOTO", 3),        # 1  room, x, z
    ("END", 0),         # 2
    ("REPEAT", 0),      # 3
    ("MARK", 1),        # 4
    ("WALK", 0),        # 5
    ("RUN", 0),         # 6
    ("STOP", 0),        # 7
    ("BACK", 0),        # 8
    ("SET_ANGLE", 1),   # 9
    ("COL_OFF", 0),     # 10
    ("COL_ON", 0),      # 11
    ("SET_DIST", None), # 12 (no interpreter case)
    ("DEC_OFF", 0),     # 13
    ("DEC_ON", 0),      # 14
    ("GOTO_3D", 5),     # 15 room, x, y, z, time
    ("MEMO_COOR", 0),   # 16
    ("GOTO_3DX", 3),    # 17 x, y, z
    ("GOTO_3DZ", 3),    # 18 x, y, z
    ("ANGLE", 3),       # 19 alpha, beta, gamma
    ("CLOSE", None),    # 20 (no interpreter case; only in the trailer)
]
OPCODE_BY_NAME = {name: i for i, (name, _) in enumerate(OPCODES)}
TERMINATORS = {OPCODE_BY_NAME["END"], OPCODE_BY_NAME["REPEAT"]}


class TrackError(Exception):
    pass


@dataclass
class TrackInstr:
    op: int
    args: list[int] = field(default_factory=list)
    word_offset: int = -1

    @property
    def name(self) -> str:
        return OPCODES[self.op][0]


@dataclass
class Track:
    instrs: list[TrackInstr]
    trailer: list[int] = field(default_factory=list)


def decode(data: bytes) -> Track:
    if len(data) % 2:
        raise TrackError("odd track length")
    words = list(struct.unpack(f"<{len(data) // 2}h", data))
    instrs: list[TrackInstr] = []
    i = 0
    while i < len(words):
        op = words[i]
        if op < 0 or op >= len(OPCODES) or OPCODES[op][1] is None:
            if instrs and instrs[-1].op in TERMINATORS:
                return Track(instrs, words[i:])
            raise TrackError(f"unsupported opcode {op} at word {i}")
        n = OPCODES[op][1]
        if i + 1 + n > len(words):
            raise TrackError(f"truncated {OPCODES[op][0]} at word {i}")
        instrs.append(TrackInstr(op, words[i + 1:i + 1 + n], i))
        i += 1 + n
    return Track(instrs, [])


def encode(track: Track) -> bytes:
    words: list[int] = []
    for ins in track.instrs:
        ins.word_offset = len(words)
        words.append(ins.op)
        words += ins.args
    words += track.trailer
    return struct.pack(f"<{len(words)}h", *words)


def format_track(track: Track) -> str:
    lines = [f"{ins.name} {' '.join(map(str, ins.args))}".rstrip() + f"    ; @w{ins.word_offset}"
             for ins in track.instrs]
    if track.trailer:
        lines.append("trailer " + " ".join(map(str, track.trailer)))
    return "\n".join(lines) + "\n"


def parse_track(text: str) -> Track:
    instrs, trailer = [], []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split(";", 1)[0].split()
        if not line:
            continue
        if line[0].lower() == "trailer":
            trailer = [int(v, 0) for v in line[1:]]
            continue
        name = line[0].upper()
        if name not in OPCODE_BY_NAME or OPCODES[OPCODE_BY_NAME[name]][1] is None:
            raise TrackError(f"line {n}: unknown TRACK opcode '{line[0]}'")
        op = OPCODE_BY_NAME[name]
        if len(line) - 1 != OPCODES[op][1]:
            raise TrackError(f"line {n}: {name} takes {OPCODES[op][1]} operand(s)")
        instrs.append(TrackInstr(op, [int(v, 0) for v in line[1:]]))
    return Track(instrs, trailer)
