param([ValidateSet('app','app-update','app-microphones','app-accuracy','app-recovery','app-streaming','app-sentences','app-whisper-endpoints','app-prerelease','app-formatting','app-comma-lists','app-orb','app-automatic')][string]$Destination = 'app', [ValidateSet('LocalFlow','Vowely')][string]$AppName = 'Vowely')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BuildDir = Join-Path $ProjectRoot 'build\pyinstaller'
$DistDir = Join-Path $ProjectRoot $Destination
Push-Location $ProjectRoot
try {
    # Generate the UIA bindings before freezing, then collect them explicitly.
    & $Python -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"
    if ($LASTEXITCODE -ne 0) { throw 'UI Automation bindings failed.' }
    $VersionFile = Join-Path $BuildDir 'version-info.txt'
    & $Python scripts/write_version_info.py $VersionFile
    if ($LASTEXITCODE -ne 0) { throw 'Executable version metadata failed.' }
    & $Python -m PyInstaller --noconfirm --windowed --onedir --name $AppName --version-file $VersionFile --distpath $DistDir --workpath $BuildDir --specpath $BuildDir --paths (Join-Path $ProjectRoot 'src') --collect-submodules comtypes.gen --collect-submodules localflow scripts\freeze_entry.py
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
    & $Python scripts\fix_bundle.py (Join-Path $DistDir $AppName)
    if ($LASTEXITCODE -ne 0) { throw 'Windows runtime compatibility check failed.' }
    Write-Host "Packaged application: $DistDir\$AppName\$AppName.exe"
} finally { Pop-Location }
