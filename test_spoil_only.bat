@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" test_controls.py --probe-action spoil
set "spoil_exit=%errorlevel%"
echo.
echo Spoil-only test ended. No further input will be sent.
pause
exit /b %spoil_exit%
