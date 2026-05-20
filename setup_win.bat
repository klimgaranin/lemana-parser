@echo off
echo ============================================================
echo  LemanapPRO Parser v2 — установка (Windows)
echo ============================================================

python -m venv .venv
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Устанавливаем Chromium для Playwright...
playwright install chromium

echo.
echo ============================================================
echo  Готово! Запуск: run_win.bat
echo ============================================================
pause
