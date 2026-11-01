#Requires AutoHotkey v2.0
#SingleInstance Ignore

SetKeyDelay -1, -1
SetTitleMatchMode 1
PROBE_VERSION := "0.2"
cancelled := false
DirCreate A_ScriptDir "\runs"
logPath := A_ScriptDir "\runs\ahk-f2-" A_NowUTC "-" A_TickCount ".jsonl"

F9:: {
    global cancelled
    cancelled := true
}

try {
    Probe()
    ExitApp 0
} catch Error as err {
    try WriteEvent("stopped", ',"reason":"' EscapeJSON(err.Message) '"')
    MsgBox "Test stopped: " err.Message "`nLog: " logPath, "LU4 F2 test 0.2"
    ExitApp 1
}

Probe() {
    WriteEvent("ready", ',"elevated":' (A_IsAdmin ? "true" : "false") ',"key":"F2","vk":113,"scan":60,"hold_ms":300')
    if !A_IsAdmin
        throw Error("Run test_ahk_f2.bat as administrator.")
    WaitChecked(10000)
    hwnd := ActiveGame()
    for key in ["Shift", "Ctrl", "Alt", "LWin", "RWin"] {
        if GetKeyState(key)
            throw Error("Release modifier keys before testing.")
    }
    WriteEvent("active_game", ',"handle":' hwnd ',"pid":' WinGetPID("ahk_id " hwnd))
    CheckStopped()
    if ActiveGame() != hwnd
        throw Error("The active LU4 window changed.")
    WriteEvent("keydown_attempt", ',"method":"SendEvent","key_spec":"vk71sc03C"')
    try {
        SendEvent "{vk71sc03C down}"
        WriteEvent("keydown_dispatched")
        WaitChecked(300, hwnd)
    } finally {
        ; Always try to release, including when cancelled or focus is lost.
        SendEvent "{vk71sc03C up}"
    }
    WriteEvent("keyup_dispatched")
    WriteEvent("finished", ',"game_result_verified":false')
}

WaitChecked(duration, hwnd := 0) {
    deadline := A_TickCount + duration
    loop {
        CheckStopped()
        if hwnd && ActiveGame() != hwnd
            throw Error("LU4 lost focus while holding F2.")
        remaining := deadline - A_TickCount
        if remaining <= 0
            return
        Sleep Min(20, remaining)
    }
}

CheckStopped() {
    global cancelled
    if cancelled
        throw Error("Cancelled with F9.")
}

ActiveGame() {
    hwnd := WinExist("A")
    if !hwnd || !WinActive("LU4 -") || WinGetClass("ahk_id " hwnd) != "UnrealWindow"
        throw Error("Keep the LU4 game window active.")
    return hwnd
}

WriteEvent(name, extra := "") {
    global logPath, PROBE_VERSION
    line := '{"utc":"' A_NowUTC '","tick_ms":' A_TickCount ',"engine":"ahk-v2-sendevent","probe_version":"' PROBE_VERSION '","ahk_version":"' A_AhkVersion '","event":"' name '"' extra "}`n"
    FileAppend line, logPath, "UTF-8-RAW"
}

EscapeJSON(value) {
    value := StrReplace(value, "\", "\\")
    value := StrReplace(value, '"', '\"')
    value := StrReplace(value, "`r", "\r")
    value := StrReplace(value, "`n", "\n")
    return StrReplace(value, "`t", "\t")
}
