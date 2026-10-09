[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MeridianArgs
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $nextAction = '安装 Python 3.12，在当前 checkout 执行 uv sync --frozen --group dev。'
    if ($MeridianArgs -contains '--json') {
        [pscustomobject]@{
            run_id = 'failed-' + [guid]::NewGuid().ToString('N')
            status = 'FAILED'
            runtime_status = 'FAILED'
            error_code = 'MERIDIAN_PYTHON_MISSING'
            path = $python
            next_actions = @($nextAction)
            output_files = @{}
        } | ConvertTo-Json -Compress
    } else {
        Write-Host ('MERIDIAN_PYTHON_MISSING: ' + $nextAction)
    }
    exit 3
}
$env:PYTHONUTF8 = '1'
$configuredHome = [Environment]::GetEnvironmentVariable('MERIDIAN_HOME', 'User')
if (-not $env:MERIDIAN_HOME -and $configuredHome) { $env:MERIDIAN_HOME = $configuredHome }
$configuredCache = [Environment]::GetEnvironmentVariable('MERIDIAN_CACHE', 'User')
if (-not $env:MERIDIAN_CACHE -and $configuredCache) {
    $env:MERIDIAN_CACHE = $configuredCache
}
if (-not $MeridianArgs) { $MeridianArgs = @('doctor') }
$identityJson = & $python -m meridian.launch_identity --expected-root $root
if ($LASTEXITCODE -ne 0) { $identityJson; exit 3 }
if ($MeridianArgs[0] -eq 'preflight') { $identityJson; exit 0 }
if ($MeridianArgs -notcontains '--json') {
    $identity = $identityJson | ConvertFrom-Json
    Write-Host ('[BOOT] SHA=' + $identity.environment.code_sha + ' Python=' + $python)
    Write-Host ('[POLICY] ' + $identity.environment.policy_directory + ' Model=' + $identity.model.name)
}
& $python -m meridian @MeridianArgs
exit $LASTEXITCODE
