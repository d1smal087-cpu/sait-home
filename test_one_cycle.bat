@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" test_one_cycle.py
set "cycle_exit=%errorlevel%"
echo.
echo Single-cycle test ended. Hotkeys are released.
pause
exit /b %cycle_exit%
