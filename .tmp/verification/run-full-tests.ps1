$started=(Get-Date).ToUniversalTime()
& .venv\Scripts\pytest.exe -q --durations=25 *> .tmp\verification\pytest-final.out
$code=$LASTEXITCODE
$finished=(Get-Date).ToUniversalTime()
@{started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_seconds=[math]::Round(($finished-$started).TotalSeconds,3);exit_code=$code}|ConvertTo-Json|Set-Content -LiteralPath .tmp\verification\pytest-final.json -Encoding utf8
exit $code
