$ErrorActionPreference = 'Stop'
$TaskRoot = $PSScriptRoot
$VowelyExe = Join-Path $TaskRoot 'app\Vowely\Vowely.exe'
if (-not (Test-Path -LiteralPath $VowelyExe)) {
    throw 'Extract the complete Windows portable ZIP first. Source users should follow SETUP.md.'
}
Write-Host 'Explicit Vowely setup: downloads about 3.3 GB of pinned models and engines.'
Write-Host 'No microphone is opened and no voice or transcript is uploaded.'
Write-Host 'Allow at least 10 GB of free disk space. Downloads are reused on a retry.'
$SetupLog = Join-Path $TaskRoot 'setup-downloads.log'
$TaskArguments = @('--root', ('"' + $TaskRoot + '"'), '--provision-assets', '--setup-log', ('"' + $SetupLog + '"'))
$SetupProcess = Start-Process -FilePath $VowelyExe -ArgumentList $TaskArguments -WindowStyle Hidden -PassThru
$LastPrintedLine = 0
while (-not $SetupProcess.HasExited) {
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $SetupLog) {
        $TaskLines = @(Get-Content -LiteralPath $SetupLog)
        if ($TaskLines.Count -gt $LastPrintedLine) {
            $TaskLines[$LastPrintedLine..($TaskLines.Count - 1)] | Write-Host
            $LastPrintedLine = $TaskLines.Count
        }
    }
    $SetupProcess.Refresh()
}
$SetupProcess.WaitForExit()
if ($SetupProcess.ExitCode -ne 0) { throw "Setup failed. See $SetupLog and retry; existing different files are preserved." }
Write-Host 'Setup complete. Double-click Start Vowely.vbs. Dictation now works offline.'
