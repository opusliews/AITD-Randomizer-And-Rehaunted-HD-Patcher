"""One-off edit (2026-10-16): 3 items per location (growth 1->3, 2-item cascade -> 3) and the
cap-3 fallback in generate.py. Kept for the record; running it twice fails on purpose."""
from pathlib import Path

p = Path(__file__).with_name("generate.py")
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''MAX_PER_LOCATION = 2       # user rule 2026-10-15: every location holds 0, 1 or 2 items
''', '''MAX_PER_LOCATION = 2       # user rule 2026-10-15: every location holds 0, 1 or 2 items
FALLBACK_MAX = 3           # user fallback rule 2026-10-15: cap 3 when the positions run out
''')
rep('''    for x in out:
        grows = len(x["items"]) < MAX_PER_LOCATION and x["family"] in GROWABLE_FAMILIES
        x["positions"] = MAX_PER_LOCATION if grows else len(x["items"])
        x["cap"] = min(x["positions"], MAX_PER_LOCATION)
        x["min"] = 1 if x["family"] in PUT_AT_FAMILIES else 0   # put_at cannot be emptied
    return out
''', '''    for x in out:
        x["min"] = 1 if x["family"] in PUT_AT_FAMILIES else 0   # put_at cannot be emptied
    set_cap(out, MAX_PER_LOCATION)
    return out


def set_cap(slots, max_per):
    """Positions and cap of every slot for a per-location maximum (2, or 3 as the fallback).
    Growable locations grow to the maximum; vanilla multi-item spots keep their positions;
    new places (extra spots, enemy drops) hold up to the maximum."""
    for x in slots:
        if x["family"] in ("extra_spot", "enemy_drop"):
            x["positions"] = x["cap"] = max_per
            continue
        grows = len(x["items"]) < max_per and x["family"] in GROWABLE_FAMILIES
        x["positions"] = max_per if grows else len(x["items"])
        x["cap"] = min(x["positions"], max_per)
''')

rep('''        for k in range(len(s["items"]), len(placement[s["id"]])):
            if placement[s["id"]][k] is not None:
                growth.append((s, placement[s["id"]][0], placement[s["id"]][k]))
''', '''        extras = [i for i in placement[s["id"]][len(s["items"]):] if i is not None]
        if extras:
            growth.append((s, placement[s["id"]], extras))
''')
rep('''    growth = []                       # (slot, vanilla item, added item)''',
    '''    growth = []                       # (slot, its placement, items added beyond the vanilla positions)''')

a = s.index("    # Growth: a second item in a 1-item location.")
b = s.index("    # Many Search Places: an empty zone gets an award block (PoC A pattern).")
NEW_GROWTH = '''    # Growth: items beyond a location's vanilla positions (up to the cap, 2 or 3).
    #   1-item search/container shape "if_egal object(A) #0 @Lmsg / found A / ... / goto / Lmsg:
    #   message" becomes the PoC A pattern: offer all items when any is untaken, else the
    #   message (one declared flow change: the check now jumps to the offer);
    #   2-item cascade (vanilla "A untaken: found A, found B / else B untaken: found B / else
    #   message"): every "found B" is followed by the new items, and a branch "a new item is
    #   untaken: found them" goes in front of the message (the jumps to the message are the
    #   declared flow changes);
    #   put_at shape: more "put_at X self" right after the first (pure insertion).
    by_life = defaultdict(list)
    for s, got, extras in growth:
        words = [[x for x in s["sites"][item] if x["kind"] == "word"] for item in s["items"]]
        n_van = len(s["items"])
        if s["family"] in PUT_AT_FAMILIES:
            if n_van != 1:
                raise SystemExit(f"{s['id']}: growth of a {n_van}-item put_at location")
            for site in words[0]:                  # every death branch (the knight has two scripts)
                by_life[site["life"]].append(("put_at", s, site["at"], extras))
        elif n_van == 1:
            site = words[0][0]                     # the single found of the 1-item shape
            by_life[site["life"]].append(("offer", s, site["at"], [got[0]] + extras))
        else:
            last = s["items"][-1]
            checks = [x for x in s["sites"][last] if x["kind"] == "expr_arg"]
            if len(checks) != 1 or len({x["life"] for x in s["sites"][last]}) != 1:
                raise SystemExit(f"{s['id']}: unexpected cascade shape for growth")
            by_life[checks[0]["life"]].append(
                ("cascade", s, checks[0]["at"], (got[n_van - 1], [x["at"] for x in words[-1]], extras)))
    for life, ops in by_life.items():
        before = L.decode(bytes(entries[life]))
        offs = [i.offset for i in before]
        lines = L.format_script(before).splitlines()
        line_at = {int(l.rsplit("; @", 1)[1]): n for n, l in enumerate(lines) if "; @" in l}
        intended = set()
        edits = {}                         # line index -> replacement lines

        def edit(n, new_lines, sid):
            if n in edits:
                raise SystemExit(f"{sid}: LIFE {life} line {n} edited twice by growth")
            edits[n] = new_lines

        for n_op, (kind, s, at, data) in enumerate(ops):
            ins = before[offs.index(at)]
            if kind == "put_at":
                n = line_at[at]
                edit(n, [lines[n]] + [f"put_at {x} {ins.args[1]}" for x in data], s["id"])
                continue
            if kind == "offer":
                items = data
                chk = before[offs.index(at) - 1]
                text = bare(chk)
                if not (chk.name == "if_egal" and text.startswith(f"if_egal object({items[0]}) #0 @")):
                    raise SystemExit(f"{s['id']}: unexpected shape before found: {text}")
                lab = f"Lgrow{n_op}"
                n_chk, n_found = line_at[chk.offset], line_at[at]
                head = lines[n_chk].split("    ; @")[0]
                prefix = head.split(": ")[0] + ": " if head.startswith("L") and ": " in head else ""
                msg = text.rsplit("@", 1)[1]
                edit(n_chk, [f"{prefix}if_egal object({items[0]}) #1 @{lab}    ; @{chk.offset}"]
                     + [f"if_egal object({x}) #1 @{lab}" for x in items[1:]] + [f"goto @{msg}"], s["id"])
                edit(n_found, [f"{lab}: {lines[n_found]}"] + [f"found {x}" for x in items[1:]], s["id"])
                intended.add(chk.offset)
                continue
            # cascade
            cur_last, found_ats, extras = data
            text = bare(ins)
            if not (ins.name == "if_egal" and text.startswith(f"if_egal object({cur_last}) #0 @")):
                raise SystemExit(f"{s['id']}: unexpected cascade check: {text}")
            msg_lab = text.rsplit("@", 1)[1]
            k = offs.index(at)
            exit_ins = next((x for x in before[k + 1:] if x.name == "goto"), None)
            n_msg = next((n for n, l in enumerate(lines) if l.startswith(f"{msg_lab}: ")), None)
            if exit_ins is None or n_msg is None:
                raise SystemExit(f"{s['id']}: cascade without exit or message")
            msg_line = lines[n_msg][len(msg_lab) + 2:]
            if not msg_line.startswith("message "):
                raise SystemExit(f"{s['id']}: cascade ends in {msg_line!r}, not a message")
            exit_lab = bare(exit_ins).rsplit("@", 1)[1]
            for fa in found_ats:
                if bare(before[offs.index(fa)]) != f"found {cur_last}":
                    raise SystemExit(f"{s['id']}: expected found {cur_last} at @{fa}")
                n = line_at[fa]
                edit(n, [lines[n]] + [f"found {x}" for x in extras], s["id"])
            offer, new_msg = f"Lcasc{n_op}", f"Lcascm{n_op}"
            edit(n_msg, [f"{msg_lab}: if_egal object({extras[0]}) #1 @{offer}"]
                 + [f"if_egal object({x}) #1 @{offer}" for x in extras[1:]]
                 + [f"goto @{new_msg}", f"{offer}: found {extras[0]}"] + [f"found {x}" for x in extras[1:]]
                 + [f"goto @{exit_lab}", f"{new_msg}: {msg_line}"], s["id"])
            intended |= {x.offset for x in before if x.jump() and x.jump().label == msg_lab}
            msg_off = int(msg_line.rsplit("; @", 1)[1])
            intended.add(before[offs.index(msg_off) - 1].offset)
        out_lines = []
        for n, line in enumerate(lines):
            out_lines += edits.get(n, [line])
        patched = L.parse_script("\\n".join(out_lines) + "\\n")
        chk_r = L.check_text_patch(before, patched, intended)
        data = L.encode(patched)
        L.decode(data)
        if not chk_r.ok or chk_r.removed:
            raise SystemExit(f"LIFE {life}: growth failed the flow check: "
                             f"unexpected={chk_r.unexpected_flow} backward={chk_r.new_backward} "
                             f"removed={chk_r.removed}\\n" + "\\n".join(out_lines))
        entries[life] = bytearray(data)
        report[life] = dict(report.get(life, {}), ok=True, grown=len(ops),
                            sha256=hashlib.sha256(data).hexdigest())
'''
s = s[:a] + NEW_GROWTH + s[b:]

rep('''    ap.add_argument("--key-names", action="store_true",''', '''    ap.add_argument("--max-per-location", type=int, choices=(2, 3), default=None,
                    help="testing: force this per-location maximum (default: 2, and 3 only if "
                         "the items do not fit at 2)")
    ap.add_argument("--key-names", action="store_true",''')

a = s.index("    # User fallback rule (2026-10-15): raise the cap to 3 if positions run out. NOT active yet:")
b = s.index('    out = a.out or (GEN / "Seeds" / f"seed_{a.seed}")')
NEW_MAIN = '''    # User fallback rule (2026-10-15): every location holds at most 2 items; only when the items
    # do not all fit (or no valid placement exists) the seed is filled again with at most 3.
    caps = (a.max_per_location,) if a.max_per_location else (MAX_PER_LOCATION, FALLBACK_MAX)
    best = None
    for cap_used in caps:
        set_cap(slots, cap_used)
        placement, omitted, why = None, [], ""
        for attempt in range(a.attempts):
            rng = random.Random(f"{a.seed}:{attempt}")
            placement, omitted, why = fill(rng, slots, prog, has_body, world, pool)
            if placement is None:
                continue
            ok, st, spheres, got = C.sweep(nodes, edges, wslots, events, man, placement)
            if ok:
                break
            placement, why = None, "final check failed"
        if placement is not None and (best is None or len(omitted) < len(best[1])):
            best = (placement, omitted, attempt, cap_used)
        if placement is not None and not omitted:
            break
    if best is None:
        print(f"seed {a.seed}: no valid placement after {a.attempts} attempts per cap ({why})")
        return 1
    placement, omitted, attempt, cap_used = best
    set_cap(slots, cap_used)

'''
s = s[:a] + NEW_MAIN + s[b:]

rep('''                    "max_per_location": cap_used}, "omitted_items": omitted,''',
    '''                    "max_per_location": cap_used,
                    **({"forced_max_per_location": a.max_per_location} if a.max_per_location else {})},
        "omitted_items": omitted,''')
rep('VERSION = "v11 (2026-10-16)"', 'VERSION = "v12 (2026-10-16)"')
p.write_text(s, encoding="utf-8")
print("ok")
