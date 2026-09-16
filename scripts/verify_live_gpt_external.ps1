[CmdletBinding()]
param(
    [string]$MarketFixturePath,
    [string]$MarketFixturePath2
)

$ErrorActionPreference = 'Stop'
Write-Output 'MERIDIAN EXTERNAL LIVE GPT ACCEPTANCE'

function Get-Ancestry {
    param([int]$ProcessId)
    $rows = @()
    $current = $ProcessId
    for ($index = 0; $index -lt 8 -and $current; $index++) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $current" -ErrorAction SilentlyContinue
        if (-not $process) { break }
        $name = [IO.Path]::GetFileName([string]$process.Name)
        $rows += [ordered]@{
            pid = [int]$process.ProcessId
            parent_pid = [int]$process.ParentProcessId
            executable_basename = $name
            process_role = if ($index -eq 0) { 'acceptance_shell' } elseif ($name -match '(?i)codex|chatgpt') { 'codex_ancestor' } elseif ($name -match '(?i)python|pytest') { 'meridian_ancestor' } else { 'parent_ancestor' }
        }
        $current = [int]$process.ParentProcessId
    }
    return $rows
}

$ancestry = @(Get-Ancestry $PID)
if (@($ancestry | Where-Object { $_.process_role -eq 'codex_ancestor' }).Count -gt 0) {
    Write-Output 'EXTERNAL_HOST_INVALID: RUN_FROM_NORMAL_POWERSHELL'
    exit 2
}

function Quote-ProcessArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Get-FailureCategory {
    param([string]$Stdout, [string]$Stderr)
    $message = (($Stdout + "`n" + $Stderr).ToLowerInvariant())
    $auth = @('not logged in','not authenticated','authentication failed','authorization failed','sign in to','please log in','please login','login required','unauthorized','invalid api key','credential is invalid') | Where-Object { $message.Contains($_) }
    $rate = @('rate limit','too many requests',' 429','[429]') | Where-Object { $message.Contains($_) }
    $model = @('model not found','unknown model','unsupported model','model unavailable') | Where-Object { $message.Contains($_) }
    $sandbox = @('sandbox','permission denied','not permitted') | Where-Object { $message.Contains($_) }
    if ($rate) { return 'RATE_LIMITED' }
    if ($auth) { return 'AUTH_ERROR' }
    if ($model) { return 'MODEL_ERROR' }
    if ($sandbox) { return 'SANDBOX' }
    if ($message.Trim().Length -gt 0) { return 'UNCLASSIFIED_PROCESS_ERROR' }
    return 'EMPTY_PROCESS_ERROR'
}

function Invoke-BoundedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds,
        [string]$WorkingDirectory
    )
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FilePath
    $info.Arguments = (($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join ' ')
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $started = [Diagnostics.Stopwatch]::StartNew()
    try {
        $null = $process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            try { & taskkill.exe /PID $process.Id /T /F *> $null } catch { try { $process.Kill() } catch {} }
            $process.WaitForExit(3000)
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $started.Stop()
        $exitCode = if ($completed) { $process.ExitCode } else { $null }
        [pscustomobject]@{
            completed = $completed
            exit_code = $exitCode
            duration_ms = [int]$started.Elapsed.TotalMilliseconds
            stdout = $stdout
            stderr = $stderr
            failure_category = if ($completed -and $exitCode -eq 0) { $null } else { Get-FailureCategory $stdout $stderr }
        }
    } finally {
        $process.Dispose()
    }
}

function Get-CleanResult {
    param($Raw, [string]$StatusOnSuccess)
    $valid = $false
    if ($Raw.completed -and $Raw.exit_code -eq 0) {
        try { $null = $Raw.stdout | ConvertFrom-Json -ErrorAction Stop; $valid = $true } catch { $valid = $false }
    }
    [ordered]@{
        status = if ($valid) { $StatusOnSuccess } else { 'FAILURE' }
        exit_code = $Raw.exit_code
        duration_ms = $Raw.duration_ms
        output_valid = $valid
        failure_category = $Raw.failure_category
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'PROJECT_VENV_NOT_FOUND' }
$codexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue
if (-not $codexCommand) { $codexCommand = Get-Command codex -ErrorAction SilentlyContinue }
if (-not $codexCommand) { throw 'CODEX_CLI_NOT_FOUND' }
$codex = $codexCommand.Source
$versionRaw = Invoke-BoundedProcess $codex @('--version') 10 $repoRoot
$version = ($versionRaw.stdout | Select-Object -First 1).Trim()
$envSnapshot = [ordered]@{}
foreach ($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','CODEX_HOME')) { $envSnapshot[($key.ToLowerInvariant() + '_present')] = [bool](Get-Item "Env:$key" -ErrorAction SilentlyContinue) }

$directRoot = Join-Path ([IO.Path]::GetTempPath()) ('meridian-direct-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directRoot | Out-Null
try {
    $schemaPath = Join-Path $directRoot 'schema.json'
    $outputPath = Join-Path $directRoot 'output.json'
    Set-Content -LiteralPath $schemaPath -Encoding UTF8 -Value '{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":false}'
    $directArgs = @('exec','--ephemeral','--ignore-user-config','--ignore-rules','--sandbox','read-only','--skip-git-repo-check','--output-schema',$schemaPath,'--output-last-message',$outputPath,'--color','never','Return exactly {"ok":true}.')
    $directRaw = Invoke-BoundedProcess $codex $directArgs 20 $repoRoot
    $directValid = $false
    if ($directRaw.completed -and $directRaw.exit_code -eq 0 -and (Test-Path -LiteralPath $outputPath)) { try { $directJson = Get-Content -Raw $outputPath | ConvertFrom-Json -ErrorAction Stop; $directValid = ($directJson.ok -eq $true) } catch {} }
    $directResult = [ordered]@{ status = if ($directValid) { 'DIRECT_MODEL_SUCCESS' } elseif ($directRaw.failure_category -eq 'SANDBOX') { 'DIRECT_MODEL_SANDBOX_BLOCKED' } elseif ($directRaw.failure_category -eq 'AUTH_ERROR') { 'DIRECT_MODEL_AUTH_ERROR' } elseif ($directRaw.failure_category -eq 'RATE_LIMITED') { 'DIRECT_MODEL_RATE_LIMITED' } else { 'DIRECT_MODEL_OTHER_FAILURE' }; exit_code = $directRaw.exit_code; duration_ms = $directRaw.duration_ms; output_valid = $directValid; failure_category = $directRaw.failure_category }
} finally { Remove-Item -LiteralPath $directRoot -Recurse -Force -ErrorAction SilentlyContinue }

$matrix = [ordered]@{ A = 'DIRECT_MODEL_SANDBOX_BLOCKED'; B = $directResult.status; C = 'SANDBOX_BLOCKED'; D = 'NOT_RUN' }
$artifactRoot = Join-Path $repoRoot ('.tmp\external-acceptance\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
$artifactPath = Join-Path $artifactRoot 'external_live_acceptance.json'
$artifact = [ordered]@{
    schema_version = 'meridian-external-live-acceptance.v1'
    host_context = 'NORMAL_POWERSHELL'
    ancestry = $ancestry
    environment = $envSnapshot
    checkout = $repoRoot
    codex = [ordered]@{ executable = $codex; version = $version }
    runtime_matrix = $matrix
    direct_codex = $directResult
    role_results = [ordered]@{}
    full_chain_run_1 = $null
    full_chain_run_2 = $null
    quality = $null
    latency = $null
    safety = [ordered]@{ shadow_only = $true; orders_created = 0; orders_executed = 0; execution_authority = 'NONE' }
    decision = $null
}
if ($directResult.status -ne 'DIRECT_MODEL_SUCCESS') {
    $artifact.decision = 'P1_STAGE2_EXTERNAL_CODEX_BLOCKED'
    $artifact | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $artifactPath -Encoding UTF8
    Write-Output ('RESULT FILE: ' + $artifactPath)
    Write-Output ('DECISION: ' + $artifact.decision)
    exit 1
}

$roles = @('PRIMARY_ANALYST','SKEPTIC','SCENARIO_ANALYST','DECISION_SYNTHESIZER')
foreach ($role in $roles) {
    $roleRaw = Invoke-BoundedProcess $python @((Join-Path $repoRoot 'scripts\verify_live_gpt_role.py'), $role) 60 $repoRoot
    $roleJson = $null
    if ($roleRaw.completed -and $roleRaw.stdout.Trim()) { try { $roleJson = $roleRaw.stdout | ConvertFrom-Json -ErrorAction Stop } catch {} }
    if ($roleJson) { $artifact.role_results[$role] = $roleJson } else { $artifact.role_results[$role] = [ordered]@{ status = 'FAILURE'; duration_ms = $roleRaw.duration_ms; failure_category = $roleRaw.failure_category; schema_valid = $false; evidence_ids_valid = $false } }
    if (-not $roleJson -or $roleJson.status -ne 'SUCCESS' -or -not $roleJson.schema_valid -or -not $roleJson.evidence_ids_valid) {
        $matrix.D = 'OTHER_FAILURE'
        $artifact.decision = 'P1_STAGE2_RUNTIME_BLOCKED'
        $artifact | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $artifactPath -Encoding UTF8
        Write-Output ('RESULT FILE: ' + $artifactPath)
        Write-Output ('DECISION: ' + $artifact.decision)
        exit 1
    }
}
$matrix.D = 'SUCCESS'

if (-not $MarketFixturePath) { throw 'MARKET_FIXTURE_PATH_REQUIRED_FOR_FULL_CHAIN' }
$fixture1 = (Resolve-Path $MarketFixturePath).Path
$fixture2 = if ($MarketFixturePath2) { (Resolve-Path $MarketFixturePath2).Path } else { $fixture1 }
function Invoke-ShadowRecord {
    param([string]$Fixture)
    $raw = Invoke-BoundedProcess $python @('-m','meridian','shadow-run','--market-fixture',$Fixture,'--json') 180 $repoRoot
    if (-not $raw.completed -or $raw.exit_code -ne 0) { return [ordered]@{ status = 'FAILURE'; duration_ms = $raw.duration_ms; failure_category = $raw.failure_category } }
    try { $record = $raw.stdout | ConvertFrom-Json -ErrorAction Stop } catch { return [ordered]@{ status = 'FAILURE'; duration_ms = $raw.duration_ms; failure_category = 'INVALID_JSON' } }
    $stages = [ordered]@{}
    foreach ($name in @('PRIMARY_ANALYST','SKEPTIC','SCENARIO_ANALYSIS','DECISION_SYNTHESIS')) { $stage = $record.stages.$name; $stages[$name] = [ordered]@{ status = $stage.status; schema_valid = $stage.schema_valid; duration_ms = $stage.duration_ms; attempt_count = $stage.attempt_count; failure_category = $stage.error_type } }
    [ordered]@{ status = if (($stages.Values.status | Where-Object { $_ -ne 'SUCCESS' }).Count -eq 0) { 'FULL_CHAIN_SUCCESS' } else { 'FULL_CHAIN_FAILURE' }; run_id = $record.run_id; stages = $stages; quality_metrics = $record.quality_metrics; system_confidence = $record.system_confidence; gpt_shadow_confidence = $record.gpt_shadow_confidence; confidence_breakdown = $record.confidence_breakdown; latency_ms = $record.latency_ms; orders_created = $record.orders_created; orders_executed = $record.orders_executed; execution_authority = $record.shadow_decision_authority }
}
$artifact.full_chain_run_1 = Invoke-ShadowRecord $fixture1
if ($artifact.full_chain_run_1.status -ne 'FULL_CHAIN_SUCCESS') { $artifact.decision = 'P1_STAGE2_MODEL_CHAIN_BLOCKED' } else {
    $artifact.full_chain_run_2 = Invoke-ShadowRecord $fixture2
    if ($artifact.full_chain_run_2.status -ne 'FULL_CHAIN_SUCCESS') { $artifact.decision = 'P1_STAGE2_MODEL_CHAIN_BLOCKED' } else {
        $artifact.quality = [ordered]@{ run_1 = $artifact.full_chain_run_1.quality_metrics; run_2 = $artifact.full_chain_run_2.quality_metrics }
        $artifact.latency = [ordered]@{ run_1_ms = $artifact.full_chain_run_1.latency_ms; run_2_ms = $artifact.full_chain_run_2.latency_ms }
        if (($artifact.full_chain_run_1.orders_created -ne 0) -or ($artifact.full_chain_run_1.orders_executed -ne 0) -or ($artifact.full_chain_run_2.orders_created -ne 0) -or ($artifact.full_chain_run_2.orders_executed -ne 0)) { $artifact.decision = 'P1_STAGE2_SAFETY_VIOLATION' } else { $artifact.decision = 'P1_STAGE2_PASS' }
    }
}
$artifact | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $artifactPath -Encoding UTF8
Write-Output ('RESULT FILE: ' + $artifactPath)
Write-Output ('DECISION: ' + $artifact.decision)
if ($artifact.decision -eq 'P1_STAGE2_PASS') { exit 0 } else { exit 1 }