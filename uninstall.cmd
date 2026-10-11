@echo off
rem ScanScribe Native Windows Uninstaller Wrapper
setlocal
for %%I in ("%~dp0.") do set "ROOT_DIR=%%~fI"

rem Execute PowerShell uninstaller bypassing script restriction policy
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\uninstall.ps1" %*
exit /b %ERRORLEVEL%
