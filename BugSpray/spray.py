"""The Bug Spray: a new item that kills the Garden spiders (user design 2026-10-28,
Research/BugSpray.md). Every randomized seed, never seed 0.

Vanilla problem: searching the Garden's Center Bed (F3:R4:HC14, LIFE 304 sets var_123) drops six
spiders (OBJ 156-161, LIFE 308-310) into the Garden once (var_122 = 1). They have no death
branch and chase and bite the player whenever he is in the Garden, so the Garden's other spots
and the way from the Garden into the Ballroom can become unusable.

Item: OBJETS record cloned from key 37 (same flags, weight, Use/Throw/Drop actions 0x601: bit 0
"Use" = action 1, bit 9 "Throw" = 512, bit 10 "Drop/Put" = 1024; inventory text 23 + bit), with
its own model (spray_assets.can_body, body CAN_BODY), name text and found-LIFE. Its found-LIFE is
key 37's (LIFE 50: pick up, throw, drop) with "Use" replaced:
- in the Garden (stage 3, room 4) with the spiders down (var_122 == 1): the player switches to
  PLAYER life (as the flask switches him to the drinking LIFE 59);
- anywhere else, or before the spiders appear: a message, and the can stays.
No "already sprayed" variable is needed (all 207 game variables are in use): the can is deleted
when used and only one exists, and var_122 is never reset, so the spiders never come back.

PLAYER life (the drinking LIFE 59 pattern): save the body in var_204, switch to the can-in-hand
body (HELD_BODY), play the spray animation (SPRAY_ANIM, then idle 4); at the same time every
spider switches to FREEZE (no movement, no bite: the player is immune while spraying). When the
animation ends each spider runs its DIE life (the usual monster death: do_real_zv + special 0,
the particle burst), the can is deleted (LM_DELETE also clears the in-inventory flag 0x8000),
the body comes back and the player returns to LIFE 549. The spray sound (SPRAY_SOUND, the user's
recording) plays once when the spray starts.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "Patcher"), str(HERE.parent / "Generator")]

CAN_BODY, HELD_BODY = 275, 276          # VisibleItems/placement.CUSTOM_BODIES (both model files)
CAN_INVENTORY_BODY = 277                # the can at spray_assets.INVENTORY_SCALE (found_body)
SPRAY_ANIM = 305                        # appended to LISTANIM.PAK and LISTANI2.PAK (305 entries each)
TEXT_NAME, TEXT_NOTHING = 1310, 1311
TEXTS = {TEXT_NAME: "A Can of Bug Spray", TEXT_NOTHING: "There is nothing here to spray."}
MODEL_KEY = 37                          # the record and found-LIFE (LIFE 50) the can is cloned from
SPIDERS = range(156, 162)
GARDEN, BALLROOM = "3/4", "3/3"
ARROW_SPOT = "F3:R4:HC14"               # searching it is what drops the spiders
SPIDERS_DOWN = 122                      # var_122: set once by LIFE 304 when the spiders drop in
DEATH_SOUND = 6                         # the monster death sound (giant spider, zombies)
SPRAY_SOUND = 101                       # appended to LISTSAMP.PAK (101 entries): the user's recording
SOUND_FILE = HERE / "spray_sound.voc"   # References/Spray.wav at 11025 Hz (make_spray_sound.py; user pick)
PLAYER_LIFE, IDLE_ANIM, BODY_VAR = 549, 4, 204


def record(objs: list[dict]) -> dict:
    """The can's OBJETS record; found_life is set by add_scripts."""
    rec = dict(objs[MODEL_KEY])
    rec.update(body=CAN_BODY, found_body=CAN_INVENTORY_BODY, found_name=TEXT_NAME, found_flag=0x601)
    return rec


EVENT = "spiders_sprayed"


def logic(edges, wslots, events: dict, man: dict, spray_obj: int, Expr) -> list[str]:
    """The spray in the logic (randomized seeds): event EVENT (the can + the Garden) is needed
    from the Garden into the Ballroom, and for every Garden location except the arrow spot (that
    search is what drops the spiders). The checker can't tell whether the spiders are down yet,
    so it always assumes they are. An event (not just the item) so the walkthrough says to spray
    (Logic/walkthrough_text.json) and the spoiler lists it like the other events."""
    req = f"item:{spray_obj} & reach:{GARDEN}"
    man["events"][EVENT] = {"requires": req, "status": "rule",
                            "evidence": "user 2026-10-28: the Bug Spray kills the Garden spiders"}
    events[EVENT] = Expr(req)
    changed = []
    for e in edges:
        if e["from"] == GARDEN and e["to"] == BALLROOM:
            e["requires"] = f"({e['requires']}) & event:{EVENT}"
            e["expr"] = Expr(e["requires"])
            changed.append(f"edge {GARDEN}->{BALLROOM}")
    for s in wslots:
        if s.get("region") == GARDEN and s["id"] != ARROW_SPOT:
            s["requires"] = f"({s['requires']}) & event:{EVENT}"
            s["expr"] = Expr(s["requires"])
            changed.append(f"slot {s['id']}")
    if not any(c.startswith("edge") for c in changed):
        raise SystemExit(f"bug spray: no logic edge {GARDEN} -> {BALLROOM}")
    return changed


def _lines(L, data: bytes) -> list[str]:
    return [x.split("    ; @")[0] for x in L.format_script(L.decode(data)).splitlines()]


def _assemble(L, text: str, what: str) -> bytes:
    instrs = L.parse_script(text + "\n")
    if L.backward_branches(instrs):
        raise SystemExit(f"bug spray {what}: backward branch")
    data = L.encode(instrs)
    L.decode(data)
    return data


def add_scripts(L, entries: list[bytearray], spray_obj: int, rec: dict) -> dict:
    """Appends the spray's scripts to `entries` (before the padding entry) and sets the record's
    found_life. Returns a report."""
    rep = {}

    def add(name, text):
        n = len(entries)
        entries.append(bytearray(_assemble(L, text, name)))
        rep[name] = n
        return n

    freeze = add("freeze", "anim_once -1 -1\ntrackmode 0 -1\nendlife")
    die = {}
    for k, sp in enumerate(SPIDERS):
        sound = f"sound #{DEATH_SOUND}\n" if k == 0 else ""
        die[sp] = add(f"die_{sp}", f"do_real_zv\nspecial 0\n{sound}delete {sp}\nendlife")
    froze = "\n".join(f"obj_{sp}.life {freeze}" for sp in SPIDERS)
    kill = "\n".join(f"obj_{sp}.life {die[sp]}" for sp in SPIDERS)
    player = add("player", "\n".join([
        f"if_different anim #{SPRAY_ANIM} @Lspraying",
        f"var {BODY_VAR} body",
        f"body #{HELD_BODY}",
        f"anim_once {SPRAY_ANIM} {IDLE_ANIM}",
        f"sound #{SPRAY_SOUND}",
        froze,
        "goto @Lend",
        "Lspraying: if_egal end_anim #1 @Lend",
        kill,
        f"delete {spray_obj}",
        f"body var_{BODY_VAR}",
        f"life {PLAYER_LIFE}",
        "allow_inventory 1",
        "Lend: endlife"]))

    # found-LIFE: key 37's LIFE 50 for the new object, with "Use" (case 1) replaced
    import locked_doors
    key = locked_doors.key_found_script(L, entries, spray_obj)
    lines = _lines(L, L.encode(key))
    i = next(k for k, x in enumerate(lines) if re.sub(r"^L\w+: ", "", x).startswith("case 1 @"))
    if lines[i + 1] != "obj_1.body #12" or lines[i + 2] != f"in_hand {spray_obj}" or not lines[i + 3].startswith("goto @"):
        raise SystemExit(f"bug spray: unexpected key 'Use' branch {lines[i:i + 4]}")
    end = lines[i + 3]
    lines[i + 1:i + 3] = [
        "if_egal obj_1.stage #3 @Lnospray",
        "if_egal obj_1.room #4 @Lnospray",
        f"if_egal var_{SPIDERS_DOWN} #1 @Lnospray",
        f"obj_1.life {player}",
        "allow_inventory 0",
        end,
        f"Lnospray: message {TEXT_NOTHING}"]
    rec["found_life"] = add("found", "\n".join(lines))
    rep["object"] = spray_obj
    return rep


def anim_paks() -> dict[str, bytes]:
    """LISTANIM.PAK (Edward) and LISTANI2.PAK (Emily) with the spray animation appended as
    SPRAY_ANIM, then one padding entry (the engine reads one entry fewer, as LISTLIFE)."""
    import gamedata, spray_assets as S
    from aitd_pak import write_pak
    out = {}
    for name in ("LISTANIM.PAK", "LISTANI2.PAK"):
        ents = gamedata.pak_entries(name)
        if len(ents) != SPRAY_ANIM:
            raise SystemExit(f"{name} has {len(ents)} entries, expected {SPRAY_ANIM}")
        anim = S.spray_anim(ents[IDLE_ANIM], **S.POSE[name])
        out[name] = write_pak(list(ents) + [anim, anim])
    return out


def sample_pak() -> bytes:
    """LISTSAMP.PAK with the spray sound appended as SPRAY_SOUND, then one padding entry (ReHaunted's
    PAK_getNumFiles also counts one entry fewer). Each entry must fit the DOS 64000-byte buffer."""
    import gamedata
    from aitd_pak import write_pak
    ents = gamedata.pak_entries("LISTSAMP.PAK")
    if len(ents) != SPRAY_SOUND:
        raise SystemExit(f"LISTSAMP.PAK has {len(ents)} entries, expected {SPRAY_SOUND}")
    voc = SOUND_FILE.read_bytes()
    if not voc.startswith(b"Creative Voice File\x1a") or len(voc) > 64000:
        raise SystemExit(f"{SOUND_FILE}: not a VOC of at most 64000 bytes")
    return write_pak(list(ents) + [voc, voc])
