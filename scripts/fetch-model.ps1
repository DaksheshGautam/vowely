param(
    [Parameter(Mandatory)][ValidateSet('base','small','qwen','vad')][string]$Kind,
    [Parameter(Mandatory)][uri]$Url,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$Sha256
)
# Intentionally opt-in. No audio or transcript is accessed by this script.
$ErrorActionPreference = 'Stop'
if ($Url.Scheme -ne 'https' -or $Url.Host -notin @('huggingface.co', 'hf.co')) {
    throw 'Only HTTPS Hugging Face model URLs are accepted. Inspect the official model page first.'
}
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ModelDir = Join-Path $ProjectRoot 'models'
New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
$Names = @{ base='ggml-base.bin'; small='ggml-small.bin'; qwen='Qwen3-1.7B-Q4_K_M.gguf'; vad='ggml-silero-v6.2.0.bin' }
$Destination = Join-Path $ModelDir $Names[$Kind]
if (Test-Path -LiteralPath $Destination) { throw 'Destination exists; preserving existing model.' }
$Temporary = Join-Path $ModelDir ([guid]::NewGuid().ToString() + '.part')
try {
    Invoke-WebRequest -Uri $Url -OutFile $Temporary
    if ((Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash -ne $Sha256) {
        throw 'Checksum mismatch; downloaded file rejected.'
    }
    Move-Item -LiteralPath $Temporary -Destination $Destination
    Write-Host "Verified local model: $Destination"
} finally {
    if (Test-Path -LiteralPath $Temporary) { Remove-Item -LiteralPath $Temporary }
}
