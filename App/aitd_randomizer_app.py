"""AITD Randomizer: the player's patcher app (Tkinter). One app for both ways of playing:
the original DOS game (GOG/Steam DOSBox, "Classic") and ReHaunted, whose AITD Randomizer
edition Tatou.exe is bundled. Frozen into one exe by build_app.ps1 (PyInstaller).

It wraps the project tools without changing what they do:
  Generator/generate.py  main(argv)     the seed, from the player's own game files
  Generator/install.py   apply/unpatch  backup, install, verified restore
The app ships no game data: generate.py reads the files the player's game folder (or the
Steam/GOG install install.py finds) holds, after they matched the known GOG hashes
(install.check_game_data), through AITD_RANDO_DATA (Patcher/gamedata.py).

Run from source: C:\\Tools\\PythonFull\\python.exe Generated\\App\\aitd_randomizer_app.py
"""
from __future__ import annotations

# Standard modules the bundled tools use. The tools are bundled as plain .py files (their
# paths stay relative to each other), so PyInstaller only sees these through this list.
import argparse, bisect, collections, contextlib, copy, csv, ctypes, dataclasses, functools  # noqa: F401,E401
import glob, hashlib, heapq, io, itertools, json, math, os, queue, random, re, shutil  # noqa: F401,E401
import string, struct, sys, threading, time, traceback, typing, winreg  # noqa: F401,E401
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "AITD Randomizer"
APP_VERSION = "0.1 (2026-10-17)"
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    sys.dont_write_bytecode = True    # the bundled tools are .py files in a temporary folder
BASE =Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parents[2]
GEN = BASE / "Generated"
for _d in ("Generator", "Patcher", "Logic", "VisibleItems", "HDRepaint"):
    sys.path.insert(0, str(GEN / _d))
EDITION_EXE = (BASE / "edition" / "Tatou.exe" if FROZEN else
               BASE / "ReHaunted24" / "TatouSource" / "build" / "randomizer-edition" / "Fitd" / "Tatou.exe")
USER_DIR = Path.home() / "Documents" / APP_NAME
SEEDS = USER_DIR / "Seeds"
SETTINGS = USER_DIR / "settings.json"
SEED_MAX = 999_999_999
VANILLA_SEED = 0            # the original item layout with the fixes (generate.py VANILLA_SEED)

import install as I   # noqa: E402  (light: no game data read at import)
import custom_hd as CH  # noqa: E402  (the same install logic as the standalone custom textures patcher)

HELP = {
    "seed": "The seed number decides where everything goes. The same number with the same options "
            "always gives the same game, so you can share it with a friend.\n"
            "Seed 0: the original game's item layout, with nothing randomized. You still get every "
            "fix and the other options (key names, unbreakable mirrors, hints, controls...); the "
            "randomizing options are greyed out and ignored.",
    "drops": "Some enemies may carry items and drop them when they die. "
             "Each eligible enemy rolls this chance independently. Items dropped by monsters "
             "stand in a pale light beam until you take them.",
    "spots": "Search locations in the mansion that normally contain no items can hide items with "
             "this option on. In the Rehaunted version they will show a magnifying glass icon when "
             "nearby, indicating they can be searched. In other versions you'll see a \"?\" icon if "
             "hints are on. This many are picked at random (0 = None, Maximum 40).",
    "doors": "Each mansion room has this chance to have its doors locked with a new key, "
             "which is hidden somewhere. A room with several doors has them all locked by the same key "
             "(e.g. both Dining Room entrances). 0 = No new doors locked. The keys are named after their room. "
             "Doors that were locked in Vanilla are unaffected by this setting and remain locked.",
    "hints": "Shows a \"?\" with a black border at the bottom right of the screen while you are "
             "near a place that can be searched (empty places too: it never tells where an item "
             "is). For the original game (DOS). ReHaunted has its own magnifying glass icon.",
    "keep_aspect": "ReHaunted only: when the window is resized, maximized or fullscreen, the "
                   "picture keeps its shape (16:10) with black bars around it instead of being "
                   "stretched.",
    "controls": "Adds keyboard and mouse controls (the arrows, Space and Enter work as before):\n"
                "  W A S D: move   Shift: run\n"
                "  E (hold): Open/Search   C: Close (near an open door, walks up to it first)\n"
                "  R (hold): Push   J: Jump\n"
                "  T: Throw the held item   G: Drop the held item\n"
                "  Left click: right punch   Ctrl + left click: left punch   Right click: kick\n"
                "  With a knife, dagger, sword or saber: left / right click and Ctrl + click are its "
                "four attacks\n"
                "  Gun or bow: hold the right button to aim or draw, left click to fire once aimed\n"
                "  Q: turn around (one exact half-turn per press; walking, he walks on after the turn)\n"
                "An action is chosen as in the Actions menu, and only when the game allows it there. "
                "The mouse cursor is hidden while playing; a left click turns book pages and closes "
                "pictures. ReHaunted's quick turn right key is not used. Original game (DOSBox): click "
                "once in the window to capture the mouse (Ctrl+F10 releases it); S no longer toggles "
                "the sound effects (the menu still does); door walking is ReHaunted only. Off: nothing "
                "changes.",
    "mirrors": "Being hit no longer breaks a mirror you carry. In the original game a hit breaks "
               "one, and a broken mirror can't defeat the medusas, so the game can't be finished.",
    "difficulty": "Picks a layout of this difficulty for the seed. The difficulty is the length of the "
                  "shortest route through the seed's puzzle chain, against the original game's layout "
                  "(= 100): Easy under 60, Normal 60-89, Hard 90-119, Very hard 120 and up. More locked "
                  "doors make seeds harder; more search places and enemy drops make them easier. Very "
                  "hard sets More locked doors to at least 60 % and Many search places to at most 10. Any: no filter, fastest. A chosen "
                  "difficulty can take up to a minute or two; if no layout fits, try another seed.",
    "keynames": "Keys show their real name from the start (in the original game every key is "
                "\"A Key\" until you use it).",
    "edition": "Installs the AITD Randomizer edition of ReHaunted over your ReHaunted Tatou.exe "
               "(your original is backed up and restored by Uninstall). It reads the seed from disk, "
               "has engine fixes the randomizer relies on, and press F7 makes a bug report capture. "
               "Every seed needs it: the shuffled visible items change OBJETS.ITD, which stock "
               "ReHaunted reads from its exe.",
    "custom_hd": "Also installs the custom HD backgrounds (repainted stills and animations that match "
                 "the original rooms exactly, with the original masks) from the custom HD pack, a "
                 "separate download: choose its folder below (it holds TatouHd.exe and the "
                 "backgrounds_custom folder). Start TatouHd.exe instead of Tatou.exe to play with them; "
                 "HD backgrounds must be on in ReHaunted's options. ReHaunted 2.4 only. Only "
                 "TatouHd.exe and backgrounds_custom are added; Uninstall seed removes them again.",
    "folder": "The folder you play from: the one holding INDARK.EXE (the original game, e.g. "
              "C:\\GOG Games\\Alone in the Dark\\INDARK) or ReHaunted's Tatou.exe. The seed is "
              "installed here.",
    "data": "ReHaunted normally plays on data built into its exe, which the randomizer can't change. "
            "The randomizer edition plays from the original game files instead: they are copied "
            "into the game directory from your own copy of the game (GOG, Steam or CD), which is "
            "only read, never changed. It is found automatically when it can be; tick this to "
            "choose another copy.",
}
# Shuffle Visible Items and Saber Pieces are always on (user decision 2026-10-17), and so is the
# drop glow on every monster drop (user, 2026-10-18)
DEFAULTS = {"seed": "", "drops": True, "drop_chance": 25, "spots_on": True, "spots": 10,
            "doors_on": True, "doors": 25, "keynames": False, "mirrors": True, "hints": True, "controls": False, "keep_aspect": False, "edition": True,
            "difficulty": "Any", "vh_doors_warned": False,
            "folder": "", "sep_data": False, "data_dir": "", "custom_hd": False, "hd_assets": ""}
DIFFICULTIES = {"Any": None, "Easy": "easy", "Normal": "normal", "Hard": "hard", "Very hard": "very-hard"}
VERY_HARD_DOORS = 60     # Very hard turns More locked doors on at this chance or more (user, 2026-10-18)
VERY_HARD_SPOTS = 10     # ... and lowers Many search places to this many if it is on and higher
RED, GREEN = "#b00020", "#1b6e20"
NO_DATA = ("Your original game files were not found. Choose your game data directory: the folder of "
           "your GOG, Steam or CD copy of Alone in the Dark that holds ITD_RESS.PAK (usually called "
           "INDARK).")
SAVES = ("Saves belong to their seed: start a New Game. Loading a save made with another seed, or "
         "with the unpatched game, will break the game.")


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(SETTINGS.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(s: dict) -> None:
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(s, indent=1), encoding="utf-8")
    except OSError:
        pass


class Tip:
    """Hover help."""
    def __init__(self, widget, text: str):
        self.widget, self.text, self.win, self.job = widget, text, None, None
        widget.bind("<Enter>", self._later, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _later(self, _e=None):
        self.job = self.widget.after(450, self._show)

    def _show(self):
        if self.win:
            return
        x, y = self.widget.winfo_rootx() + 16, self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.win = tk.Toplevel(self.widget)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry(f"+{x}+{y}")
        tk.Label(self.win, text=self.text, justify="left", wraplength=380, background="#ffffe0",
                 relief="solid", borderwidth=1, padx=6, pady=4).pack()

    def _hide(self, _e=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.win:
            self.win.destroy()
            self.win = None


class LogWriter(io.TextIOBase):
    """print() from the worker thread -> the log box (through a queue)."""
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        self.q.put(("log", s))
        return len(s)


class Refused(Exception):
    pass


class NeedData(Refused):
    """No original game files: the window then asks for the game data directory."""


_GOOD_DATA: set[str] = set()       # folders already found to hold the original files


def check_data(path: Path) -> tuple[bool, str]:
    """Is this a folder with the original GOG/Steam game files? (ok, plain message)"""
    if not path.is_dir():
        return False, "This folder does not exist."
    if str(path.resolve()) in _GOOD_DATA:
        return True, "OK: the original game files."
    if not I.find(path, I.SENTINEL):
        return False, ("No game files here: choose the folder that holds ITD_RESS.PAK (usually called "
                       "INDARK).")
    missing, different = I.check_game_data(path)
    if missing or different:
        return False, ("These are not the original GOG/Steam game files (modded?)"
                       + (f"; missing: {', '.join(missing)}" if missing else "")
                       + (f"; different: {', '.join(different)}" if different else "") + ".")
    _GOOD_DATA.add(str(path.resolve()))
    return True, "OK: the original game files."


def writable(folder: Path) -> None:
    """install.apply writes its marker last, so a write refused half-way would leave changes no
    Uninstall knows about: check before anything is written (e.g. a game under Program Files)."""
    probe = folder / f"~{APP_NAME.replace(' ', '')}_write_test.tmp"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        raise Refused(f"Windows does not allow changing files in {folder}. If the game is under "
                      "Program Files, run this app as administrator.") from None


def describe(folder: Path) -> tuple[str, dict | None]:
    """A short, plain account of what is in the folder."""
    if not folder.is_dir():
        return "Choose the game folder (the one holding INDARK.EXE or ReHaunted's Tatou.exe).", None
    try:
        info = I.detect(folder)
    except OSError as e:
        return f"Can't read this folder: {e}", None
    names = {p["file"].upper(): p["identified_as"] for p in info["programs"]}
    lines = []
    if "INDARK.EXE" in names:
        lines.append("Original DOS game (Classic): found")
    if "TATOU.EXE" in names:
        t = names["TATOU.EXE"]
        lines.append("ReHaunted: " + ("AITD Randomizer edition installed" if t.startswith("AITD Randomizer")
                                       else "found" + ("" if "ReHaunted" in t else " (unknown build)")))
    if not lines:
        lines.append("No Alone in the Dark program found here (INDARK.EXE or Tatou.exe).")
    if info["installed_seed"] is not None:
        lines.append(f"Installed: seed {info['installed_seed']}")
    else:
        lines.append("Installed: no seed (the game is unchanged)")
    return "\n".join(lines), info


class App:
    def __init__(self, root: tk.Tk):
        self.root, self.q, self.busy = root, queue.Queue(), False
        self.s = load_settings()
        root.title(f"{APP_NAME} {APP_VERSION}")
        root.minsize(640, 560)
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        # game directory (where you play) and game data directory (the original files)
        g = ttk.LabelFrame(main, text="Game directory (where you play)", padding=8)
        g.pack(fill="x")
        self.folder = tk.StringVar(value=self.s["folder"])
        e = ttk.Entry(g, textvariable=self.folder)
        e.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        e.bind("<FocusOut>", lambda _e: self.refresh())
        e.bind("<Return>", lambda _e: self.refresh())
        Tip(e, HELP["folder"])
        ttk.Button(g, text="Browse...", command=self.browse).grid(row=0, column=1)
        b = ttk.Button(g, text="Find", command=self.find)
        b.grid(row=0, column=2, padx=(6, 0))
        Tip(b, "Looks for your Steam or GOG installation of Alone in the Dark.")
        g.columnconfigure(0, weight=1)
        self.status = ttk.Label(g, text="", justify="left")
        self.status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.edition = tk.BooleanVar(value=self.s["edition"])
        self.edition_cb = ttk.Checkbutton(g, text="Install the AITD Randomizer edition of ReHaunted "
                                          "(recommended)", variable=self.edition, command=self.sync)
        self.edition_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        Tip(self.edition_cb, HELP["edition"])
        self.sep = tk.BooleanVar(value=self.s["sep_data"])
        self.data_dir = tk.StringVar(value=self.s["data_dir"])   # the player's choice
        self.found_dir = tk.StringVar()                           # shown while the box is unticked
        self.sep_cb = ttk.Checkbutton(g, text="Use separate game data directory", variable=self.sep,
                                      command=self.refresh_data)
        self.sep_cb.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        Tip(self.sep_cb, HELP["data"])
        self.data_entry = ttk.Entry(g, textvariable=self.data_dir)
        self.data_entry.grid(row=4, column=0, sticky="ew", padx=(0, 6), pady=(2, 0))
        self.data_entry.bind("<FocusOut>", lambda _e: self.refresh_data())
        self.data_entry.bind("<Return>", lambda _e: self.refresh_data())
        Tip(self.data_entry, HELP["data"])
        self.data_browse = ttk.Button(g, text="Browse...", command=self.browse_data)
        self.data_browse.grid(row=4, column=1, pady=(2, 0))
        self.data_status = tk.Label(g, text="", justify="left", anchor="w", wraplength=580)
        self.data_status.grid(row=5, column=0, columnspan=3, sticky="w")
        self.custom_hd = tk.BooleanVar(value=self.s["custom_hd"])
        self.hd_assets = tk.StringVar(value=self.s["hd_assets"])
        self.hd_cb = ttk.Checkbutton(g, text="Include custom HD backgrounds (TatouHd)", variable=self.custom_hd,
                                     command=self.sync)
        self.hd_cb.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        Tip(self.hd_cb, HELP["custom_hd"])
        self.hd_entry = ttk.Entry(g, textvariable=self.hd_assets)
        self.hd_entry.grid(row=7, column=0, sticky="ew", padx=(0, 6), pady=(2, 0))
        self.hd_entry.bind("<FocusOut>", lambda _e: self.sync())
        Tip(self.hd_entry, HELP["custom_hd"])
        self.hd_browse = ttk.Button(g, text="Browse...", command=self.browse_hd)
        self.hd_browse.grid(row=7, column=1, pady=(2, 0))
        self.hd_status = tk.Label(g, text="", justify="left", anchor="w", wraplength=580)
        self.hd_status.grid(row=8, column=0, columnspan=3, sticky="w")
        self.hd_problem, self.hd_ok = None, False   # why custom HD can't go into this folder (None: it can)
        self.found = []                 # the Steam/GOG/CD search, per refresh
        self.data_ok, self.data_path = False, None

        # seed and options
        o = ttk.LabelFrame(main, text="Seed and options", padding=8)
        o.pack(fill="x", pady=(8, 0))
        ttk.Label(o, text="Seed").grid(row=0, column=0, sticky="w")
        self.seed = tk.StringVar(value=self.s["seed"] or str(random.randint(1, SEED_MAX)))
        se = ttk.Entry(o, textvariable=self.seed, width=14)
        se.grid(row=0, column=1, sticky="w", **pad)
        Tip(se, HELP["seed"])
        ttk.Button(o, text="Random", command=lambda: self.seed.set(str(random.randint(1, SEED_MAX)))
                   ).grid(row=0, column=2, sticky="w")

        self.drops = tk.BooleanVar(value=self.s["drops"])
        self.drop_chance = tk.IntVar(value=self.s["drop_chance"])
        self.spots_on = tk.BooleanVar(value=self.s["spots_on"])
        self.spots = tk.IntVar(value=self.s["spots"])
        self.doors_on = tk.BooleanVar(value=self.s["doors_on"])
        self.doors = tk.IntVar(value=self.s["doors"])
        self.keynames = tk.BooleanVar(value=self.s["keynames"])
        self.mirrors = tk.BooleanVar(value=self.s["mirrors"])
        self.hints = tk.BooleanVar(value=self.s["hints"])
        self.hints_pref = self.s["hints"]         # the player's choice, kept while ReHaunted greys it out
        self.controls = tk.BooleanVar(value=self.s["controls"])
        self.controls_pref = self.s["controls"]   # the player's choice, kept while the original game greys it out
        self.keep_aspect = tk.BooleanVar(value=self.s["keep_aspect"])
        self.keep_aspect_pref = self.s["keep_aspect"]   # kept while the original game greys it out

        c = ttk.Checkbutton(o, text="Enemy drops, chance per monster (%)", variable=self.drops, command=self.sync)
        c.grid(row=1, column=0, columnspan=2, sticky="w")
        Tip(c, HELP["drops"])
        self.random_cbs = {"drops": c}     # the randomizing options, greyed out for seed 0
        self.drop_sb = ttk.Spinbox(o, from_=1, to=100, width=5, textvariable=self.drop_chance)
        self.drop_sb.grid(row=1, column=2, sticky="w", **pad)
        Tip(self.drop_sb, HELP["drops"])
        self.number_sb = {}
        for row, (label, on, var, lo, hi, key) in enumerate(
                [("Many search places: extra hiding spots", self.spots_on, self.spots, 0, 40, "spots"),
                 ("More locked doors: chance per room (%)", self.doors_on, self.doors, 0, 100, "doors")],
                start=2):
            c = ttk.Checkbutton(o, text=label, variable=on, command=self.very_hard_settings_changed)
            c.grid(row=row, column=0, columnspan=2, sticky="w")
            sb = ttk.Spinbox(o, from_=lo, to=hi, width=5, textvariable=var, command=self.very_hard_settings_changed)
            sb.grid(row=row, column=2, sticky="w", **pad)
            sb.bind("<KeyRelease>", lambda _e: self.sync())
            # typed numbers: checked when done, not per keystroke
            sb.bind("<FocusOut>", lambda _e: self.very_hard_settings_changed())
            Tip(c, HELP[key])
            Tip(sb, HELP[key])
            self.number_sb[key] = sb
            self.random_cbs[key] = c
        c = ttk.Checkbutton(o, text="Show key names", variable=self.keynames, command=self.sync)
        c.grid(row=4, column=0, columnspan=3, sticky="w")
        Tip(c, HELP["keynames"])
        c = ttk.Checkbutton(o, text="Prevent mirrors from breaking", variable=self.mirrors, command=self.sync)
        c.grid(row=5, column=0, columnspan=3, sticky="w")
        Tip(c, HELP["mirrors"])
        self.hints_cb = ttk.Checkbutton(o, text="Hints On", variable=self.hints, command=self.hints_clicked)
        self.hints_cb.grid(row=6, column=0, columnspan=3, sticky="w")
        Tip(self.hints_cb, HELP["hints"])
        self.controls_cb = ttk.Checkbutton(o, text="Keyboard and mouse controls", variable=self.controls,
                                           command=self.controls_clicked)
        self.controls_cb.grid(row=7, column=0, columnspan=3, sticky="w")
        Tip(self.controls_cb, HELP["controls"])
        self.keep_aspect_cb = ttk.Checkbutton(o, text="Maintain aspect ratio", variable=self.keep_aspect,
                                              command=self.keep_aspect_clicked)
        self.keep_aspect_cb.grid(row=8, column=0, columnspan=3, sticky="w")
        Tip(self.keep_aspect_cb, HELP["keep_aspect"])
        ttk.Label(o, text="Difficulty").grid(row=9, column=0, sticky="w", pady=(4, 0))
        self.difficulty = tk.StringVar(value=self.s["difficulty"] if self.s["difficulty"] in DIFFICULTIES else "Any")
        self.vh_warned = bool(self.s["vh_doors_warned"])
        dc = ttk.Combobox(o, textvariable=self.difficulty, values=list(DIFFICULTIES), state="readonly", width=12)
        dc.grid(row=9, column=1, sticky="w", **pad)
        dc.bind("<<ComboboxSelected>>", lambda _e: self.difficulty_changed())
        Tip(dc, HELP["difficulty"])
        self.difficulty_cb = dc
        self.seed.trace_add("write", lambda *_: self.sync())

        # actions
        a = ttk.Frame(main)
        a.pack(fill="x", pady=(10, 0))
        self.go = ttk.Button(a, text="Randomize and install", command=self.randomize)
        self.go.pack(side="left")
        self.undo = ttk.Button(a, text="Uninstall seed", command=self.uninstall)
        self.undo.pack(side="left", padx=6)
        Tip(self.undo, "Restores every file the randomizer changed, and checks each one.")
        ttk.Button(a, text="About", command=self.about).pack(side="right")
        ttk.Button(a, text="Seed folder", command=self.open_seeds).pack(side="right", padx=6)
        sp = ttk.Button(a, text="Spoiler...", command=self.spoiler)
        sp.pack(side="right")
        Tip(sp, "Where every item is, and a route through the game, for the installed seed.")

        self.log = ScrolledText(main, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(10, 0))
        self.info = None
        self.refresh()
        self.sync()
        root.after(100, self.pump)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---- state ---------------------------------------------------------------------------------
    def options(self) -> dict:
        """The window's state (saved as settings). The generator gets spots/doors only when their box
        is ticked (spots_count/doors_count); hints only for the original game (not ReHaunted)."""
        return {"seed": self.seed.get().strip(), "drops": self.drops.get(), "drop_chance": self._int(self.drop_chance, 25),
                "spots_on": self.spots_on.get(), "spots": self._int(self.spots, 0),
                "doors_on": self.doors_on.get(), "doors": self._int(self.doors, 0),
                "keynames": self.keynames.get(), "mirrors": self.mirrors.get(), "hints": self.hints_pref, "controls": self.controls_pref, "keep_aspect": self.keep_aspect_pref, "edition": self.edition.get(),
                "difficulty": self.difficulty.get(), "vh_doors_warned": self.vh_warned,
                "folder": self.folder.get().strip(), "sep_data": self.sep.get(),
                "data_dir": self.data_dir.get().strip(),
                "custom_hd": self.custom_hd.get(), "hd_assets": self.hd_assets.get().strip()}

    def difficulty_changed(self):
        """Very hard seeds come from many locked doors and few extra spots (Research/SeedDifficulty.md:
        none of 80 seeds without locked doors reached it; 40 spots with doors 60 % gave 12 %): it turns
        More locked doors on at 60 % or more, and lowers Many search places to 10 if it is on and higher."""
        if self.difficulty.get() == "Very hard":
            self.doors_on.set(True)
            if self._int(self.doors, 0) < VERY_HARD_DOORS:
                self.doors.set(VERY_HARD_DOORS)
            if self.spots_on.get() and self._int(self.spots, 0) > VERY_HARD_SPOTS:
                self.spots.set(VERY_HARD_SPOTS)
        self.sync()

    def very_hard_settings_changed(self):
        """Under Very hard, More locked doors off or under 60 %, or Many search places on and over 10:
        a warning, once ever (user, 2026-10-18)."""
        self.sync()
        doors_low = not self.doors_on.get() or self._int(self.doors, 0) < VERY_HARD_DOORS
        spots_high = self.spots_on.get() and self._int(self.spots, 0) > VERY_HARD_SPOTS
        if self.difficulty.get() == "Very hard" and (doors_low or spots_high) and not self.vh_warned:
            self.vh_warned = True
            save_settings(self.options())
            messagebox.showwarning(APP_NAME, "Very hard seeds come from many locked doors and few extra "
                                   f"hiding spots. With More locked doors off or under {VERY_HARD_DOORS} %, "
                                   f"or Many search places over {VERY_HARD_SPOTS}, finding a Very hard layout "
                                   "can take very long, or fail for this seed.\n\nThis warning is "
                                   "shown only once.")

    def hints_clicked(self):
        self.hints_pref = self.hints.get()
        self.sync()

    def controls_clicked(self):
        self.controls_pref = self.controls.get()
        self.sync()

    def keep_aspect_clicked(self):
        self.keep_aspect_pref = self.keep_aspect.get()
        self.sync()

    @staticmethod
    def _int(var, default):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    def has_rehaunted(self) -> bool:
        return bool(self.info) and any(p["file"] == "Tatou.exe" for p in self.info["programs"])

    def is_vanilla_seed(self) -> bool:
        s = self.seed.get().strip()
        return s.isdigit() and int(s) == VANILLA_SEED

    def sync(self):
        """Enable what applies to this folder. Every seed shuffles the visible items, which writes
        OBJETS.ITD, so ReHaunted always needs the edition; hints are for the original game only.
        Seed 0 (the original layout) greys out the randomizing options; their values stay as they are."""
        vanilla = self.is_vanilla_seed()
        for c in self.random_cbs.values():
            c.state(["disabled"] if vanilla else ["!disabled"])
        self.difficulty_cb.state(["disabled"] if vanilla else ["!disabled", "readonly"])
        self.drop_sb.state(["!disabled"] if self.drops.get() and not vanilla else ["disabled"])
        for key, on in (("spots", self.spots_on), ("doors", self.doors_on)):
            self.number_sb[key].state(["!disabled"] if on.get() and not vanilla else ["disabled"])
        if not self.has_rehaunted():
            self.edition_cb.grid_remove()             # Classic only: nothing to choose
            self.hints.set(self.hints_pref)
            self.hints_cb.state(["!disabled"])
            self.keep_aspect.set(False)               # ReHaunted only
            self.keep_aspect_cb.state(["disabled"])
        else:
            self.edition_cb.grid()
            self.edition.set(True)
            self.edition_cb.state(["disabled"])
            self.hints.set(False)
            self.hints_cb.state(["disabled"])
            self.keep_aspect.set(self.keep_aspect_pref)
            self.keep_aspect_cb.state(["!disabled"])
        self.sync_hd()
        idle = not self.busy
        self.go.state(["!disabled"] if idle and self.data_ok and not self.hd_blocks() else ["disabled"])
        self.undo.state(["!disabled"] if idle and self.info and self.info["installed_seed"] is not None
                        else ["disabled"])

    def sync_hd(self):
        """Custom HD backgrounds: ReHaunted 2.4 folders only (custom_hd.detect); the row is hidden
        for the original game. The status line says what is wrong, if anything."""
        rows = (self.hd_cb, self.hd_entry, self.hd_browse, self.hd_status)
        if not self.has_rehaunted():
            for w in rows:
                w.grid_remove()
            return
        for w in rows:
            w.grid()
        msg, ok = "", True
        if self.hd_problem:
            self.custom_hd.set(False)
            self.hd_cb.state(["disabled"])
            msg, ok = "Custom HD backgrounds: " + self.hd_problem, False
        else:
            self.hd_cb.state(["!disabled"])
            if self.custom_hd.get():
                try:
                    s = self._check_pack(Path(self.hd_assets.get().strip() or "."))
                    msg = (f"{s['stills']} still(s), {s['animations']} animation(s) ({s['frames']} frames), "
                           f"{s['bytes'] / 1e6:.0f} MB")
                except CH.Refused as e:
                    msg, ok = str(e), False
        on = self.custom_hd.get()
        self.hd_entry.state(["!disabled"] if on else ["disabled"])
        self.hd_browse.state(["!disabled"] if on else ["disabled"])
        self.hd_status.config(text=msg, fg=GREEN if ok else RED)
        self.hd_ok = ok

    def hd_blocks(self) -> bool:
        """The option is ticked but can't be installed: Randomize stays off."""
        return self.has_rehaunted() and self.custom_hd.get() and not self.hd_ok

    @staticmethod
    def _check_pack(pack: Path) -> dict:
        """The custom HD pack: its TatouHd must be the edition build (the other one can't play a
        seed) and it must hold backgrounds. Returns the asset summary; raises CH.Refused."""
        _exe, flavor, _desc = CH.pack_exe(pack)
        if flavor != "edition":
            raise CH.Refused(f"the TatouHd.exe in {pack} is not the randomizer edition build")
        return CH.scan_assets(pack)[2]

    def browse_hd(self):
        d = filedialog.askdirectory(initialdir=self.hd_assets.get() or None,
                                    title="The custom HD pack folder (TatouHd.exe + backgrounds_custom)")
        if d:
            self.hd_assets.set(d)
            self.sync()

    def refresh(self):
        f = self.folder.get().strip()
        text, self.info = describe(Path(f)) if f else (
            "Choose the game directory (the one holding INDARK.EXE or ReHaunted's Tatou.exe), or press "
            "Find.", None)
        self.status.config(text=text)
        if self.info is not None:
            # game files a ReHaunted install copied in are removed again before the next seed
            self.info["copied_data"] = False
            if self.info["installed_seed"] is not None:
                try:
                    rec = json.loads((Path(f) / I.MARKER).read_text(encoding="utf-8"))
                    self.info["copied_data"] = bool(rec.get("copied_data"))
                except (OSError, ValueError):
                    pass
        self.hd_problem = None
        if self.has_rehaunted():
            try:
                problems = CH.detect(Path(f))["problems"]
                self.hd_problem = problems[0] if problems else None
            except OSError as e:
                self.hd_problem = str(e)
        self.found = I.search_game_data() if self.has_rehaunted() else []
        self.refresh_data()

    def refresh_data(self):
        """The game data directory row: where the original files come from.
        - The game directory has them (Classic, ReHaunted inside the GOG/Steam folder): nothing to
          choose; the box is locked off.
        - ReHaunted without them, a Steam/GOG/CD copy found: it is shown greyed; the box may be
          ticked to choose another copy.
        - ReHaunted without them, nothing found: the box is ticked and locked on; Randomize stays
          off until the chosen folder holds the original files."""
        info, ok, msg = self.info, False, ""
        self.data_path = None
        own = bool(info) and info["sentinel"] and not info["copied_data"]
        if info is None or own or not self.has_rehaunted():
            self.sep.set(False)
            self.sep_cb.state(["disabled"])
            self.found_dir.set("")
            if own:
                ok, msg = True, "Game data: in the game directory."
            elif info is not None:
                msg = "No game files in the game directory (no ITD_RESS.PAK)."
        else:
            if not self.found:
                self.sep.set(True)
            self.sep_cb.state(["!disabled"] if self.found else ["disabled"])
            if self.sep.get():
                p = self.data_dir.get().strip()
                if p:
                    ok, msg = check_data(Path(p))
                    self.data_path = Path(p).resolve()
                else:
                    msg = NO_DATA if not self.found else "Choose your game data directory."
            else:
                how, path = self.found[0]
                self.found_dir.set(str(path))
                ok, msg = check_data(path)
                msg = f"Game data: your {how} copy. {msg}"
                self.data_path = path
        on = self.sep.get()
        self.data_entry.config(textvariable=self.data_dir if on else self.found_dir)
        self.data_entry.state(["!disabled"] if on else ["disabled"])
        self.data_browse.state(["!disabled"] if on else ["disabled"])
        self.data_status.config(text=msg, fg=GREEN if ok else RED)
        self.data_ok = ok
        self.sync()

    def browse(self):
        d = filedialog.askdirectory(title="The game directory (where you play)", initialdir=self.folder.get() or None)
        if d:
            self.folder.set(str(Path(d)))
            self.refresh()

    def browse_data(self):
        d = filedialog.askdirectory(title="The game data directory (your GOG, Steam or CD copy; the folder "
                                          "with ITD_RESS.PAK)", initialdir=self.data_dir.get() or None)
        if d:
            self.data_dir.set(str(Path(d)))
            self.refresh_data()

    def find(self):
        found = I.search_game_data()
        if not found:
            messagebox.showinfo(APP_NAME, "No Steam or GOG installation of Alone in the Dark was found. "
                                          "Choose the folder with Browse.")
            return
        how, path = found[0]
        self.folder.set(str(path))
        self.refresh()
        self.say(f"Found your {how} installation: {path}\n")

    # ---- log -----------------------------------------------------------------------------------
    def say(self, s: str):
        self.log.config(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.config(state="disabled")

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.say(payload)
                elif kind == "done":
                    self.busy = False
                    self.refresh()
                    title, msg, ok = payload[:3]
                    if payload[3:] == ("need_data",):     # found before, gone now: ask for it
                        self.sep.set(True)
                        self.refresh_data()
                        self.data_entry.focus_set()
                    (messagebox.showinfo if ok else messagebox.showerror)(title, msg)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def run(self, job, *args):
        self.busy = True
        self.sync()
        save_settings(self.options())

        def work():
            out = LogWriter(self.q)
            try:
                with contextlib.redirect_stdout(out):
                    res = job(*args)
            except NeedData as e:
                res = (APP_NAME, str(e), False, "need_data")
            except Refused as e:
                res = (APP_NAME, str(e), False)
            except PermissionError as e:
                res = (APP_NAME, f"Windows did not allow writing a file ({e.filename}). If the game is "
                                 "under Program Files, run this app as administrator.", False)
            except BaseException as e:            # SystemExit from the tools, or a bug
                msg = str(e) if isinstance(e, SystemExit) and not isinstance(e.code, int) else \
                    "".join(traceback.format_exception(e))
                self.q.put(("log", msg + "\n"))
                res = (APP_NAME, "Something went wrong; the details are in the log below. Nothing was "
                                 "installed unless the log says so.", False)
            self.q.put(("done", res))
        threading.Thread(target=work, daemon=True).start()

    # ---- actions -------------------------------------------------------------------------------
    def randomize(self):
        opt = self.options()
        if not opt["seed"].isdigit() or not VANILLA_SEED <= int(opt["seed"]) <= SEED_MAX:
            messagebox.showerror(APP_NAME, f"The seed must be a number from {VANILLA_SEED} to {SEED_MAX} "
                                           f"({VANILLA_SEED} = the original item layout).")
            return
        opt["seed"] = str(int(opt["seed"]))          # "00" is seed 0 too, in one seed folder
        self.refresh()
        if self.info is None:
            messagebox.showerror(APP_NAME, "Choose the game directory first.")
            return
        if not self.data_ok:
            messagebox.showerror(APP_NAME, self.data_status.cget("text") or NO_DATA)
            return
        own = self.info["sentinel"] and not self.info["copied_data"]
        opt["data_override"] = None if own or self.data_path is None else str(self.data_path)
        if self.info["installed_seed"] is not None and not messagebox.askyesno(
                APP_NAME, f"Seed {self.info['installed_seed']} is installed in this folder. Replace it?\n\n"
                          "It is uninstalled first (every original file restored)." + "\n\n" + SAVES):
            return
        self.say(f"\n=== Seed {opt['seed']} ===\n")
        self.run(self._randomize, Path(opt["folder"]).resolve(), opt, self.has_rehaunted())

    def _randomize(self, folder: Path, opt: dict, rehaunted: bool):
        writable(folder)
        if rehaunted and opt.get("custom_hd"):     # every custom HD check that can refuse, before any write
            problems = CH.detect(folder)["problems"]
            if problems:
                raise Refused("Custom HD backgrounds: " + problems[0])
            try:
                self._check_pack(Path(opt["hd_assets"]))
            except CH.Refused as e:
                raise Refused(f"Custom HD backgrounds: {e}") from None
        if I.detect(folder)["installed_seed"] is not None:
            print("Uninstalling the current seed...")
            if I.unpatch(folder) != 0:
                raise Refused("The installed seed could not be uninstalled; see the log.")
        data = self._game_data(folder, opt.get("data_override"))
        print(f"Original game files: {data}")
        os.environ["AITD_RANDO_DATA"] = str(data)
        import generate as G
        G.SRC = data
        out = SEEDS / f"seed_{opt['seed']}"
        argv = ["--seed", opt["seed"], "--out", str(out)]
        vanilla = int(opt["seed"]) == VANILLA_SEED        # the original layout: no randomizing option
        if opt["drops"] and not vanilla:
            argv += ["--enemy-drops", "--drop-chance", str(opt["drop_chance"])]
        if opt["spots_on"] and opt["spots"] and not vanilla:
            argv += ["--extra-spots", str(opt["spots"])]
        if opt["doors_on"] and opt["doors"] and not vanilla:
            argv += ["--locked-doors", str(opt["doors"])]
        # always on (visible items and saber pieces shuffle, so not for seed 0)
        argv += ["--drop-glow"] + ([] if vanilla else ["--visible-items", "--saber-pieces"])
        argv += ["--key-names"] * opt["keynames"] + ["--whole-mirrors"] * opt["mirrors"]
        wanted = None if vanilla else DIFFICULTIES.get(opt.get("difficulty"))
        if vanilla:
            print("Seed 0: the original item layout, with the fixes and options...")
        elif wanted:
            argv += ["--difficulty", wanted]
            print(f"Generating a {opt['difficulty']} layout (this can take a minute or two)...")
        else:
            print("Generating...")
        if G.main(argv) != 0:
            if wanted:
                raise Refused(f"No {opt['difficulty']} layout was found for seed {opt['seed']} with these "
                              "options. Press Random for another seed, or choose another difficulty "
                              "(more locked doors make seeds harder).")
            raise Refused("This seed could not be generated with these options; see the log.")
        diff = json.loads((out / "patchset" / "manifest.json").read_text(encoding="utf-8"))["difficulty"]
        edition = EDITION_EXE if rehaunted else None    # every seed writes OBJETS.ITD (visible items)
        print("Installing...")
        rc = I.apply(out, folder, force=False, fix_config=True, edition=edition,
                     game_data=None if I.find(folder, I.SENTINEL) else data, force_data=False,
                     hints=opt["hints"] and not rehaunted, controls=bool(opt.get("controls")),
                     keep_aspect=bool(opt.get("keep_aspect")) and rehaunted)
        if rc != 0:
            raise Refused("The seed was generated but not installed; see the log. Your game is unchanged.")
        hd_note = self._custom_hd(folder, opt) if rehaunted else ""
        what = (": the original item layout, with the fixes and your options" if vanilla else
                f". Difficulty: {diff['label']} (score {diff['score']}; the original game = 100)")
        return (APP_NAME, f"Seed {opt['seed']} is installed{what}.\n\nStart the game as usual and choose "
                          f"New Game.{hd_note}\n\n{SAVES}", True)

    @staticmethod
    def _custom_hd(folder: Path, opt: dict) -> str:
        """After the seed: install or update the custom HD backgrounds (option ticked), or remove the
        ones this app installed (option unticked). Custom HD installed by the standalone patcher is
        left alone. A failure here leaves the seed installed."""
        m = CH.load_manifest(folder)
        if opt.get("custom_hd"):
            print("Installing the custom HD backgrounds...")
            try:
                CH.install(folder, Path(opt["hd_assets"]), installed_by="randomizer", require_flavor="edition")
            except CH.Refused as e:
                raise Refused(f"The seed is installed, but the custom HD backgrounds are not: {e}") from None
            return "\n\nCustom HD backgrounds: start TatouHd.exe (not Tatou.exe) to play with them."
        if m and m.get("installed_by") == "randomizer":
            print("Removing the custom HD backgrounds (the option is off)...")
            CH.uninstall(folder)
        return ""

    @staticmethod
    def _game_data(folder: Path, override: str | None = None) -> Path:
        """The original files to build the seed from: the game data directory when the window
        chose one, else the game directory's own, else the Steam/GOG/CD install install.py would
        copy in (the same search). Must be the known GOG files."""
        if override:
            cands = [("game data directory", Path(override))]
        elif I.find(folder, I.SENTINEL):
            cands = [("this folder", folder)]
        else:
            cands = I.search_game_data()
            if not cands:
                raise NeedData(NO_DATA)
        how, path = cands[0]
        missing, different = I.check_game_data(path)
        if missing or different:
            raise Refused(f"The game files in {path} ({how}) are not the original Steam/GOG release files"
                          + (f"\nmissing: {', '.join(missing)}" if missing else "")
                          + (f"\ndifferent: {', '.join(different)}" if different else "")
                          + "\n\nIf another mod is installed, remove it first (or reinstall the game).")
        return path

    def uninstall(self):
        folder = Path(self.folder.get().strip()).resolve()
        if not messagebox.askyesno(APP_NAME, "Uninstall the seed and restore the original files?\n\n" + SAVES):
            return
        self.say("\n=== Uninstall ===\n")
        self.run(self._uninstall, folder)

    @staticmethod
    def _uninstall(folder: Path):
        writable(folder)
        if I.unpatch(folder) != 0:
            raise Refused("Uninstall stopped; see the log.")
        m = CH.load_manifest(folder)            # the TatouHd edition plays from the seed's game files
        if m and m.get("installed_by") == "randomizer":
            print("Removing the custom HD backgrounds...")
            if CH.uninstall(folder):
                return (APP_NAME, "The original files are restored. Some custom HD files changed "
                                  "since install were kept; see the log.", True)
        return (APP_NAME, "The original files are restored.", True)

    def spoiler(self):
        folder = Path(self.folder.get().strip() or ".")
        marker = folder / I.MARKER
        try:
            rec = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            messagebox.showinfo(APP_NAME, "No seed is installed in this folder.")
            return
        path = SEEDS / str(rec.get("seed_dir")) / "spoiler.md"
        if not path.is_file():
            messagebox.showinfo(APP_NAME, f"The spoiler of seed {rec.get('seed')} is not on this computer "
                                          f"(looked for {path}).")
            return
        if not messagebox.askyesno(APP_NAME, "The spoiler shows where every item is. Show it?"):
            return
        w = tk.Toplevel(self.root)
        w.title(f"Spoiler: seed {rec.get('seed')}")
        w.geometry("900x650")
        t = ScrolledText(w, wrap="none", font=("Consolas", 9))
        t.pack(fill="both", expand=True)
        t.insert("1.0", path.read_text(encoding="utf-8"))
        t.config(state="disabled")

    def open_seeds(self):
        SEEDS.mkdir(parents=True, exist_ok=True)
        os.startfile(SEEDS)

    def about(self):
        messagebox.showinfo(f"About {APP_NAME}", f"""{APP_NAME} {APP_VERSION}

An item and key randomizer for Alone in the Dark (1992), for the original DOS game (GOG/Steam) and for ReHaunted.

Unofficial fan project, not affiliated with or endorsed by the owners of Alone in the Dark or by the ReHaunted authors. It contains no game data: seeds are built from your own copy of the game.

Includes:
- the AITD Randomizer edition of ReHaunted (Tatou.exe), a modified build of Alone In The Dark: Re-Haunted by Jake Jackson / Spacefarer Retro Remasters, based on Free in the Dark (FITD). GNU General Public License v2; source code: published with the release.
- Python (PSF License), Tcl/Tk (BSD-style licence), packaged with PyInstaller (GPL v2 with the bootloader exception).

Seeds and spoilers are saved in {SEEDS}.""")

    def close(self):
        if self.busy and not messagebox.askyesno(APP_NAME, "Still working. Quitting now can leave the "
                                                 "game folder half-changed. Quit anyway?"):
            return
        save_settings(self.options())
        self.root.destroy()


def selftest(game: Path) -> int:
    """`--selftest GAME`: the install flow inside the frozen exe, without the window (checks the
    bundle has every module and data file). GAME: a throwaway copy of a game folder. Randomizes
    seed 4242 with every option (hints too, for the original game), uninstalls, compares the whole folder; writes GAME.selftest.log."""
    log = Path(str(game) + ".selftest.log")
    global SEEDS
    SEEDS = Path(str(game) + ".seeds")
    with open(log, "w", encoding="utf-8") as f, contextlib.redirect_stdout(f):
        def tree():
            return {str(p.relative_to(game)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(game.rglob("*")) if p.is_file()}
        before = tree()
        print("search_game_data:", I.search_game_data())
        print("describe:", describe(game)[0].replace("\n", " | "))
        opt = {**DEFAULTS, "seed": "4242", "keynames": True, "hints": True, "folder": str(game)}
        try:
            res = App._randomize(App.__new__(App), game, opt, any(
                p["file"] == "Tatou.exe" for p in I.detect(game)["programs"]))
            ok = res[2] and I.detect(game)["installed_seed"] == 4242
        except Exception:
            traceback.print_exc()
            ok = False
        ok = I.unpatch(game) == 0 and ok
        same = tree() == before
        print(f"SELFTEST {'PASS' if ok and same else 'FAIL'} (install {ok}, folder restored {same})")
    return 0 if ok and same else 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(Path(sys.argv[2]).resolve()))
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
