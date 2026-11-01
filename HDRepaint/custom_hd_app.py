"""ReHaunted Custom Textures: the standalone patcher for the custom HD backgrounds (no randomizer).
Adds TatouHd.exe and backgrounds_custom/ to a ReHaunted 2.4 or 2.5 folder, verifies, and uninstalls
(custom_hd.py does the work; the randomizer app uses the same module and the same pack).

It ships inside the custom HD pack (make_hd_pack.ps1):
  ReHaunted Custom Textures.exe
  TatouHd.exe                                  the edition build: no game data inside
  backgrounds_custom/CAMERA00_000.png ...  anim_CAMERA00_000/ezgif-frame-001.png ...
The pack folder defaults to the app's own folder, so a new TatouHd or new cameras need no new
app. The edition TatouHd plays from the original game files: when the ReHaunted folder has none,
they are copied in from the player's GOG/Steam/CD copy (found automatically, or chosen).

Run from source: C:\\Tools\\PythonFull\\python.exe Generated\\HDRepaint\\custom_hd_app.py
Frozen by build_custom_hd_app.ps1.
"""
from __future__ import annotations

import contextlib, json, queue, sys, threading, traceback  # noqa: E401
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "ReHaunted Custom Textures"
FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else HERE
sys.path.insert(0, str(BUNDLE / "Generated" / "HDRepaint") if FROZEN else str(HERE))
import custom_hd as CH  # noqa: E402

SETTINGS = Path.home() / "Documents" / APP_NAME / "settings.json"


class LogWriter:
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        self.q.put(("log", s))

    def flush(self):
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root, self.q, self.busy = root, queue.Queue(), False
        try:
            s = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            s = {}
        root.title(APP_NAME)
        root.minsize(620, 500)
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)
        self.game = tk.StringVar(value=s.get("game", ""))
        self.pack = tk.StringVar(value=s.get("pack") or str(HERE))
        self.data = tk.StringVar(value=s.get("data", ""))
        self.status = self._row(main, "ReHaunted 2.4 or 2.5 folder (the one holding Tatou.exe)", self.game)
        self.pack_status = self._row(main, "Custom HD pack (TatouHd.exe and backgrounds_custom)", self.pack)
        self.data_status = self._row(main, "Original game files (only needed if not found automatically: "
                                           "the folder holding ITD_RESS.PAK)", self.data)
        b = ttk.Frame(main)
        b.pack(fill="x", pady=(10, 0))
        self.go = ttk.Button(b, text="Install / Update", command=self.install)
        self.go.pack(side="left")
        self.ver = ttk.Button(b, text="Verify", command=self.verify)
        self.ver.pack(side="left", padx=6)
        self.undo = ttk.Button(b, text="Uninstall", command=self.uninstall)
        self.undo.pack(side="left")
        self.log = ScrolledText(main, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(10, 0))
        self.info, self.ready = None, False
        self.refresh()
        root.after(100, self.pump)

    def _row(self, parent, title, var) -> ttk.Label:
        f = ttk.LabelFrame(parent, text=title, padding=8)
        f.pack(fill="x", pady=(0, 8))
        e = ttk.Entry(f, textvariable=var)
        e.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        e.bind("<FocusOut>", lambda _e: self.refresh())
        e.bind("<Return>", lambda _e: self.refresh())
        ttk.Button(f, text="Browse...", command=lambda: self.browse(var)).grid(row=0, column=1)
        f.columnconfigure(0, weight=1)
        status = ttk.Label(f, text="", justify="left", wraplength=580)
        status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        return status

    def browse(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or None)
        if d:
            var.set(d)
            self.refresh()

    def chosen_data(self) -> Path | None:
        d = self.data.get().strip()
        return Path(d) if d else None

    def refresh(self):
        ok_game = ok_pack = ok_data = False
        g = self.game.get().strip()
        self.info = CH.detect(Path(g)) if g else None
        if self.info is None:
            text = "Choose ReHaunted's folder."
        elif self.info["problems"]:
            text = self.info["problems"][0]
        else:
            ok_game = True
            m = self.info["manifest"]
            text = (f"ReHaunted {self.info['rehaunted']}: OK\n"
                    + (f"Custom HD installed ({m['files']} files, {m['installed']})" if m else "Custom HD: not installed")
                    + "".join("\nNote: " + n for n in self.info["notes"]))
        self.status.config(text=text)
        flavor = None
        try:
            pack = Path(self.pack.get().strip())
            _exe, flavor, desc = CH.pack_exe(pack)
            _files, warn, s = CH.scan_assets(pack)
            ok_pack = s["stills"] + s["animations"] + s["models"] > 0
            self.pack_status.config(text=f"{desc}; {s['stills']} still(s), {s['animations']} animation(s) "
                                         f"({s['frames']} frames), {s['models']} model(s), {s['bytes'] / 1e6:.0f} MB"
                                         + (f"; {len(warn)} note(s), see Install" if warn else ""))
        except CH.Refused as e:
            self.pack_status.config(text=str(e))
        if not ok_game or flavor != "edition":
            ok_data, text = True, ""
        elif self.info["game_data"]:
            ok_data, text = True, "In the ReHaunted folder: nothing to copy."
        else:
            try:
                how, src = CH.find_game_data(self.chosen_data())
                ok_data, text = True, f"Will be copied into the ReHaunted folder from {src} ({how}); only read there."
            except CH.Refused as e:
                text = str(e)
        self.data_status.config(text=text)
        self.ready = ok_game and ok_pack and ok_data
        self.sync()

    def sync(self):
        idle = not self.busy
        self.go.state(["!disabled"] if idle and self.ready else ["disabled"])
        has = idle and self.info is not None and self.info["manifest"] is not None
        self.ver.state(["!disabled"] if has else ["disabled"])
        self.undo.state(["!disabled"] if has else ["disabled"])

    def say(self, s):
        self.log.config(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.config(state="disabled")

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.say(val)
                else:
                    self.busy = False
                    self.refresh()
                    title, msg, ok = val
                    (messagebox.showinfo if ok else messagebox.showerror)(title, msg)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def run(self, job):
        self.busy = True
        self.sync()
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({"game": self.game.get().strip(), "pack": self.pack.get().strip(),
                                        "data": self.data.get().strip()}), encoding="utf-8")

        def work():
            try:
                with contextlib.redirect_stdout(LogWriter(self.q)):
                    res = job()
            except CH.Refused as e:
                res = (APP_NAME, str(e), False)
            except PermissionError as e:
                res = (APP_NAME, f"Windows did not allow writing {e.filename}. If ReHaunted is under "
                                 "Program Files, run this app as administrator.", False)
            except Exception as e:
                self.q.put(("log", "".join(traceback.format_exception(e))))
                res = (APP_NAME, "Something went wrong; the details are in the log.", False)
            self.q.put(("done", res))
        threading.Thread(target=work, daemon=True).start()

    def install(self):
        game, pack, data = Path(self.game.get().strip()), Path(self.pack.get().strip()), self.chosen_data()
        self.say("\n=== Install ===\n")

        def job():
            CH.install(game, pack, installed_by="standalone", game_data=data)
            return (APP_NAME, "Installed. Start TatouHd.exe (not Tatou.exe) to play with the custom "
                              "backgrounds. HD backgrounds must be on in the options window.", True)
        self.run(job)

    def verify(self):
        game = Path(self.game.get().strip())
        self.say("\n=== Verify ===\n")

        def job():
            bad = CH.verify(game, full=True)
            return (APP_NAME, "All installed files are present and unchanged." if not bad else
                    f"{len(bad)} problem(s), see the log. Install / Update repairs them.", not bad)
        self.run(job)

    def uninstall(self):
        game = Path(self.game.get().strip())
        if not messagebox.askyesno(APP_NAME, "Remove TatouHd.exe, the custom backgrounds and any game files "
                                             "this tool copied in?\n\nReHaunted's own files are not touched."):
            return
        self.say("\n=== Uninstall ===\n")

        def job():
            kept = CH.uninstall(game)
            return (APP_NAME, "Removed." if not kept else
                    f"Removed, except {kept} file(s) changed since install (see the log).", not kept)
        self.run(job)


def main():
    if len(sys.argv) > 1:                       # command line: same as custom_hd.py
        if sys.argv[1] == "install" and "--pack" not in sys.argv:
            sys.argv += ["--pack", str(HERE)]
        if sys.stdout is None:                  # the frozen app has no console: log next to the exe
            sys.stdout = sys.stderr = open(HERE / f"{APP_NAME}.log", "w", encoding="utf-8")
        sys.exit(CH.main())
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
