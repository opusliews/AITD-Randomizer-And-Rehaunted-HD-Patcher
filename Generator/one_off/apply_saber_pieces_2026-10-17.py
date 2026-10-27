"""One-off edit (2026-10-17): option --saber-pieces (generate.py, reproduce.py). Running it twice fails."""
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]


def edit(name, pairs):
    p = GEN / name
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (name, a[:70], s.count(a))
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


edit("generate.py", [
    ('VERSION = "v14 (2026-10-17)"', 'VERSION = "v15 (2026-10-17)"'),
    ('''def add_key_names(entries: list[bytearray], objs) -> dict:''',
     '''SABER, SABER_BLADE = 38, 41
# Option Saber Pieces (user, 2026-10-13/17; Research/AnnotationReview_2026-10-13.md §3.2): what the
# game sets when the saber breaks (LIFE 49 @612-656), applied at new game when the seed's 50/50 roll
# says broken. Every consumer reads var_38 and the object ids, so nothing else changes; the break
# branch itself checks var_38 = 0, so the blade can never drop a second time.
SABER_BROKEN_LINES = [f"obj_{SABER}.body #42", f"obj_{SABER}.found_body 43", f"obj_{SABER}.found_name 580",
                      f"obj_{SABER}.found_weight 15", "var 38 #1", "var 39 #2"]


def break_saber_at_new_game(entries: list[bytearray]) -> dict:
    """The new-game script (LIFE 562) breaks the saber, right after 'take 2' (as Show Key Names)."""
    before = L.decode(bytes(entries[NEW_GAME_LIFE]))
    out_lines, done = [], False
    for line in L.format_script(before).splitlines():
        out_lines.append(line)
        if not done and line.split("    ; @")[0] == "take 2":
            out_lines += SABER_BROKEN_LINES
            done = True
    if not done:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: 'take 2' not found (saber pieces)")
    patched = L.parse_script("\\n".join(out_lines) + "\\n")
    chk = L.check_text_patch(before, patched, set())
    data = L.encode(patched)
    L.decode(data)
    if not chk.ok or chk.added != len(SABER_BROKEN_LINES) or chk.removed:
        raise SystemExit(f"LIFE {NEW_GAME_LIFE}: saber insertion failed the flow check")
    entries[NEW_GAME_LIFE] = bytearray(data)
    return {"ok": True, "saber_broken": True, "sha256": hashlib.sha256(data).hexdigest()}


def add_key_names(entries: list[bytearray], objs) -> dict:'''),
    ('''def patch(slots, placement, key_names_objs=None, doors=None, visible=None):''',
     '''def patch(slots, placement, key_names_objs=None, doors=None, visible=None, saber_broken=False):'''),
    ('''    if vis_report is not None:
        report["visible_items"] = vis_report''',
     '''    if vis_report is not None:
        report["visible_items"] = vis_report
    if saber_broken:
        report["saber_pieces"] = break_saber_at_new_game(entries)'''),
    ('''    ap.add_argument("--visible-items", action="store_true",''',
     '''    ap.add_argument("--saber-pieces", action="store_true",
                    help="option Saber Pieces: 50/50 per seed, the saber starts broken and its blade is "
                         "shuffled as its own item (the coat-of-arms passage then needs both pieces)")
    ap.add_argument("--visible-items", action="store_true",'''),
    ('''    if a.visible_items:
        wl = world_slots()''',
     '''    saber_broken = bool(a.saber_pieces) and random.Random(f"{a.seed}:saber").random() < 0.5
    if saber_broken:
        pool.append(SABER_BLADE)
        # the saber can't break any more, so the blade's vanilla source (Y:38) gives nothing
        slots = slots + [{"id": "Y:38", "family": "byproduct", "items": [], "sites": {},
                          "positions": 0, "cap": 0, "min": 0}]
        for e in edges:                       # the coat of arms takes both pieces, in either order
            if e["from"] == "3/11" and e["to"] == "5/0" and f"item:{SABER}" in e["requires"]:
                e["requires"] = e["requires"].replace(f"item:{SABER}", f"item:{SABER} & item:{SABER_BLADE}")
                e["expr"] = C.Expr(e["requires"])
    if a.visible_items:
        wl = world_slots()'''),
    ('''    pak, report = patch(slots, placement, objs if a.key_names else None, doors, visible)''',
     '''    pak, report = patch(slots, placement, objs if a.key_names else None, doors, visible, saber_broken)'''),
    ('''                    "locked_doors": a.locked_doors or None, "visible_items": a.visible_items,''',
     '''                    "locked_doors": a.locked_doors or None, "visible_items": a.visible_items,
                    "saber_pieces": a.saber_pieces,'''),
    ('''        "omitted_items": omitted,''', '''        "omitted_items": omitted, "saber_broken": saber_broken,'''),
    ('''        if s["family"] == "world" and not s["positions"]:
            continue                      # P:232, the altar's touch side (alias of F6:R6:HC81)''',
     '''        if not s["positions"] and not s["items"]:
            continue                      # empty aliases: P:232 (the altar's touch side), Y:38 (broken saber)'''),
    ('''             "" if not a.key_names else "Option: keys show their real names from the start (vanilla: \\"A Key\\" until used).",''',
     '''             "" if not a.key_names else "Option: keys show their real names from the start (vanilla: \\"A Key\\" until used).",
             "" if not a.saber_pieces else (
                 "Option Saber Pieces: this seed's saber **starts broken**; its blade is a separate item (see the "
                 "table). The coat of arms in Jeremy's study takes both pieces, in either order."
                 if saber_broken else "Option Saber Pieces: this seed rolled a **whole** saber (50/50)."),'''),
])

edit("reproduce.py", [
    ('''    if opts.get("visible_items"):''', '''    if opts.get("saber_pieces"):
        cmd += ["--saber-pieces"]
    if opts.get("visible_items"):'''),
])
print("ok")
