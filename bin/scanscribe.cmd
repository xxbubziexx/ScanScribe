@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"

rem Check for .venv python
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    "%ROOT_DIR%\.venv\Scripts\python.exe" -m app.cli %*
    exit /b %ERRORLEVEL%
)

rem Fallback to system python
python -m app.cli %*
exit /b %ERRORLEVEL%
