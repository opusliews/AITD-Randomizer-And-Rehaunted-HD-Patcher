"""Binary patches for the vanilla DOS executable INDARK.EXE (GOG release).

  python vanilla_exe.py SOURCE_EXE OUTPUT_EXE [--max-objects N] [--items-dont-block-push] [--search-hint]
                        [--controls]

Only the known GOG build is patched (SHA-256 below); every patched location
is checked against its original bytes first. Evidence and addresses:
Research/VanillaExe_Ghidra.md (Ghidra 12.1.4 decompilation, 2026-10-15).

Patches:
  --max-objects N  raise the world-object table from 300 to N records
                   (52 bytes each). Three constants hold the 300:
                     - farmalloc(0x3CF0) of the table (12c8:023f, push imm16)
                     - save-block 6 size 15600 (DS:0x61E, dword)
                     - FUN_1854_011e loop `cmp dx, 300` over all records: now
                       `cmp dx,[ab52]` (the real count). It counts the objects of
                       a room for drop's limit of 47; with a constant bound the
                       zeroed unused slots count as attic (floor 0 room 0)
                       objects and drops in the attic fail ("There is no room").
                   Saves made with a patched exe have a larger block 6 and do
                   not load in an unpatched exe (and vice versa).
  --items-dont-block-push
                   takable items (AF_FOUNDABLE 0x80) no longer block pushing
                   furniture. CheckObjectCol (1d8a:017f) is called with the
                   moving actor (DS:83F7) for movement and with the pushed
                   object only by the push check (19d9:0714); when the index
                   is not the moving actor it now skips takable actors. The
                   room comes from merging its two identical "record a
                   collision" blocks (1d8a:0213 / 1d8a:0246).
  --search-hint    an outlined "?" near the bottom right while the player is
                   within 1000 units (Manhattan, XZ) of a type-9 hard-collision
                   zone (the searchable zones), like ReHaunted's magnifier.
                   Code: asm/search_hint.asm (built by asm/build_search_hint.py),
                   appended as a new segment after the image; the 0x80-byte
                   initial stack moves after it (header SS). The text overlay
                   1f84:0451 (FITD drawTextOverlay) jumps to it from its
                   epilogue 1f84:06ad; three relocation entries are added.
  --controls       keyboard + mouse controls (the ReHaunted option's scheme): W/A/S/D, Shift
                   run, E/C/R/J held actions, T/G throw/drop, mouse fight and aiming, Q quick
                   turn, left click in the book/picture/item-found screens; the S sound toggle
                   is removed. Code: asm/controls.asm (built by asm/build_controls.py), appended
                   as another segment (after the hint's, if any); eight hooks
                   (Research/VanillaControls_Design.md).
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

GOG_SHA256 = "2f2c0c27aa84fc10958ac10ab77a804cc500b531fac14bab7d7613064a874df1"
RECORD = 52
VANILLA_MAX = 300

# (file offset, original bytes, builder(N) -> new bytes, description)
OBJECT_LIMIT = [
    (0x4AC1, bytes.fromhex("f03c"), lambda n: struct.pack("<H", n * RECORD),
     "12c8:023f push 3CF0h: farmalloc size of the object table"),
    (0x1B6DE, bytes.fromhex("f03c0000"), lambda n: struct.pack("<I", n * RECORD),
     "DS:061E save-block 6 size (object table)"),
    (0xA30C, bytes.fromhex("81fa2c01"), lambda n: bytes.fromhex("3b1652ab"),
     "1854:01cc cmp dx,300 -> cmp dx,[ab52] (object count) in FUN_1854_011e, the per-room "
     "object count that drop (1854:0739) limits to 47; unused table slots read as floor 0 room 0"),
]


# 1d8a:017f CheckObjectCol, file offset = 0xF4A0 + segment offset
ITEMS_DONT_BLOCK_PUSH = [
    (0xF4A0 + 0x1B8, bytes.fromhex("8b46fe"), bytes.fromhex("e98d00"),
     "1d8a:01b8 mov ax,[bp-2] -> jmp 0248 (the check; the mov is redone there)"),
    (0xF4A0 + 0x246,
     bytes.fromhex("8bc6d1e0c41ef98303d826897f7e4683fe037507b803005f5ec9cb"),
     bytes.fromhex("ebcb"            # 0246 jmp 0213   (shared record-collision block)
                   "8b4606"          # 0248 mov ax,[bp+6]      index argument
                   "3b06f783"        # 024b cmp ax,[83f7]      the moving actor?
                   "7408"            # 024f je 0259            yes: unchanged behaviour
                   "26f747048000"    # 0251 test es:[bx+4],80h loop actor takable?
                   "7508"            # 0257 jnz 0261           yes: skip it (next actor)
                   "8b46fe"          # 0259 mov ax,[bp-2]      displaced instruction
                   "e95cff"          # 025c jmp 01bb
                   "9090"),          # 025f unreachable
     "1d8a:0246 duplicate block -> jmp 0213 + takable-item check"),
]


# asm/search_hint.asm, assembled by asm/build_search_hint.py (which checks this copy)
SEARCH_HINT_CODE = bytes.fromhex(
    "893efd628976faeb078b46fa5f5ec9cb833ec2060075f28b1eac060bdb78ea69dba00081c30e8c8b470803470ad1f8"
    "8946fe8b4710034712d1f88946fc8b47300bc078c5c1e002c41ef20603d826c41f26031f268b0f83c302e3ae26837f"
    "0e0975378b46fe268b172bd07f0a262b47028bd07f0233d281fae8037d1d8b46fc268b77082bf07f0a262b470a8bf0"
    "7f0233f603d681fae8037c0883c310e2bde968ffb80000e87300be2c012e8a44019805aa008bd02e8a0498052f01e8"
    "440083c60281fe3c0172e3b81000e84d00b82f01baaa00e82c00c746fa0100b82e013b06fb627d03a3fb62b838013b"
    "06ff627e03a3ff62b8aa003b06fd627d03a3fd62e907ff0ebb3c0153ff36907cff368e7c52509a1200000083c40cc3"
    "50ff36a288ff36a0889a1d01000083c406c3ffff00ff01ffff000100ff01000101013f00")
EXE_HEADER = 0x1C00                     # file offset of the load image (segment 0 = Ghidra 1000)

# asm/controls.asm, assembled by asm/build_controls.py (which checks this copy)
CONTROLS_CODE = bytes.fromhex(
    "eb15e9a900e96503e98103e95a04e9ad04e9c604e9df048adc80e37f33ff2e3a9d110574084783ff0f72f3eb538bcfbb"
    "0100d3e3f6c48075132e851e3a0575052e091e3c052e091e3a05eb07f7d32e211e3a05803ea87c00752683ff03771750"
    "2e8b1e3a05e823008a1ea07c80e3f00ad8881ea07c5883ff0b7305ea3d020718f706be7cffffeade01071833c0f7c301"
    "0874020c01f7c3041074020c02f7c3022074020c04f7c3084074020c08c35053515256062eff064405e84c002ea34205"
    "2e891e4005fa2e8b1e3c052ec7063c050000fb2e891e3e05f7c3000474082ea144052ea346052e8b1e3a0583e30fe89a"
    "ff0906ac8be86700075e5a595b58833eae8b00ea9b002d035152562e803e490500751533c0cd332ec60649050283f8ff"
    "75062ec60649050133f633db2e803e4905017525b8050033dbcd330bdb740383ce01b80500bb0100cd330bdb740383ce"
    "02b80300cd3383e3038bc65e5a59c30bff7407833eae06007504e81701c32ea048053c01740a3c0274163c037429eb4b"
    "2ea13a052e85064a057539e8f600eb3b2e8b1e40050bdb7505e8e800eb2de8f1002ea34c05eb1d2ef70640050200740f"
    "e80a012e3b064e057505e89f01eb05e8c200eb07c706aa8b0100c3833eaa8b0075f8833e06070075f12e8b1e3e05be20"
    "052e8b040bc0742885d8741f8bc82e8b4402e8f30072142ec6064805012e890e4a052ec7064c05ffffebb983c604ebd1"
    "b80002f7c300017509b80004f7c300027404e8f500c32e8b1e42050bdb7454e88b008bc8be32052e8b0483f8ff74203b"
    "c1740583c602ebeff7c3020074352e890e4e052ec606480503e80001e965ff833e94ab027508b81000e87c0072152ec6"
    "064805022e8b1e4005e816002ea34c05e941ffc32ec6064805002ec7064c05ffffc3f606b67c04750db80800f7c30100"
    "7510b80100c3b80400f7c301007503b80200c36bc034c41e4eab03d8c35306a194ab0bc07809e8eaff268b470eeb03b8"
    "ffff075bc3a354ab529ae01f8f0a83c402c70654ab0000c353518bc8b80200e8c1ff26854f0c741e833e94ab02750bc4"
    "1e8b8326398fb40074088bc1ba0200e8c3ff595bf8c3595bf9c38bc8a194ab83f80274140bc078108bd0e886ff26854f"
    "0c74058bc1e89dffc35006a1aa060bc07816e86eff268b070bc0780c69d8a00081c30e8c0758f8c30758f9c333c02ef7"
    "06400501007401402ea34c05c32e803e480500740c2ea14c0583f8ff74035ec9cbf706ac8b0400eaf4038f0a505306a1"
    "f7832e3b065005752d2e8b1e44052e2b1e540583fb0177172e8b1e44052e891e540569d8a00081c30e8ce88400eb6e2e"
    "c7065005ffff2e8b1e46052e3b1e44057561e864ff725c6906f783a000050e8c3bc3754fc7477400002ec7064605ffff"
    "8b472a05000225ff032ea35205531e8d476a506a242eff365205ff772a9a05003e1483c40a5bc747720200a1f7832ea3"
    "50052ea144052ea35405e81400075b585ec9cb075b58f706ac8b0400ea5900a60c531e8d476a509a82003e1483c4045b"
    "89472a837f6e00750e2ea1520589472a2ec7065005ffffc35053a1f7832e3b065005751469d8a00081c30e8cc7477400"
    "005b58ea0e0da60cf706ac8b01007421f606b67c02741a69d8a00081c30e8c837f74007c0cc7477405005b58ea2302a6"
    "0c5b58f706ac8b0100eac901a60c5053e845fca901007406c706ae8b1c005b58833eae8b01eaaa0f840f5053e829fca9"
    "01007406c706aa8b01005b58833ea88b00ea840454085053e80dfca901005b587405ea991b8f0a833eaa7c00ea971b8f"
    "0a111e1f20122e132414221048504b4d1000400020008000400000018000200000000c006d011d00ffff000000000000"
    "000000000000ffff00000000ffff0000ffff00000000")
CONTROLS_ENTRIES = {'found': 17, 'fwd': 11, 'irq': 0, 'kin': 5, 'lire': 14, 'pic': 20, 'play': 2, 'rot': 8}
CONTROLS_RELOCS = [126, 137, 262, 732, 906, 1040, 1087, 1098, 1158, 1199, 1212, 1240, 1268, 1285, 1295]
# (entry, file-relative segment, offset, displaced instruction); Research/VanillaControls_Investigation.md
CONTROLS_HOOKS = [
    ("irq", 0x1807, 0x01D8, bytes.fromhex("f706be7cffff")),    # IRQ1, scan code in AH
    ("play", 0x032D, 0x0096, bytes.fromhex("833eae8b00")),     # PlayWorld after the input copy
    ("kin", 0x0A8F, 0x03EE, bytes.fromhex("f706ac8b0400")),    # evalVar keyboard_input
    ("rot", 0x0CA6, 0x0053, bytes.fromhex("f706ac8b0400")),    # GereManualRot
    ("fwd", 0x0CA6, 0x01C3, bytes.fromhex("f706ac8b0100")),    # processTrack manual forward
    ("lire", 0x0F84, 0x0FA5, bytes.fromhex("833eae8b01")),     # Lire page loop
    ("found", 0x0854, 0x047F, bytes.fromhex("833ea88b00")),    # FoundObjet prompt loop
    ("pic", 0x0A8F, 0x1B92, bytes.fromhex("833eaa7c00")),      # LIFE PICTURE wait
]
CONTROLS_PATCHES = [
    (0x1C00 + 0x032D * 16 + 0x0138, bytes.fromhex("1f"), bytes.fromhex("ff"),
     "132d:0134 cmp [8bae],1Fh -> cmp [8bae],-1: the S sound-effects toggle removed (S moves)"),
]
HINT_HOOK = 0x0F84, 0x06AD              # text overlay epilogue (file-relative segment)
HINT_HOOK_ORIG = bytes.fromhex("893efd628bc65f5ec9cb")   # mov [62fd],di; mov ax,si; pop di; pop si; leave; retf
HINT_CALLS = (bytes.fromhex("9a1200"), bytes.fromhex("9a1d01"))   # call far 2770:0012 / 2770:011D
FONT_SEG = 0x1770                       # segment 2770 (file-relative)


def append_segment(data: bytearray, code: bytes, code_relocs, hooks, label: str) -> bool:
    """Appends `code` as a new segment after the image (the initial stack, which ends the image,
    moves after it) and writes a far jump to it over each hook.
    code_relocs: offsets in `code` of segment words that need relocation entries.
    hooks: (file-relative segment, offset, original bytes (>= 5), entry offset in `code`)."""
    (nreloc,) = struct.unpack_from("<H", data, 6)
    hdr_par, _, _, ss, sp = struct.unpack_from("<5H", data, 8)
    relo = struct.unpack_from("<H", data, 0x18)[0]
    image = len(data) - EXE_HEADER
    if hdr_par * 16 != EXE_HEADER or image % 16 or ss * 16 + sp != image:
        print(f"{label}: unexpected exe layout (header, image end, initial stack)")
        return False
    for seg, off, orig, _ in hooks:
        at = EXE_HEADER + seg * 16 + off
        if len(orig) < 5 or data[at:at + len(orig)] != orig:
            print(f"{label}: unexpected bytes at {at:#x} ({seg + 0x1000:04x}:{off:04x}): "
                  f"{data[at:at + len(orig)].hex()}")
            return False
    count = len(hooks) + len(code_relocs)
    table_end = relo + 4 * (nreloc + count)
    if table_end > EXE_HEADER or any(data[relo + 4 * nreloc:table_end]):
        print(f"{label}: no free room in the relocation table")
        return False
    new_seg = image // 16
    for seg, off, orig, entry in hooks:
        at = EXE_HEADER + seg * 16 + off
        data[at:at + len(orig)] = bytes([0xEA]) + struct.pack("<HH", entry, new_seg) + bytes([0x90] * (len(orig) - 5))
        print(f"  {at:#07x}  {orig.hex()} -> {data[at:at + len(orig)].hex()}  "
              f"{seg + 0x1000:04x}:{off:04x} jmp far {new_seg + 0x1000:04x}:{entry:04x} ({label})")
    padded = bytes(code) + bytes(-len(code) % 16)
    data += padded + bytes(sp)                          # the code, then the initial stack as before
    new_ss = new_seg + len(padded) // 16
    relocs = [(off + 3, seg) for seg, off, _, _ in hooks] + [(c, new_seg) for c in code_relocs]
    for i, (o, sg) in enumerate(relocs):
        struct.pack_into("<HH", data, relo + 4 * (nreloc + i), o, sg)
    struct.pack_into("<H", data, 6, nreloc + len(relocs))
    struct.pack_into("<HH", data, 2, len(data) % 512, (len(data) + 511) // 512)
    struct.pack_into("<H", data, 0x0E, new_ss)
    print(f"  appended {len(code)} bytes of code as segment {new_seg + 0x1000:04x} "
          f"(file {EXE_HEADER + image:#x}); SS {ss:#x} -> {new_ss:#x}; relocations {nreloc} -> {nreloc + len(relocs)}")
    return True


def add_search_hint(data: bytearray) -> bool:
    """Appends SEARCH_HINT_CODE as a new segment and hooks the text overlay to it."""
    calls = [SEARCH_HINT_CODE.index(c) + 3 for c in HINT_CALLS]    # segment word of each far call
    code = bytearray(SEARCH_HINT_CODE)
    for c in calls:
        struct.pack_into("<H", code, c, FONT_SEG)
    seg, off = HINT_HOOK
    return append_segment(data, code, calls, [(seg, off, HINT_HOOK_ORIG, 0)], "search hint")


def add_controls(data: bytearray) -> bool:
    """The keyboard + mouse controls: the S toggle patch, then CONTROLS_CODE and its hooks."""
    if not apply(data, CONTROLS_PATCHES, "controls"):
        return False
    hooks = [(seg, off, orig, CONTROLS_ENTRIES[name]) for name, seg, off, orig in CONTROLS_HOOKS]
    return append_segment(data, CONTROLS_CODE, CONTROLS_RELOCS, hooks, "controls")


def apply(data: bytearray, patches, label: str) -> bool:
    for off, orig, new, desc in patches:
        if data[off:off + len(orig)] != orig:
            print(f"{label}: unexpected bytes at {off:#x} ({desc}): {data[off:off + len(orig)].hex()}")
            return False
        if len(new) != len(orig):
            print(f"{label}: patch size mismatch at {off:#x}")
            return False
    for off, orig, new, desc in patches:
        data[off:off + len(new)] = new
        print(f"  {off:#07x}  {orig.hex()} -> {new.hex()}  {desc}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--max-objects", type=int)
    ap.add_argument("--items-dont-block-push", action="store_true")
    ap.add_argument("--search-hint", action="store_true")
    ap.add_argument("--controls", action="store_true")
    a = ap.parse_args()

    data = bytearray(a.source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != GOG_SHA256:
        print(f"not the known GOG INDARK.EXE (sha256 {digest}); nothing written")
        return 1
    print(f"source {a.source}: GOG INDARK.EXE, sha256 {digest}")

    if a.max_objects is not None:
        n = a.max_objects
        # far heap block < 64 KiB; the save-block size and loop are 16-bit
        if not VANILLA_MAX <= n <= 0xFFFF // RECORD:
            print(f"--max-objects must be {VANILLA_MAX}..{0xFFFF // RECORD}")
            return 1
        for off, orig, build, desc in OBJECT_LIMIT:
            if data[off:off + len(orig)] != orig:
                print(f"unexpected bytes at {off:#x} ({desc}): {data[off:off + len(orig)].hex()}")
                return 1
            new = build(n)
            data[off:off + len(new)] = new
            print(f"  {off:#07x}  {orig.hex()} -> {new.hex()}  {desc}")

    if a.items_dont_block_push and not apply(data, ITEMS_DONT_BLOCK_PUSH, "items-dont-block-push"):
        return 1

    if a.search_hint and not add_search_hint(data):
        return 1

    if a.controls and not add_controls(data):
        return 1

    a.output.write_bytes(bytes(data))
    print(f"wrote {a.output}: sha256 {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
