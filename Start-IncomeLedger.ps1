param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$FrontendUrl = "http://localhost:5173"
$BackendHealthUrl = "http://127.0.0.1:8001/api/health"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue

function Test-LocalUrl {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Stop-PortProcess {
    param([int]$Port)
    $lines = netstat -ano | Select-String ":$Port"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }
        if ($parts.Count -gt 0) {
            $processId = $parts[-1]
            if ($processId -match '^\d+$') {
                Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

if ($Restart) {
    Stop-PortProcess -Port 8001
    Stop-PortProcess -Port 5173
    Start-Sleep -Seconds 1
}

if (-not (Test-Path $Python)) {
    if ($PythonCommand) {
        & $PythonCommand.Source -m venv $Venv
    } elseif (Test-Path $BundledPython) {
        & $BundledPython -m venv $Venv
    } else {
        throw "Python 3 was not found. Install Python 3 or run from an environment that provides python.exe."
    }
}

& $Pip install -r (Join-Path $Root "requirements.txt")

if (-not (Test-LocalUrl $BackendHealthUrl)) {
    $BackendRunner = Join-Path $Backend "run-backend.ps1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c start `"Income Ledger Backend`" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$BackendRunner`"" -WorkingDirectory $Root -WindowStyle Hidden
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    if (-not $NpmCommand) {
        throw "npm.cmd was not found. Install Node.js LTS to run the React dashboard."
    }
    Push-Location $Frontend
    & $NpmCommand.Source install
    Pop-Location
}

if (-not $NpmCommand) {
    throw "npm.cmd was not found. Install Node.js LTS to run the React dashboard."
}

if (-not (Test-LocalUrl $FrontendUrl)) {
    $FrontendRunner = Join-Path $Frontend "run-frontend.ps1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c start `"Income Ledger Frontend`" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$FrontendRunner`"" -WorkingDirectory $Root -WindowStyle Hidden
}
Start-Sleep -Seconds 3
Start-Process $FrontendUrl

Write-Host "Income Ledger is starting at $FrontendUrl"
