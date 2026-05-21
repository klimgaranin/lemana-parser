@echo off
echo ============================================================
echo  LemanapPRO Parser v2 — установка (Windows)
echo ============================================================

python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Устанавливаем Chromium для Playwright...
".venv\Scripts\python.exe" -m playwright install chromium

echo.
echo ============================================================
echo  Готово! Запуск: run_win.bat
echo ============================================================
pause
