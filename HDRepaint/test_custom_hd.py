"""Tests of custom_hd.py (install / update / verify / uninstall) on a fake ReHaunted 2.4 folder.

  python test_custom_hd.py WORK_DIR

WORK_DIR is created and filled with: game/ (Tatou.exe stand-in, version.txt 2.4.0.1008,
backgrounds_hd.hda / backgrounds_hd / masks_hd stand-ins, a config) and pack/ (an HD pack:
TatouHd.exe + backgrounds_custom with 5 stills from Generated/HDRepaint/test_images and a 10-frame animation).
OriginalGame/INDARK stands in for the player's GOG copy (only read). Prints PASS/FAIL per check.
"""
import hashlib, shutil, sys  # noqa: E401
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import custom_hd as CH  # noqa: E402

ROOT = HERE.parents[1]
BUILD = ROOT / "ReHaunted24/TatouSource/build"
SCEN_EXE = BUILD / "hd-repaint/Fitd/TatouHd.exe"
ED_EXE = BUILD / "hd-edition/Fitd/TatouHd.exe"
GOG = ROOT / "OriginalGame/INDARK"
results = []


def check(name, cond):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name)


def tree(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


def refused(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
    except CH.Refused as e:
        return str(e)
    return ""


def tiny_png(path: Path, channels: int):
    """A 4x4 PNG, RGB (3) or RGBA (4)."""
    import struct, zlib  # noqa: E401
    row = b"\0" + bytes([200, 200, 200, 128][:channels]) * 4
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6 if channels == 4 else 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * 4)) + chunk(b"IEND", b""))


def quiet(*a, **k):
    return CH.install(*a, log=lambda s: None, **k)


def main(work: Path):
    if work.exists():
        shutil.rmtree(work)
    game, pack = work / "game", work / "pack"
    (game / "backgrounds_hd").mkdir(parents=True)
    (game / "masks_hd/FLOOR00/CAM000").mkdir(parents=True)
    (game / "Tatou.exe").write_bytes(b"stand-in for ReHaunted's Tatou.exe")
    (game / "version.txt").write_text("2.4.0.1008\n")
    (game / "backgrounds_hd.hda").write_bytes(b"HDBG stand-in")
    (game / "backgrounds_hd/CAMERA00_000.png").write_bytes(b"rehaunted loose still")
    (game / "masks_hd/FLOOR00/CAM000/RID000_ROOM00_MASK00.png").write_bytes(b"mask")
    (game / "aitd_remaster.cfg").write_text("graphics.hdBackgrounds = true\n")
    bc = pack / "backgrounds_custom"
    bc.mkdir(parents=True)
    shutil.copy2(SCEN_EXE, pack / "TatouHd.exe")
    for i in range(5):
        shutil.copy2(ROOT / f"Generated/HDRepaint/test_images/CAMERA00_{i:03d}.png", bc)
    anim = bc / "anim_CAMERA00_000"
    anim.mkdir()
    for i in range(10):
        shutil.copy2(ROOT / f"Generated/HDRepaint/test_images/CAMERA00_{i % 5:03d}.png", anim / f"ezgif-frame-{i + 1:03d}.png")
    (bc / "Thumbs.db").write_bytes(b"x")
    rehaunted = tree(game)
    log = []

    d = CH.detect(game)
    check("detect: 2.4 by version.txt, no problems", d["rehaunted"] and not d["problems"])
    check("exe_info: marker builds and old builds recognised, the edition Tatou.exe not",
          CH.exe_info(SCEN_EXE)[0] == "scenario" and CH.exe_info(ED_EXE)[0] == "edition"
          and CH.exe_info(BUILD / "randomizer-edition/Fitd/Tatou.exe") is None)
    m = CH.install(game, pack, log=log.append)
    check("install: manifest lists exe + 5 stills + 10 frames, no game data", len(m["files"]) == 16 and not m["game_data"])
    check("install: Thumbs.db skipped with a note", any("Thumbs.db" in s for s in log))
    check("install: ReHaunted's files unchanged", all(tree(game)[k] == v for k, v in rehaunted.items()))
    check("verify (full): no problems", CH.verify(game, full=True, log=lambda s: None) == [])

    log.clear()
    CH.install(game, pack, log=log.append)
    check("re-run: nothing copied", any("copying 0 file(s)" in s for s in log))

    (anim / "ezgif-frame-010.png").unlink()
    shutil.copy2(ROOT / "Generated/HDRepaint/test_images/CAMERA01_000.png", bc)
    log.clear()
    CH.install(game, pack, log=log.append)
    check("update: 1 copied, 1 removed", any("copying 1 file(s)" in s and "1 to remove" in s for s in log))
    check("update: removed frame is gone", not (game / "backgrounds_custom/anim_CAMERA00_000/ezgif-frame-010.png").exists())

    (game / "backgrounds_custom/CAMERA00_001.png").write_bytes(b"user edit")
    check("verify: finds the changed file", any("CAMERA00_001" in b for b in CH.verify(game, log=lambda s: None)))

    shutil.copy2(ROOT / "Generated/HDRepaint/test_images/CAMERA01_002.png", game / "backgrounds_custom/CAMERA09_000.png")
    shutil.copy2(ROOT / "Generated/HDRepaint/test_images/CAMERA01_003.png", bc / "CAMERA09_000.png")
    check("unmanaged different file: refused", "were not installed by this tool" in refused(quiet, game, pack))
    quiet(game, pack, replace_unmanaged=True)
    check("--replace-unmanaged: taken over", "backgrounds_custom/CAMERA09_000.png" in CH.load_manifest(game)["files"])
    (bc / "CAMERA09_000.png").unlink()
    quiet(game, pack)

    # the edition TatouHd: game files copied in from the player's copy (search pointed at OriginalGame)
    shutil.copy2(ED_EXE, pack / "TatouHd.exe")
    real_search = CH.I.search_game_data
    CH.I.search_game_data = lambda: []
    check("edition, no game files anywhere: refused", "none are in the ReHaunted folder" in refused(quiet, game, pack))
    CH.I.search_game_data = lambda: [("GOG", GOG)]
    m = quiet(game, pack)
    check("edition: exe replaced in place, 37 original game files copied and recorded",
          m["exe"]["flavor"] == "edition" and len(m["game_data"]) == 37 and (game / "ITD_RESS.PAK").exists())
    check("edition: verify covers the game files", CH.verify(game, full=True, log=lambda s: None) == [])
    log.clear()
    CH.install(game, pack, log=log.append)
    check("edition re-run: game files not copied again", not any("original game files" in s for s in log))
    CH.I.search_game_data = real_search
    shutil.copy2(SCEN_EXE, pack / "TatouHd.exe")
    check("require_flavor=edition with a scenario TatouHd: refused",
          "needs the edition build" in refused(quiet, game, pack, require_flavor="edition"))
    shutil.copy2(ED_EXE, pack / "TatouHd.exe")

    (game / "AITD_Randomizer.json").write_text("{}")      # a seed installed after the custom HD
    (game / "backgrounds_custom/CAMERA00_002.png").write_bytes(b"user edit 2")
    kept = CH.uninstall(game, log=lambda s: None)
    check("uninstall with a seed installed: keeps the game files and the changed still",
          kept == 1 and (game / "ITD_RESS.PAK").exists() and len(CH.load_manifest(game)["game_data"]) == 37)
    (game / "AITD_Randomizer.json").unlink()
    (game / "backgrounds_custom/CAMERA00_002.png").unlink()
    CH.uninstall(game, log=lambda s: None)
    check("uninstall without the seed: game files removed, folder exactly as before",
          tree(game) == rehaunted and not (game / CH.MANIFEST).exists())

    clash = game / "TatouHD.exe"
    clash.write_bytes(b"old 2.3 HD inspector stand-in")
    msg = refused(quiet, game, pack)
    check("name clash TatouHD.exe (unknown): refused, file untouched",
          "TatouHD.exe" in msg and clash.read_bytes() == b"old 2.3 HD inspector stand-in")
    clash.unlink()
    shutil.copy2(SCEN_EXE, pack / "TatouHd.exe")
    shutil.copy2(SCEN_EXE, game / "TATOUHD.EXE")
    quiet(game, pack)
    names = [p.name for p in game.iterdir() if p.name.lower() == "tatouhd.exe"]
    check("our build under another case: replaced, one file named TatouHd.exe", names == ["TatouHd.exe"])
    CH.uninstall(game, log=lambda s: None)
    check("uninstall again: folder exactly as before", tree(game) == rehaunted)

    (pack / "TatouHd.exe").write_bytes(b"not ours")
    check("pack with a foreign TatouHd.exe: refused", "not one of our TatouHd builds" in refused(quiet, game, pack))
    (pack / "TatouHd.exe").unlink()
    check("pack without TatouHd.exe: refused", "no TatouHd.exe in" in refused(quiet, game, pack))
    shutil.copy2(SCEN_EXE, pack / "TatouHd.exe")
    (game / "version.txt").write_text("2.3.0.900\n")
    check("ReHaunted 2.3 (version.txt, unknown exe): refused", "not ReHaunted 2.4" in refused(quiet, game, pack))
    (game / "Tatou.exe").unlink()
    check("no Tatou.exe: refused", "no Tatou.exe" in refused(quiet, game, pack))

    # overlays and the animation text files (scan only)
    ov_pack = work / "ov_pack"
    ob = ov_pack / "backgrounds_custom"
    ov, ov_rgb, an = ob / "overlay_CAMERA03_013", ob / "overlay_CAMERA03_014", ob / "anim_CAMERA03_015"
    for d in (ov, ov_rgb, an, ob / "overlay_CAMERA03_016_DARK"):
        d.mkdir(parents=True)
    for i in range(4):
        tiny_png(ov / f"frame_{i + 1:03d}.png", 4)
        tiny_png(ov_rgb / f"frame_{i + 1:03d}.png", 3)
        tiny_png(an / f"frame_{i + 1:03d}.png", 3)
    (ov / "loop_from.txt").write_text("3\n")
    (ov / "show_while_object.txt").write_text("98\n")
    (ov / "frame_ms.txt").write_text("100")
    (ov_rgb / "loop_from.txt").write_text("9")
    (an / "show_while_object.txt").write_text("98")
    files, warn, summary = CH.scan_assets(ov_pack)
    check("overlay: frames and its three text files packed",
          all(f"backgrounds_custom/overlay_CAMERA03_013/{n}" in files
              for n in ("frame_004.png", "loop_from.txt", "show_while_object.txt", "frame_ms.txt")))
    check("overlay: counted with the animations", summary["animations"] == 3 and summary["frames"] == 12)
    check("overlay with a suffix: skipped as a bad name", any("overlay_CAMERA03_016_DARK" in w for w in warn))
    check("overlay without alpha: warned", any("CAMERA03_014: overlay frames without an alpha" in w for w in warn))
    check("loop_from.txt past the last frame: warned", any("CAMERA03_014/loop_from.txt" in w for w in warn))
    check("show_while_object.txt in an animation: warned", any("CAMERA03_015/show_while_object.txt" in w for w in warn))
    check("good overlay: no warnings", not any("CAMERA03_013" in w for w in warn))
    sy = ob / "overlay_CAMERA03_008"
    sy.mkdir()
    for i in range(3):
        tiny_png(sy / f"frame_{i + 1:03d}.png", 4)
    (sy / "sync_smoke.txt").write_text("")
    files, warn, _ = CH.scan_assets(ov_pack)
    check("synced overlay: sync_smoke.txt packed, no warnings",
          "backgrounds_custom/overlay_CAMERA03_008/sync_smoke.txt" in files and not any("CAMERA03_008" in w for w in warn))
    (sy / "frame_ms.txt").write_text("100")
    _, warn, _ = CH.scan_assets(ov_pack)
    check("synced overlay with frame_ms.txt: warned as unused", any("CAMERA03_008: frame_ms.txt not used" in w for w in warn))
    # background overlays: bgoverlay_<NAME>_<idx>, frame_ms.txt / loop_from.txt only
    bo, bo_rgb = ob / "bgoverlay_CAMERA05_013", ob / "bgoverlay_CAMERA05_014"
    bo2, bo3 = ob / "bgoverlay2_CAMERA05_013", ob / "bgoverlay3_CAMERA05_016"   # second layer; no third
    for d in (bo, bo_rgb, ob / "bgoverlay_CAMERA05_015_DARK", bo2, bo3):
        d.mkdir()
    for i in range(3):
        tiny_png(bo / f"frame_{i + 1:03d}.png", 4)
        tiny_png(bo_rgb / f"frame_{i + 1:03d}.png", 3)
        tiny_png(bo2 / f"frame_{i + 1:03d}.png", 4)
        tiny_png(bo3 / f"frame_{i + 1:03d}.png", 4)
    (bo / "frame_ms.txt").write_text("120")
    (bo / "loop_from.txt").write_text("2")
    (bo_rgb / "show_while_object.txt").write_text("98")
    files, warn, _ = CH.scan_assets(ov_pack)
    check("background overlay: frames and its text files packed, no warnings",
          all(f"backgrounds_custom/bgoverlay_CAMERA05_013/{n}" in files
              for n in ("frame_003.png", "frame_ms.txt", "loop_from.txt"))
          and not any("CAMERA05_013" in w for w in warn))
    check("background overlay without alpha: warned",
          any("bgoverlay_CAMERA05_014: overlay frames without an alpha channel cover the whole background" in w
              for w in warn))
    check("show_while_object.txt in a background overlay: warned",
          any("bgoverlay_CAMERA05_014/show_while_object.txt: only overlay_ folders use it" in w for w in warn))
    check("background overlay with a suffix: skipped as a bad name",
          any("skipped folder bgoverlay_CAMERA05_015_DARK" in w for w in warn))
    check("second background overlay bgoverlay2_: packed, no warnings",
          "backgrounds_custom/bgoverlay2_CAMERA05_013/frame_003.png" in files
          and not any("bgoverlay2_CAMERA05_013" in w for w in warn))
    check("bgoverlay3_: skipped as a bad name (two layers only)",
          any("skipped folder bgoverlay3_CAMERA05_016" in w for w in warn)
          and not any(k.startswith("backgrounds_custom/bgoverlay3_") for k in files))
    for d in (bo, bo_rgb, ob / "bgoverlay_CAMERA05_015_DARK", bo2, bo3):
        shutil.rmtree(d)
    # ending pictures: ITD_RESS_<idx>.png and its overlays, as for a camera
    er = [ob / "bgoverlay_ITD_RESS_017", ob / "bgoverlay2_ITD_RESS_017"]
    tiny_png(ob / "ITD_RESS_017.png", 3)
    for d in er:
        d.mkdir()
        for i in range(2):
            tiny_png(d / f"frame_{i + 1:03d}.png", 4)
    files, warn, _ = CH.scan_assets(ov_pack)
    check("ending picture ITD_RESS_017 with both background overlays: packed, no skip warnings",
          "backgrounds_custom/ITD_RESS_017.png" in files
          and all(f"backgrounds_custom/{d.name}/frame_002.png" in files for d in er)
          and not any("skipped" in w and "ITD_RESS" in w for w in warn))
    (ob / "ITD_RESS_017.png").unlink()
    for d in er:
        shutil.rmtree(d)
    # no_masks markers: anim_CAMERA03_015 has no overlay, CAMERA03_013 gets a still, CAMERA03_099 has both
    for cam in ("CAMERA03_015", "CAMERA03_013", "CAMERA03_099"):
        (ob / f"no_masks_{cam}.txt").write_text("")
    tiny_png(ob / "CAMERA03_013.png", 3)
    for d in ("anim_CAMERA03_099", "overlay_CAMERA03_099"):
        (ob / d).mkdir()
        for i in range(2):
            tiny_png(ob / d / f"frame_{i + 1:03d}.png", 4 if d.startswith("overlay") else 3)
    (ob / "no_masks_cam.txt").write_text("")
    files, warn, _ = CH.scan_assets(ov_pack)
    check("no_masks: markers packed",
          all(f"backgrounds_custom/no_masks_{c}.txt" in files for c in ("CAMERA03_015", "CAMERA03_013", "CAMERA03_099")))
    check("no_masks with an animation and an overlay: no warning", not any("no_masks_CAMERA03_099" in w for w in warn))
    check("no_masks with a still and an overlay: no warning", not any("no_masks_CAMERA03_013" in w for w in warn))
    check("no_masks without an overlay: warned", any("no_masks_CAMERA03_015.txt: no overlay_CAMERA03_015" in w for w in warn))
    check("no_masks with a bad name: skipped", "backgrounds_custom/no_masks_cam.txt" not in files
          and any("no_masks_cam.txt" in w for w in warn))
    (ob / "no_masks_CAMERA03_099.txt").write_text("0, 2\n3")
    _, warn, _ = CH.scan_assets(ov_pack)
    check("no_masks with mask numbers: no warning", not any("no_masks_CAMERA03_099" in w for w in warn))
    (ob / "no_masks_CAMERA03_099.txt").write_text("0 grass")
    _, warn, _ = CH.scan_assets(ov_pack)
    check("no_masks with a word: warned", any("no_masks_CAMERA03_099.txt: expected mask numbers" in w for w in warn))
    (ob / "CAMERA03_013.png").unlink()
    _, warn, _ = CH.scan_assets(ov_pack)
    check("no_masks without a custom background: warned",
          any("no_masks_CAMERA03_013.txt: no custom background" in w for w in warn))
    test_models(work)
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


def test_models(work: Path):
    """models_custom/ (TatouHd custom models): a models-only pack, warnings, install, uninstall."""
    game, pack = work / "mgame", work / "mpack"
    (game / "atlases").mkdir(parents=True)
    (game / "Tatou.exe").write_bytes(b"stand-in for ReHaunted's Tatou.exe")
    (game / "version.txt").write_text("2.4.0.1008\n")
    (game / "atlases/body_LISTBOD2_012.png").write_bytes(b"ReHaunted's own atlas")
    shutil.copytree(GOG, game, dirs_exist_ok=True)             # game files present: nothing copied in
    before = tree(game)
    mc = pack / "models_custom"
    pack.mkdir(parents=True)
    shutil.copy2(ED_EXE, pack / "TatouHd.exe")
    check("models: a pack with neither folder is refused", "no backgrounds_custom or models_custom" in refused(CH.scan_assets, pack))
    mc.mkdir()
    model = HERE.parent / "HDModel/test_models/models_custom/LISTBOD2_012.bin"   # from test_aitd_blender.py --write-dir
    shutil.copy2(model, mc / "LISTBOD2_012.bin")
    tiny_png(mc / "body_LISTBOD2_012.png", 4)
    shutil.copy2(model, mc / "LISTBOD2_011.bin")                # no picture: warned
    tiny_png(mc / "body_LISTBODY_030.png", 4)                   # picture without a model: warned
    (mc / "emily.blend").write_bytes(b"x")                      # not a model: skipped
    files, warn, s = CH.scan_assets(pack)
    check("models: models-only pack accepted, 2 models + 2 pictures packed",
          s["models"] == 2 and set(files) == {"models_custom/LISTBOD2_011.bin", "models_custom/LISTBOD2_012.bin",
                                              "models_custom/body_LISTBODY_030.png", "models_custom/body_LISTBOD2_012.png"})
    check("models: model without a body picture warned", any("LISTBOD2_011.bin has no body_LISTBOD2_011.png" in w for w in warn))
    check("models: picture without a model warned", any("pictures for LISTBODY_030 without" in w for w in warn))
    check("models: other file skipped", any("models_custom/emily.blend" in w for w in warn))
    check("models: the complete model gets no warning", not any("LISTBOD2_012" in w for w in warn))
    m = quiet(game, pack)
    check("models: installed into models_custom/, ReHaunted's atlases untouched",
          (game / "models_custom/LISTBOD2_012.bin").read_bytes() == model.read_bytes()
          and "models_custom/body_LISTBOD2_012.png" in m["files"]
          and (game / "atlases/body_LISTBOD2_012.png").read_bytes() == b"ReHaunted's own atlas")
    check("models: verify (full) clean", CH.verify(game, full=True, log=lambda s: None) == [])
    (mc / "LISTBOD2_011.bin").unlink()
    log = []
    CH.install(game, pack, log=log.append)
    check("models: removed from the pack -> removed from the game", not (game / "models_custom/LISTBOD2_011.bin").exists())
    CH.uninstall(game, log=lambda s: None)
    check("models: uninstall leaves the folder exactly as before", tree(game) == before)


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
