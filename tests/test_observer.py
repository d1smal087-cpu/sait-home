import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from lu4_observer.config import LEFT_JOURNAL_REGION, LEGACY_JOURNAL_REGION, OCR_REGIONS, Settings
from lu4_observer.diagnostics import save_bundle
from lu4_observer.recognition import Analyzer, Resource, TextReading, parse_resource


class ScriptedReader:
    def __init__(self):
        self.values = []

    def feed(self, name="Ghoul", hp="1068 / 1068", confidence=0.99):
        self.values = [TextReading(name, confidence), TextReading(hp, confidence),
                       TextReading("2031 / 2031", 0.99), TextReading("444 / 456", 0.99)]

    def read(self, image):
        return self.values.pop(0)


class ResourceTests(unittest.TestCase):
    def test_zero_hp_and_spaces(self):
        self.assertEqual(parse_resource(" 0 / 1068 "), Resource(0, 1068))

    def test_invalid_or_ambiguous_ocr_stays_unknown(self):
        for value in ("O / 1068", "0", "0/0", "1200/1068", "HP: 0 / 1068", "0/1068 1/2", "-1/1068", ""):
            with self.subTest(value=value):
                self.assertIsNone(parse_resource(value))


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load()
        self.reader = ScriptedReader()
        self.analyzer = Analyzer(self.reader)
        self.image = Image.new("RGB", tuple(self.settings.reference_size), "black")

    def observe(self, name="Ghoul", hp="1068 / 1068", confidence=0.99, second=0, source="window:1", image=None):
        self.reader.feed(name, hp, confidence)
        return self.analyzer.analyze(image or self.image, self.settings, source, f"2026-11-01T00:00:{second:02d}+00:00")

    def test_allowed_alive_target_and_player_resources(self):
        value = self.observe()
        self.assertTrue(value.allowed_target)
        self.assertEqual(value.target_state, "alive")
        self.assertEqual(value.player_hp.percent, 100)
        self.assertEqual(value.player_mp.current, 444)
        self.assertFalse(value.stable)

    def test_dead_needs_two_fresh_observations(self):
        self.assertFalse(self.observe(hp="0/1068").stable)
        value = self.observe(hp="0/1068", second=2)
        self.assertEqual(value.target_state, "dead")
        self.assertTrue(value.stable)

    def test_low_confidence_zero_is_not_death(self):
        value = self.observe(hp="0/1068", confidence=0.4)
        self.assertEqual(value.target_state, "unknown")
        self.assertIsNone(value.target_hp)
        self.assertFalse(value.allowed_target)

    def test_empty_name_is_not_a_dead_target(self):
        value = self.observe(name="", hp="0/1068")
        self.assertEqual(value.target_state, "unknown")

    def test_lost_target_does_not_reuse_previous_hp(self):
        self.observe(hp="0/1068")
        missing = self.observe(name="", hp="", second=2)
        self.assertIsNone(missing.target_hp)
        self.assertEqual(missing.target_state, "unknown")
        self.assertFalse(self.observe(hp="0/1068", second=4).stable)

    def test_only_exact_allowed_names(self):
        for name, allowed in (("Dead Seeker", True), (" dead   seeker ", True), ("Granite Golem", False),
                              ("Ghoul Player", False), ("Gh0ul", False)):
            with self.subTest(name=name):
                self.assertEqual(self.observe(name=name).allowed_target, allowed)

    def test_changed_window_or_target_cannot_confirm_old_death(self):
        self.observe(hp="0/1068")
        self.assertFalse(self.observe(hp="0/1068", second=2, source="window:2").stable)
        self.assertFalse(self.observe(name="Dead Seeker", hp="0/1068", second=4, source="window:2").stable)

    def test_stale_duplicate_and_offline_frames_never_confirm(self):
        self.observe(hp="0/1068")
        self.assertFalse(self.observe(hp="0/1068").stable)
        self.assertFalse(self.observe(hp="0/1068", second=30).stable)
        self.assertFalse(self.observe(hp="0/1068", second=32, source="saved-image").stable)
        self.assertFalse(self.observe(hp="0/1068", second=34, source="saved-image").stable)

    def test_size_change_requires_calibration(self):
        value = self.observe(image=Image.new("RGB", (1280, 720)))
        self.assertEqual(value.target_state, "uncalibrated")
        self.assertFalse(value.stable)
        self.assertFalse(value.allowed_target)

    def test_reset_invalidates_confirmation(self):
        self.observe(hp="0/1068")
        self.analyzer.reset()
        self.assertFalse(self.observe(hp="0/1068", second=2).stable)


class SettingsAndDiagnosticTests(unittest.TestCase):
    def test_legacy_journal_upgrade_preserves_other_settings_and_file(self):
        settings = Settings.load()
        settings.regions["journal"] = list(LEGACY_JOURNAL_REGION)
        settings.regions["target_hp"] = [0.61, 0.11, 0.72, 0.14]
        settings.reference_size = [1600, 840]
        settings.interval_seconds = 3
        settings.allowed_targets = ["Dead Seeker"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            settings.save(path)
            original = path.read_bytes()
            expected = asdict(settings)
            expected["regions"]["journal"] = list(LEFT_JOURNAL_REGION)
            updated = Settings.load(path)
            self.assertEqual(asdict(updated), expected)
            self.assertEqual(path.read_bytes(), original)
            updated.save(path)
            self.assertEqual(Settings.load(path), updated)

    def test_custom_journal_is_not_overwritten(self):
        settings = Settings.load()
        settings.regions["journal"] = [0.01, 0.30, 0.28, 0.67]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            settings.save(path)
            self.assertEqual(Settings.load(path), settings)

    def test_left_journal_crop_covers_system_text_above_main_chat(self):
        settings = Settings.load()
        self.assertEqual(tuple(settings.regions["journal"]), LEFT_JOURNAL_REGION)
        self.assertEqual(settings.crop_box("journal", (1600, 838)), (4, 344, 431, 573))

    def test_new_size_requires_all_four_ocr_regions(self):
        settings = Settings.load()
        for name in OCR_REGIONS:
            self.assertFalse(settings.calibrated_for((1280, 720)))
            settings.set_region(name, list(settings.regions[name]), (1280, 720))
        self.assertTrue(settings.calibrated_for((1280, 720)))

    def test_invalid_region_does_not_change_previous_calibration(self):
        settings = Settings.load()
        before = json.dumps(settings.__dict__, sort_keys=True)
        with self.assertRaises(ValueError):
            settings.set_region("target_hp", [-1, 0, 1, 1], (1280, 720))
        self.assertEqual(json.dumps(settings.__dict__, sort_keys=True), before)

    def test_settings_roundtrip_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            settings = Settings.load()
            settings.save(path)
            self.assertEqual(Settings.load(path), settings)
            data = json.loads(path.read_text())
            data["interval_seconds"] = -1
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                Settings.load(path)

    def test_diagnostics_contain_matching_image_config_and_observation(self):
        settings, reader = Settings.load(), ScriptedReader()
        image = Image.new("RGB", tuple(settings.reference_size), "#223344")
        reader.feed(hp="0/1068")
        observation = Analyzer(reader).analyze(image, settings, "saved-image")
        with tempfile.TemporaryDirectory() as folder:
            path = save_bundle(Path(folder), image, observation, settings)
            with ZipFile(path) as archive:
                self.assertIn("frame.png", archive.namelist())
                for name in settings.regions:
                    self.assertIn(f"regions/{name}.png", archive.namelist())
                self.assertEqual(json.loads(archive.read("observation.json"))["target_hp"]["current"], 0)
                self.assertEqual(json.loads(archive.read("config.json"))["reference_size"], list(image.size))
                self.assertEqual(json.loads(archive.read("observation.json"))["source"], "saved-image")
                with archive.open("frame.png") as stream:
                    with Image.open(stream) as decoded:
                        self.assertEqual(decoded.size, image.size)


if __name__ == "__main__":
    unittest.main()
