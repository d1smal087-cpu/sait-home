"""A single foreground-only F2 probe. No combat loop or background input."""
from __future__ import annotations

import ctypes
import argparse
import json
import math
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from . import __version__
from .capture import CaptureUnavailable, WindowsCapture, enable_dpi_awareness
from .config import ROOT, Settings


# Use fixed-width Win32 types so the INPUT layout can also be checked on Linux.
DWORD, WORD, LONG = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_int32
ULONG_PTR = ctypes.c_size_t
SCANCODE, KEYUP, F2_SCAN = 0x0008, 0x0002, 0x003C
PROBE_ID, STOP_ID = 1701, 1702


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", DWORD), ("data", INPUTUNION)]


def f2_event(release: bool = False, key_mode: str = "scan") -> INPUT:
    event = INPUT()
    event.type = 1  # INPUT_KEYBOARD
    if key_mode == "scan":
        event.ki = KEYBDINPUT(0, F2_SCAN, SCANCODE | (KEYUP if release else 0), 0, 0)
    elif key_mode == "virtual":
        event.ki = KEYBDINPUT(0x71, 0, KEYUP if release else 0, 0, 0)  # VK_F2
    else:
        raise ValueError("Unknown F2 key mode")
    return event


def tap_f2(check_foreground, send, sleep=time.sleep, *, key_mode="scan", hold_seconds=0.08) -> None:
    """Check focus immediately before keydown and always release an accepted key."""
    if not math.isfinite(hold_seconds) or not 0.03 <= hold_seconds <= 1.0:
        raise ValueError("Key hold must be between 0.03 and 1 second")
    down, up = f2_event(key_mode=key_mode), f2_event(release=True, key_mode=key_mode)
    check_foreground()
    if send(down) != 1:
        raise RuntimeError("Windows did not accept the F2 keydown event.")
    try:
        sleep(hold_seconds)
    finally:
        # Release even if focus changed or the probe was interrupted during hold.
        if send(up) != 1:
            raise RuntimeError("Windows did not accept the F2 keyup event.")


def find_active_game(capture, prefix, report_windows=None):
    """Resolve again for every trigger: the game may start or recreate its HWND."""
    windows = capture.windows(prefix)
    if report_windows is not None:
        report_windows([window.handle for window in windows])
    if not windows:
        raise CaptureUnavailable("No LU4 window found. Open LU4, switch to the game, then press F8 again.")
    for window in windows:
        try:
            capture.bounds(window.handle)
            return window
        except CaptureUnavailable:
            continue
    raise CaptureUnavailable("LU4 is not active. Switch to the game, then press F8 again.")


def wait_for_countdown(poll_stop, deadline, clock=time.monotonic, sleep=time.sleep):
    while True:
        # A queued stop wins even when the timer expires at the same moment.
        if poll_stop():
            return STOP_ID
        if clock() >= deadline:
            return PROBE_ID
        sleep(0.05)


@contextmanager
def probe_hotkeys(api, include_start=True):
    registered = []
    try:
        bindings = [(STOP_ID, 0x78, "F9")]
        if include_start:
            bindings.append((PROBE_ID, 0x77, "F8"))
        for key_id, virtual_key, label in bindings:
            if not api.RegisterHotKey(None, key_id, 0x4000, virtual_key):  # MOD_NOREPEAT
                error = getattr(ctypes, "get_last_error", lambda: 0)()
                raise RuntimeError(f"Cannot register {label} (Windows error {error}). It may be reserved by another application.")
            registered.append(key_id)
        yield
    finally:
        for key_id in reversed(registered):
            api.UnregisterHotKey(None, key_id)


def probe_elevation():
    """Read this process's token elevation flag only; never read credentials."""
    if sys.platform != "win32":
        return {"probe_elevated": None, "elevation_error": "unsupported_platform"}
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], wintypes.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return {"probe_elevated": None, "elevation_error": ctypes.get_last_error()}
    try:
        elevated, returned = wintypes.DWORD(), wintypes.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(returned)):
            return {"probe_elevated": None, "elevation_error": ctypes.get_last_error()}
        return {"probe_elevated": bool(elevated.value), "elevation_error": 0}
    finally:
        kernel.CloseHandle(token)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One foreground-only F2 input test")
    parser.add_argument("--countdown", type=int, choices=range(3, 31), metavar="3..30",
                        help="Send one F2 after this many seconds, without F8")
    parser.add_argument("--key-mode", choices=("virtual", "scan"), default="virtual")
    parser.add_argument("--hold-ms", type=int, choices=range(30, 1001), default=300, metavar="30..1000")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("The input probe requires Windows. No input was sent.")
        return 1
    from ctypes import wintypes

    log = None
    try:
        enable_dpi_awareness()
        settings = Settings.load()
        capture = WindowsCapture()
        api = capture.api
        api.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        api.SendInput.restype = ctypes.c_uint
        api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        api.RegisterHotKey.restype = wintypes.BOOL
        api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        api.UnregisterHotKey.restype = wintypes.BOOL
        api.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
        api.GetMessageW.restype = ctypes.c_int
        api.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        api.PeekMessageW.restype = wintypes.BOOL
        api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        api.GetClassNameW.restype = ctypes.c_int
        folder = ROOT / "runs"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log = folder / f"controls-test-{stamp}.jsonl"

        def record(event, **data):
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                                         "version": __version__, "event": event, **data}) + "\n")

        def send(event):
            ctypes.set_last_error(0)
            count = int(api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)))
            error = ctypes.get_last_error()
            # Logging must not interrupt the down/up pair after Windows accepted
            # a keydown (for example, if the disk becomes full).
            try:
                record("keyup" if event.ki.dwFlags & KEYUP else "keydown", accepted=count,
                       scan=int(event.ki.wScan), virtual_key=int(event.ki.wVk),
                       flags=int(event.ki.dwFlags), windows_error=error)
            except OSError as error:
                print(f"Cannot write input log: {error}", flush=True)
            return count

        def foreground_info():
            handle = api.GetForegroundWindow()
            name = ctypes.create_unicode_buffer(256)
            pid = wintypes.DWORD()
            if handle:
                api.GetClassNameW(handle, name, len(name))
                api.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            return {"handle": int(handle or 0), "class_name": name.value, "pid": int(pid.value)}

        with probe_hotkeys(api, include_start=args.countdown is None):
            elevation = probe_elevation()
            record("ready", mode="countdown" if args.countdown else "hotkey", delay=args.countdown,
                   key_mode=args.key_mode, hold_ms=args.hold_ms, **elevation)
            print(f"LU4 input probe {__version__}", flush=True)
            print(f"Input mode: {args.key_mode}, hold: {args.hold_ms} ms, elevated: {elevation['probe_elevated']}", flush=True)
            print(f"Log: {log}", flush=True)
            print("Switch to LU4. Close chat input and remove the current target with Esc.", flush=True)
            if args.countdown:
                print(f"COUNTDOWN: switch to LU4 within {args.countdown} seconds. F9 cancels.", flush=True)
                print("F8 is not used in this test. One F2 will be attempted when the timer expires.", flush=True)
            else:
                print("The probe stays ready even if LU4 has not been opened yet.", flush=True)
                print("F8: send F2 ONCE to the active LU4 window. F9: finish/cancel.", flush=True)
            print("No attack, Spoil, Sweep, movement or pickup is sent.", flush=True)
            message = wintypes.MSG()
            used = False
            deadline = time.monotonic() + (args.countdown or 0)

            def poll_stop():
                while api.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x0012 or (message.message == 0x0312 and message.wParam == STOP_ID):
                        return True
                return False

            def cancellable_hold(duration):
                if wait_for_countdown(poll_stop, time.monotonic() + duration) == STOP_ID:
                    raise KeyboardInterrupt()

            while True:
                if args.countdown:
                    command = wait_for_countdown(poll_stop, deadline)
                    message.message, message.wParam = 0x0312, command
                    result = 1
                else:
                    result = api.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    return 0
                if message.message != 0x0312:  # WM_HOTKEY
                    continue
                if message.wParam == STOP_ID:
                    record("hotkey_received", key="F9")
                    record("finished" if used else "cancelled")
                    print("Probe stopped. No further input will be sent.", flush=True)
                    return 0
                if message.wParam == PROBE_ID:
                    if args.countdown:
                        record("countdown_elapsed")
                    else:
                        record("hotkey_received", key="F8")
                    if used:
                        print("The one F2 tap was already sent. Press F9 to finish.", flush=True)
                        continue
                    try:
                        record("foreground_before_probe", **foreground_info())
                        window = find_active_game(capture, settings.window_title_prefix,
                                                  lambda handles: record("game_windows", handles=handles))
                        record("active_game_found", handle=window.handle)
                        tap_f2(lambda: capture.bounds(window.handle), send, cancellable_hold,
                               key_mode=args.key_mode, hold_seconds=args.hold_ms / 1000)
                    except CaptureUnavailable as error:
                        record("waiting_for_game", reason=str(error))
                        print(str(error), flush=True)
                        if args.countdown:
                            print("Timer test ended without sending F2. See the log for window details.", flush=True)
                            return 1
                        continue
                    record("probe_finished")
                    used = True
                    print("Windows accepted the F2 events. Check whether LU4 selected a target.", flush=True)
                    print(f"Log: {log}", flush=True)
                    if args.countdown:
                        return 0
                    print("Press F9 to finish. Further F8 presses will not send input.", flush=True)
    except KeyboardInterrupt:
        print("Probe cancelled.", flush=True)
        return 0
    except Exception as error:
        if log is not None:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": "error", "message": str(error)}) + "\n")
        print(f"Probe error: {error}", flush=True)
        return 1
