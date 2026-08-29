param(
    [string]$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$OutputPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "artifacts\meridian-alpha-review.zip"),
    [string]$ManifestPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "artifacts\meridian-alpha-review-manifest.txt")
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $SourceRoot).Path
$output = [IO.Path]::GetFullPath($OutputPath)
$manifestOutput = [IO.Path]::GetFullPath($ManifestPath)
$secretName = [regex]::new('^(\.env|\.env\..+)$', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
$excludedDirectories = @('.git', '.venv', 'vendor_cache', 'artifacts', 'secrets', 'credentials', 'var', '.pytest_cache', '.ruff_cache', '.pyright', '.pytest_tmp', '__pycache__', 'logs', 'cache')
$excludedExtensions = @('.db', '.sqlite', '.sqlite3', '.key', '.pem', '.p12', '.pfx')
$suspiciousName = [regex]::new('(?i)(secret|credential|password|token|api[-_]?key)')
$staging = Join-Path ([IO.Path]::GetTempPath()) ("meridian-review-" + [guid]::NewGuid().ToString("N"))

function Test-ExcludedPath([IO.FileInfo]$File) {
    $relative = $File.FullName.Substring($root.Length).TrimStart([char[]]('\\/'))
    $parts = $relative -split '[\\/]'
    if ($secretName.IsMatch($File.Name)) { return $true }
    if ($suspiciousName.IsMatch($File.Name)) { return $true }
    if ($parts | Where-Object { $excludedDirectories -contains $_ -or $_ -like '*pycache*' }) { return $true }
    if ($excludedExtensions -contains $File.Extension.ToLowerInvariant()) { return $true }
    if ([IO.Path]::GetFullPath($File.FullName) -eq $output) { return $true }
    if ([IO.Path]::GetFullPath($File.FullName) -eq $manifestOutput) { return $true }
    return $false
}

try {
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $files = Get-ChildItem -LiteralPath $root -Recurse -File -Force |
        Where-Object { -not (Test-ExcludedPath $_) }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($root.Length).TrimStart([char[]]('\\/'))
        $destination = Join-Path $staging $relative
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }
    $manifestPath = Join-Path $staging "REVIEW-MANIFEST.txt"
    $manifest = @(
        "Meridian Alpha safe source-review manifest",
        "Generated before ZIP creation; excluded files are not listed.",
        ""
    ) + @(
        $files |
            ForEach-Object {
                $_.FullName.Substring($root.Length).TrimStart([char[]]('\\/'))
            } |
            Sort-Object
    )
    $manifest | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    $packagedSecret = Get-ChildItem -LiteralPath $staging -Recurse -File -Force |
        Where-Object { $secretName.IsMatch($_.Name) -or $suspiciousName.IsMatch($_.Name) -or $excludedExtensions -contains $_.Extension.ToLowerInvariant() }
    if ($packagedSecret) { throw "Refusing to package a suspicious secret filename or credential material." }
    $parentOutput = Split-Path -Parent $output
    New-Item -ItemType Directory -Path $parentOutput -Force | Out-Null
    $parentManifest = Split-Path -Parent $manifestOutput
    New-Item -ItemType Directory -Path $parentManifest -Force | Out-Null
    $manifest | Set-Content -LiteralPath $manifestOutput -Encoding UTF8
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $output -CompressionLevel Optimal
    Write-Output "Created review archive: $output"
}
finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
