from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEGACY_JOURNAL_REGION = (0.5613, 0.7088, 0.8031, 0.9582)
LEFT_JOURNAL_REGION = (0.0025, 0.41051, 0.2694, 0.6838)
OCR_REGIONS = ("target_name", "target_hp", "player_hp", "player_mp")
REGION_LABELS = {
    "target_name": "Имя цели",
    "target_hp": "HP цели (числа)",
    "player_hp": "HP персонажа (числа)",
    "player_mp": "MP персонажа (числа)",
    "minimap": "Миникарта",
    "journal": "Системный журнал",
}


@dataclass
class Settings:
    window_title_prefix: str
    reference_size: list[int]
    interval_seconds: float
    min_confidence: float
    allowed_targets: list[str]
    regions: dict[str, list[float]]
    calibrated_regions: list[str] = field(default_factory=list)
    game_key_bindings: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        source = path or ROOT / "config.json"
        if path is None and not source.exists():
            source = ROOT / "config.example.json"
        settings = cls(**json.loads(source.read_text(encoding="utf-8")))
        settings.validate()
        # Upgrade only the untouched 0.1.0 journal preset. Preserve every custom
        # region, calibration, and the on-disk file until the user saves settings.
        if tuple(settings.regions["journal"]) == LEGACY_JOURNAL_REGION:
            settings.regions["journal"] = list(LEFT_JOURNAL_REGION)
        return settings

    def validate(self) -> None:
        if not isinstance(self.window_title_prefix, str) or not self.window_title_prefix.strip():
            raise ValueError("window_title_prefix не должен быть пустым")
        if len(self.reference_size) != 2 or any(type(v) is not int or v < 100 for v in self.reference_size):
            raise ValueError("reference_size должен содержать ширину и высоту окна")
        if not math.isfinite(self.interval_seconds) or not 0.5 <= self.interval_seconds <= 60:
            raise ValueError("interval_seconds должен быть между 0.5 и 60")
        if not math.isfinite(self.min_confidence) or not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence должен быть между 0 и 1")
        if not self.allowed_targets or any(not isinstance(v, str) or not v.strip() for v in self.allowed_targets):
            raise ValueError("Укажите непустые имена allowed_targets")
        for name in REGION_LABELS:
            rect = self.regions.get(name, [])
            if len(rect) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in rect):
                raise ValueError(f"Некорректная область {name}")
            x1, y1, x2, y2 = rect
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                raise ValueError(f"Область {name} должна быть внутри кадра")

    def size_matches_reference(self, size: tuple[int, int]) -> bool:
        # Windows captures can differ by one vertical pixel at the same layout.
        # Keep width exact; larger size changes still require full calibration.
        return size[0] == self.reference_size[0] and abs(size[1] - self.reference_size[1]) <= 1

    def calibrated_for(self, size: tuple[int, int]) -> bool:
        return self.size_matches_reference(size) and set(OCR_REGIONS) <= set(self.calibrated_regions)

    def set_region(self, name: str, rect: list[float], size: tuple[int, int]) -> None:
        if name not in REGION_LABELS:
            raise ValueError(name)
        previous = self.regions[name]
        self.regions[name] = rect
        try:
            self.validate()
        except (TypeError, ValueError):
            self.regions[name] = previous
            raise
        if list(size) != self.reference_size:
            if not self.size_matches_reference(size):
                self.calibrated_regions = []
            self.reference_size = list(size)
        if name not in self.calibrated_regions:
            self.calibrated_regions.append(name)

    def save(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def crop_box(self, name: str, size: tuple[int, int]) -> tuple[int, int, int, int]:
        w, h = size
        x1, y1, x2, y2 = self.regions[name]
        return (int(x1 * w), int(y1 * h), max(int(x1 * w) + 1, round(x2 * w)),
                max(int(y1 * h) + 1, round(y2 * h)))
