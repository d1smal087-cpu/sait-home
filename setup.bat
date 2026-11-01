@echo off
setlocal
cd /d "%~dp0"
echo LU4 Observer - setup for Windows x64 and Python 3.12
py -3.12 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 (
    echo Install Python 3.12 x64 from https://www.python.org/downloads/windows/
    echo Include the Python launcher and Tcl/Tk in the installation.
    echo Then run setup.bat again.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install --only-binary=:all: --require-hashes -r requirements-windows.lock
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" observer.py --check
if errorlevel 1 goto :failed
echo.
echo Ready. Open the game, then double-click run.bat.
pause
exit /b 0
:failed
echo.
echo Setup failed. Copy the error text from this window for diagnosis.
pause
exit /b 1
