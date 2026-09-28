param(
  [int]$Port = 8765
)
$env:PYTHONUTF8 = "1"
$env:PR_BACKEND_PORT = "$Port"
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m app.backend.main
