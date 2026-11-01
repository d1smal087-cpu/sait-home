from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="LU4 Observer — локальное наблюдение за окном игры")
    parser.add_argument("--config", type=Path, help="Путь к config.json")
    parser.add_argument("--image", type=Path, help="Проанализировать сохранённый снимок вместо окна")
    parser.add_argument("--output", type=Path, help="Сохранить JSON; используется вместе с --image")
    parser.add_argument("--check", action="store_true", help="Проверить зависимости и инициализацию OCR")
    args = parser.parse_args()
    if args.output and not args.image:
        parser.error("--output требует --image")
    try:
        from lu4_observer.config import Settings

        settings = Settings.load(args.config)
        if args.check:
            from lu4_observer.diagnostics import metadata
            from lu4_observer.recognition import LocalOCR

            LocalOCR()
            print(json.dumps({**metadata(), "ocr": "ready", "live_capture": sys.platform == "win32"},
                             ensure_ascii=False, indent=2))
            return 0
        if args.image:
            from PIL import Image
            from lu4_observer.recognition import Analyzer, LocalOCR

            with Image.open(args.image) as source:
                image = source.convert("RGB")
            result = Analyzer(LocalOCR()).analyze(image, settings, "saved-image").to_dict()
            text = json.dumps(result, ensure_ascii=False, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0
        from lu4_observer.capture import enable_dpi_awareness

        enable_dpi_awareness()
        from lu4_observer.gui import run

        run(settings, args.config)
        return 0
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
