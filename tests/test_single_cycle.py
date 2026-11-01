import unittest
from types import SimpleNamespace

from lu4_observer.recognition import Resource
from lu4_observer.single_cycle import CyclePolicy, CycleStopped, run_one_cycle


def view(hp=1068, *, stable=True, name="Ghoul", own_hp=1844, allowed=True):
    return SimpleNamespace(target_name=name, target_hp=Resource(hp, 1068) if hp is not None else None,
                           target_state="unknown" if hp is None else ("dead" if hp == 0 else "alive"),
                           stable=stable, allowed_target=allowed, calibrated=True,
                           player_hp=Resource(own_hp, 1844), player_mp=Resource(407, 407))


class Harness:
    def __init__(self, observations):
        self.observations = iter(observations)
        self.last = None
        self.time = 0
        self.actions = []
        self.events = []

    def read(self):
        self.last = next(self.observations, self.last)
        return self.last

    def press(self, action): self.actions.append(action)
    def wait(self, duration): self.time += duration
    def record(self, event, **data): self.events.append((event, data))
    def run(self, **overrides):
        run_one_cycle(self.read, self.press, self.wait, lambda: self.time, self.record, CyclePolicy(**overrides))


class SingleCycleTests(unittest.TestCase):
    def test_one_complete_cycle_does_not_search_for_another_target(self):
        h = Harness([view(stable=False), view(), view(), view(800), view(0, stable=False), view(0), view(None), view(None)])
        h.run()
        self.assertEqual(h.actions, ["spoil", "attack", "sweep", "pickup"])
        self.assertEqual(h.events[-1][0], "cycle_finished")
        self.assertFalse(h.events[-1][1]["spoil_success_confirmed"])
        self.assertFalse(h.events[-1][1]["loot_confirmed"])

    def test_wrong_target_never_receives_commands(self):
        h = Harness([view(name="Granite Golem", allowed=False)])
        with self.assertRaises(CycleStopped): h.run()
        self.assertEqual(h.actions, [])

    def test_low_player_health_never_starts(self):
        h = Harness([view(own_hp=500)])
        with self.assertRaisesRegex(CycleStopped, "HP below"): h.run()
        self.assertEqual(h.actions, [])

    def test_already_damaged_target_never_starts(self):
        h = Harness([view(900)])
        with self.assertRaisesRegex(CycleStopped, "undamaged"): h.run()
        self.assertEqual(h.actions, [])

    def test_no_damage_stops_chase(self):
        h = Harness([view()])
        with self.assertRaisesRegex(CycleStopped, "No target HP progress"): h.run()
        self.assertEqual(h.actions, ["spoil", "attack"])
        self.assertLess(h.time, 10)

    def test_target_switch_stops_before_attack(self):
        h = Harness([view(), view(name="Dead Seeker")])
        with self.assertRaisesRegex(CycleStopped, "target changed"): h.run()
        self.assertEqual(h.actions, ["spoil"])

    def test_target_loss_stops_before_sweep(self):
        h = Harness([view(), view(), view(None, allowed=False)])
        with self.assertRaisesRegex(CycleStopped, "Lost target"): h.run()
        self.assertEqual(h.actions, ["spoil", "attack"])

    def test_unconfirmed_death_never_sweeps(self):
        h = Harness([view(), view(), view(0, stable=False)])
        with self.assertRaises(CycleStopped): h.run()
        self.assertNotIn("sweep", h.actions)

    def test_drop_in_player_health_stops_fight(self):
        h = Harness([view(), view(), view(800, own_hp=500)])
        with self.assertRaisesRegex(CycleStopped, "HP below"): h.run()
        self.assertEqual(h.actions, ["spoil", "attack"])

    def test_target_health_increase_stops_fight(self):
        h = Harness([view(), view(), view(500), view(900)])
        with self.assertRaisesRegex(CycleStopped, "HP increased"): h.run()

    def test_combat_deadline_stops_even_with_damage(self):
        h = Harness([view(), view(), view(900), view(800), view(700), view(600)])
        with self.assertRaisesRegex(CycleStopped, "Combat time limit"): h.run(combat_timeout=1)
        self.assertNotIn("sweep", h.actions)

    def test_stop_during_spoil_wait_prevents_attack(self):
        h = Harness([view()])
        def stop(_): raise CycleStopped("F9")
        with self.assertRaisesRegex(CycleStopped, "F9"):
            run_one_cycle(h.read, h.press, stop, lambda: h.time, h.record)
        self.assertEqual(h.actions, ["spoil"])
