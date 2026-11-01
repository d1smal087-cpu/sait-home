@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" test_controls.py
set "probe_exit=%errorlevel%"
echo.
echo The input probe has ended. Hotkeys are released.
pause
exit /b %probe_exit%
