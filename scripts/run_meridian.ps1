[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MeridianArgs
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'MERIDIAN_PYTHON_MISSING: Install Python 3.12 and run uv sync --group dev in the project directory.'
    exit 3
}
$env:PYTHONUTF8 = '1'
if (-not $MeridianArgs) { $MeridianArgs = @('doctor') }
& $python -m meridian @MeridianArgs
exit $LASTEXITCODE
