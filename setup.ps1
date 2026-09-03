<#
.SYNOPSIS
ScanScribe First-Time Setup Launcher for Windows PowerShell.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python setup.py $args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py setup.py $args
} else {
    Write-Host "Error: Python 3 was not found in PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/downloads/ (check 'Add python.exe to PATH' during install)."
    Write-Host "Alternatively, follow the manual setup guide in README.md."
    exit 1
}
