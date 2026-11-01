"""Foreground-only tests: a single F2 or one manually selected combat target."""
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
from .config import ROOT, Settings, FUNCTION_BINDINGS


# Use fixed-width Win32 types so the INPUT layout can also be checked on Linux.
DWORD, WORD, LONG = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_int32
ULONG_PTR = ctypes.c_size_t
SCANCODE, KEYUP, F2_SCAN = 0x0008, 0x0002, 0x003C
UNICODE = 0x0004
SPOIL_COMMAND = "/useskill Spoil"
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


def scan_event(scan: int, release: bool = False) -> INPUT:
    event = INPUT()
    event.type = 1
    event.ki = KEYBDINPUT(0, scan, SCANCODE | (KEYUP if release else 0), 0, 0)
    return event


def f2_event(release: bool = False, key_mode: str = "scan") -> INPUT:
    event = INPUT()
    event.type = 1  # INPUT_KEYBOARD
    if key_mode == "scan":
        return scan_event(F2_SCAN, release)
    elif key_mode == "virtual":
        event.ki = KEYBDINPUT(0x71, 0, KEYUP if release else 0, 0, 0)  # VK_F2
    else:
        raise ValueError("Unknown F2 key mode")
    return event


def tap_f2(check_foreground, send, sleep=time.sleep, *, key_mode="scan", hold_seconds=0.08) -> None:
    """Check focus immediately before keydown and always release an accepted key."""
    if key_mode == "scan":
        return tap_scan(F2_SCAN, check_foreground, send, sleep, hold_seconds)
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


ACTION_SCANS = {"attack": 0x3B, "next_target": 0x3C, "spoil": 0x3D, "sweep": 0x3E, "pickup": 0x3F, "cancel": 0x01}


def require_function_bindings(settings, actions):
    for action in actions:
        if settings.game_key_bindings.get(action) != FUNCTION_BINDINGS[action]:
            raise RuntimeError(f"Configure {action} as {FUNCTION_BINDINGS[action]} in config.json and in LU4.")


def tap_action(action, check_foreground, send, sleep=time.sleep):
    return tap_scan(ACTION_SCANS[action], check_foreground, send, sleep, 0.3)


def tap_scan(scan, check_foreground, send, sleep=time.sleep, hold_seconds=0.3):
    if not math.isfinite(hold_seconds) or not 0.03 <= hold_seconds <= 1.0:
        raise ValueError("Key hold must be between 0.03 and 1 second")
    check_foreground()
    down, up = scan_event(scan), scan_event(scan, True)
    if send(down) != 1:
        raise RuntimeError("Windows did not accept the action keydown")
    try:
        sleep(hold_seconds)
    finally:
        if send(up) != 1:
            raise RuntimeError("Windows did not accept the action keyup")


def send_spoil_command(check_foreground, send, sleep=time.sleep):
    """Type one fixed command into an already open, empty chat, then submit."""
    for char in SPOIL_COMMAND:
        check_foreground()
        down, up = INPUT(), INPUT()
        down.type = up.type = 1
        down.ki = KEYBDINPUT(0, ord(char), UNICODE, 0, 0)
        up.ki = KEYBDINPUT(0, ord(char), UNICODE | KEYUP, 0, 0)
        if send(down) != 1:
            raise RuntimeError("Windows did not accept command text keydown")
        try:
            sleep(0.02)
        finally:
            if send(up) != 1:
                raise RuntimeError("Windows did not accept command text keyup")
        sleep(0.03)
    sleep(0.3)
    tap_scan(0x1C, check_foreground, send, sleep, 0.3)  # Enter, once


MODIFIER_KEYS = {"SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12, "LWIN": 0x5B, "RWIN": 0x5C}


def pressed_modifiers(get_state):
    return [name for name, key in MODIFIER_KEYS.items() if get_state(key) & 0x8000]


def spoil_click_position(bounds, position):
    x, y, w, h = bounds
    if w != 1600 or h not in (837, 838):
        raise RuntimeError("Mouse test requires the verified 1600x837/838 client layout.")
    px, py = position
    # Small rectangle around the Spoil icon in the latest supplied layout.
    if not (x + 0.298*w <= px <= x + 0.320*w and y + 0.908*h <= py <= y + 0.947*h):
        raise RuntimeError("Place the cursor over the orange Spoil icon (first button in the row marked 1).")
    return px, py


def tap_mouse(check_position, send, sleep=time.sleep):
    check_position()
    down, up = INPUT(), INPUT()
    down.type = up.type = 0
    down.mi = MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)
    up.mi = MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)
    if send(down) != 1:
        raise RuntimeError("Windows did not accept mouse down")
    try:
        sleep(0.3)
    finally:
        if send(up) != 1:
            raise RuntimeError("Windows did not accept mouse up")


class RECT32(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("flags", DWORD), ("hwndActive", ctypes.c_void_p),
                ("hwndFocus", ctypes.c_void_p), ("hwndCapture", ctypes.c_void_p),
                ("hwndMenuOwner", ctypes.c_void_p), ("hwndMoveSize", ctypes.c_void_p),
                ("hwndCaret", ctypes.c_void_p), ("rcCaret", RECT32)]


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
    parser.add_argument("--one-cycle", action="store_true", help="One manually selected mob, then stop")
    parser.add_argument("--probe-action", choices=("next_target", "spoil", "spoil_click", "spoil_command"), default="next_target")
    args = parser.parse_args(argv)
    if args.one_cycle:
        args.countdown, args.key_mode, args.hold_ms = 10, "scan", 300
    elif args.probe_action in ("spoil", "spoil_click", "spoil_command"):
        args.countdown, args.key_mode, args.hold_ms = 10, "scan", 300
    if sys.platform != "win32":
        print("The input probe requires Windows. No input was sent.")
        return 1
    from ctypes import wintypes

    log = None
    try:
        enable_dpi_awareness()
        settings = Settings.load()
        if args.probe_action == "spoil_click":
            raise RuntimeError("Old mouse layout test disabled. Bind Spoil to F3 and use test_spoil_f3.bat.")
        if args.probe_action == "spoil":
            require_function_bindings(settings, ["spoil"])
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
        api.GetAsyncKeyState.argtypes = [ctypes.c_int]
        api.GetAsyncKeyState.restype = ctypes.c_int16
        api.GetGUIThreadInfo.argtypes = [DWORD, ctypes.POINTER(GUITHREADINFO)]
        api.GetGUIThreadInfo.restype = ctypes.c_int32
        api.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        api.GetCursorPos.restype = wintypes.BOOL
        api.WindowFromPoint.argtypes = [wintypes.POINT]
        api.WindowFromPoint.restype = wintypes.HWND
        api.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        api.GetAncestor.restype = wintypes.HWND
        folder = ROOT / "runs"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log = folder / f"controls-test-{stamp}.jsonl"
        events = []

        def record(event, **data):
            entry = {"time": datetime.now(timezone.utc).isoformat(), "version": __version__, "event": event, **data}
            events.append(entry)
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry) + "\n")

        def send(event):
            if not event.ki.dwFlags & KEYUP:
                modifiers = pressed_modifiers(api.GetAsyncKeyState)
                info = GUITHREADINFO()
                info.cbSize = ctypes.sizeof(info)
                has_info = bool(api.GetGUIThreadInfo(0, ctypes.byref(info)))
                focus_class = ctypes.create_unicode_buffer(256)
                if has_info and info.hwndFocus:
                    api.GetClassNameW(info.hwndFocus, focus_class, len(focus_class))
                record("keyboard_state", modifiers=modifiers, gui_info_available=has_info,
                       focus_handle=int(info.hwndFocus or 0), focus_class=focus_class.value,
                       active_handle=int(info.hwndActive or 0), gui_flags=int(info.flags))
                if modifiers:
                    raise RuntimeError("Release modifier keys and retry: " + ", ".join(modifiers))
            ctypes.set_last_error(0)
            count = int(api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)))
            error = ctypes.get_last_error()
            # Logging must not interrupt the down/up pair after Windows accepted
            # a keydown (for example, if the disk becomes full).
            try:
                record("keyup" if event.ki.dwFlags & KEYUP else "keydown", accepted=count,
                       scan=int(event.ki.wScan), virtual_key=int(event.ki.wVk),
                       flags=int(event.ki.dwFlags), windows_error=error,
                       encoding="unicode" if event.ki.dwFlags & UNICODE else "key")
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
            record("ready", mode="single_cycle" if args.one_cycle else ("countdown" if args.countdown else "hotkey"), delay=args.countdown,
                   key_mode=args.key_mode, hold_ms=args.hold_ms, action=args.probe_action,
                   input_kind=("chat_command" if args.probe_action == "spoil_command" else
                               "mouse" if args.probe_action == "spoil_click" else "keyboard"),
                   text_mode="unicode" if args.probe_action == "spoil_command" else None,
                   uses_ocr=args.one_cycle, bindings=settings.game_key_bindings, **elevation)
            if (args.one_cycle or args.probe_action in ("spoil", "spoil_click", "spoil_command")) and elevation["probe_elevated"] is not True:
                raise RuntimeError("Run this test BAT as administrator, matching the verified LU4 setup.")
            print(f"LU4 input probe {__version__}", flush=True)
            print(f"Input mode: {args.key_mode}, hold: {args.hold_ms} ms, elevated: {elevation['probe_elevated']}", flush=True)
            print(f"Log: {log}", flush=True)
            if args.one_cycle:
                print("ONE CYCLE: select a nearby living, undamaged Ghoul or Dead Seeker.", flush=True)
                print("Keep LU4 active. Start in 10 seconds. F9 stops; Escape cancels the target while LU4 is active.", flush=True)
                print("Attempts: Spoil (F3), attack (F1), Sweep (F4), pickup (F5). No next-target search or return.", flush=True)
            elif args.probe_action == "spoil_command":
                print("SPOIL CHAT COMMAND: select a nearby living mob that is not spoiled yet.", flush=True)
                print("Within 10 seconds: switch to LU4 and OPEN THE EMPTY CHAT INPUT. Keep the target selected.", flush=True)
                print("Types /useskill Spoil once using Unicode text, then presses Enter. No Escape or attack. F9 cancels.", flush=True)
            elif args.probe_action == "spoil_click":
                print("SPOIL CLICK: choose a nearby living mob, close chat and keep the target selected.", flush=True)
                print("Hover over the orange Spoil icon. One left click in 10 seconds. Keep the mouse still.", flush=True)
                print("No OCR, no attack. Escape follows after 3 seconds. F9 cancels.", flush=True)
            elif args.probe_action == "spoil":
                print("SPOIL F3 ONLY: bind Spoil to F3 IN THE GAME first. Choose a nearby mob and close chat.", flush=True)
                print("One F3 in 10 seconds; Escape after 3 seconds. No OCR, no attack. F9 cancels.", flush=True)
            elif args.countdown:
                print("Switch to LU4. Close chat input and remove the current target with Esc.", flush=True)
                print(f"COUNTDOWN: switch to LU4 within {args.countdown} seconds. F9 cancels.", flush=True)
                print("F8 is not used in this test. One F2 will be attempted when the timer expires.", flush=True)
            else:
                print("The probe stays ready even if LU4 has not been opened yet.", flush=True)
                print("F8: send F2 ONCE to the active LU4 window. F9: finish/cancel.", flush=True)
            if not args.one_cycle and args.probe_action == "next_target":
                print("Only F2 is sent. Its in-game action depends on your current LU4 binding.", flush=True)
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
                        if args.one_cycle:
                            return execute_one_cycle(capture, window, settings, send, poll_stop, events, record)
                        if args.probe_action == "spoil_command":
                            record("probe_action", action="spoil_command", command=SPOIL_COMMAND,
                                   text_mode="unicode", requires_empty_open_chat=True, uses_ocr=False)
                            send_spoil_command(lambda: capture.bounds(window.handle), send, cancellable_hold)
                            record("command_events_sent", command=SPOIL_COMMAND, result_not_inferred=True)
                            cancellable_hold(3.0)
                            record("probe_finished", action="spoil_command", result_not_inferred=True)
                            print(f"Command test ended. Report whether Spoil started, or text/error remained. Log: {log}", flush=True)
                            return 0
                        if args.probe_action in ("spoil", "spoil_click"):
                            try:
                                record("probe_action", action=args.probe_action,
                                       bound_key=settings.game_key_bindings.get("spoil"), uses_ocr=False)
                                if args.probe_action == "spoil_click":
                                    def check_mouse():
                                        bounds = capture.bounds(window.handle)
                                        position = wintypes.POINT()
                                        if not api.GetCursorPos(ctypes.byref(position)):
                                            raise ctypes.WinError(ctypes.get_last_error())
                                        spoil_click_position(bounds, (position.x, position.y))
                                        hit = api.WindowFromPoint(position)
                                        root = api.GetAncestor(hit, 2) if hit else None
                                        if root != window.handle:
                                            raise RuntimeError("The cursor is covered by a different window")
                                        modifiers = pressed_modifiers(api.GetAsyncKeyState)
                                        record("mouse_position", x=position.x, y=position.y, modifiers=modifiers)
                                        if modifiers:
                                            raise RuntimeError("Release modifier keys before mouse test")
                                    def send_mouse(event):
                                        ctypes.set_last_error(0)
                                        accepted = int(api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)))
                                        error = ctypes.get_last_error()
                                        now = time.monotonic()
                                        actual_hold_ms = None
                                        if event.mi.dwFlags == 2 and accepted == 1:
                                            send_mouse.pressed_at = now
                                        elif event.mi.dwFlags == 4 and hasattr(send_mouse, "pressed_at"):
                                            actual_hold_ms = round((now - send_mouse.pressed_at) * 1000, 1)
                                        try:
                                            record("mouse_down" if event.mi.dwFlags == 2 else "mouse_up", accepted=accepted,
                                                   windows_error=error, actual_hold_ms=actual_hold_ms)
                                        except OSError:
                                            pass  # Never interrupt the down/up pair because of logging.
                                        return accepted
                                    tap_mouse(check_mouse, send_mouse, cancellable_hold)
                                else:
                                    tap_action("spoil", lambda: capture.bounds(window.handle), send, cancellable_hold)
                                cancellable_hold(3.0)
                                record("probe_finished", action="spoil", result_not_inferred=True)
                            finally:
                                try:
                                    tap_action("cancel", lambda: capture.bounds(window.handle), send)
                                    record("cancel_target_sent")
                                except Exception as error:
                                    record("cancel_target_failed", reason=str(error))
                            print(f"Spoil-only test ended. Inspect skill animation/MP and send log: {log}", flush=True)
                            return 0
                        tap_f2(lambda: capture.bounds(window.handle), send, cancellable_hold,
                               key_mode=args.key_mode, hold_seconds=args.hold_ms / 1000)
                    except CaptureUnavailable as error:
                        record("waiting_for_game", reason=str(error))
                        print(str(error), flush=True)
                        if args.countdown:
                            print("Timer test ended. See the log for input and window details.", flush=True)
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


def execute_one_cycle(capture, window, settings, send, poll_stop, events, record):
    from .diagnostics import save_bundle
    from .recognition import Analyzer, LocalOCR
    from .single_cycle import CycleStopped, run_one_cycle

    require_function_bindings(settings, ["attack", "spoil", "sweep", "pickup"])
    analyzer = Analyzer(LocalOCR())
    latest_frame = latest_value = None
    attempted = False

    def check_stop():
        if poll_stop():
            raise CycleStopped("F9 stop requested")

    def wait(duration):
        if wait_for_countdown(poll_stop, time.monotonic() + duration) == STOP_ID:
            raise CycleStopped("F9 stop requested")

    def read():
        nonlocal latest_frame, latest_value
        check_stop()
        frame = capture.grab(window.handle)
        stamp = datetime.now(timezone.utc).isoformat()
        value = analyzer.analyze(frame, settings, f"window:0x{window.handle:x}", stamp)
        latest_frame, latest_value = frame, value
        record("cycle_observation", observation=value.to_dict())
        check_stop()
        return value

    def press(action):
        nonlocal attempted
        check_stop()
        record("cycle_action", action=action, bound_key=settings.game_key_bindings.get(action))
        # Set before dispatch so cleanup also covers interrupted key holds.
        attempted = True
        tap_action(action, lambda: capture.bounds(window.handle), send, wait)

    code = 0
    try:
        run_one_cycle(read, press, wait, time.monotonic, record)
        print("Single cycle ended. Command attempts completed; check Spoil/Sweep and loot in the game.", flush=True)
    except (Exception, KeyboardInterrupt) as error:
        code = 1
        record("cycle_stopped", reason=str(error) or "Interrupted")
        print(f"Cycle stopped: {error}", flush=True)
        if attempted:
            try:
                tap_action("cancel", lambda: capture.bounds(window.handle), send)
                record("cancel_target_sent")
            except Exception as stop_error:
                record("cancel_target_failed", reason=str(stop_error))
                print("Press Escape in LU4 to stop any existing autoattack.", flush=True)
    finally:
        if latest_frame is not None and latest_value is not None:
            path = save_bundle(ROOT / "diagnostics", latest_frame, latest_value, settings, control_events=events)
            print(f"Report ZIP: {path}", flush=True)
    return code
