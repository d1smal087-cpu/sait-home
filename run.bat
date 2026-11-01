@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" observer.py
if errorlevel 1 (
    echo.
    echo Observer failed. Copy the error text from this window for diagnosis.
    pause
    exit /b 1
)
