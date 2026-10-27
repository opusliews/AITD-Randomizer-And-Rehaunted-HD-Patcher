"""One-off edit (2026-10-17): option --visible-items in generate.py, walkthrough.py, verify_seed.py,
reproduce.py (Research/VisibleItems_Proposal.md). Running it twice fails on purpose."""
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
    ('VERSION = "v12 (2026-10-16)"', 'VERSION = "v13 (2026-10-17)"'),
    ('''                "enemy_drop": "Enemy drop", "extra_spot": "Search (extra spot)"}''',
     '''                "enemy_drop": "Enemy drop", "extra_spot": "Search (extra spot)", "world": "In plain sight"}
# Option Shuffle Visible Items: names of the touch locations (contact zones use the user's zone names)
WORLD_DESC = {"P:17": "Floor", "P:25": "Against the wall", "P:96": "Floor", "P:148": "Floor",
              "P:205": "Wedge by the barrels"}'''),
    ('''def set_cap(slots, max_per):''', '''def world_slots():
    """Option Shuffle Visible Items (user, 2026-10-16): the logic's contact and touch slots, one
    position per world location, exactly one item each (Generated/VisibleItems/placement.py).
    The hook altar is one location with a contact zone (F6:R6:HC81) and a touch pickup (P:232):
    P:232 becomes an empty alias, so the logic gives the altar's item once. `sites` (the contact
    zones' found operands) are for verify_seed.py; the patch itself is VisibleItems/mechanics.py."""
    sys.path.insert(0, str(GEN / "VisibleItems"))
    import placement as VIS
    contact = {s["slot_id"]: {i["obj"]: [dict(x, life=x.get("life", s.get("life"))) for x in i["sites"]]
                              for i in s["items"]}
               for s in json.loads((CAT / "search_slots.json").read_text(encoding="utf-8"))["slots"]
               if s["mechanism"] == "contact"}
    by_slot = defaultdict(list)
    for sp in VIS.world_spots():
        by_slot[sp["slot_id"]].append(sp)
    out = []
    for sid, sps in by_slot.items():
        items = [sp["vanilla_item"] for sp in sps]
        out.append({"id": sid, "family": "world", "items": items, "world": [sp["id"] for sp in sps],
                    "sites": {i: contact.get(sid, {}).get(i, []) for i in items},
                    "positions": len(items), "cap": len(items), "min": len(items)})
    out.append({"id": "P:232", "family": "world", "items": [], "world": [], "sites": {},
                "positions": 0, "cap": 0, "min": 0})
    return out


def set_cap(slots, max_per):'''),
    ('''    for x in slots:
        if x["family"] in ("extra_spot", "enemy_drop"):
            x["positions"] = x["cap"] = max_per
            continue''', '''    for x in slots:
        if x["family"] == "world":            # exactly one item per world location
            continue
        if x["family"] in ("extra_spot", "enemy_drop"):
            x["positions"] = x["cap"] = max_per
            continue'''),
    ('''        if s["family"] in ("enemy_drop", "extra_spot"):
            continue                  # these are built below, not grown''',
     '''        if s["family"] in ("enemy_drop", "extra_spot", "world"):
            continue                  # built below (world locations: VisibleItems/mechanics.py)'''),
    ('''def patch(slots, placement, key_names_objs=None, doors=None):''',
     '''def patch(slots, placement, key_names_objs=None, doors=None, visible=None):'''),
    ('''    report[TOILET_LIFE] = dict(report.get(TOILET_LIFE, {}), **add_toilet_message(entries))
    if doors is not None:                 # More Locked Doors: key and lock scripts are appended
        keys, key_recs, door_objs = doors
        report["locked_doors"] = locked_doors.add_scripts(L, entries, key_recs, keys, door_objs)''',
     '''    report[TOILET_LIFE] = dict(report.get(TOILET_LIFE, {}), **add_toilet_message(entries))
    if visible is not None:               # Shuffle Visible Items: OBJETS moves + spot scripts
        sys.path.insert(0, str(GEN / "VisibleItems"))
        import mechanics as VIS_M
        assignment, displaced, vis_objs = visible
        report["visible_items"] = VIS_M.apply(entries, vis_objs, assignment, displaced)
    if doors is not None:                 # More Locked Doors: key and lock scripts are appended
        keys, key_recs, door_objs = doors
        report["locked_doors"] = locked_doors.add_scripts(L, entries, key_recs, keys, door_objs)
    elif visible is not None:             # appended scripts need the padding entry (see locked_doors)
        entries.append(bytearray(L.encode(L.parse_script("endlife\\n"))))'''),
    ('''    ap.add_argument("--max-per-location", type=int, choices=(2, 3), default=None,''',
     '''    ap.add_argument("--visible-items", action="store_true",
                    help="option Shuffle Visible Items: the items lying in the world (tables, floors, the "
                         "bow, the pantry key...) join the shuffle; any item can be shown at any world "
                         "location (Research/VisibleItems_Proposal.md)")
    ap.add_argument("--max-per-location", type=int, choices=(2, 3), default=None,'''),
    ('''    pool = [i for x in slots for i in x["items"]]
''', '''    pool = [i for x in slots for i in x["items"]]
    if a.visible_items:
        wl = world_slots()
        slots = slots + wl
        pool += [i for x in wl for i in x["items"]]
        # the cellar passage: whatever lies at the wedge location releases the barrels when taken
        # (mechanics.py), and it can always be taken there
        for e in edges:
            if e["from"] == "4/0" and e["to"] == "5/3" and "item:205" in e["requires"]:
                e["requires"] = e["requires"].replace("item:205", "true")
                e["expr"] = C.Expr(e["requires"])
'''),
    ('''    pak, report = patch(slots, placement, objs if a.key_names else None, doors)''',
     '''    visible = None
    if a.visible_items:
        assignment = {w: placement[s["id"]][k] for s in slots if s["family"] == "world"
                      for k, w in enumerate(s["world"])}
        displaced = {i for s in slots if s["family"] == "world" for i in s["items"]} - set(assignment.values())
        visible = (assignment, displaced, objs)
    pak, report = patch(slots, placement, objs if a.key_names else None, doors, visible)'''),
    ('''    if doors:                                            # new key records + locked door leaves''',
     '''    if doors or a.visible_items:                         # new key records, door leaves, moved items'''),
    ('''                    "locked_doors": a.locked_doors or None,''',
     '''                    "locked_doors": a.locked_doors or None, "visible_items": a.visible_items,'''),
    ('''    desc_of = lambda sid: desc.get({"H:117": "F2:R0:HC18"}.get(sid, sid))''',
     '''    desc.update(WORLD_DESC)
    desc_of = lambda sid: desc.get({"H:117": "F2:R0:HC18"}.get(sid, sid))'''),
    ('''             "the hidden library book. Contact slots and floor pickups are vanilla. "''',
     '''             "the hidden library book. "
             + ("Visible items: everything lying in the world is shuffled too (any item can be shown at any "
                "world location; each holds exactly one). " if a.visible_items else
                "Contact slots and floor pickups are vanilla. ") +'''),
    ('''    for s in sorted(slots, key=lambda s: (where(s["id"]) or "", s["id"])):
        lines.append(''', '''    for s in sorted(slots, key=lambda s: (where(s["id"]) or "", s["id"])):
        if s["family"] == "world" and not s["positions"]:
            continue                      # P:232, the altar's touch side (alias of F6:R6:HC81)
        lines.append('''),
])

edit("walkthrough.py", [
    ('''                        "direct_pickup": "Pick up from the floor"}.get(fam, "Search the spot")''',
     '''                        "direct_pickup": "Pick up from the floor", "world": "Take it"}.get(fam, "Search the spot")'''),
    ('''                            "direct_pickup": "Pick up from the"}.get(fam, "Search the")''',
     '''                            "direct_pickup": "Pick up from the", "world": "Take from the"}.get(fam, "Search the")'''),
])

edit("verify_seed.py", [
    ('''for s in G.load_slots():''', '''world = [w for w in G.world_slots() if w['id'] in pl]   # option Shuffle Visible Items
for s in G.load_slots() + world:'''),
    ('''zones={z["zone_id"]: z''', '''if world and pl.get("P:205", [205])[0] != 205:      # LIFE 550 path 2 offers the wedge-spot item
    expect[550][("found", pl["P:205"][0])] += 1
zones={z["zone_id"]: z'''),
])

edit("reproduce.py", [
    ('''    if opts.get("forced_max_per_location"):''', '''    if opts.get("visible_items"):
        cmd += ["--visible-items"]
    if opts.get("forced_max_per_location"):'''),
])
print("ok")
