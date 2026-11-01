# Alone in the Dark Randomizer and ReHaunted HD Patcher

Windows patching tools for the 1992 DOS release of *Alone in the Dark* and the
[ReHaunted](https://github.com/opusliews/AloneInTheDarkReHaunted) engine.

The randomizer creates deterministic seeds, validates that the resulting item
placement can be completed, and installs the randomized data into a player's own
copy of the game. The same application can also install the project's ReHaunted
bug fixes and optional HD-texture support.

This repository contains source code only. It does **not** include the original
game data, a compiled ReHaunted executable, or the custom HD image pack.

## Downloads

Player-ready installers are published separately on the
[Releases page](https://github.com/opusliews/AITD-Randomizer-And-Rehaunted-HD-Patcher/releases)
when a release is available:

- **AITD Randomizer.exe** — randomizer, ReHaunted bug-fix patcher, and HD-pack
  installer.
- **AITD Custom HD pack** — standalone custom-texture installer for ReHaunted.

The Python files in this repository are development entry points, not substitutes
for a complete release package.

## Requirements

- Windows 10 or Windows 11.
- A legally obtained GOG or Steam installation of *Alone in the Dark*.
- Either the original DOS version or ReHaunted 2.4 or 2.5, depending on the selected
  patching mode.

Free in the Dark (FITD) is not a supported installation target.

## Using the randomizer

1. Download **AITD Randomizer.exe** from the Releases page.
2. Close the game if it is running.
3. Start the randomizer and select the folder containing your game installation.
4. Choose the desired options and seed, then select **Randomize and install**.
5. Start a new game. Existing saves retain world state from the version and seed
   with which they were created.

The application records the installed seed and randomizer version so a run can be
reproduced. Select **Unpatch Game** to restore the files backed up during installation.
Keep the game closed while installing or removing a patch so its executable and
data files can be replaced safely.

## Using the custom HD pack

The image pack is distributed as a release asset rather than committed to this
source repository. Run the custom-texture installer from that package and point it
at a ReHaunted installation. It installs the HD-capable engine as `TatouHd.exe`
alongside the required images. The randomizer can install the same pack when the
corresponding option is selected.

## Repository contents

| Folder | Purpose |
|---|---|
| `App` | Tk desktop interface for generating, installing, and removing randomizer seeds and optional HD assets |
| `Generator` | Seed placement, locked-door generation, patch assembly, installation and restoration, seed verification, and spoiler walkthroughs |
| `Logic` | World-region and progression data, the reachability checker, and supporting audits and tests |
| `Patcher` | Readers and writers for AITD PAK, LIFE, TRACK, OBJETS, and text data; LIFE assembly, item-location catalogs, and classic `INDARK.EXE` patches |
| `BugSpray` | Implementation, models, animation, and sound for the randomizer's new Bug Spray item |
| `DropGlow` | Model, animation, and LIFE-script support for the light beams marking items dropped by monsters |
| `VisibleItems` | Placement and posing rules, custom models, and game-data changes for shuffled items at visible world locations |
| `Sounds` | Utility that extracts `LISTSAMP.PAK` VOC effects to WAV and builds a local browser showing their LIFE-script usage |
| `HDRepaint` | Installation, verification, and packaging tools for the custom ReHaunted background/model pack, plus HDA inspection utilities |
| `AnimExport` | Bidirectional conversion between AITD bodies/animations and glTF/GLB, with preview and validation tools |

Generated build output, original game files, compiled engine binaries, and the HD
image assets are intentionally excluded from version control. Private reverse-
engineering notes from the development workspace are also not part of this
repository.

## Building from source

The applications use Python, Tk, and PyInstaller. The relevant build scripts are:

- `App/build_app.ps1` — builds the randomizer application.
- `HDRepaint/build_custom_hd_app.ps1` — builds the standalone HD installer.
- `HDRepaint/make_hd_pack.ps1` — assembles the distributable HD package.

These scripts reflect the maintainer's release environment and may require local
path adjustments. A complete release build also requires separately compiled
`Tatou.exe` and `TatouHd.exe` binaries from the ReHaunted source, plus the HD image
assets. The source tree is therefore best suited to code review and development;
players should use the packaged release downloads.
