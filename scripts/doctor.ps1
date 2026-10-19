$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') -m localflow.doctor --root $ProjectRoot
exit $LASTEXITCODE
