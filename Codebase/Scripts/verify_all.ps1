$ErrorActionPreference = "Continue"
Write-Host "== Python tests =="
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest "$PSScriptRoot\..\Tests\Backend" -q
Write-Host "== Legacy builder audit =="
& "$PSScriptRoot\..\.venv\Scripts\python.exe" "$PSScriptRoot\build_family.py" --check
Write-Host "== Frontend typecheck + production build =="
npm --prefix "$PSScriptRoot\..\App\Frontend" run build
Write-Host "== SQLite integrity =="
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -c "import sqlite3; con=sqlite3.connect(r'$PSScriptRoot\..\..\Database\Main\family.db'); print('integrity:', con.execute('PRAGMA integrity_check').fetchone()[0]); con.close()"
