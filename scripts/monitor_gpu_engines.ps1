param([string]$TargetPids, [string]$StopPath, [string]$OutputPath)
# Read Windows' GPU engine counters for only the benchmark's own processes.
$ErrorActionPreference = 'Stop'
$BenchmarkPids = @($TargetPids.Split(',') | ForEach-Object { [int]$_ })
$Rows = [System.Collections.Generic.List[object]]::new()
$MonitorResult = @{ samples = @(); error = $null }
try {
    while (-not (Test-Path -LiteralPath $StopPath)) {
        # Dynamic process instances can disappear while Windows samples them.
        # Keep valid entries instead of stopping because an unrelated one expired.
        $Counters = Get-Counter -Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue
        foreach ($Sample in $Counters.CounterSamples) {
            if ($Sample.InstanceName -match '^pid_(\d+)_') {
                $BenchmarkProcessId = [int]$Matches[1]
                if ($BenchmarkPids -contains $BenchmarkProcessId -and $Sample.Status -in @(0,1) -and -not [double]::IsNaN($Sample.CookedValue)) {
                    $Rows.Add([pscustomobject]@{
                        timestamp = $Sample.Timestamp.ToUniversalTime().ToString('o')
                        pid = $BenchmarkProcessId
                        engine = $Sample.InstanceName
                        percent = [math]::Round([math]::Max(0, $Sample.CookedValue), 3)
                    })
                }
            }
        }
    }
} catch {
    $MonitorResult.error = $_.Exception.Message
} finally {
    $MonitorResult.samples = @($Rows.ToArray())
    $MonitorResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding utf8
}
