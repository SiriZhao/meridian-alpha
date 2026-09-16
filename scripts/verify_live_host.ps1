[CmdletBinding()]
param([string]$Account = 'Schwab-Paper', [string]$Snapshot)
$ErrorActionPreference = 'Stop'
# Preserve the existing external acceptance distinction; never hide Codex ancestry.
$currentPid = $PID
for ($i = 0; $i -lt 20 -and $currentPid -gt 0; $i++) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$currentPid"
    if (-not $processInfo) { break }
    if ($processInfo.Name -match '(?i)codex') {
        Write-Output 'EXTERNAL_HOST_INVALID: RUN_FROM_NORMAL_POWERSHELL'
        exit 3
    }
    $currentPid = $processInfo.ParentProcessId
}
$parameters = @{ Account = $Account }
if ($Snapshot) { $parameters.Snapshot = $Snapshot }
$reports = @()
for ($i = 1; $i -le 2; $i++) {
    $output = @(& (Join-Path $PSScriptRoot 'run_live_advisory.ps1') @parameters)
    $code = $LASTEXITCODE
    Write-Output $output
    if ($code -ne 0) { exit $code }
    $report = $output[-1] | ConvertFrom-Json
    if (-not $report.LIVE_RUN_READY) { throw 'LIVE_RUN_NOT_READY' }
    $reports += $report
}
if ($reports[0].run_id -eq $reports[1].run_id) { throw 'DISTINCT_RUN_IDS_REQUIRED' }
$blockers = @()
foreach ($report in $reports) {
    if ($report.portfolio_summary.source -ne 'USER_SUPPLIED_HOST_SNAPSHOT') {
        $blockers += 'FRESH_REAL_ACCOUNT_SNAPSHOT_REQUIRED'
    }
    if ($report.freshness -ne 'LIVE') { $blockers += 'REALTIME_FEED_ACCEPTANCE_REQUIRED' }
    if ($report.AUTO_EXECUTION -ne 'DISABLED' -or -not $report.MANUAL_CONFIRMATION_REQUIRED -or $report.ORDER_AUTHORITY -ne 'NONE') {
        $blockers += 'SAFETY_INVARIANT_FAILED'
    }
}
$receipt = @{
    schema_version = 'meridian-live-host-acceptance.v1'
    verified_at = [DateTimeOffset]::UtcNow.ToString('o')
    host = 'WINDOWS_NORMAL_POWERSHELL'
    run_ids = @($reports | ForEach-Object { $_.run_id })
    report_paths = @($reports | ForEach-Object { $_.report_json })
    blockers = @($blockers | Select-Object -Unique)
    MERIDIAN_LIVE_ADVISORY_READY = ($blockers.Count -eq 0)
}
$python = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
$receiptJson = $receipt | ConvertTo-Json -Depth 8
$receiptJson | & $python -c 'import json,sys; from meridian.runtime import RuntimePaths; from meridian.runtime_io import atomic_write; value=json.load(sys.stdin); path=RuntimePaths.from_environment().home / "state" / "live-host-acceptance.json"; atomic_write(path,json.dumps(value,indent=2)); print(path)'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output $receiptJson
if ($blockers.Count -gt 0) { exit 3 }
exit 0
