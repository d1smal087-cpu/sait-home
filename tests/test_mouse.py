import unittest
from lu4_observer.controls import spoil_click_position, tap_mouse


class MouseProbeTests(unittest.TestCase):
    def test_spoil_icon_point(self):
        self.assertEqual(spoil_click_position((100, 40, 1600, 837), (590, 816)), (590, 816))

    def test_world_and_wrong_layout_rejected(self):
        for bounds, point in [((0, 0, 1600, 837), (800, 400)), ((0, 0, 1280, 720), (490, 776))]:
            with self.assertRaises(RuntimeError): spoil_click_position(bounds, point)

    def test_one_click_and_release(self):
        events, held = [], []
        tap_mouse(lambda: None, lambda e: events.append(e) or 1, held.append)
        self.assertEqual([e.type for e in events], [0, 0])
        self.assertEqual([e.mi.dwFlags for e in events], [2, 4])
        self.assertEqual(held, [0.08])

    def test_cancel_releases_mouse(self):
        events = []
        def stop(_): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            tap_mouse(lambda: None, lambda e: events.append(e) or 1, stop)
        self.assertEqual(events[-1].mi.dwFlags, 4)

    def test_invalid_position_never_clicks(self):
        events = []
        def invalid(): raise RuntimeError('position')
        with self.assertRaises(RuntimeError): tap_mouse(invalid, lambda e: events.append(e) or 1)
        self.assertEqual(events, [])
