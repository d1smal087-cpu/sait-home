import ctypes
import unittest

from lu4_observer.capture import CaptureUnavailable
from lu4_observer.controls import INPUT, KEYUP, SCANCODE, F2_SCAN, STOP_ID, f2_event, probe_hotkeys, tap_f2


class InputProbeTests(unittest.TestCase):
    def test_win32_input_layout(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_single_f2_down_and_up(self):
        calls = []
        checked = []
        tap_f2(lambda: checked.append(True), lambda event: calls.append(event) or 1, lambda duration: None)
        self.assertEqual(checked, [True])
        self.assertEqual(len(calls), 2)
        self.assertEqual([e.ki.wScan for e in calls], [F2_SCAN, F2_SCAN])
        self.assertEqual([e.ki.dwFlags for e in calls], [SCANCODE, SCANCODE | KEYUP])
        self.assertEqual([e.type for e in calls], [1, 1])

    def test_inactive_window_receives_no_input(self):
        calls = []
        def inactive():
            raise CaptureUnavailable("inactive")
        with self.assertRaises(CaptureUnavailable):
            tap_f2(inactive, lambda e: calls.append(e) or 1)
        self.assertEqual(calls, [])

    def test_interruption_releases_key(self):
        calls = []
        def interrupted(_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            tap_f2(lambda: None, lambda e: calls.append(e) or 1, interrupted)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[-1].ki.dwFlags & KEYUP)

    def test_rejected_keydown_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "keydown"):
            tap_f2(lambda: None, lambda e: 0)

    def test_hotkey_registration_failure_rolls_back(self):
        class Api:
            def __init__(self): self.registered = []; self.released = []
            def RegisterHotKey(self, window, key_id, flags, key):
                self.registered.append(key_id)
                return len(self.registered) == 1
            def UnregisterHotKey(self, window, key_id): self.released.append(key_id)
        api = Api()
        with self.assertRaisesRegex(RuntimeError, "F8"):
            with probe_hotkeys(api):
                self.fail("Failed registration must not arm the probe")
        self.assertEqual(api.released, [STOP_ID])

    def test_hotkeys_are_released_after_error(self):
        class Api:
            def __init__(self): self.registered = []; self.released = []
            def RegisterHotKey(self, window, key_id, flags, key): self.registered.append(key_id); return True
            def UnregisterHotKey(self, window, key_id): self.released.append(key_id)
        api = Api()
        with self.assertRaises(ValueError):
            with probe_hotkeys(api):
                raise ValueError("test")
        self.assertEqual(api.released, list(reversed(api.registered)))

    def test_keyup_failure_is_reported(self):
        values = iter([1, 0])
        with self.assertRaisesRegex(RuntimeError, "keyup"):
            tap_f2(lambda: None, lambda e: next(values), lambda _: None)


if __name__ == "__main__":
    unittest.main()
