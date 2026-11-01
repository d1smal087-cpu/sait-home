from __future__ import annotations

import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from . import __version__
from .config import Settings
from .recognition import Observation


def metadata() -> dict:
    packages = {}
    for name in ("mss", "Pillow", "numpy", "opencv-python", "onnxruntime", "rapidocr_onnxruntime"):
        try:
            packages[name] = version(name)
        except Exception:
            packages[name] = "not installed"
    return {"observer_version": __version__, "python": sys.version.split()[0],
            "platform": platform.platform(), "packages": packages}


def save_bundle(folder: Path, image: Image.Image, observation: Observation, settings: Settings, control_events=None) -> Path:
    from io import BytesIO

    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = folder / f"lu4-diagnostic-{stamp}.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        def add_json(name, value):
            archive.writestr(name, json.dumps(value, ensure_ascii=False, indent=2))

        def add_image(name, value):
            stream = BytesIO()
            value.save(stream, "PNG")
            archive.writestr(name, stream.getvalue())

        add_json("observation.json", observation.to_dict())
        add_json("config.json", asdict(settings))
        add_json("system.json", metadata())
        if control_events is not None:
            add_json("controls.json", control_events)
        add_image("frame.png", image)
        for name in settings.regions:
            add_image(f"regions/{name}.png", image.crop(settings.crop_box(name, image.size)))
        archive.writestr("README.txt", "LU4 Observer: explicit local diagnostic export.\n"
                         "Frame is the last successfully analyzed image, not necessarily current.\n"
                         "Check captured_at and source in observation.json.\n"
                         + ("No game commands were sent. " if control_events is None else "Input attempts are recorded in controls.json. ")
                         + "No uploads are performed.\n")
    return path
