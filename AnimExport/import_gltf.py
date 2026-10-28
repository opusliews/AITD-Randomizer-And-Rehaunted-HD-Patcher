"""Convert glTF animations (from export_gltf.py, possibly edited in Blender) back to AITD1 animations.

Usage: python import_gltf.py file.glb [--anim NAME] --out-dir DIR [--no-extras]
Writes one <name>.anim per glTF animation (raw LISTANIM entry bytes).

Inverse of export_gltf.py:
- keys after time 0 become AITD keyframes; durations = key time differences in ticks (25 fps);
- bone rotation -> engine Euler angles for p' = Rz*Rx*Ry*p (1024 units), choosing, of the two
  equivalent solutions, the one closest to the previous key (the engine interpolates each angle
  linearly, so this keeps the in-between motion the same);
- a translation channel on a bone -> type 1 (translate) for keys where it differs from the rest
  offset; scale -> type 2;
- Actor translation differences -> the keyframe step (root motion).
Values the engine ignores (group 0, extra groups) come from the animation's extras when present,
otherwise they are written as zero. Blender drops extras, so --no-extras shows what a
Blender-edited file gives.
"""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aitd_model import Anim, Frame, write_anim
from verify_gltf import load_glb, quat_mat
from export_gltf import engine_rot

FPS = 25.0
C = np.diag([1.0, -1.0, -1.0])
U = 1024 / (2 * math.pi)
warnings: list[str] = []


def euler_from_matrix(M, prev=None):
    """Engine angles (x, y, z) with M = Rz*Rx*Ry (engine space)."""
    sx = max(-1.0, min(1.0, M[2, 1]))
    cxa = math.hypot(M[2, 0], M[2, 2])
    sols = []
    for cx in (cxa, -cxa):
        x = math.atan2(sx, cx)
        if abs(cx) > 1e-3:
            y = math.atan2(M[2, 0] / cx, M[2, 2] / cx); z = math.atan2(-M[0, 1] / cx, M[1, 1] / cx)
        else:   # x = +-90 deg (gimbal lock): only y -+ z is defined; put it all in y
            x = math.copysign(math.pi / 2, sx); z = 0.0; y = math.atan2(-M[0, 2], M[0, 0])
        sols.append(tuple(int(round(v * U)) % 1024 for v in (x, y, z)))
    # Two angle triples give the same rotation. Prefer the one closest to the previous key (the
    # engine interpolates each angle linearly), then the smaller angles (as the original data does).
    def dist(s, ref): return sum(min((a - b) % 1024, (b - a) % 1024) for a, b in zip(s, ref))
    return min(sols, key=lambda s: (dist(s, prev) if prev is not None else 0, dist(s, (0, 0, 0))))


def to_engine(v):
    return (C @ np.asarray(v, float)) * 1000


def _joint_map(doc):
    """(actor node, [node of group 0, 1, ...]) by name (Blender may reorder joints), else by order."""
    import re
    joints = doc["skins"][0]["joints"]
    names = {j: doc["nodes"][j].get("name", "") for j in joints}
    actor = next((j for j in joints if names[j] == "Actor"), joints[0])
    groups = {}
    for j in joints:
        m = re.match(r"g(\d+)", names[j])
        if m: groups[int(m.group(1))] = j
    if not groups or sorted(groups) != list(range(len(groups))):
        return actor, [j for j in joints if j != actor]
    return actor, [groups[i] for i in range(len(groups))]


def import_anims(path, only=None, use_extras=True):
    """Each joint's skinning matrix S = world * inverseBind maps the rest mesh to the posed mesh,
    whatever rest orientation the bones have (Blender adds its own). A group's own motion is
    L = S_parent^-1 * S: its rotation part is the AITD group rotation, and how far it moves the
    group's pivot is a type 1 (translate) offset."""
    doc, acc = load_glb(path)
    nodes = doc["nodes"]
    skin = doc["skins"][0]
    joints = skin["joints"]
    ibm = {j: m for j, m in zip(joints, acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1).astype(float))}
    actor, gnode = _joint_map(doc)
    ngroups = len(gnode)
    head = [np.linalg.inv(ibm[gnode[gi]])[:3, 3] for gi in range(ngroups)]   # rest pivots, glTF space
    parent_of = {}
    for i, nd in enumerate(nodes):
        for c in nd.get("children", []): parent_of[c] = i
    gparent = {}
    for gi, j in enumerate(gnode):
        p = parent_of.get(j)
        if p in gnode: gparent[gi] = gnode.index(p)
    result = {}
    for an in doc["animations"]:
        if only and an["name"] != only: continue
        ex = an.get("extras", {}) if use_extras else {}
        ch = {}
        for c in an["channels"]:
            s = an["samplers"][c["sampler"]]
            ch[(c["target"]["node"], c["target"]["path"])] = (acc(s["input"])[:, 0], acc(s["output"]))
        # key times in ticks; keep fractional keys apart (a zero-length keyframe is 0.01 tick long)
        times = []
        for tk in sorted(float(x) * FPS for tt, _ in ch.values() for x in tt):
            if not times or tk - times[-1] > 1e-4: times.append(tk)

        def sample(node, path, t, default):
            if (node, path) not in ch:
                return np.array(default, float)
            tt, vv = ch[(node, path)]
            tt = tt * FPS
            if t <= tt[0]: return vv[0].astype(float)
            if t >= tt[-1]: return vv[-1].astype(float)
            k = int(np.searchsorted(tt, t)); a = (t - tt[k - 1]) / (tt[k] - tt[k - 1])
            if abs(a) < 1e-4: return vv[k - 1].astype(float)
            if abs(a - 1) < 1e-4: return vv[k].astype(float)
            v0, v1 = vv[k - 1].astype(float), vv[k].astype(float)
            if path == "rotation":                       # nlerp is enough between keys
                if np.dot(v0, v1) < 0: v1 = -v1
                q = v0 * (1 - a) + v1 * a; return q / np.linalg.norm(q)
            return v0 * (1 - a) + v1 * a

        def skinning(t):
            world = {}
            def W(i):
                if i not in world:
                    nd = nodes[i]
                    tr = sample(i, "translation", t, nd.get("translation", [0, 0, 0]))
                    q = sample(i, "rotation", t, nd.get("rotation", [0, 0, 0, 1]))
                    sc = sample(i, "scale", t, nd.get("scale", [1, 1, 1]))
                    m = np.eye(4); m[:3, :3] = quat_mat(q) @ np.diag(sc); m[:3, 3] = tr
                    world[i] = W(parent_of[i]) @ m if i in parent_of else m
                return world[i]
            return {j: W(j) @ ibm[j] for j in joints}

        def local(S, gi):
            P = S[gnode[gparent[gi]]] if gi in gparent else S[actor]
            return np.linalg.inv(P) @ S[gnode[gi]]

        def pivot_move(L, gi):
            return L[:3, :3] @ head[gi] + L[:3, 3] - head[gi]

        S_all = [skinning(t) for t in times]
        # bones whose pivot moves somewhere in this animation are translate (type 1) bones
        movers = {gi for gi in range(1, ngroups) for S in S_all if np.abs(pivot_move(local(S, gi), gi)).max() > 1e-4}
        num_groups = ex.get("aitd_num_groups", ngroups)
        raw_groups = ex.get("aitd_groups")
        prev_angles = [None] * ngroups
        for gi in range(1, ngroups):                     # the start pose seeds the angle choice
            prev_angles[gi] = euler_from_matrix(C @ local(S_all[0], gi)[:3, :3] @ C)
        frames = []
        for k in range(1, len(times)):
            S = S_all[k]
            if np.abs(S[actor][:3, :3] - np.eye(3)).max() > 1e-3:
                warnings.append(f"{an['name']} key {k}: the Actor bone is rotated; only its movement is used")
            step = tuple(int(round(v)) for v in to_engine(S[actor][:3, 3] - S_all[k - 1][actor][:3, 3]))
            groups = []
            for gi in range(num_groups):
                if gi == 0 or gi >= ngroups:
                    if raw_groups and k - 1 < len(raw_groups):
                        r = raw_groups[k - 1][gi]; groups.append((r[0], tuple(r[1:])))
                    else:
                        if gi == 0 and np.abs(local(S, 0)[:3, :3] - np.eye(3)).max() > 1e-3:
                            warnings.append(f"{an['name']} key {k}: group 0 is rotated; the game ignores that "
                                            "(it uses the actor's facing), rotate its children instead")
                        groups.append((0, (0, 0, 0)))
                    continue
                L = local(S, gi)
                M = L[:3, :3]
                scale = np.linalg.norm(M, axis=0)
                R = M / scale
                d = pivot_move(L, gi)
                rotated = np.abs(R - np.eye(3)).max() > 1e-4
                scaled = np.abs(scale - 1).max() > 1e-4
                if rotated and ((gi in movers and np.abs(d).max() > 1e-4) or scaled):
                    warnings.append(f"{an['name']} key {k} {nodes[gnode[gi]].get('name')}: an AITD group can only "
                                    "rotate, move or scale in one keyframe; kept the rotation")
                if not rotated and scaled:
                    g = (2, tuple(int(round(v * 256 - 256)) for v in scale))
                elif not rotated and gi in movers:
                    g = (1, tuple(int(round(v)) for v in to_engine(d)))
                else:
                    ang = euler_from_matrix(C @ R @ C, prev_angles[gi])
                    prev_angles[gi] = ang
                    g = (0, ang)
                if raw_groups and k - 1 < len(raw_groups):
                    r = raw_groups[k - 1][gi]; rv = tuple(r[1:])
                    zero = not any(rv) and not any(g[1])
                    if r[0] == g[0] == 0:
                        same = np.abs(engine_rot(*rv) - engine_rot(*g[1])).max() < 0.01
                    else:
                        same = r[0] == g[0] and rv == g[1]
                    if same or zero:
                        g = (r[0], rv)                    # same pose: keep the original spelling
                        if r[0] == 0: prev_angles[gi] = rv
                groups.append(g)
            frames.append(Frame(int(round(times[k])) - int(round(times[k - 1])), step, groups))
        result[an["name"]] = Anim(frames, num_groups)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("glb"); ap.add_argument("--anim"); ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-extras", action="store_true")
    a = ap.parse_args()
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    for name, anim in import_anims(a.glb, a.anim, not a.no_extras).items():
        (out / f"{name}.anim").write_bytes(write_anim(anim))
        print(f"{name}: {len(anim.frames)} keyframes, {sum(f.time for f in anim.frames)} ticks")
    for w in warnings:
        print("WARNING:", w)
