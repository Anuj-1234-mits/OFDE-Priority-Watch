<#
.SYNOPSIS
  Set up (first run), check, and start OFDE on Windows PowerShell. Stops at the first failure.
.DESCRIPTION
  1. Checks Python 3.10+   2. Creates .venv if missing   3. Installs requirements if they changed
  4. Runs the test suite   5. Verifies SGP4 on this machine   6. Starts the server and opens the browser.
  Uses .venv\Scripts\python.exe directly, so Activate.ps1 / execution-policy changes are not needed.
.PARAMETER SkipTests       Skip step 4 (not recommended).
.PARAMETER SkipVerify      Skip step 5.
.PARAMETER AllowUnverified Continue if SGP4 verification fails (results will be labelled unverified in the app).
.PARAMETER E2E             After verification, run tools\e2e_real_backend.py (real-backend workflow check, no extra packages).
.PARAMETER NoBrowser       Do not open the browser.
.PARAMETER Port            Port to serve on (default 8000).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start_ofde.ps1
#>
[CmdletBinding()]
param([switch]$SkipTests, [switch]$SkipVerify, [switch]$AllowUnverified, [switch]$E2E, [switch]$NoBrowser, [int]$Port = 8000)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step([string]$m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Ok([string]$m)   { Write-Host "[ OK ] $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }
# Run a native program and return ONLY its exit code. stderr output of native programs (pip/uvicorn warnings) must not
# become a terminating error in Windows PowerShell 5.1, so error preference is relaxed around the call.
function Invoke-Native([string]$Exe, [string[]]$ArgList) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Exe @ArgList | Out-Host; $code = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    if ($null -eq $code) { $code = 1 }
    return [int]$code
}

# ---- 1. Python ----
Step "Checking Python (3.10 or newer)"
$base = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $base = @("py", "-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $base = @("python") }
else { Fail "Python was not found. Install Python 3.10-3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then reopen PowerShell. If typing python opens the Microsoft Store, turn off the python.exe App execution alias in Windows Settings > Apps > Advanced app settings > App execution aliases." }
$exe = $base[0]; $pre = @(); if ($base.Count -gt 1) { $pre = $base[1..($base.Count - 1)] }
$rc = Invoke-Native $exe ($pre + @("-c", "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"))
if ($rc -ne 0) { Fail "Python 3.10 or newer is required (or this python is the Microsoft Store stub). Install from python.org and reopen PowerShell." }
Ok "Python is 3.10 or newer"

# ---- 2. Virtual environment ----
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Step "Creating virtual environment .venv"
    $rc = Invoke-Native $exe ($pre + @("-m", "venv", ".venv"))
    if ($rc -ne 0 -or -not (Test-Path $venvPy)) { Fail "Could not create .venv (exit code $rc)" }
    Ok "Created .venv"
} else { Ok ".venv exists" }

# ---- 3. Dependencies (reinstall only when the requirement files change) ----
Step "Checking dependencies"
$hash = (Get-FileHash requirements.txt, requirements-dev.txt -Algorithm SHA256 | ForEach-Object { $_.Hash }) -join ""
$marker = Join-Path $PSScriptRoot ".venv\.ofde_deps_hash"
$installed = ""; if (Test-Path $marker) { $installed = (Get-Content $marker -Raw).Trim() }
if ($installed -ne $hash) {
    Step "Installing dependencies (needs internet the first time)"
    $rc = Invoke-Native $venvPy @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-dev.txt")
    if ($rc -ne 0) { Fail "pip install failed. Check your internet connection. If a pinned version is not found, run 'pip index versions <package>', edit the pin in requirements.txt, and retry. Offline? See README (pre-downloaded wheels)." }
    Set-Content -Path $marker -Value $hash
    Ok "Dependencies installed"
} else { Ok "Dependencies already installed" }

# ---- 4. Tests ----
if (-not $SkipTests) {
    Step "Running tests"
    $rc = Invoke-Native $venvPy @("-m", "pytest", "-q")
    if ($rc -ne 0) { Fail "Tests failed (exit code $rc). Fix them before presenting, or rerun with -SkipTests if you accept the risk." }
    Ok "Tests passed"
} else { Warn "Tests skipped by request" }

# ---- 5. SGP4 verification ----
if (-not $SkipVerify) {
    Step "Verifying SGP4 on this machine"
    $rc = Invoke-Native $venvPy @("tools\verify_sgp4.py")
    if ($rc -ne 0) {
        if ($AllowUnverified) { Warn "SGP4 verification failed; continuing because -AllowUnverified was given. The app will label results UNVERIFIED." }
        else { Fail "SGP4 verification failed (see output above). Fix it, or rerun with -AllowUnverified to continue with results labelled unverified." }
    } else { Ok "SGP4 verified" }
} else { Warn "SGP4 verification skipped by request" }

# ---- 5b. Optional real-backend end-to-end check ----
if ($E2E) {
    Step "Running real-backend end-to-end check (starts its own temporary server and database)"
    $rc = Invoke-Native $venvPy @("tools\e2e_real_backend.py")
    if ($rc -ne 0) { Fail "End-to-end check reported failures (exit code $rc). See e2e_results.json and the output above." }
    Ok "End-to-end check passed"
}

# ---- 6. Start ----
Step "Starting OFDE"
$listening = $null
try { $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue } catch { }
if ($listening) { Fail "Port $Port is already in use. Close the other program or use: .\start_ofde.ps1 -Port 8010" }
$url = "http://127.0.0.1:$Port"
Write-Host "OFDE will be available at $url   (press Ctrl+C in this window to stop)" -ForegroundColor Green
if (-not $NoBrowser) { Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 3; Start-Process $u } -ArgumentList $url | Out-Null }
$rc = Invoke-Native $venvPy @("-m", "ofde", "--port", "$Port")
if ($rc -ne 0) { Fail "The server exited with code $rc" }
