@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_win.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m unittest discover -s tests
exit /b %ERRORLEVEL%

