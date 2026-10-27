"""End-to-end checks of the patcher app's install flows on throwaway copies of the game
(OriginalGame is only read). Calls the app's own methods, no clicks:

  A  Classic (GOG folder copy): randomize with every option and hints, the seed's files and the
     INDARK.EXE fixes + search hint are in place; randomize again without hints and with Many
     Search Places / More Locked Doors / Prevent Mirrors From Breaking unticked (replaces the seed, exe without the hint);
     uninstall -> every file identical to the copy before (whole tree compared).
  B  ReHaunted without game files, no Steam/GOG found -> refused before any write.
  C  ReHaunted without game files, data found (the search is pointed at OriginalGame/INDARK):
     data copied in, edition installed; the keyboard + mouse controls flag in the install record
     only when ticked; uninstall -> folder as before.
  D  ReHaunted inside the GOG folder: the edition is always installed (every seed writes
     OBJETS.ITD), and hints are off for ReHaunted even when the setting is on, so INDARK.EXE
     gets the Classic fixes without the hint; then uninstall.
  E  Classic copy whose LISTLIFE.PAK is not the original -> refused before any write.
  V  Seed 0 (the original item layout) with every randomizing option ticked: they are ignored,
     every location keeps its items, the fixes and other options apply; uninstall -> folder as
     before. V2: the window greys the randomizing options out for seed 0, values unchanged.
  H  The window's Very hard rules: More locked doors on at 60 %, Many search places down to 10;
     raising spots or lowering doors shows one warning,
     remembered in the settings, never shown again.

The ReHaunted Tatou.exe is a placeholder file (no ReHaunted release is in the project):
install.py only needs a Tatou.exe that is not an edition build.

  C:\\Tools\\PythonFull\\python.exe Generated\\App\\test_app_flows.py WORKDIR
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_randomizer_app as A     # noqa: E402

ORIG = Path(__file__).resolve().parents[2] / "OriginalGame"
I = A.I
ALL = {**A.DEFAULTS, "seed": "4242", "keynames": True, "hints": True, "difficulty": "Normal"}
PLAIN = {**ALL, "seed": "77", "spots_on": False, "doors_on": False, "hints": False, "mirrors": False,
         "difficulty": "Any"}


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def check(cond, what):
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        check.failed += 1
check.failed = 0


def randomize(folder: Path, opt: dict, rehaunted: bool):
    try:
        return A.App._randomize(A.App.__new__(A.App), folder, {**opt, "folder": str(folder)}, rehaunted)
    except A.Refused as e:
        return ("REFUSED", str(e), False)


def main(work: Path):
    if work.exists():
        shutil.rmtree(work)
    A.SEEDS = work / "Seeds"
    # A: Classic
    gog = work / "A_gog"
    shutil.copytree(ORIG / "INDARK", gog / "INDARK")
    shutil.copytree(ORIG / "DOSBOX", gog / "DOSBOX")
    game = gog / "INDARK"
    before = tree(gog)
    r = randomize(game, ALL, False)
    check(r[2], f"A randomize all options: {r[1][:60]!r}")
    d = json.loads((A.SEEDS / "seed_4242" / "patchset" / "manifest.json").read_text(encoding="utf-8"))["difficulty"]
    check(d["label"] == "Normal" and d["requested"] == "normal" and 60 <= d["score"] <= 89
          and "Difficulty: Normal" in r[1], f"A difficulty Normal requested and shown ({d})")
    rec = I.detect(game)
    check(rec["installed_seed"] == 4242, "A marker says seed 4242")
    check(I.sha(game / "INDARK.EXE") == I.INDARK_CLASSIC_HINT, "A INDARK.EXE has the Classic fixes + search hint")
    seed_files = sorted(p.name for p in (A.SEEDS / "seed_4242" / "patchset").iterdir()
                        if p.suffix.upper() in (".PAK", ".ITD"))      # what install.py copies
    check(all(I.sha(game / n) == I.sha(A.SEEDS / "seed_4242" / "patchset" / n) for n in seed_files),
          f"A all {len(seed_files)} seed files installed ({', '.join(seed_files)})")
    m = json.loads((A.SEEDS / "seed_4242" / "patchset" / "manifest.json").read_text(encoding="utf-8"))
    check(m["options"]["whole_mirrors"] and m["scripts"].get("553", {}).get("whole_mirrors"),
          "A Prevent mirrors from breaking: LIFE 553 patched")
    glows = m["scripts"].get("drop_glow") or {}
    check(m["options"]["drop_glow"] and {"M:82", "M:149"} <= {g["slot"] for g in glows.values()}
          and "LISTBODY.PAK" in seed_files and "LISTBOD2.PAK" in seed_files,
          f"A drop glow on every monster drop ({len(glows)} glows: {sorted(g['slot'] for g in glows.values())})")
    r = randomize(game, {**PLAIN, "controls": True}, False)
    check(r[2] and I.detect(game)["installed_seed"] == 77, "A second randomize replaces the seed")
    check(I.sha(game / "INDARK.EXE") == I.INDARK_CLASSIC_CTRL,
          "A keyboard + mouse controls ticked: INDARK.EXE has the Classic fixes + the controls")
    r = randomize(game, {**PLAIN, "keep_aspect": True}, False)
    check(r[2] and I.sha(game / "INDARK.EXE") == I.INDARK_CLASSIC, "A without hints: INDARK.EXE has the Classic fixes only")
    check("keep_aspect" not in json.loads((game / I.MARKER).read_text(encoding="utf-8")),
          "A maintain aspect ratio is ReHaunted only: no flag for the original game")
    r = randomize(game, {**ALL, "controls": True}, False)
    check(r[2] and I.sha(game / "INDARK.EXE") == I.INDARK_CLASSIC_HINT_CTRL,
          "A hints + controls: INDARK.EXE has the Classic fixes, the search hint and the controls")
    r = randomize(game, PLAIN, False)
    o = json.loads((A.SEEDS / "seed_77" / "patchset" / "manifest.json").read_text(encoding="utf-8"))["options"]
    check(not o["whole_mirrors"] and "553" not in json.loads((A.SEEDS / "seed_77" / "patchset" / "manifest.json")
          .read_text(encoding="utf-8"))["scripts"], "A mirrors box unticked: LIFE 553 vanilla")
    check(not o["extra_spots"] and not o["locked_doors"] and o["visible_items"] and o["saber_pieces"],
          f"A unticked boxes: no extra spots or locked doors; visible items and saber pieces always on ({o})")
    check(I.unpatch(game) == 0 and tree(gog) == before, "A uninstall: whole folder identical to before")

    # B: ReHaunted, no data, nothing found
    rh = work / "B_rehaunted"
    rh.mkdir()
    (rh / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    before = tree(rh)
    real_search = I.search_game_data
    I.search_game_data = lambda: []
    r = randomize(rh, PLAIN, True)
    check(not r[2] and "Choose your game data directory" in r[1], "B refused: no game data, asks for the directory")
    check(tree(rh) == before, "B folder untouched")

    # B2: the same, with a game data directory chosen in the window
    r = randomize(rh, {**ALL, "data_override": str(ORIG / "INDARK")}, True)
    check(r[2] and I.sha(rh / "Tatou.exe") in I.EDITION and (rh / "ITD_RESS.PAK").exists(),
          "B2 chosen game data directory: data copied in, edition installed")
    r = randomize(rh, {**PLAIN, "edition": True, "data_override": str(ORIG / "INDARK")}, True)
    check(r[2] and I.detect(rh)["installed_seed"] == 77,
          "B2 second seed (the copied data is removed by the uninstall first, then copied again)")
    check(I.unpatch(rh) == 0 and tree(rh) == before, "B2 uninstall: folder identical to before")

    # F: a chosen game data directory with modified files
    mod = work / "F_modded_data"
    shutil.copytree(ORIG / "INDARK", mod)
    (mod / "OBJETS.ITD").write_bytes((mod / "OBJETS.ITD").read_bytes()[:-2] + b"\0\0")
    r = randomize(rh, {**PLAIN, "data_override": str(mod)}, True)
    check(not r[2] and "OBJETS.ITD" in r[1] and tree(rh) == before, "F refused: modded game data directory")
    ok, msg = A.check_data(mod)
    check(not ok and "OBJETS.ITD" in msg, f"F window check: {msg[:70]!r}")
    check(A.check_data(ORIG / "INDARK")[0] and not A.check_data(work)[0], "window check: original OK, no-data folder refused")

    # C: ReHaunted, data found elsewhere, edition
    I.search_game_data = lambda: [("GOG", ORIG / "INDARK")]
    rc = work / "C_rehaunted"
    rc.mkdir()
    (rc / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    before = tree(rc)
    r = randomize(rc, ALL, True)
    check(r[2], f"C randomize with edition: {r[1][:60]!r}")
    check(I.sha(rc / "Tatou.exe") in I.EDITION, "C Tatou.exe is the edition")
    check((rc / "ITD_RESS.PAK").exists() and (rc / "aitd_remaster.cfg").exists(), "C data copied, config written")
    check("modern_controls" not in json.loads((rc / I.MARKER).read_text(encoding="utf-8")),
          "C keyboard + mouse controls off (default): no flag in the install record")
    check("keep_aspect" not in json.loads((rc / I.MARKER).read_text(encoding="utf-8")),
          "C maintain aspect ratio off (default): no flag in the install record")
    r = randomize(rc, {**ALL, "controls": True}, True)
    check(r[2] and json.loads((rc / I.MARKER).read_text(encoding="utf-8")).get("modern_controls") is True,
          "C keyboard + mouse controls on: \"modern_controls\": true in the install record")
    r = randomize(rc, {**ALL, "keep_aspect": True}, True)
    check(r[2] and json.loads((rc / I.MARKER).read_text(encoding="utf-8")).get("keep_aspect") is True,
          "C maintain aspect ratio on: \"keep_aspect\": true in the install record")
    check(I.unpatch(rc) == 0 and tree(rc) == before, "C uninstall: folder identical to before")

    # G: ReHaunted 2.4 with "Include custom HD backgrounds" (custom_hd.py; Research/HDRepaint.md)
    CH = A.CH
    assets = work / "G_assets"
    (assets / "backgrounds_custom" / "anim_CAMERA00_000").mkdir(parents=True)
    refs = ORIG.parent / "Generated" / "HDRepaint" / "test_images"
    for i in range(2):
        shutil.copy2(refs / f"CAMERA00_00{i}.png", assets / "backgrounds_custom")
    for i in range(3):
        shutil.copy2(refs / f"CAMERA00_00{i}.png",
                     assets / "backgrounds_custom" / "anim_CAMERA00_000" / f"ezgif-frame-{i + 1:03d}.png")
    hd_build = ORIG.parent / "ReHaunted24" / "TatouSource" / "build"
    shutil.copy2(hd_build / "hd-repaint" / "Fitd" / "TatouHd.exe", assets / "TatouHd.exe")
    hd = {"custom_hd": True, "hd_assets": str(assets)}
    rs = work / "G0_rehaunted24"
    rs.mkdir()
    (rs / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    (rs / "version.txt").write_text("2.4.0.1008\n")
    before = tree(rs)
    r = randomize(rs, {**PLAIN, **hd}, True)
    check(not r[2] and "not the randomizer edition build" in r[1] and tree(rs) == before,
          "G0 HD pack with the test TatouHd (not the edition): refused before any write")
    shutil.copy2(hd_build / "hd-edition" / "Fitd" / "TatouHd.exe", assets / "TatouHd.exe")
    rg = work / "G_rehaunted24"
    rg.mkdir()
    (rg / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    (rg / "version.txt").write_text("2.4.0.1008\n")
    before = tree(rg)
    r = randomize(rg, {**ALL, **hd}, True)
    m = CH.load_manifest(rg)
    check(r[2] and "TatouHd.exe" in r[1] and m and m["installed_by"] == "randomizer"
          and m["exe"]["flavor"] == "edition" and len(m["files"]) == 6,
          f"G seed + custom HD: TatouHd edition + 2 stills + 3 frames ({r[1][:50]!r})")
    check(CH.verify(rg, full=True, log=lambda s: None) == [] and I.sha(rg / "Tatou.exe") in I.EDITION,
          "G custom HD verified; Tatou.exe is the edition")
    r = randomize(rg, {**PLAIN, **hd}, True)
    check(r[2] and I.detect(rg)["installed_seed"] == 77 and CH.verify(rg, log=lambda s: None) == [],
          "G second seed: custom HD kept and still verified")
    r = randomize(rg, {**PLAIN, "custom_hd": False}, True)
    check(r[2] and CH.load_manifest(rg) is None and not (rg / "TatouHd.exe").exists()
          and not (rg / "backgrounds_custom").exists(), "G option unticked: custom HD removed")
    r = randomize(rg, {**PLAIN, **hd}, True)
    check(r[2] and CH.load_manifest(rg) is not None, "G option ticked again: custom HD installed")
    r = A.App._uninstall(rg)
    check(r[2] and tree(rg) == before, "G Uninstall seed (app): seed and custom HD removed, folder identical to before")
    rh2 = work / "G2_not24"
    rh2.mkdir()
    (rh2 / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    before = tree(rh2)
    r = randomize(rh2, {**PLAIN, **hd}, True)
    check(not r[2] and "not ReHaunted 2.4" in r[1] and tree(rh2) == before,
          "G2 custom HD on a folder that is not ReHaunted 2.4: refused before any write")
    I.search_game_data = real_search

    # D: ReHaunted deployed into the GOG folder, no edition
    gd = work / "D_gog_rehaunted"
    shutil.copytree(ORIG / "INDARK", gd / "INDARK")
    (gd / "INDARK" / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    before = tree(gd)
    r = randomize(gd / "INDARK", ALL, True)
    check(r[2] and I.sha(gd / "INDARK" / "Tatou.exe") in I.EDITION, "D installed with the edition")
    check(I.sha(gd / "INDARK" / "INDARK.EXE") == I.INDARK_CLASSIC, "D ReHaunted folder: no search hint in INDARK.EXE")
    check(I.unpatch(gd / "INDARK") == 0 and tree(gd) == before, "D uninstall: folder identical to before")

    # E: modified game files
    ge = work / "E_modded"
    shutil.copytree(ORIG / "INDARK", ge)
    (ge / "LISTLIFE.PAK").write_bytes((ge / "LISTLIFE.PAK").read_bytes() + b"x")
    before = tree(ge)
    r = randomize(ge, PLAIN, False)
    check(not r[2] and "not the original" in r[1] and "LISTLIFE.PAK" in r[1], "E refused: modified LISTLIFE.PAK")
    check(tree(ge) == before, "E folder untouched")

    # V: seed 0 = the original item layout (every randomizing option on in the window: ignored)
    gv = work / "V_vanilla"
    shutil.copytree(ORIG / "INDARK", gv / "INDARK")
    shutil.copytree(ORIG / "DOSBOX", gv / "DOSBOX")
    game = gv / "INDARK"
    before = tree(gv)
    r = randomize(game, {**ALL, "seed": "0", "difficulty": "Hard"}, False)
    check(r[2] and "original item layout" in r[1] and I.detect(game)["installed_seed"] == 0,
          f"V seed 0 installed: {r[1][:70]!r}")
    m = json.loads((A.SEEDS / "seed_0" / "patchset" / "manifest.json").read_text(encoding="utf-8"))
    o = m["options"]
    check(o["vanilla_layout"] and not o["enemy_drops"] and not o["extra_spots"] and not o["locked_doors"]
          and not o["visible_items"] and not o["saber_pieces"] and o["key_names"] and o["whole_mirrors"]
          and m["difficulty"]["label"] == "Vanilla" and not m["saber_broken"],
          f"V randomizing options ignored, the others kept ({o}, {m['difficulty']})")
    pl = json.loads((A.SEEDS / "seed_0" / "placement.json").read_text(encoding="utf-8"))
    G = sys.modules["generate"]
    vanilla = {s["id"]: [i for i in s["items"]] for s in G.load_slots()}
    check(all(pl.get(k) == v for k, v in vanilla.items()) and set(pl) == set(vanilla),
          f"V every location holds its original items ({len(vanilla)} locations)")
    fixes = m["scripts"]
    check(fixes.get("460", {}).get("worm_chase_wall_collision") and fixes.get("522", {}).get("endgame_lure_flag")
          and fixes.get("550", {}).get("cellar_tunnel_fixes") and "LISTTRAK.PAK" in m["files"],
          "V the fixes are applied (worm chase, cellar/tunnel LIFE 550/522, TRACK 40/41)")
    check(I.sha(game / "INDARK.EXE") == I.INDARK_CLASSIC_HINT, "V INDARK.EXE has the Classic fixes + search hint")
    check(I.unpatch(game) == 0 and tree(gv) == before, "V uninstall: whole folder identical to before")

    # H: the window's Very hard rules (settings redirected to the work folder)
    A.SETTINGS = work / "settings.json"
    warnings = []
    real_warning = A.messagebox.showwarning
    A.messagebox.showwarning = lambda *a, **k: warnings.append(a)
    root = A.tk.Tk()
    root.withdraw()
    app = A.App(root)
    app.doors.set(25)
    app.spots_on.set(True)
    app.spots.set(30)
    app.difficulty.set("Very hard")
    app.difficulty_changed()
    check(app.doors_on.get() and app.doors.get() == 60 and app.spots.get() == 10 and not warnings,
          "H Very hard: More locked doors on at 60 %, Many search places down to 10")
    app.spots_on.set(False)
    app.spots.set(40)
    app.very_hard_settings_changed()
    check(not warnings, "H Many search places unticked (even at 40): no warning")
    app.spots_on.set(True)
    app.very_hard_settings_changed()
    app.doors.set(40)
    app.very_hard_settings_changed()
    check(len(warnings) == 1 and json.loads(A.SETTINGS.read_text(encoding="utf-8"))["vh_doors_warned"],
          f"H raising spots / lowering doors under Very hard: one warning, remembered ({len(warnings)} shown)")
    app2 = A.App(A.tk.Toplevel(root))                       # a new window reads the saved settings
    app2.difficulty.set("Very hard")
    app2.doors_on.set(False)
    app2.very_hard_settings_changed()
    check(len(warnings) == 1, "H the warning is not shown again in a new session")
    # V2: the window greys the randomizing options out for seed 0, without changing them
    values = (app2.drops.get(), app2.spots_on.get(), app2.doors_on.get(), app2.difficulty.get())
    app2.seed.set("0")
    grey = all(c.instate(["disabled"]) for c in app2.random_cbs.values()) and \
        app2.difficulty_cb.instate(["disabled"]) and app2.drop_sb.instate(["disabled"]) and \
        all(sb.instate(["disabled"]) for sb in app2.number_sb.values())
    same = values == (app2.drops.get(), app2.spots_on.get(), app2.doors_on.get(), app2.difficulty.get())
    check(grey and same, "V2 seed 0: randomizing options greyed out, their values unchanged")
    app2.seed.set("123")
    check(all(c.instate(["!disabled"]) for c in app2.random_cbs.values())
          and app2.difficulty_cb.instate(["!disabled"]), "V2 another seed: the options are back")
    root.destroy()
    A.messagebox.showwarning = real_warning
    print(f"{check.failed} failure(s)")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
