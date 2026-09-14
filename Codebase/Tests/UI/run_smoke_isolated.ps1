$ErrorActionPreference = "Stop"

$codebaseRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$repositoryRoot = (Resolve-Path (Join-Path $codebaseRoot "..")).Path
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$smokeRoot = Join-Path $temporaryBase ("phase10-smoke-" + [guid]::NewGuid().ToString("N"))
$service = $null
$testExit = 1

function Stop-IsolatedServices {
  $listenerPids = @(
    Get-NetTCPConnection -State Listen -LocalPort 1420, 8765 -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
  foreach ($listenerPid in $listenerPids) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerPid"
    if ($process.CommandLine -match "vite|app.backend.main") {
      Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
    }
  }
}

try {
  New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $repositoryRoot "Database") -Destination $smokeRoot -Recurse
  Copy-Item -LiteralPath (Join-Path $repositoryRoot "Backups") -Destination $smokeRoot -Recurse

  $env:PEOPLE_RELATIONSHIPS_ROOT = $smokeRoot
  $stdout = Join-Path $smokeRoot "service.log"
  $stderr = Join-Path $smokeRoot "service.err.log"
  $service = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
    -WorkingDirectory $codebaseRoot -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

  $ready = $false
  for ($attempt = 0; $attempt -lt 120; $attempt += 1) {
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 1
      $web = Invoke-WebRequest -Uri "http://localhost:1420" -TimeoutSec 1 -UseBasicParsing
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
  Stop-IsolatedServices
  if ($service -and -not $service.HasExited) {
    Stop-Process -Id $service.Id -Force -ErrorAction SilentlyContinue
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
