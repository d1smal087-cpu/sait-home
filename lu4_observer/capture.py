from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

from PIL import Image, ImageStat


class CaptureUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class GameWindow:
    handle: int
    title: str


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)


class WindowsCapture:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CaptureUnavailable("Живой захват доступен только на Windows. Можно открыть сохранённый снимок.")
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.title_prefix = "LU4 -"
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = {
            "EnumWindows": ([self.callback_type, wintypes.LPARAM], wintypes.BOOL),
            "GetWindowTextLengthW": ([wintypes.HWND], ctypes.c_int),
            "GetWindowTextW": ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            "IsWindowVisible": ([wintypes.HWND], wintypes.BOOL),
            "IsIconic": ([wintypes.HWND], wintypes.BOOL),
            "GetForegroundWindow": ([], wintypes.HWND),
            "GetClientRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "ClientToScreen": ([wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def title(self, handle: int) -> str:
        length = self.api.GetWindowTextLengthW(handle)
        text = ctypes.create_unicode_buffer(length + 1)
        self.api.GetWindowTextW(handle, text, length + 1)
        return text.value

    def windows(self, prefix: str) -> list[GameWindow]:
        self.title_prefix = prefix
        found = []

        @self.callback_type
        def visit(handle, _):
            if not self.api.IsWindowVisible(handle):
                return True
            pid = wintypes.DWORD()
            self.api.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value == os.getpid():
                return True
            title = self.title(handle)
            if title.casefold().startswith(prefix.casefold()):
                found.append(GameWindow(int(handle), title))
            return True

        if not self.api.EnumWindows(visit, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return found

    def bounds(self, handle: int) -> tuple[int, int, int, int]:
        if not self.title(handle).casefold().startswith(self.title_prefix.casefold()):
            raise CaptureUnavailable("Выбранное окно LU4 больше не существует. Обнови список окон.")
        if not self.api.IsWindowVisible(handle) or self.api.IsIconic(handle):
            raise CaptureUnavailable("Окно игры закрыто или свёрнуто. Разверни LU4.")
        if self.api.GetForegroundWindow() != handle:
            raise CaptureUnavailable("Ожидание активного окна LU4. Переключись в игру; старый кадр не обновляется.")
        rect, point = wintypes.RECT(), wintypes.POINT(0, 0)
        if not self.api.GetClientRect(handle, ctypes.byref(rect)) or not self.api.ClientToScreen(handle, ctypes.byref(point)):
            raise CaptureUnavailable("Не удалось определить границы окна LU4.")
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w < 300 or h < 200:
            raise CaptureUnavailable("Слишком маленькое окно LU4.")
        return point.x, point.y, w, h

    def grab(self, handle: int) -> Image.Image:
        import mss

        before = self.bounds(handle)
        x, y, w, h = before
        with mss.mss() as screen:
            if not any(m["left"] <= x and m["top"] <= y and
                       x + w <= m["left"] + m["width"] and y + h <= m["top"] + m["height"]
                       for m in screen.monitors[1:]):
                raise CaptureUnavailable("Помести окно игры целиком на один монитор.")
            shot = screen.grab({"left": x, "top": y, "width": w, "height": h})
            frame = Image.frombytes("RGB", shot.size, shot.rgb)
        if self.bounds(handle) != before:
            raise CaptureUnavailable("Окно переместилось во время захвата. Повтори снимок.")
        stats = ImageStat.Stat(frame.resize((80, 40)).convert("L"))
        if stats.mean[0] < 5 and stats.stddev[0] < 2:
            raise CaptureUnavailable("Захват вернул чёрный кадр. Проверь оконный режим LU4.")
        return frame
