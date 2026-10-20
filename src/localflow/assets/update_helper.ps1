# Runs as a separate hidden process after the app has requested an update.
# Variables are supplied as safely quoted literals by update_handoff.py.
$ErrorActionPreference='Stop'
function Write-UpdateState([string]$Stage,[string]$Message) {
    $State=@{schema=1;stage=$Stage;message=$Message;version=$UpdateVersion}
    $Temporary=$StatusPath+'.tmp'
    [IO.File]::WriteAllText($Temporary,($State | ConvertTo-Json -Compress))
    if ([IO.File]::Exists($StatusPath)) {
        # Windows PowerShell converts a null string argument to an empty path.
        $Previous=$StatusPath+'.previous'
        [IO.File]::Replace($Temporary,$StatusPath,$Previous)
        [IO.File]::Delete($Previous)
    }
    else { [IO.File]::Move($Temporary,$StatusPath) }
}
try {
    Write-UpdateState 'waiting' 'Waiting for Vowely to close.'
    try { $ParentProcess=[Diagnostics.Process]::GetProcessById($ParentId) } catch { $ParentProcess=$null }
    if ($null -ne $ParentProcess -and -not $ParentProcess.WaitForExit(90000)) {
        throw 'Vowely did not close within 90 seconds. The update was not installed.'
    }
    $Stream=[IO.File]::OpenRead($Installer)
    $Hasher=[Security.Cryptography.SHA256]::Create()
    try { $ActualHash=[BitConverter]::ToString($Hasher.ComputeHash($Stream)).Replace('-','').ToLowerInvariant() }
    finally { $Stream.Dispose(); $Hasher.Dispose() }
    if ($ActualHash -ne $ExpectedHash) {
        throw 'Installer checksum changed. The update was blocked.'
    }
    Write-UpdateState 'installing' 'Installing the verified Vowely update.'
    $Info=New-Object Diagnostics.ProcessStartInfo
    $Info.FileName=$Installer
    $Info.Arguments='/SILENT /SUPPRESSMSGBOXES /NORESTART /RESTARTEXITCODE=3010 /DIR="'+$InstallDir+'"'
    $Info.UseShellExecute=$false; $Info.CreateNoWindow=$true; $Info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
    $Setup=[Diagnostics.Process]::Start($Info)
    $Setup.WaitForExit()
    if ($Setup.ExitCode -eq 3010) {
        Write-UpdateState 'reboot_required' 'The update needs a Windows restart. Restart Windows before opening Vowely.'
        exit 0
    }
    if ($Setup.ExitCode -ne 0) { throw ('Installer stopped with exit code '+$Setup.ExitCode+'. Reopen Vowely to retry.') }
    Write-UpdateState 'complete' 'Vowely updated successfully.'
} catch {
    Write-UpdateState 'failed' $_.Exception.Message
}
if ([IO.File]::Exists($AppPath)) {
    $Launch=New-Object Diagnostics.ProcessStartInfo
    $Launch.FileName=$AppPath; $Launch.Arguments='--root "'+$DataRoot+'"'
    $Launch.UseShellExecute=$false; $Launch.CreateNoWindow=$true; $Launch.WindowStyle=[Diagnostics.ProcessWindowStyle]::Normal
    [void][Diagnostics.Process]::Start($Launch)
}
