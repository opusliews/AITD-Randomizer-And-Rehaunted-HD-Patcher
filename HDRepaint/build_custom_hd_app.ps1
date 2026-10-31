# Builds the standalone patcher: Generated\HDRepaint\dist\ReHaunted Custom Textures.exe (one file,
# no Python needed). It holds no TatouHd and no images: it installs from the custom HD pack it
# sits in (make_hd_pack.ps1 puts it there).
#   powershell -ExecutionPolicy Bypass -File Generated\HDRepaint\build_custom_hd_app.ps1
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Gen = Split-Path $Here -Parent
$Py = "C:\Tools\PythonFull\python.exe"
if (-not (Test-Path $Py)) { $Py = (Get-Command python).Source }

$args = @("-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
          "--name", "ReHaunted Custom Textures",
          "--distpath", (Join-Path $Here "dist"), "--workpath", (Join-Path $Here "build"),
          "--specpath", (Join-Path $Here "build"),
          "--add-data", "$(Join-Path $Here 'custom_hd.py');Generated\HDRepaint",
          "--add-data", "$(Join-Path $Gen 'Generator\install.py');Generated\Generator",
          "--hidden-import", "winreg",
          (Join-Path $Here "custom_hd_app.py"))
& $Py @args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
$out = Join-Path $Here "dist\ReHaunted Custom Textures.exe"
"{0}  {1}  {2:N0} bytes" -f (Get-FileHash $out).Hash, $out, (Get-Item $out).Length
