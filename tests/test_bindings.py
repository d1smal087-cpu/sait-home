import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from lu4_observer.config import Settings, LEGACY_BINDINGS, FUNCTION_BINDINGS
from lu4_observer.controls import require_function_bindings


class FunctionBindingTests(unittest.TestCase):
    def test_legacy_migration_preserves_other_settings_and_original_file(self):
        settings = Settings.load()
        settings.game_key_bindings = dict(LEGACY_BINDINGS)
        settings.regions['target_hp'] = [0.62, 0.10, 0.70, 0.13]
        settings.interval_seconds = 3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            settings.save(path)
            original = path.read_bytes()
            expected = asdict(settings)
            expected['game_key_bindings'] = dict(FUNCTION_BINDINGS)
            self.assertEqual(asdict(Settings.load(path)), expected)
            self.assertEqual(path.read_bytes(), original)

    def test_custom_bindings_are_preserved_and_not_silently_dispatched(self):
        settings = Settings.load()
        settings.game_key_bindings['spoil'] = 'F7'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            settings.save(path)
            loaded = Settings.load(path)
            self.assertEqual(loaded.game_key_bindings['spoil'], 'F7')
            with self.assertRaisesRegex(RuntimeError, 'F3'):
                require_function_bindings(loaded, ['spoil'])

    def test_full_function_row_profile_is_accepted(self):
        settings = Settings.load()
        require_function_bindings(settings, ['attack', 'spoil', 'sweep', 'pickup'])
        self.assertEqual(settings.game_key_bindings, FUNCTION_BINDINGS)
