param(
    [string]$Python = 'py',
    [switch]$Online,
    [string]$Wheelhouse = ''
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11–3.13 required. Pass -Python with its full executable path.' }
    }
    $VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if ($Online) {
        & $VenvPython -m pip install -c constraints-windows-py312.txt -e .
    } elseif ($Wheelhouse) {
        & $VenvPython -m pip install --no-index --find-links $Wheelhouse -c constraints-windows-py312.txt -e .
    } else {
        throw 'Choose -Online for dependency setup only, or -Wheelhouse for offline installation. No models are downloaded.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $VenvPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    Write-Host 'Setup complete. Follow SETUP.md for local engines/models, then run scripts\doctor.ps1.'
} finally { Pop-Location }
