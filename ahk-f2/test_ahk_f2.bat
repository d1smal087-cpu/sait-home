@echo off
setlocal
cd /d "%~dp0"
set "lu4_ahk=%ProgramFiles%\AutoHotkey\v2\AutoHotkey64.exe"
if not exist "%lu4_ahk%" set "lu4_ahk=%LocalAppData%\Programs\AutoHotkey\v2\AutoHotkey64.exe"
if not exist "%lu4_ahk%" set "lu4_ahk=%~dp0AutoHotkey64.exe"
if not exist "%lu4_ahk%" (
    echo AutoHotkey v2 is required. Download it from https://www.autohotkey.com/
    echo Install v2, then run this BAT again as administrator.
    pause
    exit /b 1
)
echo In LU4, F2 must be NEXT TARGET. Close chat and clear the target with Esc.
echo F2 SendEvent test 0.2. Switch to LU4 within 10 seconds. F9 cancels.
"%lu4_ahk%" "%~dp0f2-sendevent.ahk"
set "lu4_ahk_exit=%errorlevel%"
echo.
echo Test ended. See runs\ahk-f2-*.jsonl and whether a target was selected.
pause
exit /b %lu4_ahk_exit%
