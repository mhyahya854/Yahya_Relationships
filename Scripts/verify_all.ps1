$ErrorActionPreference = "Continue"
Write-Host "== Python tests =="
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest "$PSScriptRoot\..\Tests\Backend" -q
Write-Host "== Synthetic family audit =="
& "$PSScriptRoot\..\.venv\Scripts\python.exe" "$PSScriptRoot\check_family_synthetic.py"
Write-Host "== Frontend typecheck + production build =="
npm --prefix "$PSScriptRoot\..\App\Frontend" run build
Write-Host "== Private Data Root =="
Write-Host "No private-root database is opened by this public verification script. Use DataRootManager's explicit health check for a selected local root."
