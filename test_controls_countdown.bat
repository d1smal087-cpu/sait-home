@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" test_controls.py --countdown 10
set "probe_exit=%errorlevel%"
echo.
echo Timer test ended. No further input will be sent.
pause
exit /b %probe_exit%
