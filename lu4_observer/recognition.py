from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

from PIL import Image, ImageOps

from .config import OCR_REGIONS, Settings


@dataclass(frozen=True)
class TextReading:
    text: str
    confidence: float


@dataclass(frozen=True)
class Resource:
    current: int
    maximum: int

    @property
    def percent(self) -> float:
        return round(self.current * 100 / self.maximum, 1)


class Reader(Protocol):
    def read(self, image: Image.Image) -> TextReading: ...


class LocalOCR:
    """CPU-only OCR, using models bundled with rapidocr_onnxruntime."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self.engine = RapidOCR(
            intra_op_num_threads=2,
            inter_op_num_threads=1,
            det_use_cuda=False,
            cls_use_cuda=False,
            rec_use_cuda=False,
        )

    def read(self, image: Image.Image) -> TextReading:
        import numpy as np

        # Calibrated fields contain white/light UI text. Trim surrounding empty
        # bar/background: wide blank margins cause spurious OCR characters.
        image = image.convert("RGB")
        pixels = np.asarray(image).astype("int16")
        foreground = (pixels.min(axis=2) > 140) & ((pixels.max(axis=2) - pixels.min(axis=2)) < 90)
        if foreground.sum() < 4 or foreground.mean() > 0.75:
            return TextReading("", 0.0)
        bounds = Image.fromarray(foreground.astype("uint8") * 255).getbbox()
        assert bounds is not None
        x1, y1, x2, y2 = bounds
        image = image.crop((max(0, x1 - 3), max(0, y1 - 3), min(image.width, x2 + 3), min(image.height, y2 + 3)))
        image = ImageOps.invert(ImageOps.grayscale(image)).convert("RGB")
        image = image.resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS)
        bgr = np.asarray(image)[:, :, ::-1].copy()
        # Each calibrated crop is ONE text line. Detection can split overlapping
        # digit groups and lose the slash in HP; use the line recognizer directly.
        result, _ = self.engine(bgr, use_det=False, use_cls=False)
        if not result:
            return TextReading("", 0.0)
        # Without detection RapidOCR returns [text, confidence] for each line.
        return TextReading(" ".join(str(row[0]) for row in result), min(float(row[1]) for row in result))


def parse_resource(text: str) -> Resource | None:
    # Do not guess characters (O -> 0 etc.): a failed read must stay unknown.
    match = re.fullmatch(r"\s*(\d{1,7})\s*/\s*(\d{1,7})\s*", text)
    if not match:
        return None
    current, maximum = map(int, match.groups())
    if maximum <= 0 or current > maximum:
        return None
    return Resource(current, maximum)


def normalize_name(text: str) -> str:
    return " ".join(text.casefold().split())


@dataclass
class Observation:
    captured_at: str
    source: str
    image_size: tuple[int, int]
    calibrated: bool
    target_name: str | None
    allowed_target: bool
    target_hp: Resource | None
    player_hp: Resource | None
    player_mp: Resource | None
    target_state: str
    stable: bool
    raw: dict[str, TextReading]

    def to_dict(self) -> dict:
        result = asdict(self)
        for name in ("target_hp", "player_hp", "player_mp"):
            resource = getattr(self, name)
            if resource is not None:
                result[name]["percent"] = resource.percent
        return result


class Analyzer:
    def __init__(self, reader: Reader) -> None:
        self.reader = reader
        self.reset()

    def reset(self) -> None:
        self.previous: tuple | None = None
        self.previous_time: datetime | None = None

    def analyze(self, image: Image.Image, settings: Settings, source: str,
                captured_at: str | None = None) -> Observation:
        captured_at = captured_at or datetime.now(timezone.utc).isoformat()
        now = datetime.fromisoformat(captured_at)
        raw = {name: self.reader.read(image.crop(settings.crop_box(name, image.size))) for name in OCR_REGIONS}
        name_reading = raw["target_name"]
        target_name = name_reading.text.strip() if name_reading.confidence >= settings.min_confidence else None
        target_name = target_name or None

        def resource(key: str) -> Resource | None:
            reading = raw[key]
            return parse_resource(reading.text) if reading.confidence >= settings.min_confidence else None

        hp, own_hp, mp = (resource(key) for key in ("target_hp", "player_hp", "player_mp"))
        # With no target panel these crops show the game world. Ambient labels
        # may look like a target name with high OCR confidence. Only expose a
        # target when BOTH its name and a valid HP fraction were read this frame.
        # Keep all raw readings for diagnosis; never reuse a previous target.
        if target_name is None or hp is None:
            target_name, hp = None, None
        calibrated = settings.calibrated_for(image.size)
        if not calibrated:
            state = "uncalibrated"
        elif target_name is None or hp is None:
            state = "unknown"
        else:
            state = "dead" if hp.current == 0 else "alive"
        allowed = calibrated and target_name is not None and normalize_name(target_name) in {normalize_name(n) for n in settings.allowed_targets}
        # Two consecutive, fresh observations of the same named target are required.
        identity = (source, image.size, normalize_name(target_name or ""), hp.maximum if hp else None, state)
        gap = (now - self.previous_time).total_seconds() if self.previous_time else float("inf")
        stable = (source != "saved-image" and state in ("alive", "dead") and identity == self.previous
                  and 0 < gap <= max(6, settings.interval_seconds * 3))
        self.previous, self.previous_time = identity, now
        return Observation(captured_at, source, image.size, calibrated, target_name, allowed,
                           hp, own_hp, mp, state, stable, raw)
