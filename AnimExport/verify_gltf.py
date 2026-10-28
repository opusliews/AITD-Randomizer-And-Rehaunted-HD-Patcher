"""Check an exported .glb against the engine's own posing (aitd_model.pose, a port of AnimNuage).

For every animation and keyframe: evaluate the glTF node hierarchy at the key time the standard
glTF way (T * R * S per node, parent * child, skin = joint world * inverse bind), skin the rest
vertices, and compare with the engine pose of that keyframe. Differences come only from the
engine's fixed-point maths (>>16 <<1 per rotation), so they should be a few mm at most.

Usage: python verify_gltf.py file.glb
"""
from __future__ import annotations
import json, struct, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Patcher"))
import gamedata
from aitd_model import parse_body, parse_anim, pose


def load_glb(path):
    b = Path(path).read_bytes()
    jl, = struct.unpack_from("<I", b, 12); doc = json.loads(b[20:20 + jl])
    bl, = struct.unpack_from("<I", b, 20 + jl); binb = b[28 + jl:28 + jl + bl]
    def acc(i):
        a = doc["accessors"][i]; v = doc["bufferViews"][a["bufferView"]]
        dt = {5126: np.float32, 5121: np.uint8, 5123: np.uint16}[a["componentType"]]
        k = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
        return np.frombuffer(binb, dt, a["count"] * k, v["byteOffset"]).reshape(a["count"], k)
    return doc, acc


def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def main(path):
    doc, acc = load_glb(path)
    ex = doc["extras"]
    body = parse_body(gamedata.pak_entries(ex["aitd_body_pak"])[ex["aitd_body"]])
    nodes = doc["nodes"]; skin = doc["skins"][0]
    ibm = acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    parent = {}
    for i, nd in enumerate(nodes):
        for c in nd.get("children", []): parent[c] = i
    vg = {}
    for gi, g in enumerate(body.groups):
        for k in range(g.start, g.start + g.count): vg[k] = gi
    rest_engine = pose(body, [(0, (0, 0, 0))] * len(body.groups))
    C = np.diag([1.0, -1.0, -1.0])
    worst_all = 0
    for an in doc["animations"]:
        aex = an["extras"]
        a = parse_anim(gamedata.pak_entries(aex["aitd_pak"])[aex["aitd_anim"]])
        times = acc(an["samplers"][0]["input"])[:, 0]
        worst = 0
        for key in range(1, len(times)):
            local = {i: [np.array(nd.get("translation", [0, 0, 0]), float),
                         np.array(nd.get("rotation", [0, 0, 0, 1]), float),
                         np.array(nd.get("scale", [1, 1, 1]), float)] for i, nd in enumerate(nodes)}
            for ch in an["channels"]:
                s = an["samplers"][ch["sampler"]]; out = acc(s["output"])[key]
                slot = {"translation": 0, "rotation": 1, "scale": 2}[ch["target"]["path"]]
                local[ch["target"]["node"]][slot] = out.astype(float)
            world = {}
            def W(i):
                if i in world: return world[i]
                t, r, s = local[i]; m = np.eye(4); m[:3, :3] = quat_mat(r) @ np.diag(s); m[:3, 3] = t
                world[i] = (W(parent[i]) @ m) if i in parent else m
                return world[i]
            joints = skin["joints"]
            jm = [W(j) @ ibm[k] for k, j in enumerate(joints)]
            f = a.frames[key - 1]
            states = [(0, (0, 0, 0))] + [f.groups[i] for i in range(1, min(a.num_groups, len(body.groups)))]
            eng = pose(body, states)
            # the Actor joint carries the accumulated step; the engine applies it to the actor, not the body
            actor = W(joints[0])
            for vi in range(len(body.verts)):
                rest = (C @ np.array(rest_engine[vi], float)) * 0.001
                p = (np.linalg.inv(actor) @ jm[vg[vi] + 1] @ np.append(rest, 1))[:3]
                e = (C @ np.array(eng[vi], float)) * 0.001
                worst = max(worst, np.abs(p - e).max() * 1000)
        print(f"{an['name']}: {len(times) - 1} keys, worst vertex difference {worst:.1f} mm")
        worst_all = max(worst_all, worst)
    print(f"ALL: worst {worst_all:.1f} mm")
    return worst_all


if __name__ == "__main__":
    main(sys.argv[1])
