@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
echo Prepare a nearby living mob. During countdown, switch to LU4 and OPEN EMPTY CHAT.
".venv\Scripts\python.exe" test_controls.py --probe-action spoil_command
set "command_exit=%errorlevel%"
echo.
echo Chat command test ended.
pause
exit /b %command_exit%
