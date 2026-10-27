# AITD Randomizer: patcher source

Source for the two player downloads. No original game data is tracked here; the tools read the
player's own game files (`Patcher/gamedata.py`).

| Download | Entry point | Build |
|---|---|---|
| AITD Randomizer.exe | `App/aitd_randomizer_app.py` | `powershell -ExecutionPolicy Bypass -File Generated\App\build_app.ps1` |
| Custom HD pack (ReHaunted Custom Textures.exe + TatouHd.exe + images) | `HDRepaint/custom_hd_app.py` | `HDRepaint\build_custom_hd_app.ps1`, then `HDRepaint\make_hd_pack.ps1 [-Backgrounds DIR]` |

- Run the build scripts from a neutral folder (e.g. `Research`), not from inside `Generated`: PyInstaller puts the current directory first on its module path.
- Python: `C:\Tools\PythonFull\python.exe` (Tk, PyInstaller).
- The randomizer bundles `HDRepaint/custom_hd.py`, so both downloads share one HD install module.
- The engine builds (`Tatou.exe` edition, `TatouHd.exe` edition) come from the separate `ReHaunted24` repository (branch `rebase24`).
- Folders: `Generator` (seed generation, install), `Patcher` (PAK/LIFE/OBJETS readers and writers, slot catalogs, INDARK patches), `Logic` (progression check), `VisibleItems`, `DropGlow`, `HDRepaint`.
- Notes and test records: `Research/PatcherApp.md`, `Research/HDRepaint.md`.
