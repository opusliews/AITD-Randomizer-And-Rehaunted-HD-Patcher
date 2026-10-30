# Assembles the custom HD pack, the release that holds everything HD (Research/HDRepaint.md,
# "Shipping"). Both the standalone patcher in it and the randomizer's "Include custom HD
# backgrounds" option install from this folder.
#   powershell -ExecutionPolicy Bypass -File Generated\HDRepaint\make_hd_pack.ps1 `
#       [-Backgrounds <your backgrounds_custom folder>] [-Models <your models_custom folder>] [-Out <pack folder>]
# Result:
#   <Out>\ReHaunted Custom Textures.exe   the patcher (build_custom_hd_app.ps1)
#   <Out>\TatouHd.exe                     the edition build (build\hd-edition): no game data inside
#   <Out>\backgrounds_custom\...          mirrored from -Backgrounds (stills + anim_* folders)
#   <Out>\models_custom\...               mirrored from -Models when that folder exists (custom models,
#                                         Generated\HDModel\aitd_blender.py); otherwise left out
#   <Out>\README.txt
# Re-running updates the pack in place (robocopy /MIR: removed images are removed from the pack).
param([string] $Backgrounds = "", [string] $Models = "", [string] $Out = "")
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Root = Split-Path (Split-Path $Here -Parent) -Parent
$Py = "C:\Tools\PythonFull\python.exe"
if (-not $Backgrounds) { $Backgrounds = Join-Path $Here "backgrounds_custom" }
if (-not $Models) { $Models = Join-Path $Here "models_custom" }
if (-not $Out) { $Out = Join-Path $Here "pack\AITD Custom HD" }
$Patcher = Join-Path $Here "dist\ReHaunted Custom Textures.exe"
$TatouHd = Join-Path $Root "ReHaunted24\TatouSource\build\hd-edition\Fitd\TatouHd.exe"
foreach ($p in $Backgrounds, $Patcher, $TatouHd) { if (-not (Test-Path $p)) { throw "missing $p" } }

New-Item -ItemType Directory -Force $Out | Out-Null
Copy-Item $Patcher, $TatouHd $Out -Force
robocopy $Backgrounds (Join-Path $Out "backgrounds_custom") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
$PackModels = Join-Path $Out "models_custom"
if (Test-Path $Models) {
    robocopy $Models $PackModels /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
} elseif (Test-Path $PackModels) {
    Remove-Item -Recurse -Force $PackModels
}
@"
Custom HD backgrounds for Alone in the Dark: Re-Haunted 2.4

Without the randomizer: run "ReHaunted Custom Textures.exe", choose your ReHaunted folder, press
Install / Update. With the randomizer: tick "Include custom HD backgrounds" in the AITD Randomizer
and choose this folder.

Then start TatouHd.exe (not Tatou.exe) from the ReHaunted folder. HD backgrounds must be on in
ReHaunted's options. Uninstall removes exactly what was added (TatouHd.exe, backgrounds_custom,
and the original game files if the patcher had to copy them in from your GOG/Steam copy).
"@ | Set-Content -Encoding utf8 (Join-Path $Out "README.txt")

& $Py (Join-Path $Here "custom_hd.py") check-pack $Out
$size = (Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum).Sum
"pack: {0}  {1:N0} MB" -f $Out, ($size / 1MB)
"TatouHd.exe: {0}" -f (Get-FileHash $TatouHd).Hash
"patcher:     {0}" -f (Get-FileHash $Patcher).Hash
