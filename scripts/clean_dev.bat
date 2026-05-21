@echo off
setlocal

cd /d "%~dp0\.."

for /d /r %%D in (__pycache__) do (
    if exist "%%D" rmdir /s /q "%%D"
)

del /s /q *.pyc >nul 2>nul
del /q parser.log >nul 2>nul

echo Development artifacts cleaned.

