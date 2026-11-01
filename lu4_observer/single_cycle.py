"""One manually selected target; never searches or repeats the cycle."""
from __future__ import annotations

from dataclasses import dataclass

from .recognition import normalize_name


class CycleStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class CyclePolicy:
    prepare_timeout: float = 8
    combat_timeout: float = 30
    progress_timeout: float = 5
    sample_interval: float = 0.8
    minimum_hp_percent: float = 50
    minimum_mp_percent: float = 20


def run_one_cycle(read, press, wait, clock, record, policy=CyclePolicy()):
    """Execute command attempts; neither Spoil success nor loot is inferred."""
    def check_player(value):
        if value.player_hp is None or value.player_mp is None:
            raise CycleStopped("Player HP/MP could not be read")
        if value.player_hp.percent < policy.minimum_hp_percent:
            raise CycleStopped("Player HP below the test limit")
        if value.player_mp.percent < policy.minimum_mp_percent:
            raise CycleStopped("Player MP below the test limit")

    def complete_target(value):
        return value.calibrated and value.allowed_target and value.target_hp is not None and value.target_name is not None

    deadline = clock() + policy.prepare_timeout
    while True:
        value = read()
        check_player(value)
        if complete_target(value) and value.stable and value.target_state == "alive":
            break
        if clock() >= deadline:
            raise CycleStopped("Select a living Ghoul or Dead Seeker and keep the game active")
        wait(policy.sample_interval)
    # Initial selection is manual. Start only on an undamaged mob for this test.
    if value.target_hp.current != value.target_hp.maximum:
        raise CycleStopped("Select an undamaged mob for the single-cycle test")
    identity = (normalize_name(value.target_name), value.target_hp.maximum)

    def check_target(observation):
        check_player(observation)
        if not complete_target(observation):
            raise CycleStopped("Lost target or target OCR")
        current = (normalize_name(observation.target_name), observation.target_hp.maximum)
        if current != identity:
            raise CycleStopped("Selected target changed")

    record("cycle_phase", phase="spoil")
    press("spoil")
    wait(2.0)
    value = read()
    check_target(value)
    if value.target_state != "alive":
        raise CycleStopped("Target died before our attack")
    record("cycle_phase", phase="attack")
    press("attack")
    started = clock()
    progress_at = started
    last_hp = value.target_hp.current
    while True:
        value = read()
        check_target(value)
        now = clock()
        hp = value.target_hp.current
        if hp > last_hp:
            raise CycleStopped("Target HP increased; target identity is uncertain")
        if hp < last_hp:
            progress_at = now
        last_hp = hp
        if value.target_state == "dead" and value.stable:
            break
        if now - started >= policy.combat_timeout:
            raise CycleStopped("Combat time limit reached")
        if now - progress_at >= policy.progress_timeout:
            raise CycleStopped("No target HP progress; chase stopped")
        wait(policy.sample_interval)
    record("cycle_phase", phase="sweep")
    press("sweep")
    wait(1.0)
    # Corpse selection may disappear after Sweep. Keep player health checks.
    value = read()
    check_player(value)
    if value.target_hp is not None and value.target_hp.current > 0:
        raise CycleStopped("A living target appeared after Sweep")
    record("cycle_phase", phase="pickup")
    press("pickup")
    wait(0.8)
    check_player(read())
    record("cycle_finished", commands_only=True, spoil_success_confirmed=False, loot_confirmed=False)
