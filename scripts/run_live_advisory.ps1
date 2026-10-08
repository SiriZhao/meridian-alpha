[CmdletBinding()]
param(
    [string]$Account = 'Schwab-Paper',
    [string]$Snapshot,
    [string]$RuntimeHome,
    [switch]$Readiness,
    [ValidateRange(15,120)][int]$RoleTimeout = 90,
    [ValidateSet('low','medium','high')][string]$ReasoningEffort
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { Write-Error 'Run scripts/bootstrap_windows.ps1 first.'; exit 3 }
$env:PYTHONUTF8 = '1'
if ($RuntimeHome) { $env:MERIDIAN_HOME = $RuntimeHome }
if (-not $env:MERIDIAN_HOME) {
    $env:MERIDIAN_HOME = [Environment]::GetEnvironmentVariable('MERIDIAN_HOME','User')
}
if (-not $env:MERIDIAN_HOME) { $env:MERIDIAN_HOME = Join-Path $env:LOCALAPPDATA 'MeridianAlpha' }
$configuredCache = [Environment]::GetEnvironmentVariable('MERIDIAN_CACHE','User')
if (-not $env:MERIDIAN_CACHE -and $configuredCache) { $env:MERIDIAN_CACHE = $configuredCache }
Write-Output ('[BOOT] Python=' + $python)
Write-Output ('[RUNTIME] MERIDIAN_HOME=' + $env:MERIDIAN_HOME)
$entryPoint = if ($Readiness) { 'live-readiness' } else { 'live-advisory' }
$arguments = @('-m','meridian',$entryPoint,'--account',$Account,'--role-timeout',"$RoleTimeout",'--json')
if ($Snapshot) { $arguments += @('--snapshot',$Snapshot) }
if ($ReasoningEffort) { $arguments += @('--reasoning-effort',$ReasoningEffort) }
Push-Location $root
try {
    & $python -c "from pathlib import Path; import meridian,sys; from meridian.live_quant_bridge import LiveQuantSnapshot; from meridian.runtime import policy_directory; expected=Path(sys.argv[1]).resolve(); assert Path(meridian.__file__).resolve().is_relative_to(expected/'src'), 'WRONG_PACKAGE_ORIGIN'; print('[BOOT] import='+str(meridian.__file__)); print('[POLICY] '+str(policy_directory()))" $root
    if ($LASTEXITCODE -ne 0) { throw 'Checkout/import mismatch or Mission 2 bridge unavailable. Use the documented Mission 2 worktree and its frozen environment.' }
    & $python @arguments
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
