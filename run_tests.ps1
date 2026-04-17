Set-Location "D:\tmp\ei-fragment-calculator"
$out = & "C:\Python\Python311\python.exe" -m pytest tests -x -q --tb=short 2>&1
$out | Out-File "D:\tmp\ei-fragment-calculator\pytest_result.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
