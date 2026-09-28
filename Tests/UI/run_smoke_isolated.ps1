$ErrorActionPreference = "Stop"

$codebaseRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$smokeRoot = Join-Path $temporaryBase ("phase10-smoke-" + [guid]::NewGuid().ToString("N"))
$service = $null
$testExit = 1

function Get-AvailableTcpPort {
  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  try {
    $listener.Start()
    return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  } finally {
    $listener.Stop()
  }
}

try {
  New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null
  $backendPort = Get-AvailableTcpPort
  $frontendPort = Get-AvailableTcpPort
  $apiOrigin = "http://127.0.0.1:$backendPort"
  $webOrigin = "http://localhost:$frontendPort"
  $python = Join-Path $codebaseRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $python)) {
    throw "Expected project Python environment was not found: $python"
  }
  $previousPythonPath = $env:PYTHONPATH
  $env:PYTHONPATH = @(
    (Join-Path $codebaseRoot "App"),
    (Join-Path $codebaseRoot "Scripts"),
    $codebaseRoot,
    $previousPythonPath
  ) | Where-Object { $_ } | Join-String -Separator ";"
  & $python -c "from pathlib import Path; from Tests.synthetic_mosaic import build; import sys; build(Path(sys.argv[1]), include_backup=True)" $smokeRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Could not build the isolated synthetic smoke Data Root."
  }

  $env:PEOPLE_RELATIONSHIPS_ROOT = $smokeRoot
  $env:PR_BACKEND_PORT = "$backendPort"
  $env:PR_FRONTEND_PORT = "$frontendPort"
  $env:VITE_BACKEND_URL = $apiOrigin
  $stdout = Join-Path $smokeRoot "service.log"
  $stderr = Join-Path $smokeRoot "service.err.log"
  $service = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
    -WorkingDirectory $codebaseRoot -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

  $ready = $false
  for ($attempt = 0; $attempt -lt 120; $attempt += 1) {
    try {
      $health = Invoke-RestMethod -Uri "$apiOrigin/api/health" -TimeoutSec 1
      $web = Invoke-WebRequest -Uri $webOrigin -TimeoutSec 1 -UseBasicParsing
      if ($health.service_ok -and $web.StatusCode -eq 200) {
        $ready = $true
        break
      }
    } catch {}
    Start-Sleep -Milliseconds 250
  }
  if (-not $ready) {
    if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout }
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr }
    throw "Isolated smoke services did not become ready. See $stdout and $stderr."
  }

  & npm.cmd run test:ui:smoke
  $testExit = $LASTEXITCODE
} finally {
  if ($service -and $service.Id) {
    & taskkill.exe /PID $service.Id /T /F 2>$null | Out-Null
  }
  Start-Sleep -Milliseconds 800

  $resolvedSmoke = [IO.Path]::GetFullPath($smokeRoot)
  if (-not $resolvedSmoke.StartsWith($temporaryBase, [StringComparison]::OrdinalIgnoreCase) -or
      -not (Split-Path -Leaf $resolvedSmoke).StartsWith("phase10-smoke-")) {
    throw "Refusing cleanup outside verified smoke root: $resolvedSmoke"
  }
  for ($attempt = 1; $attempt -le 6; $attempt += 1) {
    try {
      Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
      break
    } catch {
      if ($attempt -eq 6) { throw }
      Start-Sleep -Milliseconds ($attempt * 200)
    }
  }
}

exit $testExit
