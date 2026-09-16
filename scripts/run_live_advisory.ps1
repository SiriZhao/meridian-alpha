[CmdletBinding()]
param(
    [string]$Account = 'Schwab-Paper',
    [string]$Snapshot,
    [string]$RuntimeHome,
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
$arguments = @('-m','meridian','live-advisory','--account',$Account,'--role-timeout',"$RoleTimeout",'--json')
if ($Snapshot) { $arguments += @('--snapshot',$Snapshot) }
if ($ReasoningEffort) { $arguments += @('--reasoning-effort',$ReasoningEffort) }
Push-Location $root
try {
    & $python @arguments
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
