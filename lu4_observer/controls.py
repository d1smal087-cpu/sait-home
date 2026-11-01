"""A single foreground-only F2 probe. No combat loop or background input."""
from __future__ import annotations

import ctypes
import json
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


def f2_event(release: bool = False) -> INPUT:
    event = INPUT()
    event.type = 1  # INPUT_KEYBOARD
    event.ki = KEYBDINPUT(0, F2_SCAN, SCANCODE | (KEYUP if release else 0), 0, 0)
    return event


def tap_f2(check_foreground, send, sleep=time.sleep) -> None:
    """Check focus immediately before keydown and always release an accepted key."""
    check_foreground()
    if send(f2_event()) != 1:
        raise RuntimeError("Windows did not accept the F2 keydown event.")
    try:
        sleep(0.08)
    finally:
        # Release even if focus changed or the probe was interrupted during hold.
        if send(f2_event(release=True)) != 1:
            raise RuntimeError("Windows did not accept the F2 keyup event.")


@contextmanager
def probe_hotkeys(api):
    registered = []
    try:
        for key_id, virtual_key, label in ((STOP_ID, 0x78, "F9"), (PROBE_ID, 0x77, "F8")):
            if not api.RegisterHotKey(None, key_id, 0x4000, virtual_key):  # MOD_NOREPEAT
                raise RuntimeError(f"Cannot register {label}. It may be reserved by another application.")
            registered.append(key_id)
        yield
    finally:
        for key_id in reversed(registered):
            api.UnregisterHotKey(None, key_id)


def main() -> int:
    if sys.platform != "win32":
        print("The input probe requires Windows. No input was sent.")
        return 1
    from ctypes import wintypes

    log = None
    try:
        enable_dpi_awareness()
        settings = Settings.load()
        capture = WindowsCapture()
        windows = capture.windows(settings.window_title_prefix)
        if len(windows) != 1:
            raise RuntimeError("Keep exactly one LU4 game window open, then restart this probe.")
        window = windows[0]
        api = capture.api
        api.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        api.SendInput.restype = ctypes.c_uint
        api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        api.RegisterHotKey.restype = wintypes.BOOL
        api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        api.UnregisterHotKey.restype = wintypes.BOOL
        api.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
        api.GetMessageW.restype = ctypes.c_int
        folder = ROOT / "runs"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log = folder / f"controls-test-{stamp}.jsonl"

        def record(event, **data):
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                                         "version": __version__, "event": event, **data}) + "\n")

        def send(event):
            count = int(api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)))
            # Logging must not interrupt the down/up pair after Windows accepted
            # a keydown (for example, if the disk becomes full).
            try:
                record("keyup" if event.ki.dwFlags & KEYUP else "keydown", accepted=count,
                       scan=int(event.ki.wScan))
            except OSError as error:
                print(f"Cannot write input log: {error}", flush=True)
            return count

        with probe_hotkeys(api):
            record("ready")
            print(f"LU4 input probe {__version__}", flush=True)
            print("Switch to LU4. Close chat input and remove the current target with Esc.", flush=True)
            print("F8: send F2 ONCE to the active LU4 window. F9: finish/cancel.", flush=True)
            print("No attack, Spoil, Sweep, movement or pickup is sent.", flush=True)
            message = wintypes.MSG()
            used = False
            while True:
                result = api.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    return 0
                if message.message != 0x0312:  # WM_HOTKEY
                    continue
                if message.wParam == STOP_ID:
                    record("finished" if used else "cancelled")
                    print("Probe stopped. No further input will be sent.", flush=True)
                    return 0
                if message.wParam == PROBE_ID:
                    if used:
                        print("The one F2 tap was already sent. Press F9 to finish.", flush=True)
                        continue
                    try:
                        tap_f2(lambda: capture.bounds(window.handle), send)
                    except CaptureUnavailable:
                        record("ignored_inactive_window")
                        print("LU4 must be active. Switch to the game and press F8 again.", flush=True)
                        continue
                    record("probe_finished")
                    used = True
                    print("Windows accepted the F2 events. Check whether LU4 selected a target.", flush=True)
                    print(f"Log: {log}", flush=True)
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
