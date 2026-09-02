[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MeridianArgs
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }

if ($MeridianArgs.Length -gt 0 -and $MeridianArgs[0] -eq 'data-status') {
    & $python -m meridian.operational_cli @($MeridianArgs | Select-Object -Skip 1)
    exit $LASTEXITCODE
}
if ($MeridianArgs.Length -gt 0 -and $MeridianArgs[0] -in @('snapshot', 'daily')) {
    & $python -m meridian.daily_cli @MeridianArgs
    exit $LASTEXITCODE
}

& $python -m meridian.runtime_diagnostics doctor --json
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Meridian preflight failed. Resolve the sanitized doctor report before running a stateful command.'
    exit $LASTEXITCODE
}
& $python -c 'from meridian.cli import main; main()' @MeridianArgs
exit $LASTEXITCODE
