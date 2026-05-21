@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_win.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m ruff format .
if errorlevel 1 exit /b %ERRORLEVEL%

".venv\Scripts\python.exe" -m ruff check --fix . --no-cache
exit /b %ERRORLEVEL%
