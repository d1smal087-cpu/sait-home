@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
echo Bind Spoil to F3 IN LU4 before this test.
".venv\Scripts\python.exe" test_controls.py --probe-action spoil
set "f3_exit=%errorlevel%"
echo.
echo F3 test ended.
pause
exit /b %f3_exit%
