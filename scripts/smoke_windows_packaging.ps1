$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$fixtureRoot = Join-Path $projectRoot ('.tmp\review-smoke-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $fixtureRoot 'source'
$generated = Join-Path $source '.tmp'
New-Item -ItemType Directory -Path $generated -Force | Out-Null
Set-Content -LiteralPath (Join-Path $generated 'ignored.txt') -Value 'generated fixture' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $source 'fixture.sqlite3-wal') -Value 'synthetic sidecar' -Encoding UTF8
$output = Join-Path $fixtureRoot 'review.zip'
$manifest = Join-Path $fixtureRoot 'manifest.txt'
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($version in @('first', 'replacement')) {
    Set-Content -LiteralPath (Join-Path $source 'source.txt') -Value $version -Encoding UTF8
    & (Join-Path $PSScriptRoot 'package_review.ps1') -SourceRoot $source -OutputPath $output -ManifestPath $manifest
    $archive = [IO.Compression.ZipFile]::OpenRead($output)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($names.Count -ne 2 -or 'source.txt' -notin $names -or 'REVIEW-MANIFEST.txt' -notin $names) {
            throw 'REVIEW_ARCHIVE_CONTENT_INVALID'
        }
        $reader = [IO.StreamReader]::new($archive.GetEntry('source.txt').Open())
        try { if ($reader.ReadToEnd().Trim() -ne $version) { throw 'REVIEW_ARCHIVE_REPLACEMENT_INVALID' } }
        finally { $reader.Dispose() }
    } finally { $archive.Dispose() }
}
Write-Output 'WINDOWS_REVIEW_PACKAGING_PASS'
