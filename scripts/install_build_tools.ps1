param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $Destination) { throw 'Choose a new build-tool directory.' }
New-Item -ItemType Directory -Path $Destination | Out-Null
$ToolRoot=(Resolve-Path -LiteralPath $Destination).Path
$Installer=Join-Path $ToolRoot 'innosetup-6.7.3.exe'
Invoke-WebRequest -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLower() -ne '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732') { throw 'Compiler checksum mismatch.' }
$Signature=Get-AuthenticodeSignature -LiteralPath $Installer
if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Subject -notlike '*Pyrsys*') { throw 'Compiler publisher verification failed.' }
Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',('/DIR="'+(Join-Path $ToolRoot 'compiler')+'"')) -WindowStyle Hidden -Wait
Write-Host ('Compiler: '+(Join-Path $ToolRoot 'compiler/ISCC.exe'))
