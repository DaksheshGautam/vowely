param(
    [Parameter(Mandatory)][ValidateSet('whisper','llama')][string]$Engine,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$Commit,
    [switch]$Cuda
)
$ErrorActionPreference = 'Stop'
if ($Engine -eq 'llama' -and $Cuda) { throw 'Cleanup is CPU-only for this MVP.' }
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VendorDir = Join-Path $ProjectRoot 'vendor'
New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null
$SourceDir = Join-Path $VendorDir "$Engine-source-$Commit"
if (Test-Path -LiteralPath $SourceDir) { throw 'Source directory exists; preserving it. Build manually or choose another commit.' }
$Repository = if ($Engine -eq 'whisper') { 'https://github.com/ggml-org/whisper.cpp.git' } else { 'https://github.com/ggml-org/llama.cpp.git' }
& git clone $Repository $SourceDir
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
& git -C $SourceDir checkout --detach $Commit
if ($LASTEXITCODE -ne 0) { throw 'Pinned commit checkout failed.' }
$BuildDir = Join-Path $SourceDir 'build'
$CudaFlag = if ($Cuda) { 'ON' } else { 'OFF' }
& cmake -S $SourceDir -B $BuildDir '-DBUILD_SHARED_LIBS=OFF' "-DGGML_CUDA=$CudaFlag"
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed; check Visual Studio C++ tools and CUDA toolkit if requested.' }
& cmake --build $BuildDir --config Release -j 4
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host "Built pinned source in $BuildDir. Copy executable and its runtime DLLs into vendor\$Engine, or set paths in config.json. See SETUP.md."
