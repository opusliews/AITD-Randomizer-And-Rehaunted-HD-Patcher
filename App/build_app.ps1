# Builds the patcher app: Generated\App\dist\AITD Randomizer.exe (one file, no Python needed).
#   powershell -ExecutionPolicy Bypass -File Generated\App\build_app.ps1
# The project tools are bundled as plain .py/.json files under Generated\ (their paths stay
# relative to each other, as in the project); the edition Tatou.exe goes to edition\.
# No game data is bundled: the app reads the player's own game files.
$ErrorActionPreference = "Stop"
$App = $PSScriptRoot
$Gen = Split-Path $App -Parent
$Root = Split-Path $Gen -Parent
$Py = "C:\Tools\PythonFull\python.exe"
$Edition = Join-Path $Root "ReHaunted24\TatouSource\build\randomizer-edition\Fitd\Tatou.exe"
$files = @(
    "Generator\generate.py", "Generator\install.py", "Generator\locked_doors.py", "Generator\verify_seed.py",
    "Generator\walkthrough.py", "Generator\zone_table.py",
    "Patcher\aitd_life.py", "Patcher\aitd_objets.py", "Patcher\aitd_pak.py", "Patcher\aitd_text.py",
    "Patcher\gamedata.py", "Patcher\slot_catalog2.py", "Patcher\vanilla_exe.py",
    "Logic\logic_check.py",
    "VisibleItems\placement.py", "VisibleItems\mechanics.py", "VisibleItems\scale_body.py",
    "DropGlow\glow.py", "DropGlow\glow_body.py",
    "BugSpray\spray.py", "BugSpray\spray_assets.py", "BugSpray\spray_sound.voc", "BugSpray\body_io.py", "AnimExport\aitd_model.py",
    "HDRepaint\custom_hd.py"
)
$files += Get-ChildItem (Join-Path $Gen "Patcher\catalog\*.json") | ForEach-Object { "Patcher\catalog\" + $_.Name }
$files += Get-ChildItem (Join-Path $Gen "Logic\*.json") | ForEach-Object { "Logic\" + $_.Name }

$args = @("-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
          "--name", "AITD Randomizer",
          "--distpath", (Join-Path $App "dist"), "--workpath", (Join-Path $App "build"),
          "--specpath", (Join-Path $App "build"))
foreach ($f in $files) {
    $src = Join-Path $Gen $f
    if (-not (Test-Path $src)) { throw "missing $src" }
    $args += @("--add-data", "$src;Generated\$(Split-Path $f -Parent)")
}
$args += @("--add-data", "$Edition;edition")
$args += (Join-Path $App "aitd_randomizer_app.py")
& $Py @args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
$exe = Join-Path $App "dist\AITD Randomizer.exe"
"{0}  {1}  {2:N0} bytes" -f (Get-FileHash $exe).Hash, $exe, (Get-Item $exe).Length
"edition bundled: {0}" -f (Get-FileHash $Edition).Hash