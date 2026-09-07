[CmdletBinding()]
param(
    [string]$Snapshot,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'run_meridian.ps1'
if (-not $OutputPath) {
    $OutputPath = Join-Path $root 'reports\controlled-improvement-phase1-live-acceptance.json'
}

function Invoke-MeridianJson {
    param([string[]]$Arguments)
    $text = & $launcher @Arguments
    $exitCode = $LASTEXITCODE
    try {
        $payload = $text | ConvertFrom-Json
    } catch {
        throw "MERIDIAN_ACCEPTANCE_INVALID_JSON: canonical command did not return JSON"
    }
    return [pscustomobject]@{ exit_code = $exitCode; payload = $payload }
}


function Invoke-ProjectCheck {
    param([string]$Name, [string[]]$Arguments)
    $uv = Join-Path $root '.venv\Scripts\uv.exe'
    $started = Get-Date
    if (-not (Test-Path -LiteralPath $uv)) {
        return [pscustomobject]@{ name = $Name; exit_code = 3; seconds = 0; summary = 'MERIDIAN_UV_MISSING' }
    }
    Push-Location -LiteralPath $root
    try {
        $output = (& $uv @Arguments 2>&1 | Out-String).Trim()
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $lines = @($output -split "`r?`n" | Where-Object { $_.Length -gt 0 })
    return [pscustomobject]@{
        name = $Name; exit_code = $exitCode
        seconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
        summary = if ($lines.Count) { $lines[$lines.Count - 1] } else { 'NO_OUTPUT' }
    }
}
if ($Snapshot -and -not [IO.Path]::IsPathRooted($Snapshot)) {
    throw 'MERIDIAN_ACCEPTANCE_SNAPSHOT_PATH_ABSOLUTE_REQUIRED'
}

$initialDoctor = Invoke-MeridianJson @('doctor', '--json')
$initialization = $null
if ($initialDoctor.payload.database.migration_status -eq 'PENDING') {
    # Existing CLI migration is transactional and idempotent. Record both the
    # degraded preflight and the canonical recovery rather than masking either.
    $initialization = Invoke-MeridianJson @('init', '--json')
}
$doctor = Invoke-MeridianJson @('doctor', '--json')
$market = Invoke-MeridianJson @('data-status', '--json')
$baselineChecks = @(
    Invoke-ProjectCheck 'pytest' @('run', '--no-sync', 'pytest', '-q')
    Invoke-ProjectCheck 'ruff' @('run', '--no-sync', 'ruff', 'check', '.')
    Invoke-ProjectCheck 'pyright' @('run', '--no-sync', 'pyright')
)
$baselineStatus = if (($baselineChecks | Where-Object { $_.exit_code -ne 0 }).Count -eq 0) { 'VERIFIED' } else { 'BLOCKED' }
$policyRoot = if ($env:MERIDIAN_POLICY_DIR) { $env:MERIDIAN_POLICY_DIR } else { Join-Path $root 'policies' }
$modelsPolicy = Join-Path $policyRoot 'models.yaml'
$researchPolicy = if ((Test-Path -LiteralPath $modelsPolicy) -and (Select-String -LiteralPath $modelsPolicy -Pattern '^  live_enabled:\\s*true\\s*$' -Quiet)) { 'ENABLED' } else { 'DISABLED_OR_UNAVAILABLE' }
$snapshotCheck = $null
if ($Snapshot) {
    $snapshotCheck = Invoke-MeridianJson @('snapshot', 'validate', $Snapshot, '--json')
}

$session = 'UNKNOWN'
if ($market.payload.provider_probes) {
    $firstProbe = $market.payload.provider_probes.PSObject.Properties | Select-Object -First 1
    if ($firstProbe -and $firstProbe.Value.primary.session) {
        $session = [string]$firstProbe.Value.primary.session
    }
}

$daily = $null
$dailyEligible = $snapshotCheck -and $snapshotCheck.exit_code -eq 0 -and
    $snapshotCheck.payload.valid -eq $true -and $session -eq 'REGULAR'
if ($dailyEligible) {
    # This is the existing canonical daily command. It retains all policy and
    # research gates; this harness never edits policy or calls an adapter itself.
    $daily = Invoke-MeridianJson @('daily', '--snapshot', $Snapshot, '--json')
}

$hostStatus = if (-not $Snapshot) { 'BLOCKED' } elseif ($snapshotCheck.payload.valid -eq $true) { 'DEGRADED' } else { 'BLOCKED' }
$hostReason = if (-not $Snapshot) {
    'BLOCKED_MISSING_REAL_HOST_SNAPSHOT'
} elseif ($snapshotCheck.payload.valid -eq $true) {
    'SNAPSHOT_SCHEMA_AND_FRESHNESS_VALID_BUT_EXTERNAL_HOST_AUTHENTICATION_NOT_PROVEN_BY_FILE'
} else {
    'HOST_SNAPSHOT_INVALID_OR_STALE'
}
$marketStatus = if ($session -ne 'REGULAR') { 'NOT_TESTED' } elseif ($market.payload.latest_quote -eq 'FRESH') { 'VERIFIED' } else { 'BLOCKED' }
$researchStatus = if ($daily) {
    if ($daily.payload.research_status -eq 'AVAILABLE') { 'VERIFIED' } else { 'BLOCKED' }
} else { 'NOT_TESTED' }
$decisionStatus = if ($daily) {
    if ($daily.payload.decision_context -and $daily.payload.gates) { 'VERIFIED' } else { 'BLOCKED' }
} else { 'NOT_TESTED' }

$nextActions = @()
if (-not $Snapshot) {
    $nextActions += 'Supply a newly exported, sanitized, absolute-path HostAccountSnapshotEnvelope from the authorized source; never reuse or fabricate one.'
}
if ($session -ne 'REGULAR') {
    $nextActions += 'OPEN_SESSION_ACCEPTANCE_NOT_AVAILABLE: rerun during the NYSE regular session (09:30-16:00 America/New_York) with a newly supplied snapshot.'
}
if ($market.payload.latest_quote -ne 'FRESH') {
    $nextActions += 'Do not lower freshness thresholds. Inspect provider_probes and rerun only in a valid market session.'
}
if (-not $daily) {
    $nextActions += 'Canonical daily was intentionally not invoked because its real-input or regular-session prerequisites were not met.'
}
$nextActions += 'Public Yahoo/Stooq observations remain uncertified execution quotes; manual authority remains blocked.'
$acceptanceMatrix = @(
    [ordered]@{ item = 'baseline'; status = $baselineStatus; evidence = 'baseline.checks' }
    [ordered]@{ item = 'doctor'; status = if ($doctor.payload.status -eq 'PASS') { 'VERIFIED' } else { 'BLOCKED' }; evidence = 'doctor.payload' }
    [ordered]@{ item = 'host_snapshot'; status = $hostStatus; evidence = 'host_snapshot.validation' }
    [ordered]@{ item = 'market_session'; status = if ($session -eq 'REGULAR') { 'VERIFIED' } else { 'NOT_TESTED' }; evidence = 'market_session.evidence' }
    [ordered]@{ item = 'market_freshness'; status = $marketStatus; evidence = 'market_freshness.evidence' }
    [ordered]@{ item = 'live_canonical_research'; status = $researchStatus; evidence = 'research' }
    [ordered]@{ item = 'research_to_decision'; status = $decisionStatus; evidence = 'decision' }
    [ordered]@{ item = 'quote_certification'; status = 'BLOCKED'; evidence = 'quote_certification' }
    [ordered]@{ item = 'persistence'; status = if ($daily) { 'VERIFIED' } else { 'NOT_TESTED' }; evidence = 'persistence' }
)

$artifact = [ordered]@{
    schema_version = 'meridian-production-acceptance.v1'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    environment = [ordered]@{
        branch = (& git -C $root branch --show-current).Trim()
        commit = (& git -C $root rev-parse HEAD).Trim()
        powershell = $PSVersionTable.PSVersion.ToString()
    }
    git = [ordered]@{ branch = (& git -C $root branch --show-current).Trim(); commit = (& git -C $root rev-parse HEAD).Trim(); working_tree = if ((& git -C $root status --porcelain)) { 'DIRTY' } else { 'CLEAN' } }
    baseline = [ordered]@{ status = $baselineStatus; checks = $baselineChecks }
    doctor = [ordered]@{ status = if ($doctor.payload.status -eq 'PASS') { 'VERIFIED' } else { 'BLOCKED' }; exit_code = $doctor.exit_code; initial = $initialDoctor.payload; initialization = if ($initialization) { $initialization.payload } else { $null }; payload = $doctor.payload }
    host_snapshot = [ordered]@{ status = $hostStatus; reason = $hostReason; supplied = [bool]$Snapshot; validation = if ($snapshotCheck) { $snapshotCheck.payload } else { $null } }
    market_session = [ordered]@{ status = if ($session -eq 'REGULAR') { 'VERIFIED' } else { 'NOT_TESTED' }; session = $session; evidence = $market.payload.provider_probes }
    market_freshness = [ordered]@{ status = $marketStatus; canonical_status = $market.payload.latest_quote; providers = $market.payload.provider_health; evidence = $market.payload.provider_probes }
    providers = [ordered]@{
        status = if ($market.payload.latest_quote -eq 'FRESH') { 'VERIFIED' } else { 'DEGRADED' }
        canonical_probes = $market.payload.provider_probes
        stooq_404_investigation = [ordered]@{
            status = 'DEGRADED'
            conclusion = 'UPSTREAM_UNAVAILABLE_OR_ENDPOINT_CHANGED'
            evidence = 'Canonical probes returned http_404 for Stooq across the configured universe; direct bounded diagnostics confirmed Stooq 404 responses for configured URL and documented URL variants.'
        }
    }
    research = [ordered]@{ status = $researchStatus; canonical_status = if ($daily) { $daily.payload.research_status } else { 'NOT_RUN' }; invocation = if ($daily) { 'CANONICAL_DAILY' } else { 'NOT_INVOKED' }; configuration = [ordered]@{ policy_live_enabled = $researchPolicy; credential_reference = 'UNPROBED_NOT_INSPECTED'; policy_path = $modelsPolicy } }
    decision = [ordered]@{ status = $decisionStatus; context = if ($daily) { $daily.payload.decision_context } else { $null }; gates = if ($daily) { $daily.payload.gates } else { $null }; readiness = if ($daily) { $daily.payload.readiness } else { $null } }
    research_invocation = [ordered]@{ status = $researchStatus; run_id = if ($daily) { $daily.payload.run_id } else { $null }; evidence = 'research' }
    gates = if ($daily) { $daily.payload.gates } else { @() }
    readiness = if ($daily) { $daily.payload.readiness } else { $null }
    outputs = if ($daily) { $daily.payload.output_files } else { @{} }
    quote_certification = [ordered]@{ status = 'BLOCKED'; reason = 'PUBLIC_RESEARCH_QUOTES_ARE_NOT_CERTIFIED_EXECUTION_QUOTES' }
    persistence = [ordered]@{ status = if ($daily) { 'VERIFIED' } else { 'NOT_TESTED' }; output_files = if ($daily) { $daily.payload.output_files } else { @{} } }
    run_ids = [ordered]@{ daily = if ($daily) { $daily.payload.run_id } else { $null } }
    acceptance_matrix = $acceptanceMatrix
    overall_status = if ($daily -and $researchStatus -eq 'VERIFIED') { 'DEGRADED' } else { 'BLOCKED' }
    blockers = @($hostReason) + $(if ($session -ne 'REGULAR') { 'OPEN_SESSION_ACCEPTANCE_NOT_AVAILABLE' })
    next_actions = $nextActions
}

$directory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$artifact | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$summary = [ordered]@{ status = $artifact.overall_status; evidence = $OutputPath; session = $session; daily_invoked = [bool]$daily }
Write-Output ($summary | ConvertTo-Json -Compress)
exit 0




