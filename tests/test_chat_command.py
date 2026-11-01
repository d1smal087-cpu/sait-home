import unittest

from lu4_observer.capture import CaptureUnavailable
from lu4_observer.controls import KEYUP, SCANCODE, UNICODE, SPOIL_COMMAND, send_spoil_command


class ChatCommandTests(unittest.TestCase):
    def test_types_exact_command_and_submits_once_without_escape(self):
        events = []
        send_spoil_command(lambda: None, lambda event: events.append(event) or 1, lambda _: None)
        text = ''.join(chr(e.ki.wScan) for e in events if e.ki.dwFlags == UNICODE)
        self.assertEqual(text, '/useskill Spoil')
        keys = [(e.ki.wScan, e.ki.dwFlags) for e in events if not e.ki.dwFlags & UNICODE]
        self.assertEqual(keys, [(0x1C, SCANCODE), (0x1C, SCANCODE | KEYUP)])
        self.assertEqual(len(events), 2 * len(SPOIL_COMMAND) + 2)
        for down, up in zip(events[::2], events[1::2]):
            self.assertEqual(down.ki.wVk, 0)
            self.assertEqual(up.ki.wScan, down.ki.wScan)
            self.assertEqual(up.ki.dwFlags, down.ki.dwFlags | KEYUP)

    def test_inactive_game_receives_no_input(self):
        events = []
        def inactive():
            raise CaptureUnavailable('inactive')
        with self.assertRaises(CaptureUnavailable):
            send_spoil_command(inactive, lambda e: events.append(e) or 1, lambda _: None)
        self.assertEqual(events, [])

    def test_losing_focus_during_text_does_not_submit(self):
        events = []
        checks = 0
        def focus():
            nonlocal checks
            checks += 1
            if checks == 3:
                raise CaptureUnavailable('inactive')
        with self.assertRaises(CaptureUnavailable):
            send_spoil_command(focus, lambda e: events.append(e) or 1, lambda _: None)
        self.assertEqual(len(events), 4)
        self.assertTrue(all(e.ki.dwFlags & UNICODE for e in events))

    def test_losing_focus_before_enter_does_not_submit(self):
        events = []
        checks = 0
        def focus():
            nonlocal checks
            checks += 1
            if checks > len(SPOIL_COMMAND):
                raise CaptureUnavailable('inactive')
        with self.assertRaises(CaptureUnavailable):
            send_spoil_command(focus, lambda e: events.append(e) or 1, lambda _: None)
        self.assertEqual(len(events), 2 * len(SPOIL_COMMAND))

    def test_cancellation_releases_character_without_enter(self):
        events = []
        def stop(_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            send_spoil_command(lambda: None, lambda e: events.append(e) or 1, stop)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].ki.dwFlags, UNICODE | KEYUP)

    def test_rejected_text_down_stops_before_enter(self):
        events = []
        with self.assertRaisesRegex(RuntimeError, 'keydown'):
            send_spoil_command(lambda: None, lambda e: events.append(e) or 0, lambda _: None)
        self.assertEqual(len(events), 1)

    def test_rejected_text_up_stops_before_enter(self):
        events = []
        def send(event):
            events.append(event)
            return 0 if event.ki.dwFlags & KEYUP else 1
        with self.assertRaisesRegex(RuntimeError, 'keyup'):
            send_spoil_command(lambda: None, send, lambda _: None)
        self.assertEqual(len(events), 2)
