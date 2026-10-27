"""Visible items: the data changes that make a world location give the item placed there
(2026-10-17; Research/VisibleItems_Proposal.md). Data only (OBJETS.ITD + LISTLIFE.PAK), so the
same patch works in the original DOS game and in the ReHaunted edition.

* The item's OBJETS record moves to the location (placement.pose); the touch-pickup flag
  (AF_FOUNDABLE, 128) only at touch locations (and the hook altar, which is both). A vanilla
  world item placed somewhere else (search spot, container, drop) goes off-world the way vanilla
  stores such items: floor/room -1, position and angles 0, no touch flag.
* Contact locations: the zone script's `found` and its coupled checks follow the new item
  (catalog sites: word / expr_arg / const), so spot events stay at the spot:
  the notebook mantel's werewolf (LIFE 138 @44), the vase table's werewolf jump (LIFE 66 @216).
* Ritual Chamber talisman table (LIFE 186): only `found 110` @52 follows. The talisman body/flag
  lines after it are guarded by "talisman found" and stay (retargeting them would give the new
  item the talisman's model, and could clear a touch-spot talisman's flag). The room chime @328
  (talisman never taken -> rep_sound 89) tests the dud OBJ 2 when the talisman isn't the item
  there: silent (user, 2026-10-16). A talisman lying at another world location runs the chime
  script itself (life_mode 1; test 9 prototype life563_talisman_chime.asm); inside a container or
  search spot it has no actor, so no chime.
* Cellar wedge (P:205, user rule 2026-10-16: whatever replaces the wedge releases the barrels when
  picked up; the wedge found elsewhere does not), only when another item is there:
    - LIFE 437 (the wedge's found-life) case 2048 (taken) -> an action value that never occurs;
    - LIFE 432 (barrel 201's idle script, used only before the roll) starts with "the spot's
      item taken -> roll both barrels exactly as LIFE 437 does";
    - after a roll, LIFE 433 switches barrel 201 to a new copy of the vanilla idle script
      (without that check) instead of 432, so the barrels can never roll twice, whichever path
      rolled them;
    - LIFE 550 path 2 (arriving from the tunnel with the wedge untaken: roll, delete the wedge)
      tests the spot's item, and `delete 205` becomes `found X`: the item is offered to the
      player instead of destroyed. Same size (one opcode + one word): LIFE 550 keeps every
      offset, because ReHaunted's lifeBugfixes.cpp patches it by offset (1810).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, r"C:\Projects\AITD\Generated\Patcher")
import aitd_life as L  # noqa: E402
import placement as P  # noqa: E402

DUD = 2                       # OBJ 2 "Actions": object(2) is always 1
TOUCH_FLAG = 128              # AF_FOUNDABLE
HOOK_ALTAR = "W:232"          # contact zone + touch pickup at one spot
TALISMAN, TALISMAN_SPOT = 110, "W:110"
TALISMAN_LIFE, TALISMAN_TAKEN_GUARD = 186, (56, 70, 78)    # @56 isfound check, @70/@78 obj_110 lines
CHIME_AT = 328                # LIFE 186: if_egal object(110) #0 -> rep_sound 89
WEDGE, WEDGE_SPOT = 205, "W:205"
WEDGE_FOUND_LIFE, WEDGE_TAKEN_CASE = 437, 4          # LIFE 437 @4: case 2048
BARREL_LIFE, BARREL_ROLL_LIFE, BARREL_BACK_AT = 432, 433, 34   # idle; roll; its "life 432" @34
PLAYER_LIFE, PATH2 = 550, (998, 1010, 1022, 1074)     # object / stage / room checks, delete 205
NEVER_ACTION = 32767


def site(entries, life, at, kind, value):
    """Byte offset of the operand `value` of kind `kind` in the instruction at `at`."""
    ins = next(i for i in L.decode(bytes(entries[life])) if i.offset == at)
    hits = [s for s in L.operand_sites(ins) if s.kind == kind and s.value == value]
    if len(hits) != 1:
        raise SystemExit(f"LIFE {life} @{at}: expected one {kind} {value}, found {len(hits)}")
    return hits[0].offset


def put_word(entries, life, off, old, new):
    word = int.from_bytes(entries[life][off:off + 2], "little", signed=True)
    if word != old:
        raise SystemExit(f"LIFE {life} @{off}: expected {old}, found {word}")
    entries[life][off:off + 2] = int(new).to_bytes(2, "little", signed=True)


def apply(entries: list[bytearray], objs: list[dict], assignment: dict[str, int],
          displaced: set[int], spots: list[dict] | None = None, csv_objs: dict | None = None) -> dict:
    """assignment: world location id (W:<vanilla item>) -> item placed there.
    displaced: vanilla world items that ended up in a non-world location (go off-world).
    entries: LISTLIFE entries (bytearrays, patched in place; new scripts appended).
    objs: OBJETS records (aitd_objets dicts, patched in place). Returns a report."""
    spots = spots or P.world_spots()
    csv_objs = csv_objs or P.objects()
    use_cover_model(objs)                 # before the poses: they read the item's model
    by_id = {s["id"]: s for s in spots}
    report = {"moved": {}, "off_world": sorted(displaced), "lives": {}}
    chime_life = None

    for sid, item in assignment.items():
        s = by_id[sid]
        o = objs[item]
        if o["body"] == P.ARROW_BODY:
            cross_arrow(entries, objs, item, report)
        p = P.pose(item, s, csv_objs, body=o["body"])
        o.update(stage=s["floor"], room=s["room"], x=p["x"], y=p["y"], z=p["z"],
                 alpha=p["alpha"], beta=p["beta"], gamma=p["gamma"])
        touch = s["mechanism"] == "touch" or sid == HOOK_ALTAR
        o["flags"] = (o["flags"] & ~TOUCH_FLAG) | (TOUCH_FLAG if touch else 0)
        if item == TALISMAN and sid != TALISMAN_SPOT:
            if chime_life is None:
                chime_life = len(entries)
                entries.append(bytearray(L.encode(L.parse_script(
                    f"if_egal object({TALISMAN}) #0 @Lend\nrep_sound #89 0\nLend: endlife\n"))))
            o["life"], o["life_mode"] = chime_life, 1
        report["moved"][sid] = {"item": item, **{k: p[k] for k in ("x", "y", "z", "alpha", "beta", "gamma", "rule")},
                                "touch": touch}
    for item in displaced:
        o = objs[item]
        o.update(stage=-1, room=-1, x=0, y=0, z=0, alpha=0, beta=0, gamma=0)
        o["flags"] &= ~TOUCH_FLAG

    # contact zones: the pickup and its coupled checks follow the item
    import json
    contact = [x for x in json.loads((P.CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]
               if x["mechanism"] == "contact"]
    life_of = {x["slot_id"]: None for x in contact}
    for slot in contact:
        for it in slot["items"]:
            sid = f"W:{it['obj']}"
            new = assignment.get(sid, it["obj"])
            if new == it["obj"]:
                continue
            for st in it["sites"]:
                life = st.get("life") or slot.get("life") or _slot_life(slot)
                if sid == TALISMAN_SPOT and st["at"] in TALISMAN_TAKEN_GUARD:
                    continue                      # guarded by "talisman found": stays (docstring)
                if st["kind"] in ("word", "expr_arg", "const"):
                    put_word(entries, life, st["offset"], it["obj"], new)
                    report["lives"].setdefault(life, []).append(f"@{st['at']} {it['obj']} -> {new}")
    if assignment.get(TALISMAN_SPOT, TALISMAN) != TALISMAN:
        off = site(entries, TALISMAN_LIFE, CHIME_AT, "expr_arg", TALISMAN)
        put_word(entries, TALISMAN_LIFE, off, TALISMAN, DUD)
        report["lives"].setdefault(TALISMAN_LIFE, []).append(f"@{CHIME_AT} chime silenced (object({DUD}))")

    x = assignment.get(WEDGE_SPOT, WEDGE)
    if x != WEDGE:
        _wedge(entries, x, report)
    if chime_life is not None:
        report["lives"][chime_life] = ["talisman chime script (new)"]
    return report


BODY_PAKS = ("LISTBODY.PAK", "LISTBOD2.PAK")   # Edward's and Emily's model files (the game uses one)


def listbody(name: str = "LISTBODY.PAK") -> bytes:
    """A model file with the randomizer's models appended (placement.CUSTOM_BODIES, from 272: the
    scaled cover rug), then one padding entry (the engine reads one entry fewer, as LISTLIFE).
    Both LISTBODY.PAK (Edward) and LISTBOD2.PAK (Emily) need them: playing Emily, a model only in
    LISTBODY crashed on creation (user, 2026-10-17, References/crash: InitObjet body 272)."""
    from aitd_pak import write_pak
    entries = P.gamedata.pak_entries(name)          # the original file (project copy, or the player's)
    if len(entries) != P.COVER_BODY:
        raise SystemExit(f"{name} has {len(entries)} entries, expected {P.COVER_BODY}")
    added = [P.custom_body(b) for b in sorted(P.CUSTOM_BODIES)]
    return write_pak(entries + added + [added[-1]])     # the last one again as padding


def listbodies() -> dict[str, bytes]:
    return {name: listbody(name) for name in BODY_PAKS}


VASE_BREAK_LIFE, VASE_DROP_AT = 68, 40    # LIFE 68 @40: put_at 53 56 (the vase's contents)


def vase_contents_at_player(entries: list[bytearray]) -> str:
    """The broken vase drops its contents at the player, not at the vase (user, 2026-10-17,
    mechanics test 6): thrown in another room, the vase can land beyond a wall or inside furniture,
    and `put_at X 56` left the items unreachable there. A vanilla flaw (the vase can be carried
    anywhere), so every seed gets it. One operand: the target 56 -> 1 (the player); extra items
    grown into the vase copy this target. Run before the growth edits (vanilla offsets)."""
    off = site(entries, VASE_BREAK_LIFE, VASE_DROP_AT, "word", 56)
    put_word(entries, VASE_BREAK_LIFE, off, 56, 1)
    return f"LIFE {VASE_BREAK_LIFE} @{VASE_DROP_AT}: put_at target 56 -> 1 (contents at the player)"


VASE_ACTION_LIFE, VASE_THROW_AT = 67, 86  # LIFE 67 @86: obj_1.throw 11 4 13 56 0 0 4


def vase_breaks_at_feet(entries: list[bytearray]) -> str:
    """Throwing the vase breaks it at the player's feet (user, 2026-10-17: the remains still hit the
    wall while the contents came to the feet; thrown items also sometimes stop at invisible walls).
    LIFE 67 (the vase's action script), case 512 (throw): `obj_1.throw 11 4 13 56 0 0 4` becomes
    `obj_1.anim_once 11 4` (the same throw animation, then the same next anim) + `drop #56 1`
    (the vase at the player; LIFE `drop` has no animation of its own). The script then gives the
    vase its break script (LIFE 68) as before, which breaks it where it lies, and the contents go to
    the player too (vase_contents_at_player). Run before the growth edits."""
    before = L.decode(bytes(entries[VASE_ACTION_LIFE]))
    lines = L.format_script(before).splitlines()
    n = next(k for k, l in enumerate(lines) if l.endswith(f"; @{VASE_THROW_AT}"))
    if lines[n].split("    ; @")[0] != "obj_1.throw 11 4 13 56 0 0 4":
        raise SystemExit(f"LIFE {VASE_ACTION_LIFE} @{VASE_THROW_AT}: unexpected {lines[n]!r}")
    lines[n:n + 1] = ["obj_1.anim_once 11 4", "drop #56 1"]
    patched = L.parse_script("\n".join(lines) + "\n")
    offs = [i.offset for i in before]
    k = offs.index(VASE_THROW_AT)
    chk = L.check_text_patch(before, patched, {offs[k - 1], VASE_THROW_AT})
    removed = [before[o].offset for o in chk.removed]
    if set(chk.unexpected_flow) - set(chk.removed) or chk.new_backward or removed != [VASE_THROW_AT]:
        raise SystemExit(f"LIFE {VASE_ACTION_LIFE}: vase throw rewrite failed the flow check: {chk}")
    entries[VASE_ACTION_LIFE] = bytearray(L.encode(patched))
    return f"LIFE {VASE_ACTION_LIFE} @{VASE_THROW_AT}: throw -> throw animation + drop at the player"


def cross_arrow(entries: list[bytearray], objs: list[dict], item: int, report: dict) -> None:
    """An arrow placed at a world location shows the cross arrow (P.CROSS_ARROW_BODY); its
    found-life starts with `obj_<item>.body #<plain arrow>`, so once picked up it is the vanilla
    arrow again (drops, throws). LM_BODY also works while the arrow has no actor (inventory)."""
    o = objs[item]
    o["body"] = P.CROSS_ARROW_BODY
    life = o["found_life"]
    before = L.decode(bytes(entries[life]))
    lines = L.format_script(before).splitlines()
    first = lines[0]
    if first.startswith("L"):
        raise SystemExit(f"LIFE {life}: unexpected label on the first line")
    patched = L.parse_script("\n".join([f"obj_{item}.body #{P.ARROW_BODY}"] + lines) + "\n")
    chk = L.check_text_patch(before, patched, set())
    if not chk.ok or chk.removed or chk.new_backward:
        raise SystemExit(f"LIFE {life}: cross-arrow reset failed the flow check")
    entries[life] = bytearray(L.encode(patched))
    report["lives"].setdefault(life, []).append(f"OBJ {item}: cross arrow in the world, plain arrow once found")


def use_cover_model(objs: list[dict]) -> None:
    """The cover shows the new model wherever it lies in the world (also when dropped)."""
    objs[P.COVER]["body"] = P.COVER_BODY


def _slot_life(slot):
    lives = {st.get("life") for it in slot["items"] for st in it["sites"]}
    raise SystemExit(f"{slot['slot_id']}: site without a LIFE number ({lives})")


def _wedge(entries, x, report):
    # 1. the wedge's own release on pickup never fires (it may lie anywhere now)
    off = site(entries, WEDGE_FOUND_LIFE, WEDGE_TAKEN_CASE, "case_value", 2048)
    put_word(entries, WEDGE_FOUND_LIFE, off, 2048, NEVER_ACTION)
    report["lives"].setdefault(WEDGE_FOUND_LIFE, []).append(f"@{WEDGE_TAKEN_CASE} case 2048 -> {NEVER_ACTION}")
    # 2. after any roll, barrel 201 goes back to a copy of the vanilla idle script (no check), so
    #    it can never roll twice; its original idle script is used only before the roll
    idle_copy = len(entries)
    entries.append(bytearray(entries[BARREL_LIFE]))
    off = site(entries, BARREL_ROLL_LIFE, BARREL_BACK_AT, "word", BARREL_LIFE)
    put_word(entries, BARREL_ROLL_LIFE, off, BARREL_LIFE, idle_copy)
    report["lives"].setdefault(BARREL_ROLL_LIFE, []).append(f"@{BARREL_BACK_AT} life {BARREL_LIFE} -> {idle_copy}")
    report["lives"][idle_copy] = [f"copy of the vanilla barrel idle script {BARREL_LIFE} (after the roll)"]
    # 3. barrel 201's idle script (before the roll): the spot's item taken -> roll both barrels
    #    exactly as the wedge's LIFE 437 does
    before = L.decode(bytes(entries[BARREL_LIFE]))
    lines = L.format_script(before).splitlines()
    block = [f"if_egal object({x}) #1 @Lbarrels_idle", "obj_201.test_col 0", "obj_202.test_col 0",
             "obj_201.hit_object 700 5", "obj_202.hit_object 700 5", "obj_201.anim_once 179 -1",
             "obj_202.anim_once 180 -1", "obj_201.life 433", "obj_202.life 435"]
    first = lines[0]
    if first.startswith("L"):
        raise SystemExit(f"LIFE {BARREL_LIFE}: unexpected label on the first line")
    patched = L.parse_script("\n".join(block + [f"Lbarrels_idle: {first}"] + lines[1:]) + "\n")
    chk = L.check_text_patch(before, patched, set())
    if not chk.ok or chk.removed or chk.new_backward:
        raise SystemExit(f"LIFE {BARREL_LIFE}: barrel release insertion failed the flow check")
    entries[BARREL_LIFE] = bytearray(L.encode(patched))
    report["lives"].setdefault(BARREL_LIFE, []).append(f"barrels roll when OBJ {x} is taken")
    # 4. path 2 (back from the tunnel, LIFE 550 MARK 2): test the spot's item, and offer it
    #    (`found X`) instead of `delete 205`. Same size: every LIFE 550 offset is kept.
    before_len = len(entries[PLAYER_LIFE])
    for at, kind in ((PATH2[0], "expr_arg"), (PATH2[1], "expr_obj"), (PATH2[2], "expr_obj")):
        off = site(entries, PLAYER_LIFE, at, kind, WEDGE)
        put_word(entries, PLAYER_LIFE, off, WEDGE, x)
    ins = next(i for i in L.decode(bytes(entries[PLAYER_LIFE])) if i.offset == PATH2[3])
    if ins.name != "delete" or ins.args != [WEDGE]:
        raise SystemExit(f"LIFE {PLAYER_LIFE} @{PATH2[3]}: expected 'delete {WEDGE}'")
    found_op = L.encode(L.parse_script(f"found {x}\n"))
    if len(found_op) != 4:
        raise SystemExit("found is not one opcode + one word")
    entries[PLAYER_LIFE][PATH2[3]:PATH2[3] + 4] = found_op
    after = L.decode(bytes(entries[PLAYER_LIFE]))
    if len(entries[PLAYER_LIFE]) != before_len or bare_at(after, PATH2[3]) != f"found {x}":
        raise SystemExit(f"LIFE {PLAYER_LIFE}: path 2 rewrite changed the size or failed")
    report["lives"].setdefault(PLAYER_LIFE, []).append(
        f"path 2 tests OBJ {x}; @{PATH2[3]} 'delete {WEDGE}' -> 'found {x}' (same size)")


def bare_at(instrs, at):
    ins = next(i for i in instrs if i.offset == at)
    return L.format_instr(ins).split(": ")[-1]
