"""Round trip: AITD anim -> glTF -> AITD anim, compared with the original bytes.

Usage: python roundtrip_test.py --body 12 --anims 4,254,... [--out out/roundtrip.glb]
Reports, per animation, identical / which values differ (with and without the glTF extras).
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Patcher"))
import gamedata
from aitd_model import parse_anim, write_anim
from export_gltf import export
from import_gltf import import_anims

ap = argparse.ArgumentParser()
ap.add_argument("--body", type=int, default=12); ap.add_argument("--anims", required=True)
ap.add_argument("--out", default="out/roundtrip.glb")
ap.add_argument("--body-pak", default="LISTBODY.PAK"); ap.add_argument("--anim-pak", default="LISTANIM.PAK")
a = ap.parse_args()
ids = [int(x) for x in a.anims.split(",")]
export(a.body, ids, a.out, a.body_pak, a.anim_pak)
raw = gamedata.pak_entries(a.anim_pak)
nbody = None
for mode in (True, False):
    got = import_anims(a.out, use_extras=mode)
    same = 0; problems = []
    for aid in ids:
        orig = raw[aid]; new = write_anim(got[f"anim_{aid:03d}"])
        if new == orig: same += 1; continue
        o, n = parse_anim(orig), got[f"anim_{aid:03d}"]
        diffs = []
        for k, (fo, fn) in enumerate(zip(o.frames, n.frames)):
            if fo.time != fn.time: diffs.append(f"k{k} time {fo.time}->{fn.time}")
            if fo.step != fn.step: diffs.append(f"k{k} step {fo.step}->{fn.step}")
            for gi, (go, gn) in enumerate(zip(fo.groups, fn.groups)):
                if go != gn: diffs.append(f"k{k} g{gi} {go}->{gn}")
        if o.num_groups != n.num_groups: diffs.append(f"groups {o.num_groups}->{n.num_groups}")
        problems.append((aid, diffs))
    print(f"\n== extras {'ON' if mode else 'OFF (as after Blender)'}: {same}/{len(ids)} byte-identical")
    for aid, d in problems:
        print(f"  anim {aid}: {len(d)} differences: " + "; ".join(d[:6]) + (" ..." if len(d) > 6 else ""))
