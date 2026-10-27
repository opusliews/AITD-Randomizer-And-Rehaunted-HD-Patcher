"""Independent check of a generated seed: for every patched LIFE, the awarded items
(found/put_at, ignoring the dud OBJ 2) must equal the vanilla awards with each
shuffled location's items replaced by its placement (sites, grown items, enemy
drops).  python verify_seed.py SEED_DIR
generate.py calls verify() in-process (the patcher app is one frozen exe, with no
Python to start a second process with)."""
import re, sys, json
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Patcher"))
import aitd_life as L
from aitd_pak import read_pak


def awards(ins, skip=frozenset()): return Counter((i.name, i.args[0]) for i in ins if i.name in ("found","put_at") and i.args[0]!=2 and i.args[0] not in skip)


def glow_check(P, new) -> list[str]:
    """Option Drop Glow: the glows are objects with model 274 in the seed's OBJETS. Each
    `put_at GLOW M` must directly follow a `put_at ITEM M` of an item its own script waits for
    (`if_egal isfound(#ITEM) #1`), and each glow must be put somewhere."""
    import aitd_objets as O
    f = P / "patchset" / "OBJETS.ITD"
    if not f.exists():
        return []
    objs = O.load(f)
    glows = {g: o["life"] for g, o in enumerate(objs) if o["body"] == 274}
    errs = []
    for g, life in glows.items():
        waits = {int(x) for x in re.findall(r"isfound\(#(\d+)\) #1", L.format_script(new[life]))}
        uses = 0
        for n, ins in enumerate(new):
            for k, i in enumerate(ins):
                if i.name == "put_at" and i.args[0] == g:
                    uses += 1
                    prev = ins[k - 1] if k else None
                    if not (prev and prev.name == "put_at" and prev.args[1] == i.args[1] and prev.args[0] in waits):
                        errs.append(f"glow {g}: LIFE {n} @{i.offset} does not follow a put_at of its items {sorted(waits)}")
        if not waits or not uses:
            errs.append(f"glow {g}: items {sorted(waits)}, placed {uses} time(s)")
    return errs


def verify(seed_dir) -> tuple[int, list[str]]:
    """(scripts with award mismatches, report lines)."""
    import generate as G
    P = Path(seed_dir)
    pl=json.loads((P / "placement.json").read_text(encoding="utf-8"))
    van=[L.decode(e.data) for e in read_pak(G.SRC/"LISTLIFE.PAK").entries]
    new=[L.decode(e.data) for e in read_pak(P / "patchset" / "LISTLIFE.PAK").entries]
    expect={n: awards(v) for n,v in enumerate(van)}
    world = [w for w in G.world_slots() if w['id'] in pl]   # option Shuffle Visible Items
    for s in G.load_slots() + world:
        fam = "put_at" if s['family'] in G.PUT_AT_FAMILIES else "found"
        got = pl.get(s['id'], [])
        for k, old in enumerate(s['items']):
            for x in s['sites'][old]:
                if x['kind'] != 'word': continue
                expect[x['life']][(fam, old)] -= 1
                if k < len(got): expect[x['life']][(fam, got[k])] += 1
        extra = got[len(s['items']):]                     # grown items
        if extra and len(s['items']) >= 2:                # 2-item cascade: after every "found B", + the new branch
            words=[x for x in s['sites'][s['items'][-1]] if x['kind']=='word']
            for it in extra: expect[words[0]['life']][(fam, it)] += len(words) + 1
        elif extra:
            words=[x for x in s['sites'][s['items'][0]] if x['kind']=='word']
            for x in (words if fam=="put_at" else words[:1]):
                for it in extra: expect[x['life']][(fam, it)] += 1
    if world and pl.get("P:205", [205])[0] != 205:      # LIFE 550 path 2 offers the wedge-spot item
        expect[550][("found", pl["P:205"][0])] += 1
    zones={z["zone_id"]: z for z in json.loads((G.CAT/"acquisition_slots.json").read_text(encoding="utf-8"))["optional_empty_zones"]}
    for sid,items in pl.items():
        if sid in zones:                                   # Many Search Places: new founds in the controller
            for it in items: expect[zones[sid]["controller_life"]][("found",it)] += 1
    for sid,items in pl.items():
        if sid.startswith("E:"):
            e=int(sid[2:])
            for l in G.life_owners_map(van).get(e,()):
                n=sum(1 for i in van[l] if i.name=="delete" and i.args[0]==e)
                for it in items: expect[l][("put_at",it)]+=n
    bad, lines = 0, []
    glow_errs = glow_check(P, new)
    glow_ids = set()
    if (P / "patchset" / "OBJETS.ITD").exists():
        import aitd_objets as O
        glow_ids = {g for g, o in enumerate(O.load(P / "patchset" / "OBJETS.ITD")) if o["body"] == 274}
    for n in range(len(van)):
        e=+expect[n]; g=awards(new[n], glow_ids)
        if e!=g: bad+=1; lines.append(f"LIFE {n} expected {dict(e)} got {dict(g)}")
    bad += len(glow_errs); lines += glow_errs
    lines.append(f"scripts with award mismatches: {bad}")
    return bad, lines


if __name__ == "__main__":
    print("\n".join(verify(sys.argv[1])[1]))
