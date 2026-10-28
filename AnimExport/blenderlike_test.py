"""Robustness test: re-orient every bone and shuffle the joint order, as a DCC tool may do on
re-export (Blender gives bones its own rest orientation), then check that import_gltf gives the
same AITD animations as from the untouched file.

For a bone j with an extra rest rotation B_j: new local L'_j = B_parent^-1 * L_j * B_j and
new inverse bind IBM'_j = B_j^-1 * IBM_j, so every skinning matrix (and so the mesh) is unchanged.

Usage: python blenderlike_test.py in.glb
"""
import json, struct, sys, random
from pathlib import Path
import numpy as np
from verify_gltf import load_glb, quat_mat
from export_gltf import mat_to_quat
from import_gltf import import_anims
from aitd_model import write_anim


def rand_rot(rng):
    q = np.array([rng.gauss(0, 1) for _ in range(4)]); q /= np.linalg.norm(q); return quat_mat(q)


def transform(src, dst, seed=7):
    rng = random.Random(seed)
    doc, acc = load_glb(src)
    nodes = doc["nodes"]; skin = doc["skins"][0]; joints = skin["joints"]
    parent = {c: i for i, nd in enumerate(nodes) for c in nd.get("children", [])}
    B = {j: rand_rot(rng) for j in joints}
    def Bm(j): m = np.eye(4); m[:3, :3] = B.get(j, np.eye(3)); return m
    def trs(t, q, s=(1, 1, 1)):
        m = np.eye(4); m[:3, :3] = quat_mat(q) @ np.diag(s); m[:3, 3] = t; return m
    def new_local(j, m):
        p = parent.get(j)
        return np.linalg.inv(Bm(p)) @ m @ Bm(j) if p in B else m @ Bm(j)
    bin_parts = bytearray(); views, accs = [], []
    def add(arr, typ):
        arr = np.ascontiguousarray(arr, np.float32)
        while len(bin_parts) % 4: bin_parts.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_parts), "byteLength": arr.nbytes}); bin_parts.extend(arr.tobytes())
        accs.append({"bufferView": len(views) - 1, "componentType": 5126, "count": arr.shape[0], "type": typ})
        return len(accs) - 1
    # rest TRS
    for j in joints:
        nd = nodes[j]
        m = new_local(j, trs(nd.get("translation", [0, 0, 0]), nd.get("rotation", [0, 0, 0, 1])))
        nd["translation"] = m[:3, 3].tolist(); nd["rotation"] = mat_to_quat(m[:3, :3]).tolist()
    ibm = acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    order = list(range(len(joints))); rng.shuffle(order)
    new_ibm = [(np.linalg.inv(Bm(joints[k])) @ ibm[k]).T for k in order]
    skin["joints"] = [joints[k] for k in order]
    skin["inverseBindMatrices"] = add(np.array(new_ibm).reshape(-1, 16), "MAT4")
    # animations: resample every joint's full TRS at the union of key times
    for an in doc["animations"]:
        ch = {(c["target"]["node"], c["target"]["path"]): an["samplers"][c["sampler"]] for c in an["channels"]}
        tin = an["samplers"][0]["input"]; times = acc(tin)[:, 0]
        chans, samps = [], []
        tacc = add(times.reshape(-1, 1), "SCALAR")
        for j in joints:
            nd = nodes[j]
            ts, qs = [], []
            for k in range(len(times)):
                t = acc(ch[(j, "translation")]["output"])[k] if (j, "translation") in ch else None
                q = acc(ch[(j, "rotation")]["output"])[k] if (j, "rotation") in ch else None
                # original (pre-transform) rest values are needed when a channel is absent
                t0 = orig_rest[j][0] if t is None else t
                q0 = orig_rest[j][1] if q is None else q
                m = new_local(j, trs(t0, q0))
                ts.append(m[:3, 3]); qs.append(mat_to_quat(m[:3, :3]))
            for k in range(1, len(qs)):
                if np.dot(qs[k], qs[k - 1]) < 0: qs[k] = -qs[k]
            for path, vals, typ in (("translation", ts, "VEC3"), ("rotation", qs, "VEC4")):
                samps.append({"input": tacc, "output": add(np.array(vals), typ), "interpolation": "LINEAR"})
                chans.append({"sampler": len(samps) - 1, "target": {"node": j, "path": path}})
        an["channels"] = chans; an["samplers"] = samps; an.pop("extras", None)
    # rebuild the buffer: old data first, then the new accessors
    b = Path(src).read_bytes(); jl, = struct.unpack_from("<I", b, 12); bl, = struct.unpack_from("<I", b, 20 + jl)
    old = bytearray(b[28 + jl:28 + jl + bl]); base = len(old)
    for v in views: v["byteOffset"] += base
    off = len(doc["bufferViews"]); doc["bufferViews"] += views
    for a in accs: a["bufferView"] += off
    aoff = len(doc["accessors"]); doc["accessors"] += accs
    skin["inverseBindMatrices"] += aoff
    for an in doc["animations"]:
        for s in an["samplers"]: s["input"] += aoff; s["output"] += aoff
    data = bytes(old + bin_parts); data += b"\0" * (-len(data) % 4)
    doc["buffers"] = [{"byteLength": len(data)}]
    js = json.dumps(doc).encode(); js += b" " * (-len(js) % 4)
    Path(dst).write_bytes(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(data)) + struct.pack("<II", len(js), 0x4E4F534A)
                          + js + struct.pack("<II", len(data), 0x004E4942) + data)


if __name__ == "__main__":
    src = sys.argv[1]; dst = str(Path(src).with_name(Path(src).stem + "_blenderlike.glb"))
    d0, _ = load_glb(src)
    orig_rest = {i: (nd.get("translation", [0, 0, 0]), nd.get("rotation", [0, 0, 0, 1])) for i, nd in enumerate(d0["nodes"])}
    transform(src, dst)
    a = import_anims(src, use_extras=False); b = import_anims(dst, use_extras=False)
    same = sum(write_anim(a[k]) == write_anim(b[k]) for k in a)
    print(f"{dst}: {same}/{len(a)} animations identical to the untouched file's import")
    for k in a:
        if write_anim(a[k]) != write_anim(b[k]):
            fa, fb = a[k].frames, b[k].frames
            print(" ", k, [(i, x.time, y.time, x.step, y.step) for i, (x, y) in enumerate(zip(fa, fb)) if x.time != y.time or x.step != y.step][:2],
                  [(i, gi, ga, gb) for i, (x, y) in enumerate(zip(fa, fb)) for gi, (ga, gb) in enumerate(zip(x.groups, y.groups)) if ga != gb][:3])
