"""Install, verify and uninstall the custom HD backgrounds (TatouHd.exe + backgrounds_custom/)
in a ReHaunted 2.4 folder. One implementation, used by:
  - the standalone patcher (custom_hd_app.py, and this file's command line);
  - the randomizer app (option "Include custom HD backgrounds").

  python custom_hd.py detect    GAME_DIR
  python custom_hd.py install   GAME_DIR --pack DIR [--game-data DIR] [--replace-unmanaged]
  python custom_hd.py verify    GAME_DIR [--full]
  python custom_hd.py uninstall GAME_DIR
  python custom_hd.py check-pack DIR

PACK is the HD release folder (Research/HDRepaint.md, "Shipping"):
  PACK/TatouHd.exe
  PACK/backgrounds_custom/<NAME>_<idx>[_<suffix>].png
  PACK/backgrounds_custom/anim_<NAME>_<idx>[_<suffix>]/<frames>.png
  PACK/backgrounds_custom/overlay_<NAME>_<idx>/<frames>.png  (RGBA, drawn over the scene)
  PACK/backgrounds_custom/bgoverlay_<NAME>_<idx>/<frames>.png  (RGBA, any size, drawn over the
  custom background only, under the actors)
  PACK/backgrounds_custom/bgoverlay2_<NAME>_<idx>/<frames>.png  (a second background overlay of
  that camera, the same way, drawn over the first)
  in an animation folder, optionally: frame_ms.txt, loop_from.txt (and, for an overlay,
  show_while_object.txt or sync_smoke.txt)
  PACK/backgrounds_custom/no_masks_<NAME>_<idx>.txt  (that camera's vanilla masks are not drawn
  while its custom image is shown; its overlay hides the actors instead. Empty: all masks; else
  the mask numbers to drop, counted over the camera's viewed rooms, e.g. "0")
Any camera or animation in it is installed; nothing here lists cameras. TatouHd.exe comes from the
pack, so a new TatouHd only needs a new pack: our builds are recognised by the marker string
"TatouHd build: flavor=<flavor>" in the exe (older builds by hash).

Rules:
- Only ReHaunted 2.4 folders (version.txt 2.4.x, or a known 2.4 Tatou.exe); anything else is
  refused before anything is written.
- Written: TatouHd.exe, backgrounds_custom/ and the manifest; with the edition TatouHd (no
  embedded game data) and no game files in the folder, also the original game files, copied from
  the player's own GOG/Steam/CD copy (install.py's search, checked against the GOG hashes).
  ReHaunted's own files (Tatou.exe, backgrounds_hd.hda, backgrounds_hd/, masks_hd/, configs) are
  never changed or removed.
- Name clash: Windows names are case-insensitive, so TatouHd.exe is the same file as the old 2.3
  HD inspector TatouHD.exe. A TatouHd.exe/TatouHD.exe that is not one of our builds stops the
  install (it is not renamed: that would change a file this tool did not install).
- AITD_CustomHD.json (the manifest) lists every installed file with its SHA-256. Files are
  copied to a temporary name, hashed, then moved into place. Uninstall removes exactly the files
  in the manifest that still have the recorded hash (changed ones are kept and reported).
- Re-running updates in place: unchanged files are skipped, files gone from the pack are removed,
  files already in backgrounds_custom/ that the manifest does not list are refused unless they
  are identical (then adopted) or --replace-unmanaged is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path

MANIFEST = "AITD_CustomHD.json"
EXE_NAME = "TatouHd.exe"
ASSET_DIR = "backgrounds_custom"
CFG_NAME = "aitd_remaster.cfg"          # ReHaunted 2.4 (2.3 used aitd_remaster_hd.cfg)
SEED_MARKER = "AITD_Randomizer.json"    # install.py MARKER
BUILD_MARKER = re.compile(rb"TatouHd build: flavor=(\w+)")

# TatouHd builds from before the marker (Research/HDRepaint.md). flavor "scenario": test build
# (ReHaunted + scenario tester, embedded game data); "edition": randomizer edition + custom
# backgrounds (no embedded data: needs the game files in the folder).
TATOUHD = {
    "0f0d8dbb0c94ab679ac2d20c2636fd98112e76f1d1e7be21a9ec6ec38ca2acf3":
        ("scenario", "TatouHd 0F0D8DBB (2026-10-19: custom stills only)"),
    "92160bcb3093d9e3e68fc35e7349556f263467b4bbde31701306f6cbcec6c062":
        ("scenario", "TatouHd 92160BCB (2026-10-20: custom stills and animations)"),
    "8fcd9ec777706192c72ba7d9e97232a5156926911adf5e585edbdcebd5e888b6":
        ("edition", "TatouHd edition 8FCD9EC7 (2026-10-20: randomizer edition 3526D627 + custom stills and animations)"),
}

# Tatou.exe builds known to be ReHaunted 2.4 (install.py KNOWN/EDITION)
REHAUNTED_24 = {
    "f90bf9522e41222e536c7968441b663df31de89cc722f61bda1fe7f61dfd8b79": "ReHaunted 2.4.0.1008, official release",
}

# a background name: CAMERAnn, or ITD_RESS (the title, intro and ending pictures, e.g. the
# ending's ITD_RESS_015..019, which TatouHd loads with their animations and overlays as cameras)
NAME = r"(?:ITD_RESS|[A-Z0-9]+)"
STILL_RE = re.compile(rf"^{NAME}_\d{{3}}(_[A-Z0-9]+)?\.png$", re.I)
ANIM_RE = re.compile(rf"^(anim_{NAME}_\d{{3}}(_[A-Z0-9]+)?|(overlay|bgoverlay2?)_{NAME}_\d{{3}})$", re.I)
NO_MASKS_RE = re.compile(rf"^no_masks_({NAME}_\d{{3}})\.txt$", re.I)
FRAME_EXT = (".png", ".tga", ".bmp")      # what scanAnimationDirectory accepts
FRAME_MS_FILE = "frame_ms.txt"            # optional per-animation speed (TatouHd)
LOOP_FROM_FILE = "loop_from.txt"          # optional: the frame the loop restarts at (1 = first)
SHOW_WHILE_FILE = "show_while_object.txt" # optional, overlays: shown while this object exists
SYNC_FILE = "sync_smoke.txt"              # optional, overlays: frames follow the smoke cloud's 11 s cycle
CONFIG_FILES = (FRAME_MS_FILE, LOOP_FROM_FILE, SHOW_WHILE_FILE, SYNC_FILE)

try:                                      # the game-data search and the edition hashes
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Generator"))
    import install as I
    for _h, _desc in I.EDITION.items():   # the 2.4-based randomizer editions count as ReHaunted 2.4
        if "2.4" in _desc or _desc.startswith("edition") and "as " in _desc:
            REHAUNTED_24.setdefault(_h, "AITD Randomizer " + _desc)
except ImportError:
    I = None


class Refused(Exception):
    pass


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_ci(folder: Path, name: str) -> Path | None:
    """A file or folder in `folder` whose name equals `name` ignoring case (as Windows does)."""
    if not folder.is_dir():
        return None
    return next((c for c in folder.iterdir() if c.name.lower() == name.lower()), None)


def png_info(p: Path) -> tuple[int, int, int] | None:
    """(width, height, channels) from the PNG header, or None if not a PNG."""
    with open(p, "rb") as f:
        head = f.read(26)
    if len(head) < 26 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", head[16:24])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(head[25], 0)
    return w, h, channels


def exe_info(p: Path) -> tuple[str, str] | None:
    """(flavor, description) if p is one of our TatouHd builds, else None. Read, never run."""
    data = p.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    if h in TATOUHD:
        return TATOUHD[h]
    m = BUILD_MARKER.search(data)
    if m and b"backgrounds_custom/" in data:
        flavor = m.group(1).decode()
        return flavor, f"TatouHd {'edition ' if flavor == 'edition' else ''}{h[:8].upper()}"
    return None


# ---- the game folder --------------------------------------------------------------------------
def read_cfg(game: Path) -> dict:
    cfg = find_ci(game, CFG_NAME)
    out = {}
    if cfg and cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith(("#", ";")):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def detect(game: Path) -> dict:
    """What is in the folder, and whether custom HD can go in. 'problems' stop an install."""
    game = game.resolve()
    info = {"folder": str(game), "rehaunted": None, "version": None, "tatou": None,
            "hd_archive": False, "hd_backgrounds_on": None, "game_data": False,
            "tatouhd": None, "manifest": None, "problems": [], "notes": []}
    if not game.is_dir():
        info["problems"].append(f"{game} is not a folder")
        return info
    tatou = find_ci(game, "Tatou.exe")
    ver = find_ci(game, "version.txt")
    if ver and ver.is_file():
        lines = ver.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        info["version"] = lines[0][:40] if lines else ""
    if tatou and tatou.is_file():
        h = sha(tatou)
        info["tatou"] = {"sha256": h, "identified_as": REHAUNTED_24.get(h, "unknown build")}
    known_exe = info["tatou"] is not None and info["tatou"]["sha256"] in REHAUNTED_24
    v24 = bool(info["version"]) and info["version"].startswith("2.4")
    if tatou is None:
        info["problems"].append("no Tatou.exe here: not a ReHaunted folder (choose the folder that holds "
                                "ReHaunted's Tatou.exe)")
    elif not (known_exe or v24):
        info["problems"].append("this is not ReHaunted 2.4 (version.txt says "
                                f"{info['version'] or 'nothing'}, Tatou.exe is an unknown build); "
                                "the custom HD backgrounds need ReHaunted 2.4")
    else:
        info["rehaunted"] = "2.4" + (f" ({info['version']})" if info["version"] else "")
        if not known_exe:
            info["notes"].append("Tatou.exe is not a build this tool knows, but version.txt says "
                                 f"{info['version']}: accepted as ReHaunted 2.4")
    info["hd_archive"] = find_ci(game, "backgrounds_hd.hda") is not None
    hd = read_cfg(game).get("graphics.hdBackgrounds")
    info["hd_backgrounds_on"] = None if hd is None else hd.lower() in ("true", "1")
    if info["hd_backgrounds_on"] is False:
        info["notes"].append("HD backgrounds are switched off in aitd_remaster.cfg: TatouHd only shows "
                             "the custom backgrounds with HD backgrounds on (options window, Graphics)")
    info["game_data"] = find_ci(game, "ITD_RESS.PAK") is not None
    m = load_manifest(game)
    info["manifest"] = None if m is None else {"files": len(m["files"]), "installed": m.get("installed"),
                                               "installed_by": m.get("installed_by"), "exe": m.get("exe"),
                                               "game_data": len(m.get("game_data") or {})}
    clash = find_ci(game, EXE_NAME)
    if clash is not None and clash.is_file():
        ei = exe_info(clash)
        info["tatouhd"] = {"name": clash.name, "identified_as": ei[1] if ei else "unknown"}
        if ei is None:
            info["problems"].append(
                f"{clash.name} here is not one of our TatouHd builds (probably the old ReHaunted 2.3 HD "
                f"inspector TatouHD.exe: Windows treats TatouHd.exe and TatouHD.exe as the same file). "
                "Move or rename it yourself, then run this again; it is not changed automatically")
        elif ei[0] == "edition" and not info["game_data"]:
            info["notes"].append("the installed TatouHd plays from the original game files, and this "
                                 "folder has none: run Install / Update to copy them in")
    return info


def load_manifest(game: Path) -> dict | None:
    p = game / MANIFEST
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---- the pack -------------------------------------------------------------------------------
def pack_exe(pack: Path) -> tuple[Path, str, str]:
    """(TatouHd.exe in the pack, flavor, description)."""
    exe = find_ci(pack, EXE_NAME) if pack.is_dir() else None
    if exe is None or not exe.is_file():
        raise Refused(f"no {EXE_NAME} in {pack} (choose the custom HD pack folder: it holds {EXE_NAME} "
                      f"and the {ASSET_DIR} folder)")
    ei = exe_info(exe)
    if ei is None:
        raise Refused(f"{exe} is not one of our TatouHd builds")
    return exe, ei[0], ei[1]


def check_config(folder: str, f: Path, nframes: int, overlay: bool) -> list[str]:
    """Warnings for an animation folder's text file (the game ignores a bad value)."""
    text = f.read_text(encoding="utf-8", errors="replace").strip()
    name = f.name.lower()
    try:
        v = int(text.split()[0]) if text else None
    except ValueError:
        v = None
    if name == FRAME_MS_FILE and (v is None or not 10 <= v <= 2000):
        return [f"{folder}/{f.name}: expected milliseconds per frame (10-2000), got {text!r}"]
    if name == LOOP_FROM_FILE and (v is None or not 1 <= v <= nframes):
        return [f"{folder}/{f.name}: expected a frame number (1-{nframes}), got {text!r}"]
    if name == SYNC_FILE:
        if not overlay:
            return [f"{folder}/{f.name}: only overlay_ folders use it"]
        others = [c.name for c in f.parent.iterdir() if c.name.lower() in CONFIG_FILES and c.name.lower() != SYNC_FILE]
        if others:
            return [f"{folder}: {', '.join(others)} not used by a synced overlay (its frames span the 11 s cycle)"]
        return []
    if name == SHOW_WHILE_FILE:
        if not overlay:
            return [f"{folder}/{f.name}: only overlay_ folders use it"]
        if v is None or v < 0:
            return [f"{folder}/{f.name}: expected an object number, got {text!r}"]
    return []


def scan_assets(pack: Path) -> tuple[dict[str, Path], list[str], dict]:
    """(relative path -> source file, warnings, summary) for PACK/backgrounds_custom.
    Checks names, PNG headers and that every frame of an animation has the same size."""
    root = find_ci(pack, ASSET_DIR) if pack.is_dir() else None
    if root is None or not root.is_dir():
        raise Refused(f"no {ASSET_DIR} folder in {pack} (choose the custom HD pack folder: it holds "
                      f"{EXE_NAME} and {ASSET_DIR}/CAMERA00_000.png, {ASSET_DIR}/anim_CAMERA00_000/...)")
    files, warn = {}, []
    stills, anims, frames, size = 0, 0, 0, 0
    no_masks = []
    for p in sorted(root.iterdir()):
        if p.is_file():
            if NO_MASKS_RE.match(p.name):
                files[f"{ASSET_DIR}/{p.name}"] = p
                no_masks.append(p.name)
                continue
            if not STILL_RE.match(p.name):
                warn.append(f"skipped {p.name}: not a camera image name (<NAME>_<idx>[_<suffix>].png)")
                continue
            pi = png_info(p)
            if pi is None:
                warn.append(f"skipped {p.name}: not a PNG file")
                continue
            if pi[:2] != (1280, 800):
                warn.append(f"{p.name} is {pi[0]}x{pi[1]} (the repaints are 1280x800)")
            files[f"{ASSET_DIR}/{p.name}"] = p
            stills += 1
            size += p.stat().st_size
        elif p.is_dir():
            if not ANIM_RE.match(p.name):
                warn.append(f"skipped folder {p.name}: not an animation name "
                            "(anim_<NAME>_<idx>[_<suffix>], overlay_<NAME>_<idx>, bgoverlay_<NAME>_<idx> or "
                            "bgoverlay2_<NAME>_<idx>)")
                continue
            overlay = p.name.lower().startswith("overlay_")
            bg_overlay = p.name.lower().startswith(("bgoverlay_", "bgoverlay2_"))
            fr = sorted(c for c in p.iterdir() if c.is_file() and c.suffix.lower() in FRAME_EXT)
            configs = [c for c in p.iterdir() if c.is_file() and c.name.lower() in CONFIG_FILES]
            other = [c.name for c in p.iterdir() if c not in fr and c not in configs]
            if other:
                warn.append(f"{p.name}: skipped {len(other)} non-frame item(s), e.g. {other[0]}")
            if not fr:
                warn.append(f"skipped folder {p.name}: no frames")
                continue
            for c in configs:
                files[f"{ASSET_DIR}/{p.name}/{c.name}"] = c
                warn.extend(check_config(p.name, c, len(fr), overlay))
            dims = {}
            for c in fr:
                if c.suffix.lower() == ".png":
                    dims.setdefault(png_info(c), []).append(c.name)
            if len(dims) > 1:
                common = max(dims, key=lambda k: len(dims[k]))
                odd = [n for k, v in dims.items() if k != common for n in v]
                warn.append(f"{p.name}: {len(odd)} frame(s) differ from {common} (e.g. {odd[0]}); "
                            "the game skips frames of another size")
            if overlay and any(k is not None and k[2] != 4 for k in dims):
                warn.append(f"{p.name}: overlay frames without an alpha channel cover the whole scene")
            if bg_overlay and any(k is not None and k[2] != 4 for k in dims):
                warn.append(f"{p.name}: overlay frames without an alpha channel cover the whole background")
            for c in fr:
                files[f"{ASSET_DIR}/{p.name}/{c.name}"] = c
                size += c.stat().st_size
            anims += 1
            frames += len(fr)
    packed = {k.split("/", 1)[1].lower() for k in files}
    for name in no_masks:
        cam = NO_MASKS_RE.match(name).group(1).lower()
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        bad = [w for w in re.split(r"[\s,;]+", text) if w and not w.isdigit()]
        if bad:
            warn.append(f"{name}: expected mask numbers (e.g. 0) or nothing, the game ignores {bad[0]!r}")
        if f"{cam}.png" not in packed and not any(k.startswith(f"anim_{cam}/") for k in packed):
            warn.append(f"{name}: no custom background {cam.upper()} in the pack, so its vanilla masks stay")
        elif not any(k.startswith(f"overlay_{cam}/") for k in packed):
            warn.append(f"{name}: no overlay_{cam.upper()}, so nothing hides the actors on that camera")
    summary = {"stills": stills, "animations": anims, "frames": frames, "bytes": size}
    return files, warn, summary


def find_game_data(game_data: Path | None = None) -> tuple[str, Path]:
    """The player's original game files, for an edition TatouHd in a folder without them:
    the chosen folder, else install.py's Steam/GOG/CD search; must be the GOG release files."""
    if I is None:
        raise Refused("the game-data search (install.py) is missing from this patcher")
    if game_data is not None:
        how, src = "chosen folder", game_data.resolve()
        if not I.find(src, I.SENTINEL):
            raise Refused(f"no {I.SENTINEL} in {src}: choose the folder of your GOG, Steam or CD copy of "
                          "Alone in the Dark that holds ITD_RESS.PAK (usually called INDARK)")
    else:
        found = I.search_game_data()
        if not found:
            raise Refused("TatouHd plays from the original game files, and none are in the ReHaunted "
                          "folder or in a GOG/Steam/CD install. Choose the folder of your copy of the "
                          "game that holds ITD_RESS.PAK (usually called INDARK)")
        how, src = found[0]
    missing, different = I.check_game_data(src)
    if missing or different:
        raise Refused(f"the game files in {src} ({how}) are not the original GOG/Steam release files"
                      + (f"; missing: {', '.join(missing)}" if missing else "")
                      + (f"; different: {', '.join(different)}" if different else ""))
    return how, src


# ---- install / verify / uninstall -------------------------------------------------------------
def _copy_verified(src: Path, dst: Path, want: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    if sha(tmp) != want:
        tmp.unlink()
        raise Refused(f"copy of {src} did not verify (disk or source problem); stopped")
    os.replace(tmp, dst)


def _record(p: Path, h: str) -> dict:
    st = p.stat()
    return {"sha256": h, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _unchanged(p: Path, rec: dict, full: bool) -> bool:
    """Same as recorded: size and modification time (fast), or the full hash."""
    if not p.is_file():
        return False
    st = p.stat()
    if st.st_size != rec["size"]:
        return False
    if not full and st.st_mtime_ns == rec.get("mtime_ns"):
        return True
    return sha(p) == rec["sha256"]


def install(game: Path, pack: Path, replace_unmanaged: bool = False, installed_by: str = "standalone",
            require_flavor: str | None = None, game_data: Path | None = None, log=print) -> dict:
    """Install or update from PACK. Every check that can refuse runs before the first write.
    require_flavor: the randomizer needs the edition TatouHd (the scenario one can't play seeds)."""
    game = game.resolve()
    pack = pack.resolve()
    info = detect(game)
    if info["problems"]:
        raise Refused(info["problems"][0])
    exe, flavor, exe_desc = pack_exe(pack)
    if require_flavor and flavor != require_flavor:
        raise Refused(f"the {EXE_NAME} in {pack} is the {flavor} build; this needs the {require_flavor} build")
    files, warn, summary = scan_assets(pack)
    for w in warn:
        log("note: " + w)
    if not files:
        raise Refused(f"no custom backgrounds in {pack / ASSET_DIR}")
    old = load_manifest(game) or {"files": {}}
    data_copy = {}                         # name -> source file, original game files to copy in
    if flavor == "edition" and not info["game_data"]:
        how, src = find_game_data(game_data)
        for name in I.VANILLA:
            p = I.find(src, name)
            if p is not None and not I.find(game, name):
                data_copy[p.name] = p
        log(f"original game files: {len(data_copy)} to copy from {src} ({how})")
    want = {EXE_NAME: (exe, sha(exe))}
    log(f"checking {len(files)} asset file(s) ({summary['bytes'] / 1e6:.0f} MB)...")
    for rel, src in files.items():
        # a source file with the size and time recorded at the last install keeps its hash
        rec, st = old["files"].get(rel, {}), src.stat()
        if rec.get("src_size") == st.st_size and rec.get("src_mtime_ns") == st.st_mtime_ns:
            want[rel] = (src, rec["sha256"])
        else:
            want[rel] = (src, sha(src))
    # files already in the folder that the manifest does not list
    unmanaged, adopt = [], []
    for rel, (src, h) in want.items():
        dst = game / rel
        if rel == EXE_NAME:
            dst = find_ci(game, EXE_NAME) or dst
        if dst.exists() and rel not in old["files"]:
            if rel == EXE_NAME and exe_info(dst) is not None:
                continue                       # one of our builds, copied by hand: replaced
            if sha(dst) == h:
                adopt.append(rel)
            else:
                unmanaged.append(rel)
    if unmanaged and not replace_unmanaged:
        raise Refused(f"{len(unmanaged)} file(s) already in the folder were not installed by this tool and "
                      f"differ from the new ones, e.g. {unmanaged[0]}. Move them away, or rerun with "
                      "--replace-unmanaged to overwrite them (they are then removed by uninstall)")
    copy = [rel for rel in want if rel not in adopt and not (
        rel in old["files"] and old["files"][rel]["sha256"] == want[rel][1]
        and _unchanged(game / rel, old["files"][rel], full=False))]
    remove = [rel for rel in old["files"] if rel not in want]
    need = sum(want[rel][0].stat().st_size for rel in copy) + sum(p.stat().st_size for p in data_copy.values())
    free = shutil.disk_usage(game).free
    if need > free - 200_000_000:
        raise Refused(f"not enough disk space: {need / 1e9:.2f} GB to copy, {free / 1e9:.2f} GB free")
    # ---- writes ----
    log(f"copying {len(copy)} file(s) ({need / 1e6:.0f} MB), {len(want) - len(copy)} unchanged, "
        f"{len(remove)} to remove")
    new = {"tool": "custom_hd.py", "installed_by": installed_by,
           "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
           "exe": {"sha256": want[EXE_NAME][1], "flavor": flavor, "build": exe_desc},
           "assets": summary, "files": dict(old["files"]), "game_data": dict(old.get("game_data") or {})}
    try:
        for name, src in data_copy.items():
            h = sha(src)
            _copy_verified(src, game / name, h)
            new["game_data"][name] = _record(game / name, h)
        for i, rel in enumerate(copy, 1):
            src, h = want[rel]
            dst = game / rel
            if rel == EXE_NAME:
                dst = find_ci(game, EXE_NAME) or dst
                if dst.name != EXE_NAME:          # one of our builds under another case: same file
                    dst.unlink()
                    dst = game / EXE_NAME
            _copy_verified(src, dst, h)
            new["files"][rel] = _record(dst, h)
            if i % 200 == 0:
                log(f"  {i}/{len(copy)}")
        for rel in adopt:
            new["files"][rel] = _record(game / rel, want[rel][1])
        for rel, (src, h) in want.items():
            if rel in new["files"] and new["files"][rel]["sha256"] == h:
                st = src.stat()
                new["files"][rel].update(src_size=st.st_size, src_mtime_ns=st.st_mtime_ns)
        for rel in remove:
            rec = old["files"][rel]
            p = game / rel
            if p.is_file() and _unchanged(p, rec, full=True):
                p.unlink()
            elif p.exists():
                log(f"note: {rel} is no longer in the pack but was changed since install; kept")
            new["files"].pop(rel, None)
    finally:
        (game / MANIFEST).write_text(json.dumps(new, indent=1) + "\n", encoding="utf-8")
    _remove_empty_dirs(game / ASSET_DIR)
    bad = verify(game, full=False, log=lambda s: None)
    if bad:
        raise Refused(f"verification failed after install: {bad[0]}")
    log(f"installed {EXE_NAME} ({exe_desc}) and {summary['stills']} still(s), {summary['animations']} "
        f"animation(s) ({summary['frames']} frames) into {game}; manifest {MANIFEST}"
        + (f"; copied {len(data_copy)} original game file(s)" if data_copy else ""))
    for n in info["notes"]:
        log("note: " + n)
    return new


def verify(game: Path, full: bool = True, log=print) -> list[str]:
    """Problems with the installed files (empty: all present and unchanged)."""
    game = game.resolve()
    m = load_manifest(game)
    if m is None:
        return ["no custom HD install here (no manifest)"]
    bad = []
    for rel, rec in list(m["files"].items()) + list((m.get("game_data") or {}).items()):
        p = game / rel
        if rel == EXE_NAME:
            p = find_ci(game, EXE_NAME) or p
        if not p.is_file():
            bad.append(f"missing: {rel}")
        elif not _unchanged(p, rec, full):
            bad.append(f"changed: {rel}")
    n = len(m["files"]) + len(m.get("game_data") or {})
    log(f"{n} file(s) checked{' (full hash)' if full else ''}: "
        + ("all OK" if not bad else f"{len(bad)} problem(s)"))
    for b in bad[:20]:
        log("  " + b)
    return bad


def uninstall(game: Path, log=print) -> int:
    """Remove exactly the installed files that still have their recorded hash. Game files copied
    in for TatouHd stay while a randomizer seed is installed (the seed's backup holds them)."""
    game = game.resolve()
    m = load_manifest(game)
    if m is None:
        raise Refused("no custom HD backgrounds are installed here (no manifest)")
    seed = (game / SEED_MARKER).exists()
    kept, removed = [], 0
    for rel, rec in m["files"].items():
        p = game / rel
        if rel == EXE_NAME:
            p = find_ci(game, EXE_NAME) or p
        if not p.exists():
            continue
        if _unchanged(p, rec, full=True):
            p.unlink()
            removed += 1
        else:
            kept.append(rel)
    kept_data = {}
    for name, rec in (m.get("game_data") or {}).items():
        p = game / name
        if not p.exists():
            continue
        if not seed and _unchanged(p, rec, full=True):
            p.unlink()
            removed += 1
        else:
            kept_data[name] = rec
    if kept_data:
        log(f"kept {len(kept_data)} original game file(s) copied in by this tool: "
            + ("a randomizer seed is installed and uses them" if seed else "changed since install"))
    _remove_empty_dirs(game / ASSET_DIR)
    if kept or kept_data:
        m["files"] = {rel: m["files"][rel] for rel in kept}
        m["game_data"] = kept_data
        (game / MANIFEST).write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
        if kept:
            log(f"removed {removed} file(s); kept {len(kept)} changed since install (still listed in "
                f"{MANIFEST}), e.g. {kept[0]}")
    else:
        (game / MANIFEST).unlink()
        log(f"removed {removed} file(s) and the manifest")
    return len(kept)


def _remove_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    if not any(root.iterdir()):
        root.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect").add_argument("game", type=Path)
    p = sub.add_parser("install")
    p.add_argument("game", type=Path)
    p.add_argument("--pack", type=Path, required=True, help="the HD pack folder (TatouHd.exe + backgrounds_custom)")
    p.add_argument("--game-data", type=Path, help="original game files, if not found automatically")
    p.add_argument("--replace-unmanaged", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("game", type=Path)
    v.add_argument("--full", action="store_true", help="hash every file (default: size and time)")
    sub.add_parser("uninstall").add_argument("game", type=Path)
    sub.add_parser("check-pack").add_argument("pack", type=Path)
    a = ap.parse_args()
    try:
        if a.cmd == "detect":
            print(json.dumps(detect(a.game), indent=1))
        elif a.cmd == "install":
            install(a.game, a.pack, a.replace_unmanaged, game_data=a.game_data)
        elif a.cmd == "verify":
            return 1 if verify(a.game, a.full) else 0
        elif a.cmd == "uninstall":
            return 1 if uninstall(a.game) else 0
        else:
            _exe, flavor, desc = pack_exe(a.pack.resolve())
            files, warn, s = scan_assets(a.pack.resolve())
            for w in warn:
                print("note: " + w)
            print(f"{desc} ({flavor}); {s['stills']} still(s), {s['animations']} animation(s), "
                  f"{s['frames']} frame(s), {s['bytes'] / 1e6:.0f} MB")
    except Refused as e:
        print("REFUSED: " + str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
