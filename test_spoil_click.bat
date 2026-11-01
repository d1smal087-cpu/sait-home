@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" test_controls.py --probe-action spoil_click
set "click_exit=%errorlevel%"
echo.
echo Spoil click test ended.
pause
exit /b %click_exit%
