[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MeridianArgs
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $nextAction = 'Install Python 3.12 and run uv sync --inexact --group dev in the project directory.'
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
if (-not $MeridianArgs) { $MeridianArgs = @('doctor') }
& $python -m meridian @MeridianArgs
exit $LASTEXITCODE
