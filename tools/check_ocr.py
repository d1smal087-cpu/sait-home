"""Exercise the actual bundled OCR on deterministic UI-like images, not a mock.

Run: python tools/check_ocr.py --font /path/to/DejaVuSans.ttf
These are synthetic samples, not evidence of compatibility with the live LU4 client.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

from lu4_observer.config import Settings
from lu4_observer.recognition import Analyzer, LocalOCR, Resource


def make_frame(settings, font_path, target, hp):
    image = Image.new("RGB", tuple(settings.reference_size), "#151c18")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 13)
    texts = {"target_name": target, "target_hp": hp, "player_hp": "2031 / 2031", "player_mp": "444 / 456"}
    for name, text in texts.items():
        x1, y1, x2, y2 = settings.crop_box(name, image.size)
        background = {"player_hp": "#a53342", "player_mp": "#3d73ba", "target_hp": "#993543"}.get(name, "#151c18")
        if hp.startswith("0") and name == "target_hp":
            background = "#151c18"
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=background)
        draw.text(((x1 + x2) / 2, (y1 + y2) / 2), text, font=font, fill="white", anchor="mm")
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--save-samples", type=Path)
    args = parser.parse_args()
    settings = Settings.load()
    analyzer = Analyzer(LocalOCR())
    for name, text, expected in (("Ghoul", "1068 / 1068", "alive"), ("Ghoul", "0 / 1068", "dead"),
                                 ("Dead Seeker", "725 / 1068", "alive")):
        image = make_frame(settings, args.font, name, text)
        observation = analyzer.analyze(image, settings, "saved-image")
        print(name, text, observation.target_state, {k: (v.text, round(v.confidence, 3)) for k, v in observation.raw.items()})
        assert observation.target_state == expected, observation.to_dict()
        assert observation.allowed_target, observation.to_dict()
        assert observation.player_hp == Resource(2031, 2031), observation.to_dict()
        assert observation.player_mp == Resource(444, 456), observation.to_dict()
        if args.save_samples:
            args.save_samples.mkdir(parents=True, exist_ok=True)
            image.save(args.save_samples / f"{name.replace(' ', '-')}-{expected}.png")
    blank = analyzer.analyze(Image.new("RGB", tuple(settings.reference_size), "#151c18"), settings, "saved-image")
    assert blank.target_state == "unknown" and blank.target_hp is None
    print("PASS: 3 rendered OCR cases + blank target")


if __name__ == "__main__":
    main()
