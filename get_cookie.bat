@echo off
echo Получаем cookie из Chrome...
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_win.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" cookie_grabber.py %*
