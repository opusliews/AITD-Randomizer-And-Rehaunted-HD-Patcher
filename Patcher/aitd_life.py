"""AITD1 LIFE bytecode: decoder, encoder, text assembler and relocation.

Instruction set (AITD1 only), derived from the engine interpreter:
ReHaunted FitdLib/life.cpp `processLife` (operand reads per opcode),
FitdLib/AITD1.cpp `AITD1LifeMacroTable` (opcode numbering) and
FitdLib/evalVar.cpp `evalVar` (expression encoding). Cross-checked against
LifeDISA instruction offsets and branch targets by verify_assembler.py.

Encoding
  instruction := opword [objword] operands
    opword & 0x7FFF = opcode index; opword & 0x8000 -> an object word follows
    and the instruction acts on that world object.
  operands (16-bit little-endian words):
    w  plain word
    e  expression (see below)
    J  branch: signed word offset, in words, relative to the END of the
       instruction (target = end + 2 * offset). Used by if_*, goto, case,
       multi_case. A conditional instruction continues on true and jumps on
       false.
    M  multi_case value list: count word, then `count` words
  expression := w0 ...
    w0 == -1 : constant, 1 word follows
    w0 == 0  : vars[] index, 1 word follows
    otherwise: field code = (w0 & 0x7FFF) - 1; if w0 & 0x8000 an object word
               follows first. Some fields take extra operands (FIELDS below).
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from typing import Union

# --------------------------------------------------------------------------
# Opcode table: index -> (mnemonic, operand schema). Mnemonics follow LifeDISA
# where it has a name. None = opcode exists in the table but has no AITD1
# interpreter case (never used by the original scripts); decoding it fails.
OPCODES: list[tuple[str, str | None]] = [
    ("do_move", ""),             # 0  LM_DO_MOVE
    ("anim_once", "ww"),         # 1  LM_ANIM_ONCE anim, flags
    ("anim_all_once", "ww"),     # 2  LM_ANIM_ALL_ONCE
    ("body", "e"),               # 3  LM_BODY
    ("if_egal", "eeJ"),          # 4
    ("if_different", "eeJ"),     # 5
    ("if_sup_egal", "eeJ"),      # 6
    ("if_sup", "eeJ"),           # 7
    ("if_inf_egal", "eeJ"),      # 8
    ("if_inf", "eeJ"),           # 9
    ("goto", "J"),               # 10
    ("return", ""),              # 11 LM_RETURN
    ("endlife", ""),             # 12 LM_END
    ("anim_repeat", "w"),        # 13
    ("anim_move", "wwwwwww"),    # 14
    ("trackmode", "ww"),         # 15 LM_MOVE mode, track
    ("hit", "wwwwew"),           # 16 anim, frame, group, size, force(expr), next anim
    ("message", "w"),            # 17
    ("message_value", "ww"),     # 18
    ("var", "we"),               # 19
    ("inc", "w"),                # 20
    ("dec", "w"),                # 21
    ("add", "we"),               # 22
    ("sub", "we"),               # 23
    ("life_mode", "w"),          # 24
    ("switch", "e"),             # 25
    ("case", "wJ"),              # 26
    ("camera", None),            # 27 LM_CAMERA (no interpreter case)
    ("start_chrono", ""),        # 28
    ("multi_case", "MJ"),        # 29
    ("found", "w"),              # 30
    ("life", "w"),               # 31
    ("delete", "w"),             # 32
    ("take", "w"),               # 33
    ("in_hand", "w"),            # 34
    ("read", "www"),             # 35 AITD1 reads a third word (CD voice index)
    ("anim_sound", "eww"),       # 36 LM_ANIM_SAMPLE sample(expr), anim, frame
    ("special", "w"),            # 37
    ("do_real_zv", ""),          # 38
    ("sound", "e"),              # 39 LM_SAMPLE
    ("flags", "w"),              # 40 LM_TYPE
    ("game_over", ""),           # 41
    ("manual_rot", ""),          # 42
    ("rnd_freq", "w"),           # 43
    ("music", "w"),              # 44
    ("set_beta", "ww"),          # 45
    ("do_rot_zv", ""),           # 46
    ("changeroom", "wwwww"),     # 47 LM_STAGE floor, room, x, y, z
    ("found_name", "w"),         # 48
    ("found_flag", "w"),         # 49
    ("found_life", "w"),         # 50
    ("camera_target", "w"),      # 51
    ("drop", "ew"),              # 52
    ("fire", "wwwwww"),          # 53 AITD1 form: six plain words
    ("test_col", "w"),           # 54
    ("found_body", "w"),         # 55
    ("set_alpha", "ww"),         # 56
    ("stop_beta", None),         # 57 (no interpreter case)
    ("do_max_zv", ""),           # 58
    ("put", "wwwwwwwww"),        # 59 obj, x, y, z, room, floor, alpha, beta, gamma
    ("c_var", "we"),             # 60
    ("do_normal_zv", None),      # 61 (no interpreter case)
    ("do_carre_zv", ""),         # 62
    ("sound_then", "ee"),        # 63 LM_SAMPLE_THEN
    ("light", "w"),              # 64
    ("shaking", "w"),            # 65
    ("allow_inventory", "w"),    # 66 LM_INVENTORY
    ("found_weight", "w"),       # 67
    ("up_coor_y", ""),           # 68
    ("speed", None),             # 69 (no interpreter case)
    ("put_at", "ww"),            # 70
    ("def_zv", "wwwwww"),        # 71
    ("hit_object", "ww"),        # 72
    ("get_hard_clip", ""),       # 73
    ("angle", "www"),            # 74
    ("rep_sound", "ew"),         # 75 LM_REP_SAMPLE sample(expr), frequency
    ("throw", "wwwwwww"),        # 76
    ("water", "w"),              # 77
    ("picture", "www"),          # 78
    ("stop_sound", ""),          # 79 LM_STOP_SAMPLE
    ("next_music", "w"),         # 80
    ("fade_music", "w"),         # 81
    ("stop_hit_object", ""),     # 82
    ("copy_angle", "w"),         # 83
    ("end_sequence", ""),        # 84
    ("sound_then_repeat", "ee"), # 85
    ("wait_game_over", ""),      # 86
]
OPCODE_BY_NAME = {name: i for i, (name, _) in enumerate(OPCODES)}
BRANCH_OPS = {OPCODE_BY_NAME[n] for n in
              ("if_egal", "if_different", "if_sup_egal", "if_sup", "if_inf_egal", "if_inf",
               "goto", "case", "multi_case")}
OP_GOTO = OPCODE_BY_NAME["goto"]
OP_END = OPCODE_BY_NAME["endlife"]
OP_RETURN = OPCODE_BY_NAME["return"]
OP_SWITCH = OPCODE_BY_NAME["switch"]
OP_CASE = OPCODE_BY_NAME["case"]
OP_MULTI_CASE = OPCODE_BY_NAME["multi_case"]

# Expression fields: code -> (name, extra operands: "" | "w" | "ww" | "e").
FIELDS: dict[int, tuple[str, str]] = {
    0x00: ("col", ""), 0x01: ("hard_dec", ""), 0x02: ("hard_col", ""),
    0x03: ("hit", ""), 0x04: ("hit_by", ""), 0x05: ("anim", ""),
    0x06: ("end_anim", ""), 0x07: ("frame", ""), 0x08: ("end_frame", ""),
    0x09: ("body", ""), 0x0A: ("mark", ""), 0x0B: ("num_track", ""),
    0x0C: ("chrono", ""), 0x0D: ("room_chrono", ""), 0x0E: ("dist", "w"),
    0x0F: ("col_by", ""), 0x10: ("isfound", "e"), 0x11: ("action", ""),
    0x12: ("posrel", "w"), 0x13: ("keyboard_input", ""), 0x14: ("button", ""),
    0x15: ("col_or_col_by", ""), 0x16: ("alpha", ""), 0x17: ("beta", ""),
    0x18: ("gamma", ""), 0x19: ("in_hand", ""), 0x1A: ("hit_force", ""),
    0x1B: ("camera", ""), 0x1C: ("rand", "w"), 0x1D: ("falling", ""),
    0x1E: ("room", ""), 0x1F: ("life", ""), 0x20: ("object", "w"),
    0x21: ("room_y", ""), 0x22: ("test_zv_end_anim", "ww"), 0x23: ("music", ""),
    0x24: ("cvar", "w"), 0x25: ("stage", ""), 0x26: ("thrown", "w"),
}
FIELD_BY_NAME = {name: code for code, (name, _) in FIELDS.items()}


# --------------------------------------------------------------------------
@dataclass
class Expr:
    kind: str                       # "const" | "var" | "field"
    value: int = 0                  # constant / var index / field code
    obj: int | None = None          # field read on another world object
    args: list = field(default_factory=list)   # extra words, or [Expr] for isfound

    def size(self) -> int:
        if self.kind in ("const", "var"):
            return 4
        n = 2 + (2 if self.obj is not None else 0)
        for a in self.args:
            n += a.size() if isinstance(a, Expr) else 2
        return n


@dataclass
class Jump:
    label: str


Operand = Union[int, Expr, Jump, list]


@dataclass
class Instr:
    op: int
    args: list[Operand] = field(default_factory=list)
    obj: int | None = None          # targeted world object (opword & 0x8000)
    labels: list[str] = field(default_factory=list)
    offset: int = -1                # byte offset (set by decode / layout)
    origin: int | None = None       # index in the decoded original (None = added)

    @property
    def name(self) -> str:
        return OPCODES[self.op][0]

    def size(self) -> int:
        n = 2 + (2 if self.obj is not None else 0)
        for a in self.args:
            if isinstance(a, Expr):
                n += a.size()
            elif isinstance(a, list):       # multi_case values
                n += 2 + 2 * len(a)
            else:                           # word or Jump
                n += 2
        return n

    def jump(self) -> Jump | None:
        return next((a for a in self.args if isinstance(a, Jump)), None)


class LifeError(Exception):
    pass


# --------------------------------------------------------------------------
# Decoding
def _s16(data: bytes, p: int) -> int:
    if p + 2 > len(data):
        raise LifeError(f"read past end at byte {p}")
    return struct.unpack_from("<h", data, p)[0]


def _decode_expr(data: bytes, p: int) -> tuple[Expr, int]:
    w0 = _s16(data, p)
    p += 2
    if w0 == -1:
        return Expr("const", _s16(data, p)), p + 2
    if w0 == 0:
        return Expr("var", _s16(data, p)), p + 2
    raw = w0 & 0xFFFF
    obj = None
    if raw & 0x8000:
        obj = _s16(data, p)
        p += 2
    code = (raw & 0x7FFF) - 1
    if code not in FIELDS:
        raise LifeError(f"unknown expression field 0x{code:X} at byte {p - 2}")
    e = Expr("field", code, obj)
    for kind in FIELDS[code][1]:
        if kind == "w":
            e.args.append(_s16(data, p))
            p += 2
        else:
            inner, p = _decode_expr(data, p)
            e.args.append(inner)
    return e, p


def decode(data: bytes) -> list[Instr]:
    """Decode a whole LIFE entry. Branch operands become Jump("L<offset>")."""
    out: list[Instr] = []
    p = 0
    while p < len(data):
        start = p
        word = _s16(data, p) & 0xFFFF
        p += 2
        obj = None
        if word & 0x8000:
            obj = _s16(data, p)
            p += 2
        op = word & 0x7FFF
        if op >= len(OPCODES) or OPCODES[op][1] is None:
            raise LifeError(f"unsupported opcode {op} at byte {start}")
        ins = Instr(op, obj=obj, offset=start, origin=len(out))
        for kind in OPCODES[op][1]:
            if kind == "w":
                ins.args.append(_s16(data, p))
                p += 2
            elif kind == "e":
                e, p = _decode_expr(data, p)
                ins.args.append(e)
            elif kind == "M":
                count = _s16(data, p)
                p += 2
                ins.args.append([_s16(data, p + 2 * i) for i in range(count)])
                p += 2 * count
            elif kind == "J":
                rel = _s16(data, p)
                p += 2
                ins.args.append(rel)        # resolved below (needs the end offset)
        if op in BRANCH_OPS:
            target = p + 2 * ins.args[-1]
            ins.args[-1] = Jump(f"L{target}")
        out.append(ins)
    if p != len(data):
        raise LifeError(f"decoding overran the entry ({p} > {len(data)})")
    # Attach labels to the targeted instructions.
    by_offset = {ins.offset: ins for ins in out}
    for ins in out:
        j = ins.jump()
        if j:
            target = int(j.label[1:])
            if target not in by_offset:
                raise LifeError(f"branch at byte {ins.offset} targets {target}, not an instruction boundary")
            if j.label not in by_offset[target].labels:
                by_offset[target].labels.append(j.label)
    return out


# --------------------------------------------------------------------------
# Encoding
def _encode_expr(e: Expr, out: bytearray) -> None:
    if e.kind == "const":
        out += struct.pack("<hh", -1, e.value)
    elif e.kind == "var":
        out += struct.pack("<hh", 0, e.value)
    else:
        raw = (e.value + 1) | (0x8000 if e.obj is not None else 0)
        out += struct.pack("<H", raw)
        if e.obj is not None:
            out += struct.pack("<h", e.obj)
        for a in e.args:
            if isinstance(a, Expr):
                _encode_expr(a, out)
            else:
                out += struct.pack("<h", a)


def layout(instrs: list[Instr]) -> dict[str, int]:
    """Assign byte offsets; return label -> offset."""
    labels: dict[str, int] = {}
    p = 0
    for ins in instrs:
        ins.offset = p
        for label in ins.labels:
            if label in labels:
                raise LifeError(f"duplicate label {label}")
            labels[label] = p
        p += ins.size()
    return labels


def encode(instrs: list[Instr]) -> bytes:
    labels = layout(instrs)
    out = bytearray()
    for ins in instrs:
        assert len(out) == ins.offset
        end = ins.offset + ins.size()
        word = ins.op | (0x8000 if ins.obj is not None else 0)
        out += struct.pack("<H", word)
        if ins.obj is not None:
            out += struct.pack("<h", ins.obj)
        for a in ins.args:
            if isinstance(a, Expr):
                _encode_expr(a, out)
            elif isinstance(a, list):
                out += struct.pack("<h", len(a))
                out += struct.pack(f"<{len(a)}h", *a)
            elif isinstance(a, Jump):
                if a.label not in labels:
                    raise LifeError(f"undefined label {a.label}")
                delta = labels[a.label] - end
                if delta % 2:
                    raise LifeError(f"odd branch distance to {a.label}")
                rel = delta // 2
                if not -32768 <= rel <= 32767:
                    raise LifeError(f"branch to {a.label} out of range")
                out += struct.pack("<h", rel)
            else:
                out += struct.pack("<h", a)
    return bytes(out)


# --------------------------------------------------------------------------
# Text form. One instruction per line:
#   [label: ...] [obj_N.]mnemonic operand operand ...
# Expressions: #5 (constant), var_12, field, obj_3.field, posrel(1),
# isfound(#13), cvar(36), object(15), test_zv_end_anim(4,2) ...
# Branch operands: @label. multi_case values: [1,2,3]. ';' starts a comment.
def format_expr(e: Expr) -> str:
    if e.kind == "const":
        return f"#{e.value}"
    if e.kind == "var":
        return f"var_{e.value}"
    name = FIELDS[e.value][0]
    prefix = f"obj_{e.obj}." if e.obj is not None else ""
    if e.args:
        inner = ",".join(format_expr(a) if isinstance(a, Expr) else str(a) for a in e.args)
        return f"{prefix}{name}({inner})"
    return prefix + name


def format_instr(ins: Instr, with_offset: bool = False) -> str:
    parts = []
    for a in ins.args:
        if isinstance(a, Expr):
            parts.append(format_expr(a))
        elif isinstance(a, Jump):
            parts.append("@" + a.label)
        elif isinstance(a, list):
            parts.append("[" + ",".join(str(v) for v in a) + "]")
        else:
            parts.append(str(a))
    head = (f"obj_{ins.obj}." if ins.obj is not None else "") + ins.name
    text = " ".join([head] + parts)
    labels = "".join(f"{l}: " for l in ins.labels)
    if with_offset:
        return f"{labels}{text}    ; @{ins.offset}"
    return labels + text


def format_script(instrs: list[Instr], with_offsets: bool = True) -> str:
    return "\n".join(format_instr(i, with_offsets) for i in instrs) + "\n"


_TOKEN = re.compile(r"\s*(\[[^\]]*\]|[^\s\[]+)")


def _parse_expr(text: str) -> Expr:
    text = text.strip()
    if text.startswith("#"):
        return Expr("const", int(text[1:], 0))
    m = re.fullmatch(r"var_(-?\d+)", text)
    if m:
        return Expr("var", int(m.group(1)))
    obj = None
    m = re.match(r"obj_(-?\d+)\.(.*)$", text)
    if m:
        obj, text = int(m.group(1)), m.group(2)
    m = re.fullmatch(r"(\w+)(?:\((.*)\))?", text)
    if not m or m.group(1) not in FIELD_BY_NAME:
        raise LifeError(f"bad expression '{text}'")
    code = FIELD_BY_NAME[m.group(1)]
    kinds = FIELDS[code][1]
    raw_args = [] if m.group(2) is None else _split_args(m.group(2))
    if len(raw_args) != len(kinds):
        raise LifeError(f"{m.group(1)} takes {len(kinds)} argument(s)")
    args = [_parse_expr(a) if k == "e" else int(a, 0) for k, a in zip(kinds, raw_args)]
    return Expr("field", code, obj, args)


def _split_args(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for c in text:
        if c == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        depth += c == "("
        depth -= c == ")"
        cur += c
    parts.append(cur)
    return [p.strip() for p in parts if p.strip() != ""] if text.strip() else []


def parse_instr(line: str) -> Instr | None:
    comment = line.split(";", 1)[1] if ";" in line else ""
    line = line.split(";", 1)[0].strip()
    if not line:
        return None
    # "; @N" (written by format_script) marks an instruction of the original
    # script at byte offset N; check_text_patch uses it to track identity.
    source = re.search(r"@(\d+)", comment)
    labels = []
    while True:
        m = re.match(r"([A-Za-z_][\w]*):\s*(.*)$", line)
        if not m or m.group(1).startswith("obj_"):
            break
        labels.append(m.group(1))
        line = m.group(2)
    tokens = [t.strip() for t in _TOKEN.findall(line)]
    if not tokens:
        raise LifeError("label without instruction")
    head = tokens[0]
    obj = None
    m = re.match(r"obj_(-?\d+)\.(\w+)$", head)
    if m:
        obj, head = int(m.group(1)), m.group(2)
    if head not in OPCODE_BY_NAME:
        raise LifeError(f"unknown mnemonic '{head}'")
    op = OPCODE_BY_NAME[head]
    schema = OPCODES[op][1] or ""
    if len(tokens) - 1 != len(schema):
        raise LifeError(f"{head} takes {len(schema)} operand(s), got {len(tokens) - 1}")
    args: list[Operand] = []
    for kind, tok in zip(schema, tokens[1:]):
        if kind == "w":
            args.append(int(tok, 0))
        elif kind == "e":
            args.append(_parse_expr(tok))
        elif kind == "J":
            if not tok.startswith("@"):
                raise LifeError(f"branch operand must be @label, got '{tok}'")
            args.append(Jump(tok[1:]))
        elif kind == "M":
            inner = tok.strip("[]").strip()
            args.append([int(v, 0) for v in inner.split(",")] if inner else [])
    ins = Instr(op, args, obj, labels)
    if source:
        ins.offset = int(source.group(1))
        ins.origin = -1                  # resolved by check_text_patch
    return ins


def parse_script(text: str) -> list[Instr]:
    out = []
    pending: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.split(";", 1)[0].strip()
        if re.fullmatch(r"([A-Za-z_]\w*:\s*)+", stripped) and not stripped.startswith("obj_"):
            pending += [l.strip() for l in stripped.split(":") if l.strip()]
            continue
        try:
            ins = parse_instr(line)
        except LifeError as e:
            raise LifeError(f"line {n}: {e}") from None
        if ins:
            ins.labels = pending + ins.labels
            pending = []
            out.append(ins)
    if pending:
        raise LifeError(f"label(s) {pending} at end of script")
    return out


# --------------------------------------------------------------------------
# Control flow
def label_index(instrs: list[Instr]) -> dict[str, int]:
    return {l: k for k, x in enumerate(instrs) for l in x.labels}


def successors(instrs: list[Instr], i: int, index: dict[str, int] | None = None) -> list[int]:
    """Indices of the possible next instructions of instrs[i] (-1 = leaves)."""
    ins = instrs[i]
    if index is None:
        index = label_index(instrs)
    if ins.op in (OP_END, OP_RETURN):
        return [-1]
    nxt = [i + 1] if i + 1 < len(instrs) else [-1]
    j = ins.jump()
    if ins.op == OP_GOTO:
        return [index[j.label]]
    if j:
        return nxt + [index[j.label]]
    return nxt


def backward_branches(instrs: list[Instr]) -> list[tuple[int, int]]:
    """(source index, target index) for every branch whose target is not after it."""
    index = label_index(instrs)
    out = []
    for i, ins in enumerate(instrs):
        j = ins.jump()
        if j and index[j.label] <= i:
            out.append((i, index[j.label]))
    return out


def effective_successors(instrs: list[Instr]) -> dict[int, set]:
    """For every original instruction (by origin): the original instructions
    (or "exit") it can reach next when paths through added instructions are
    collapsed. Equal to the plain successors when nothing was added."""
    index = label_index(instrs)
    succ = [successors(instrs, i, index) for i in range(len(instrs))]
    out: dict[int, set] = {}
    for i, ins in enumerate(instrs):
        if ins.origin is None:
            continue
        found, seen, stack = set(), set(), list(succ[i])
        while stack:
            k = stack.pop()
            if k == -1:
                found.add("exit")
            elif instrs[k].origin is not None:
                found.add(instrs[k].origin)
            elif k not in seen:
                seen.add(k)
                stack += succ[k]
        out[ins.origin] = found
    return out


@dataclass
class PatchReport:
    changed_flow: list[int]          # origins whose effective successors changed
    unexpected_flow: list[int]       # ... and were not declared as intended
    removed: list[int]               # original instructions no longer present
    new_backward: list[tuple]        # (source, target) new backward branches
    added: int                       # number of added instructions

    @property
    def ok(self) -> bool:
        return not self.unexpected_flow and not self.new_backward


def check_patch(original: list[Instr], patched: list[Instr],
                intended: set[int] = frozenset(), allow_removed: set[int] = frozenset()) -> PatchReport:
    """Compare a patched script with its original (both as Instr lists; the
    patched list keeps `origin` on unchanged instructions). Flow changes are
    allowed only at the `intended` origins. Any new backward branch (a branch
    to itself or an earlier instruction that the original did not have) is
    reported: it could create a loop the original game never runs."""
    before = effective_successors(original)
    after = effective_successors(patched)
    present = {i.origin for i in patched if i.origin is not None}
    removed = sorted(set(before) - present)
    changed = sorted(o for o in after if after[o] != before.get(o))
    unexpected = [o for o in changed if o not in intended]
    unexpected += [o for o in removed if o not in allow_removed and o not in unexpected]
    old_back = {(original[s].origin, original[t].origin) for s, t in backward_branches(original)}
    new_back = []
    for s, t in backward_branches(patched):
        key = (patched[s].origin, patched[t].origin)
        if None in key or key not in old_back:
            new_back.append((s, t, format_instr(patched[s])))
    return PatchReport(changed, sorted(unexpected), removed, new_back,
                       sum(1 for i in patched if i.origin is None))


def check_text_patch(original: list[Instr], patched: list[Instr],
                     intended_offsets: set[int] = frozenset()) -> PatchReport:
    """check_patch for an edited text listing: instructions that kept their
    "; @offset" comment are matched to the original by that offset."""
    by_offset = {ins.offset: ins.origin for ins in original}
    for ins in patched:
        if ins.origin == -1:
            if ins.offset not in by_offset:
                raise LifeError(f"'; @{ins.offset}' does not match an original instruction")
            ins.origin = by_offset[ins.offset]
    seen = [i.origin for i in patched if i.origin is not None]
    if len(seen) != len(set(seen)):
        raise LifeError("an original instruction ('; @offset') appears twice")
    intended = {by_offset[o] for o in intended_offsets if o in by_offset}
    return check_patch(original, patched, intended)


# --------------------------------------------------------------------------
# Operand sites: byte positions of every operand word, for in-place patching.
@dataclass
class Site:
    offset: int        # byte offset of the word in the script
    value: int
    kind: str          # "target" (instruction object), "word" (plain operand #i),
                       # "expr_obj" (object of a field read), "expr_arg" (extra word
                       # of a field such as object(X)), "const", "var", "case_value"
    detail: str = ""   # field name / operand index


def _expr_sites(e: Expr, p: int, out: list[Site], parent: str = "") -> int:
    if e.kind in ("const", "var"):
        out.append(Site(p + 2, e.value, e.kind, parent))   # parent: e.g. "isfound"
        return p + 4
    p += 2
    name = FIELDS[e.value][0]
    if e.obj is not None:
        out.append(Site(p, e.obj, "expr_obj", name))
        p += 2
    for a in e.args:
        if isinstance(a, Expr):
            p = _expr_sites(a, p, out, name)
        else:
            out.append(Site(p, a, "expr_arg", name))
            p += 2
    return p


def operand_sites(ins: Instr) -> list[Site]:
    """Requires ins.offset (from decode or layout)."""
    out: list[Site] = []
    p = ins.offset + 2
    if ins.obj is not None:
        out.append(Site(p, ins.obj, "target", ins.name))
        p += 2
    for i, a in enumerate(ins.args):
        if isinstance(a, Expr):
            p = _expr_sites(a, p, out)
        elif isinstance(a, list):
            p += 2
            for v in a:
                out.append(Site(p, v, "case_value", ins.name))
                p += 2
        elif isinstance(a, Jump):
            p += 2
        else:
            out.append(Site(p, a, "case_value" if ins.op == OP_CASE else "word", f"{ins.name}#{i}"))
            p += 2
    return out
