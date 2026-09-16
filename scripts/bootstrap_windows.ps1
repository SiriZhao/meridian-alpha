[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = '1'
Push-Location $root
try {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) { $uvExecutable = $uvCommand.Source; $uvPrefix = @() }
    else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'BOOTSTRAP_PYTHON_MISSING: install Python with pip, then rerun.' }
        & $pythonCommand.Source --version
        & $pythonCommand.Source -m uv --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            & $pythonCommand.Source -m pip install 'uv==0.12.7'
            if ($LASTEXITCODE -ne 0) { throw 'UV_INSTALL_FAILED' }
        }
        $uvExecutable = $pythonCommand.Source
        $uvPrefix = @('-m','uv')
    }
    & $uvExecutable @uvPrefix sync --locked --inexact --group dev
    if ($LASTEXITCODE -ne 0) { throw 'UV_SYNC_FAILED: install uv and Python 3.12; existing environment preserved.' }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    & $python -c 'import sys; print(sys.version); assert sys.version_info[:2] == (3,12)'
    if ($LASTEXITCODE -ne 0) { throw 'PYTHON_312_REQUIRED' }
    & $uvExecutable @uvPrefix pip check --python $python
    if ($LASTEXITCODE -ne 0) { throw 'DEPENDENCY_CHECK_FAILED' }
    & $python -m compileall -q src/meridian
    if ($LASTEXITCODE -ne 0) { throw 'COMPILE_FAILED' }
    & $python -c 'import meridian.application, meridian.live_advisory, meridian.mcp_server'
    if ($LASTEXITCODE -ne 0) { throw 'IMPORT_FAILED' }
    & (Join-Path $PSScriptRoot 'run_meridian.ps1') doctor --json
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
