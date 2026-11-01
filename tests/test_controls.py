import ctypes
import unittest

from lu4_observer.capture import CaptureUnavailable, GameWindow
from lu4_observer.controls import INPUT, KEYUP, SCANCODE, F2_SCAN, STOP_ID, PROBE_ID, find_active_game, f2_event, probe_hotkeys, tap_f2, wait_for_countdown


class InputProbeTests(unittest.TestCase):
    def test_virtual_f2_events(self):
        down, up = f2_event(key_mode="virtual"), f2_event(True, key_mode="virtual")
        self.assertEqual((down.ki.wVk, down.ki.wScan, down.ki.dwFlags), (0x71, 0, 0))
        self.assertEqual((up.ki.wVk, up.ki.wScan, up.ki.dwFlags), (0x71, 0, KEYUP))

    def test_mode_and_hold_are_preserved_for_pair(self):
        for mode in ("scan", "virtual"):
            with self.subTest(mode=mode):
                calls, held = [], []
                tap_f2(lambda: None, lambda e: calls.append(e) or 1, held.append,
                       key_mode=mode, hold_seconds=0.3)
                self.assertEqual(held, [0.3])
                self.assertEqual(calls[0].ki.wVk, calls[1].ki.wVk)
                self.assertEqual(calls[0].ki.wScan, calls[1].ki.wScan)
                self.assertEqual(calls[1].ki.dwFlags, calls[0].ki.dwFlags | KEYUP)

    def test_invalid_mode_does_not_send_input(self):
        calls = []
        with self.assertRaises(ValueError):
            tap_f2(lambda: None, lambda e: calls.append(e) or 1, key_mode="invalid")
        self.assertEqual(calls, [])

    def test_unbounded_hold_is_rejected_before_input(self):
        for hold in (0, -1, 20, float("nan")):
            with self.subTest(hold=hold):
                calls = []
                with self.assertRaises(ValueError):
                    tap_f2(lambda: None, lambda e: calls.append(e) or 1, hold_seconds=hold)
                self.assertEqual(calls, [])

    def test_virtual_key_is_released_when_cancelled(self):
        calls = []
        def cancel(_): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            tap_f2(lambda: None, lambda e: calls.append(e) or 1, cancel, key_mode="virtual", hold_seconds=0.3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1].ki.wVk, 0x71)
        self.assertEqual(calls[-1].ki.dwFlags, KEYUP)

    def test_countdown_waits_for_deadline(self):
        times = iter([0, 1, 2])
        sleeps = []
        result = wait_for_countdown(lambda: False, 2, lambda: next(times), lambda n: sleeps.append(n))
        self.assertEqual(result, PROBE_ID)
        self.assertEqual(len(sleeps), 2)

    def test_countdown_stop_wins_at_deadline(self):
        result = wait_for_countdown(lambda: True, 2, lambda: 2, lambda n: self.fail("must not wait"))
        self.assertEqual(result, STOP_ID)

    def test_countdown_stop_before_deadline(self):
        stops = iter([False, True])
        result = wait_for_countdown(lambda: next(stops), 10, lambda: 0, lambda n: None)
        self.assertEqual(result, STOP_ID)

    def test_timer_mode_does_not_register_f8(self):
        class Api:
            def __init__(self): self.registered = []; self.released = []
            def RegisterHotKey(self, window, key_id, flags, key): self.registered.append(key_id); return True
            def UnregisterHotKey(self, window, key_id): self.released.append(key_id)
        api = Api()
        with probe_hotkeys(api, include_start=False):
            self.assertEqual(api.registered, [STOP_ID])
        self.assertEqual(api.released, [STOP_ID])

    def test_missing_game_can_be_found_after_start(self):
        class Capture:
            windows_now = []
            def windows(self, prefix): return self.windows_now
            def bounds(self, handle): return (0, 0, 1600, 837)
        capture = Capture()
        with self.assertRaisesRegex(CaptureUnavailable, "No LU4"):
            find_active_game(capture, "LU4 -")
        capture.windows_now = [GameWindow(55, "LU4 - game")]
        self.assertEqual(find_active_game(capture, "LU4 -").handle, 55)

    def test_only_active_game_is_selected(self):
        class Capture:
            def windows(self, prefix): return [GameWindow(11, "LU4 - a"), GameWindow(22, "LU4 - b")]
            def bounds(self, handle):
                if handle != 22: raise CaptureUnavailable("inactive")
                return (0, 0, 1600, 837)
        self.assertEqual(find_active_game(Capture(), "LU4 -").handle, 22)

    def test_inactive_games_are_rejected(self):
        class Capture:
            def windows(self, prefix): return [GameWindow(11, "LU4 - a")]
            def bounds(self, handle): raise CaptureUnavailable("inactive")
        with self.assertRaisesRegex(CaptureUnavailable, "not active"):
            find_active_game(Capture(), "LU4 -")

    def test_recreated_window_is_resolved_again(self):
        class Capture:
            handle = 11
            def windows(self, prefix): return [GameWindow(self.handle, "LU4 - game")]
            def bounds(self, handle): return (0, 0, 1600, 837)
        capture = Capture()
        self.assertEqual(find_active_game(capture, "LU4 -").handle, 11)
        capture.handle = 22
        self.assertEqual(find_active_game(capture, "LU4 -").handle, 22)

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
