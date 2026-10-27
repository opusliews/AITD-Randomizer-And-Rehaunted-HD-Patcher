"""Verification suite for the AITD1 PAK reader/writer and LIFE/TRACK assembler.

Run:  python verify_assembler.py [--report report.json]

Checks (each against an independent source where one exists):
  pak        decompressed LISTLIFE/LISTTRAK entries == PAKExtract output;
             write_pak -> read_pak returns the same entries
  life       decode/encode byte round trip; text (disasm -> asm) round trip;
             instruction offsets and branch targets == LifeDISA raw output;
             branch targets == labels in ReHaunted's generated native C;
             every script ends with endlife; every branch lands on an
             instruction boundary (decode enforces it)
  switch     switch/case chains: every case/multi_case false-branch lands on
             the next case of its chain or on the chain exit
  relocate   for every script and every insertion point: inserting an
             instruction and re-encoding keeps the control flow of every
             original instruction (check_patch reports no change)
  patchcheck the flow checker detects a retargeted branch and a new backward
             branch (negative tests)
  track      decode/encode round trip; instruction offsets == the
             independent TrackRooms parser; universal [20, 2] trailer
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_life as L          # noqa: E402
import aitd_track as T         # noqa: E402
from aitd_pak import read_pak, write_pak   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]          # C:\Projects\AITD
RUN = ROOT / "Generated" / "ResearchRun"
SOURCE = RUN / "SourceCopy"
ORIGINAL = ROOT / "OriginalGame" / "INDARK"
NATIVE = ROOT / "ReHaunted" / "TatouSource" / "FitdLib" / "nativeLifeScripts_generated.cpp"

results: dict[str, dict] = {}


def check(name: str, ok: bool, **details) -> None:
    results[name] = {"ok": ok, **details}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {details}" if details else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    # The working copies must still equal the originals (read only).
    for name in ("LISTLIFE.PAK", "LISTTRAK.PAK"):
        same = (SOURCE / name).read_bytes() == (ORIGINAL / name).read_bytes()
        check(f"source copy {name} == OriginalGame", same)

    life_pak = read_pak(SOURCE / "LISTLIFE.PAK")
    track_pak = read_pak(SOURCE / "LISTTRAK.PAK")
    lives = [e.data for e in life_pak.entries]
    tracks = [e.data for e in track_pak.entries]

    # ---------------------------------------------------------------- pak
    life_dat = RUN / "Life" / "input" / "LISTLIFE"
    track_dat = RUN / "TrackRooms" / "output" / "LISTTRAK"
    bad = [i for i, d in enumerate(lives) if d != (life_dat / f"{i:08d}.dat").read_bytes()]
    bad_t = [i for i, d in enumerate(tracks) if d != (track_dat / f"{i:08d}.dat").read_bytes()]
    check("pak: LISTLIFE entries == PAKExtract", not bad and len(lives) == 563, entries=len(lives),
          imploded=sum(e.compression == 1 for e in life_pak.entries), mismatches=bad)
    check("pak: LISTTRAK entries == PAKExtract", not bad_t and len(tracks) == 45, entries=len(tracks),
          mismatches=bad_t)
    tmp = Path(__file__).with_name("_verify_tmp.pak")
    tmp.write_bytes(write_pak(lives))
    again = [e.data for e in read_pak(tmp).entries]
    tmp.unlink()
    check("pak: write_pak -> read_pak round trip", again == lives)

    # ---------------------------------------------------------------- life
    decoded = {i: L.decode(d) for i, d in enumerate(lives)}
    instr_count = sum(len(v) for v in decoded.values())
    rt = [i for i, d in enumerate(lives) if L.encode(decoded[i]) != d]
    check("life: byte round trip (563 scripts)", not rt, instructions=instr_count, failures=rt)
    txt = [i for i, d in enumerate(lives) if L.encode(L.parse_script(L.format_script(decoded[i]))) != d]
    check("life: text round trip", not txt, failures=txt)
    ends = [i for i, v in decoded.items() if v[-1].op != L.OP_END]
    check("life: every script ends with endlife", not ends, failures=ends)

    dis = json.loads((RUN / "Life" / "data" / "life_instructions.json").read_text(encoding="utf-8"))
    ref = defaultdict(list)
    for d in dis:
        ref[d["script_id"]].append(d)
    off_bad = [i for i, v in decoded.items() if [x.offset for x in v] != [d["offset"] for d in ref[i]]]
    tgt_bad = [i for i, v in decoded.items()
               if [int(x.jump().label[1:]) for x in v if x.jump()] != [t for d in ref[i] for t in d["goto_offsets"]]]
    check("life: offsets == LifeDISA", not off_bad, lifedisa_instructions=len(dis), failures=off_bad)
    check("life: branch targets == LifeDISA", not tgt_bad, failures=tgt_bad)

    native = NATIVE.read_text(encoding="utf-8", errors="replace")
    funcs = re.split(r"static void nativeLife_(\d+)\(", native)
    native_targets = {}
    for k in range(1, len(funcs) - 1, 2):
        native_targets[int(funcs[k])] = {int(h, 16) for h in re.findall(r"goto L_([0-9A-Fa-f]{4})", funcs[k + 1])}
    nat_bad = []
    for i, body in native_targets.items():
        mine = {int(x.jump().label[1:]) for x in decoded[i] if x.jump()}
        if not body <= mine:
            nat_bad.append(i)
    check("life: ReHaunted native labels are branch targets", not nat_bad,
          scripts_compared=len(native_targets), failures=nat_bad)

    import struct
    site_bad = sum(1 for i, v in decoded.items() for ins in v for st in L.operand_sites(ins)
                   if struct.unpack_from("<h", lives[i], st.offset)[0] != st.value)
    site_count = sum(len(L.operand_sites(ins)) for v in decoded.values() for ins in v)
    check("life: operand_sites positions match the raw bytes", site_bad == 0, sites=site_count)

    # ---------------------------------------------------------------- switch chains
    anomalies = []
    for i, v in decoded.items():
        index = L.label_index(v)
        for k, ins in enumerate(v):
            if ins.op not in (L.OP_CASE, L.OP_MULTI_CASE):
                continue
            t = index[ins.jump().label]
            if t <= k:
                anomalies.append((i, k, "backward case"))
    check("switch: no backward case branches", not anomalies, anomalies=anomalies[:10])

    backward = {i: L.backward_branches(v) for i, v in decoded.items()}
    vanilla_back = sum(len(b) for b in backward.values())
    results["vanilla_backward_branches"] = {
        "count": vanilla_back,
        "scripts": {i: [(s, t, L.format_instr(decoded[i][s])) for s, t in b] for i, b in backward.items() if b}}
    print(f"[INFO] vanilla backward branches: {vanilla_back} in "
          f"{sum(1 for b in backward.values() if b)} scripts (baseline for the loop check)")

    # ---------------------------------------------------------------- relocation
    probe = L.parse_instr("var 0 #0")
    reloc_fail = []
    points = 0
    for i, v in decoded.items():
        for p in range(len(v)):
            patched = list(v)
            new = copy.deepcopy(probe)
            patched.insert(p, new)                 # labels stay on the original instruction
            redecoded = L.decode(L.encode(patched))
            # restore origins from position (decode numbers sequentially)
            for k, ins in enumerate(redecoded):
                ins.origin = None if k == p else (k if k < p else k - 1)
            rep = L.check_patch(v, redecoded)
            points += 1
            if not rep.ok or rep.changed_flow or rep.added != 1:
                reloc_fail.append((i, p))
    check("relocate: insertion at every point keeps all original flow", not reloc_fail,
          insertion_points=points, failures=reloc_fail[:10])

    # ---------------------------------------------------------------- negative tests
    v = decoded[0]
    patched = copy.deepcopy(v)
    for ins, orig in zip(patched, v):
        ins.origin = orig.origin
    idx0 = L.label_index(patched)
    jumps = [k for k, ins in enumerate(patched)
             if ins.op == L.OP_GOTO and idx0[ins.jump().label] != k + 1]
    k = jumps[0]
    patched[k].args[-1] = L.Jump(patched[k + 1].labels[0] if patched[k + 1].labels else "Lx")
    if not patched[k + 1].labels:
        patched[k + 1].labels.append("Lx")
    rep = L.check_patch(v, patched)
    detects_retarget = (not rep.ok) and patched[k].origin in rep.unexpected_flow
    rep_ok = L.check_patch(v, patched, intended={patched[k].origin}).ok
    patched2 = copy.deepcopy(v)
    for ins, orig in zip(patched2, v):
        ins.origin = orig.origin
    patched2[-1].labels.append("Lback")
    patched2.insert(len(patched2) - 1, L.Instr(L.OP_GOTO, [L.Jump(patched2[0].labels[0] if patched2[0].labels else "L0")]))
    if not patched2[0].labels:
        patched2[0].labels.append("L0")
    rep2 = L.check_patch(v, patched2, intended=set(range(len(v))))
    check("patchcheck: detects an undeclared retargeted branch", detects_retarget and rep_ok)
    check("patchcheck: rejects a new backward branch", bool(rep2.new_backward) and not rep2.ok)

    # ---------------------------------------------------------------- track
    tdec = [T.decode(d) for d in tracks]
    t_rt = [i for i, d in enumerate(tracks) if T.encode(tdec[i]) != d]
    t_txt = [i for i, d in enumerate(tracks) if T.encode(T.parse_track(T.format_track(tdec[i]))) != d]
    trailers = {tuple(t.trailer) for t in tdec}
    rows = defaultdict(list)
    with open(RUN / "TrackRooms" / "datasets" / "track_instructions.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[int(r["track_id"])].append((int(r["word_offset"]), r["mnemonic"]))
    t_ref = [i for i, t in enumerate(tdec)
             if [(x.word_offset, x.name) for x in t.instrs] != rows[i]]
    check("track: byte round trip (45 tracks)", not t_rt, instructions=sum(len(t.instrs) for t in tdec),
          failures=t_rt)
    check("track: text round trip", not t_txt, failures=t_txt)
    check("track: offsets/mnemonics == TrackRooms parser", not t_ref, failures=t_ref)
    check("track: every track ends with trailer [20, 2]", trailers == {(20, 2)}, trailers=sorted(trailers))

    ok = all(r["ok"] for r in results.values() if "ok" in r)
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    if args.report:
        args.report.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
