$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') -m localflow.launcher --root $ProjectRoot
exit $LASTEXITCODE
