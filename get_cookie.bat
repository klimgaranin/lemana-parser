@echo off
echo Получаем cookie из Chrome...
call .venv\Scripts\activate.bat
pip install websocket-client -q
python cookie_grabber.py
pause