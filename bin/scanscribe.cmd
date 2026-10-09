@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."

rem Check for .venv python
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    "%ROOT_DIR%\.venv\Scripts\python.exe" -m app.cli %*
    exit /b %ERRORLEVEL%
)

rem Fallback to system python
python -m app.cli %*
exit /b %ERRORLEVEL%
