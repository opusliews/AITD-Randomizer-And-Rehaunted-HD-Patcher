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
  S  The installed-seed states (user, 2026-10-28): no seed -> "Randomize and install"; this
     patcher's seed with the same settings -> "Randomize Again" greyed out; another seed or seed
     option -> "Randomize Again"; only controls/hints/aspect -> "Reinstall". Another patcher's
     install: the update check regenerates the seed from the backups and compares the files ->
     same: "Update to this version" (reinstalls the same files, record becomes this patcher's);
     different, or can't check (seed folder gone): only the game directory and "Unpatch Game",
     and a plain _randomize refuses. A missing backup -> unpatch refuses before restoring
     anything; an older app's install unpatches to the identical folder.
  S2 Custom HD locked while a seed is installed: the box shows what is installed, Randomize Again
     leaves the HD files alone (no pack needed); with the pack folder set, a newer TatouHd.exe in the
     pack shows "Update HD", which installs only that file (still the randomizer's install, the
     seed untouched); Unpatch Game removes them and gives the box back.

The ReHaunted Tatou.exe is a placeholder file (no ReHaunted release is in the project):
install.py only needs a Tatou.exe that is not an edition build.

  C:\\Tools\\PythonFull\\python.exe Generated\\App\\test_app_flows.py WORKDIR
"""
import hashlib
import json
import shutil
import sys
import ctypes
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aitd_randomizer_app as A     # noqa: E402
import aitd_text as X               # noqa: E402
from aitd_pak import read_pak       # noqa: E402
import aitd_life as L               # noqa: E402

ORIG = Path(__file__).resolve().parents[2] / "OriginalGame"
I = A.I
ALL = {**A.DEFAULTS, "seed": "4242", "keynames": True, "hints": True, "difficulty": "Normal"}
PLAIN = {**ALL, "seed": "77", "spots_on": False, "doors_on": False, "hints": False, "mirrors": False, "smoke": False,
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
    key_name = "Key to the 3rd Floor Study Chest"
    language_names = {
        lang: X.entries(read_pak(A.SEEDS / "seed_4242" / "patchset" / f"{lang}.PAK").entries[0].data)
        [591].decode("cp437")
        for lang in ("ENGLISH", "USA")
    }
    check(set(language_names.values()) == {key_name},
          f"A 3rd Floor Study chest key renamed in ENGLISH/USA ({language_names})")
    old_res, new_res = read_pak(ORIG / "INDARK" / "ITD_RESS.PAK").entries, read_pak(game / "ITD_RESS.PAK").entries
    pal_old, pal_new = old_res[3].data, new_res[3].data
    changed = sorted({i // 3 for i in range(768) if pal_old[i] != pal_new[i]})
    check(len(old_res) == len(new_res) and all(a.data == b.data for k, (a, b) in enumerate(zip(old_res, new_res)) if k != 3)
          and changed == list(range(0xF1, 0xFA)) and tuple(pal_new[3 * 0xF1:3 * 0xF1 + 3]) == (255, 255, 135),
          f"A Bug Spray yellow ramp: only palette entries 0xF1..0xF9 changed ({[hex(c) for c in changed]})")
    m = json.loads((A.SEEDS / "seed_4242" / "patchset" / "manifest.json").read_text(encoding="utf-8"))
    check(m["options"]["whole_mirrors"] and m["scripts"].get("553", {}).get("whole_mirrors"),
          "A Prevent mirrors from breaking: LIFE 553 patched")
    check(A.DEFAULTS["smoke"] and m["options"]["deadly_smoke"]
          and (m["scripts"].get("427") or {}).get("damage") == 32000,
          "A Deadly Smoke on by default: LIFE 427 kills")
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
    check(not o["deadly_smoke"] and "427" not in json.loads((A.SEEDS / "seed_77" / "patchset" / "manifest.json")
          .read_text(encoding="utf-8"))["scripts"], "A Deadly Smoke unticked: LIFE 427 vanilla")
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
          and o["deadly_smoke"]
          and m["difficulty"]["label"] == "Vanilla" and not m["saber_broken"],
          f"V randomizing options ignored, the others kept ({o}, {m['difficulty']})")
    pl = json.loads((A.SEEDS / "seed_0" / "placement.json").read_text(encoding="utf-8"))
    G = sys.modules["generate"]
    vanilla = {s["id"]: [i for i in s["items"]] for s in G.load_slots()}
    check(all(pl.get(k) == v for k, v in vanilla.items()) and set(pl) == set(vanilla),
          f"V every location holds its original items ({len(vanilla)} locations)")
    fixes = m["scripts"]
    check(fixes.get("460", {}).get("worm_chase_wall_collision") and fixes.get("522", {}).get("endgame_lure_flag")
          and fixes.get("550", {}).get("cellar_tunnel_fixes")
          and all(fixes.get(str(n), {}).get("worm_parked_after_lure") for n in (477, 482))
          and "LISTTRAK.PAK" in m["files"],
          "V the fixes are applied (worm chase, permanent lure, cellar/tunnel, TRACK 40/41)")
    life_entries = read_pak(A.SEEDS / "seed_0" / "patchset" / "LISTLIFE.PAK").entries
    word = lambda life, at: int.from_bytes(life_entries[life].data[at:at + 2], "little")
    room89 = {n: L.format_script(L.decode(life_entries[n].data)) for n in (477, 482)}
    check(word(550, 1694) == word(550, 1810) == 172
          and all("if_egal var_170 #3 @L54    ; @20\nobj_222.life_mode 1    ; @32\n"
                  "if_egal var_172 #0 @L54    ; @38\ndelete 218    ; @50\nL54:" in s
                  for s in room89.values()),
          "V lured worm invariant: neither entry moves it; rooms 8/9 delete it only before the lure "
          "and still set OBJ 222's life_mode as in vanilla")
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

    # S: the installed-seed states of the window (user, 2026-10-28; Research/PatcherApp.md "Planned")
    gs = work / "S_states"
    shutil.copytree(ORIG / "INDARK", gs / "INDARK")
    game = gs / "INDARK"
    before = tree(gs)
    app2.folder.set(str(game))
    app2.seed.set("4242")
    app2.difficulty.set("Any")              # H left Very hard, which seed 4242 has no layout for
    app2.refresh()
    check(app2.go.cget("text") == "Randomize and install" and app2.go.instate(["!disabled"])
          and app2.undo.instate(["disabled"]) and app2.undo.cget("text") == "Unpatch Game",
          "S no seed: \"Randomize and install\" on, \"Unpatch Game\" off")
    r = randomize(game, app2.effective(), False)
    app2.refresh()
    rec = json.loads((game / I.MARKER).read_text(encoding="utf-8"))
    check(r[2] and rec["app"]["patcher"] == A.patcher_id() and rec["app"]["generator_args"][:2] == ["--seed", "4242"],
          f"S install record has this patcher and its generator arguments ({rec['app']['patcher']})")
    check(app2.go.cget("text") == "Randomize Again" and app2.go.instate(["disabled"])
          and "already installed" in app2.go_tip.text and app2.undo.instate(["!disabled"]),
          "S same seed and settings: \"Randomize Again\" greyed out, hover says already installed")
    app2.seed.set("4243")
    check(app2.go.cget("text") == "Randomize Again" and app2.go.instate(["!disabled"]),
          "S another seed: \"Randomize Again\" on")
    app2.seed.set("4242")
    app2.drops.set(not app2.drops.get())
    app2.sync()
    check(app2.go.instate(["!disabled"]) and app2.go.cget("text") == "Randomize Again",
          "S a seed option changed: \"Randomize Again\" on")
    app2.drops.set(not app2.drops.get())
    app2.controls.set(not app2.controls.get())
    app2.controls_clicked()
    check(app2.go.cget("text") == "Reinstall" and app2.go.instate(["!disabled"]),
          "S only the controls changed: \"Reinstall\" on")
    app2.controls.set(not app2.controls.get())
    app2.controls_clicked()
    check(app2.go.instate(["disabled"]), "S controls back: greyed out again")
    A.App.ASYNC_CHECKS = False              # the update check inline (no event loop here)
    A.USER_DIR = work
    installed = {n: f["after"] for n, f in rec["files"].items()}
    original = dict(rec)
    rec["app"]["patcher"] = "0.9 (an older app) | generator v1 | edition none"
    (game / I.MARKER).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    app2.refresh()
    kind = app2.checks[app2.check_key()][0]
    locked = all(w.instate(["disabled"]) for w in app2.seed_widgets + list(app2.random_cbs.values())
                 + [app2.hints_cb, app2.controls_cb, app2.difficulty_cb])
    check(kind == "same" and app2.go.cget("text") == "Update to this version" and app2.go.instate(["!disabled"])
          and locked and app2.undo.instate(["!disabled"]) and app2.play_tip.text != A.INCOMPATIBLE
          and "same seed files" in app2.status.cget("text"),
          "S another patcher's install, same seed files: \"Update to this version\" on, options locked")
    r = randomize(game, app2.effective(), False)
    check(not r[2] and "another version" in r[1], "S a plain randomize is still refused on another patcher's install")
    r = randomize(game, {**app2.checks[app2.check_key()][2], "update": True, "hd_keep": True}, False)
    rec2 = json.loads((game / I.MARKER).read_text(encoding="utf-8"))
    check(r[2] and rec2["app"]["patcher"] == A.patcher_id()
          and all(rec2["files"][n]["after"] == h for n, h in installed.items()),
          "S Update to this version: the same seed files, the record now this patcher's")
    app2.refresh()
    check(app2.inst[0] == "compatible" and app2.go.cget("text") == "Randomize Again",
          "S after the update: a normal install of this patcher")
    rec = dict(original)
    del rec["app"]
    rec["files"] = {**rec["files"], "LISTLIFE.PAK": {**rec["files"]["LISTLIFE.PAK"], "after": "0" * 64}}
    rec["installed"] = "test: different"
    (game / I.MARKER).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    app2.refresh()
    check(app2.checks[app2.check_key()][0] == "different" and app2.go.instate(["disabled"])
          and "LISTLIFE.PAK" in app2.go_tip.text and app2.undo.instate(["!disabled"])
          and app2.play.instate(["disabled"]),
          "S another patcher's install with other seed files: only Unpatch Game")
    rec = {**dict(original), "seed_dir": "no_such_seed", "installed": "test: unknown"}
    del rec["app"]
    (game / I.MARKER).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    app2.refresh()
    check(app2.checks[app2.check_key()][0] == "unknown" and app2.go.instate(["disabled"])
          and "not on this computer" in app2.go_tip.text,
          "S the seed's folder gone (difficulty unknown): can't check, only Unpatch Game")
    (game / I.MARKER).write_text(json.dumps(rec2, indent=1) + "\n", encoding="utf-8")
    bk = game / I.BACKUP / "LISTLIFE.PAK"
    saved = bk.read_bytes()
    bk.unlink()
    check(I.unpatch(game) != 0 and (game / I.MARKER).exists(),
          "S unpatch with a backup missing: refused, the install record kept")
    bk.write_bytes(saved)
    check(I.unpatch(game) == 0 and tree(gs) == before,
          "S unpatch of an older app's install: folder identical to before")
    app2.refresh()
    check(app2.go.cget("text") == "Randomize and install" and app2.seed_widgets[0].instate(["!disabled"]),
          "S after unpatching: everything back")

    # S2: the custom HD option is locked while a seed is installed (ReHaunted 2.4 + the HD pack)
    I.search_game_data = lambda: [("GOG", ORIG / "INDARK")]
    rs2 = work / "S2_rehaunted24"
    rs2.mkdir()
    (rs2 / "Tatou.exe").write_bytes(b"placeholder ReHaunted exe")
    (rs2 / "version.txt").write_text("2.4.0.1008\n")
    before = tree(rs2)
    app2.folder.set(str(rs2))
    app2.custom_hd.set(True)
    app2.hd_assets.set(str(assets))
    app2.refresh()
    r = randomize(rs2, {**app2.effective(), "custom_hd": True, "hd_assets": str(assets)}, True)
    app2.custom_hd.set(False)                # the player's own choice, while installed
    app2.hd_saved = None
    app2.refresh()
    check(r[2] and app2.hd_cb.instate(["disabled"]) and app2.custom_hd.get() and app2.hd_saved is False
          and "unpatch" in app2.hd_status.cget("text"),
          "S2 seed + custom HD installed: the HD box shows it, locked; the player's choice is kept aside")
    hd_before = CH.load_manifest(rs2)
    r = randomize(rs2, {**app2.effective(), "seed": "77", "hd_assets": str(work / "no_such_pack")}, True)
    check(r[2] and CH.load_manifest(rs2) == hd_before and CH.verify(rs2, log=lambda s: None) == []
          and json.loads((rs2 / I.MARKER).read_text(encoding="utf-8"))["app"]["custom_hd"],
          "S2 Randomize Again while locked: the custom HD files are left as they are (no pack needed)")
    app2.seed.set("77")
    app2.hd_assets.set(str(assets))
    app2.hd_pending.clear()
    app2.refresh()
    check(app2.hd_outdated() == "" and "up to date" in app2.hd_status.cget("text")
          and app2.hd_entry.instate(["!disabled"]) and app2.hd_cb.instate(["disabled"]),
          "S2 the pack holds what is installed: nothing to update (the pack folder stays editable)")
    exe = assets / "TatouHd.exe"
    exe_before = exe.read_bytes()
    exe.write_bytes(exe_before + b"\0")          # a newer build of the same flavor
    app2.hd_pending.clear()
    app2.refresh()
    check("TatouHd.exe" in app2.hd_outdated() and app2.go.cget("text") == "Update HD"
          and app2.go.instate(["!disabled"]) and "TatouHd.exe" in app2.hd_status.cget("text"),
          f"S2 a newer TatouHd.exe in the pack: \"Update HD\" on ({app2.hd_outdated()})")
    r = A.App._update_hd(rs2, str(assets))
    m = CH.load_manifest(rs2)
    check(r[2] and I.sha(rs2 / "TatouHd.exe") == I.sha(exe) and m["installed_by"] == "randomizer"
          and CH.verify(rs2, log=lambda s: None) == [] and I.detect(rs2)["installed_seed"] == 77,
          "S2 Update HD: only the new TatouHd.exe installed, still the randomizer's, the seed untouched")
    app2.refresh()
    check(app2.hd_outdated() == "" and app2.go.instate(["disabled"]) and app2.go.cget("text") == "Randomize Again",
          "S2 after Update HD: up to date, nothing to do")
    exe.write_bytes(exe_before)

    # A running TatouHd must refuse before the seed marker, backups or any HD file changes.
    installed_tree = tree(rs2)
    create = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    handle = create(str(rs2 / "TatouHd.exe"), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "could not hold TatouHd.exe open for the lock test")
    locked_refused = False
    try:
        A.App._uninstall(rs2)
    except I.FileInUseError as e:
        locked_refused = Path(e.filename).name.lower() == "tatouhd.exe"
    finally:
        close(handle)
    check(locked_refused and tree(rs2) == installed_tree and (rs2 / I.MARKER).is_file()
          and CH.load_manifest(rs2) is not None,
          "S2 running TatouHd: unpatch refused before any file or marker changed")

    # Recovery from the old failure mode: seed already restored, randomizer HD still present.
    check(I.unpatch(rs2) == 0 and not (rs2 / I.MARKER).exists()
          and CH.load_manifest(rs2) is not None,
          "S2 simulated old partial unpatch: only randomizer custom HD remains")
    app2.refresh()
    check(app2.undo.instate(["!disabled"]) and app2.go.instate(["disabled"])
          and "cleanup is unfinished" in app2.status.cget("text")
          and "cleanup is unfinished" in app2.hd_status.cget("text"),
          "S2 HD-only recovery state: Unpatch enabled, Randomize disabled, clear status")
    r = A.App._uninstall(rs2)
    app2.refresh()
    check(r[2] and tree(rs2) == before and app2.hd_saved is None and not app2.custom_hd.get()
          and app2.hd_cb.instate(["!disabled"]),
          "S2 Unpatch Game: seed and custom HD removed, the box unlocked with the player's choice back")
    I.search_game_data = real_search
    root.destroy()
    A.messagebox.showwarning = real_warning
    print(f"{check.failed} failure(s)")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
