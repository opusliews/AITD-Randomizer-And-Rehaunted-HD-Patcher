"""Export an AITD1 jointed body plus animations to a binary glTF (.glb) for Blender.

Usage:
  python export_gltf.py --body 12 --anims 4,254,255 --out edward.glb [--paks LISTBODY.PAK,LISTANIM.PAK]

Conventions (see Research/AnimExport.md):
- One joint per body group (bone head = the group's pivot vertex), plus an "Actor" root
  joint that carries the animation step (root motion). Every vertex is weighted 1.0 to its group.
- Engine space (x right, y down, z forward, mm) -> glTF (y up, metres): (x, -y, -z) / 1000.
- Engine group rotation: p' = Rz * Rx * Ry * p, 1024 units per turn (renderer.cpp RotateList).
- Time: 1 tick = 1 frame at 25 fps. Keyframe i of the AITD animation is reached at the sum of
  the durations 0..i. The key at time 0 is the start pose: the last keyframe (the engine
  blends into keyframe 0 from whatever pose came before; for a loop that is the last one).
- Raw AITD values the engine ignores (group 0 state, groups beyond the body, types) are kept
  in each animation's "extras" so a re-import can reproduce the original bytes.
"""
from __future__ import annotations
import argparse, json, math, struct, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Patcher"))
import gamedata
from aitd_model import parse_body, parse_anim, pose

FPS = 25.0
SCALE = 0.001
C = np.diag([1.0, -1.0, -1.0])


def to_gltf(p):
    return (C @ np.asarray(p, float)) * SCALE


def engine_rot(x, y, z):
    def ang(a): return a * 2 * math.pi / 1024
    cy, sy = math.cos(ang(y)), math.sin(ang(y))
    cx, sx = math.cos(ang(x)), math.sin(ang(x))
    cz, sz = math.cos(ang(z)), math.sin(ang(z))
    Ry = np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def mat_to_quat(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1) * 2; w = s / 4
        x = (m[2, 1] - m[1, 2]) / s; y = (m[0, 2] - m[2, 0]) / s; z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s; x = s / 4; y = (m[0, 1] + m[1, 0]) / s; z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s; x = (m[0, 1] + m[1, 0]) / s; y = s / 4; z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s; x = (m[0, 2] + m[2, 0]) / s; y = (m[1, 2] + m[2, 1]) / s; z = s / 4
    q = np.array([x, y, z, w]); return q / np.linalg.norm(q)


def load_palette():
    pal = np.frombuffer(gamedata.pak_entries("ITD_RESS.PAK")[3][:768], np.uint8).reshape(256, 3).astype(float)
    if pal.max() < 64:
        pal *= 255 / 63
    return pal / 255


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def bone_names(body):
    """Readable names for Edward's 17-group skeleton (body 12/265/268); generic otherwise."""
    edward = {0: "root", 1: "hips_offset", 2: "pelvis", 3: "thigh.L", 4: "shin.L", 5: "foot.L",
              6: "chest", 7: "head", 8: "upperarm.L", 9: "forearm.L", 10: "hand.L",
              11: "upperarm.R", 12: "forearm.R", 13: "hand.R", 14: "thigh.R", 15: "shin.R", 16: "foot.R"}
    if len(body.groups) == 17 and body.groups[16].parent == 15:
        return [f"g{i:02d}_{edward[i]}" for i in range(17)]
    return [f"g{i:02d}" for i in range(len(body.groups))]


class Glb:
    def __init__(self):
        self.bin = bytearray(); self.views = []; self.accessors = []

    def add(self, arr, comp, typ, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        while len(self.bin) % 4: self.bin.append(0)
        off = len(self.bin); self.bin += arr.tobytes()
        v = {"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes}
        if target: v["target"] = target
        self.views.append(v)
        count = arr.shape[0]
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": count, "type": typ}
        if minmax:
            a2 = arr.reshape(count, -1)
            acc["min"] = a2.min(0).tolist(); acc["max"] = a2.max(0).tolist()
        self.accessors.append(acc); return len(self.accessors) - 1


def export(body_idx, anim_ids, out, body_pak="LISTBODY.PAK", anim_pak="LISTANIM.PAK", anim_names=None):
    body = parse_body(gamedata.pak_entries(body_pak)[body_idx])
    anims = gamedata.pak_entries(anim_pak)
    pal = load_palette()
    n = len(body.groups)
    names = bone_names(body)
    rest = pose(body, [(0, (0, 0, 0))] * n)
    head = [np.array(rest[g.base], float) for g in body.groups]       # engine space, model origin
    vgroup = [None] * len(body.verts)
    for gi, g in enumerate(body.groups):
        for k in range(g.start, g.start + g.count): vgroup[k] = gi

    G = Glb()
    # ---- mesh: flat polygons (fan-triangulated), one material per palette colour
    by_color = {}
    lines = []
    skipped = {}
    for p in body.prims:
        if p.type in (1, 8, 9, 10) and len(p.points) >= 3:
            by_color.setdefault((p.color, p.material), []).append(p.points)
        elif p.type == 0:
            lines.append(p)
        else:
            skipped[p.type] = skipped.get(p.type, 0) + 1
    materials, prims_out = [], []
    for (color, mat), polys in sorted(by_color.items()):
        pos, joints = [], []
        for pts in polys:
            for a, b, c in ((pts[0], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)):
                for v in (a, b, c):
                    pos.append(to_gltf(rest[v])); joints.append(vgroup[v] + 1)
        pos = np.array(pos, np.float32)
        jn = np.zeros((len(pos), 4), np.uint8); jn[:, 0] = joints
        wt = np.zeros((len(pos), 4), np.float32); wt[:, 0] = 1
        rgb = srgb_to_linear(pal[color])
        materials.append({"name": f"pal{color:03d}" + ("_dither" if mat == 1 else "" if mat == 0 else f"_m{mat}"),
                          "pbrMetallicRoughness": {"baseColorFactor": [*rgb.tolist(), 1.0], "metallicFactor": 0, "roughnessFactor": 1},
                          "doubleSided": True, "extras": {"aitd_color": color, "aitd_material": mat}})
        prims_out.append({"attributes": {"POSITION": G.add(pos, 5126, "VEC3", 34962, True),
                                         "JOINTS_0": G.add(jn, 5121, "VEC4", 34962),
                                         "WEIGHTS_0": G.add(wt, 5126, "VEC4", 34962)},
                          "material": len(materials) - 1, "mode": 4})
    if lines:
        pos = np.array([to_gltf(rest[v]) for p in lines for v in p.points], np.float32)
        jn = np.zeros((len(pos), 4), np.uint8); jn[:, 0] = [vgroup[v] + 1 for p in lines for v in p.points]
        wt = np.zeros((len(pos), 4), np.float32); wt[:, 0] = 1
        materials.append({"name": "lines", "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 0, 1]}})
        prims_out.append({"attributes": {"POSITION": G.add(pos, 5126, "VEC3", 34962, True),
                                         "JOINTS_0": G.add(jn, 5121, "VEC4", 34962),
                                         "WEIGHTS_0": G.add(wt, 5126, "VEC4", 34962)},
                          "material": len(materials) - 1, "mode": 1})

    # ---- skeleton: node 0 = Actor (root motion), node 1+gi = group gi, mesh node last
    nodes = [{"name": "Actor", "children": []}]
    for gi, g in enumerate(body.groups):
        ph = head[g.parent] if g.parent >= 0 else np.zeros(3)
        nodes.append({"name": names[gi], "translation": to_gltf(head[gi] - ph).tolist(), "children": []})
        (nodes[0] if g.parent < 0 else nodes[1 + g.parent])["children"].append(1 + gi)
    ibm = np.zeros((n + 1, 4, 4), np.float32)
    ibm[0] = np.eye(4)
    for gi in range(n):
        m = np.eye(4); m[:3, 3] = -to_gltf(head[gi]); ibm[1 + gi] = m.T     # column-major
    skin = {"name": "Edward" if names[0].endswith("root") else "skin", "joints": list(range(n + 1)),
            "skeleton": 0, "inverseBindMatrices": G.add(ibm.reshape(n + 1, 16), 5126, "MAT4")}
    for nd in nodes:
        if not nd["children"]: del nd["children"]
    mesh_node = len(nodes)
    nodes.append({"name": f"body_{body_idx:03d}", "mesh": 0, "skin": 0})

    # ---- animations
    gl_anims = []
    for aid in anim_ids:
        a = parse_anim(anims[aid])
        nf = len(a.frames)
        # glTF key times must increase strictly: a zero-length keyframe (an instant pose, 8 anims
        # in LISTANIM, always the first keyframe) gets 0.01 tick, which the importer rounds away.
        times = [0.0]; t = 0.0
        for f in a.frames:
            t += f.time if f.time else 0.01; times.append(t / FPS)
        seq = [a.frames[-1]] + a.frames                 # key 0 = start pose (last keyframe)
        step = [np.zeros(3)]; acc = np.zeros(3)
        for f in a.frames:
            acc = acc + np.array(f.step, float); step.append(acc.copy())
        step[0] = np.zeros(3)
        tacc = G.add(np.array(times, np.float32), 5126, "SCALAR", minmax=True)
        channels, samplers = [], []

        def channel(node, path, values, typ):
            samplers.append({"input": tacc, "output": G.add(np.array(values, np.float32), 5126, typ), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path}})

        channel(0, "translation", [to_gltf(s) for s in step], "VEC3")
        ng = min(a.num_groups, n)
        for gi in range(1, ng):                         # group 0 rotation is the actor's (ignored)
            g = body.groups[gi]
            base_t = np.array(nodes[1 + gi]["translation"])
            rots, trans, scales = [], [], []
            for f in seq:
                ty, d = f.groups[gi]
                if ty == 0:
                    rots.append(mat_to_quat(C @ engine_rot(*d) @ C)); trans.append(base_t); scales.append([1, 1, 1])
                elif ty == 1:
                    rots.append([0, 0, 0, 1]); trans.append(base_t + to_gltf(d)); scales.append([1, 1, 1])
                else:
                    rots.append([0, 0, 0, 1]); trans.append(base_t); scales.append([(v + 256) / 256 for v in d])
            # keep quaternion signs continuous so slerp takes the short way
            for k in range(1, len(rots)):
                if np.dot(rots[k], rots[k - 1]) < 0: rots[k] = [-c for c in rots[k]]
            channel(1 + gi, "rotation", rots, "VEC4")
            if any(f.groups[gi][0] == 1 for f in a.frames): channel(1 + gi, "translation", trans, "VEC3")
            if any(f.groups[gi][0] == 2 for f in a.frames): channel(1 + gi, "scale", scales, "VEC3")
        name = (anim_names or {}).get(aid, f"anim_{aid:03d}")
        gl_anims.append({"name": name, "channels": channels, "samplers": samplers,
                         "extras": {"aitd_anim": aid, "aitd_pak": anim_pak, "aitd_num_groups": a.num_groups,
                                    "aitd_durations": [f.time for f in a.frames],
                                    "aitd_steps": [list(f.step) for f in a.frames],
                                    "aitd_groups": [[[ty, *d] for ty, d in f.groups] for f in a.frames]}})

    doc = {"asset": {"version": "2.0", "generator": "AITD AnimExport (Generated/AnimExport/export_gltf.py)"},
           "scene": 0, "scenes": [{"nodes": [0, mesh_node]}], "nodes": nodes,
           "meshes": [{"name": f"body_{body_idx:03d}", "primitives": prims_out}], "materials": materials,
           "skins": [skin], "animations": gl_anims, "accessors": G.accessors, "bufferViews": G.views,
           "buffers": [{"byteLength": len(G.bin)}],
           "extras": {"aitd_body": body_idx, "aitd_body_pak": body_pak, "fps": FPS,
                      "skipped_primitives": {str(k): v for k, v in skipped.items()}}}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binb = bytes(G.bin) + b"\0" * (-len(G.bin) % 4)
    total = 12 + 8 + len(js) + 8 + len(binb)
    Path(out).write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
                          + struct.pack("<II", len(binb), 0x004E4942) + binb)
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", type=int, default=12)
    ap.add_argument("--anims", default="4")
    ap.add_argument("--out", required=True)
    ap.add_argument("--body-pak", default="LISTBODY.PAK")
    ap.add_argument("--anim-pak", default="LISTANIM.PAK")
    a = ap.parse_args()
    ids = [int(x) for x in a.anims.split(",") if x]
    d = export(a.body, ids, a.out, a.body_pak, a.anim_pak)
    print(f"wrote {a.out}: {len(d['nodes'])} nodes, {len(d['animations'])} animations, skipped prims {d['extras']['skipped_primitives']}")
