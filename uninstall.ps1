<#
.SYNOPSIS
    ScanScribe Native Windows Uninstaller
.DESCRIPTION
    Stops ScanScribe, removes background Task Scheduler tasks, cleans user PATH,
    clears Python bytecode caches, and removes the .venv virtual environment.
.EXAMPLE
    .\uninstall.ps1
.EXAMPLE
    .\uninstall.ps1 -Purge -Yes
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Purge
)

$ErrorActionPreference = "Continue"

$InstallDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Red
Write-Host "                ScanScribe Windows Uninstaller              " -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Red
Write-Host "Target Directory: $InstallDir"
Write-Host ""
Write-Host "This will:"
Write-Host "  1. Stop any running ScanScribe process"
Write-Host "  2. Remove Windows Task Scheduler logon task (ScanScribe)"
Write-Host "  3. Remove $InstallDir\bin from user PATH"
Write-Host "  4. Clear all Python bytecode caches (__pycache__, *.pyc)"
Write-Host "  5. Remove isolated virtual environment (.venv) and dependencies"
if ($Purge) {
    Write-Host "  [!] PURGE: Will permanently delete database, audio storage, models, and config!" -ForegroundColor DarkRed
} else {
    Write-Host "  [i] User database, audio recordings, models, and config will be PRESERVED." -ForegroundColor Green
}
Write-Host ""

if (-not $Yes) {
    $resp = Read-Host "Are you sure you want to proceed with uninstallation? (y/N)"
    if ($resp -notin @("y", "yes", "Y", "YES")) {
        Write-Host "Uninstallation cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# 1. Stop running process
Write-Host "[1/5] Stopping ScanScribe..." -ForegroundColor Yellow
$binCmd = Join-Path $InstallDir "bin\scanscribe.cmd"
if (Test-Path $binCmd) {
    & $binCmd stop 2>$null
}
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$InstallDir*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Remove Task Scheduler task
Write-Host "[2/5] Removing Windows Task Scheduler task..." -ForegroundColor Yellow
try {
    schtasks /delete /tn "ScanScribe" /f 2>$null | Out-Null
    Write-Host "    [✓] Scheduled task removed."
} catch {
    Write-Host "    [!] Task not found or already removed."
}

# 3. Clean User PATH
Write-Host "[3/5] Cleaning User PATH..." -ForegroundColor Yellow
$binDir = Join-Path $InstallDir "bin"
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -like "*$binDir*") {
    $parts = ($userPath -split ";" | Where-Object { $_ -and $_.Trim() -ne $binDir })
    $newPath = $parts -join ";"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "    [✓] Removed $binDir from User PATH."
}

# 4. Clear Python bytecode caches
Write-Host "[4/5] Clearing Python caches..." -ForegroundColor Yellow
$pycaches = Get-ChildItem -Path $InstallDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
foreach ($p in $pycaches) {
    Remove-Item -Path $p.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
$pycs = Get-ChildItem -Path $InstallDir -Recurse -File -Include "*.pyc", "*.pyo" -ErrorAction SilentlyContinue
foreach ($f in $pycs) {
    Remove-Item -Path $f.FullName -Force -ErrorAction SilentlyContinue
}
Write-Host "    [✓] Bytecode caches cleared."

# Optional Purge
if ($Purge) {
    Write-Host "[-] Purging database, recordings, and config..." -ForegroundColor DarkRed
    $purgeTargets = @(
        (Join-Path $InstallDir "data"),
        (Join-Path $InstallDir "audio_storage"),
        (Join-Path $InstallDir "models"),
        (Join-Path $InstallDir "logs"),
        (Join-Path $InstallDir ".env"),
        (Join-Path $InstallDir "config.yml")
    )
    foreach ($target in $purgeTargets) {
        if (Test-Path $target) {
            Remove-Item -Path $target -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "    [✓] Data and configurations purged."
}

# 5. Remove .venv
Write-Host "[5/5] Removing virtual environment (.venv)..." -ForegroundColor Yellow
$venvDir = Join-Path $InstallDir ".venv"
if (Test-Path $venvDir) {
    Remove-Item -Path $venvDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $venvDir) {
        Start-Process cmd.exe -ArgumentList "/c timeout /t 1 >nul & rmdir /s /q `"$venvDir`"" -WindowStyle Hidden
        Write-Host "    [✓] Virtual environment scheduled for background removal."
    } else {
        Write-Host "    [✓] Virtual environment (.venv) removed."
    }
}

# Remove PID file
$pidFile = Join-Path $InstallDir ".scanscribe.pid"
if (Test-Path $pidFile) {
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "        ScanScribe has been uninstalled successfully.       " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
