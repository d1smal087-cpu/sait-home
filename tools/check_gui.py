"""Run the actual Tk interface and OCR on a saved synthetic frame.

Needs a display (on Linux, Xvfb). Does not test Windows capture or a game client.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import lu4_observer.gui as gui
from lu4_observer.config import Settings


def wait_for_result(root, app):
    deadline = time.monotonic() + 20
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    root.update()
    assert not app.busy, "OCR worker timed out"
    assert app.observation is not None, app.status.get()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    errors = []
    with tempfile.TemporaryDirectory() as directory:
        gui.ROOT = Path(directory)
        root = tk.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        app = gui.ObserverApp(root, Settings.load(), Path(directory) / "config.json")
        try:
            root.update()
            with Image.open(args.image) as source:
                image = source.convert("RGB")
            app.launch_job(None, image)
            wait_for_result(root, app)
            assert app.observation.target_name == "Ghoul", app.readings.get()
            assert app.observation.target_state == "dead", app.readings.get()
            assert "0/1068" in app.readings.get(), app.readings.get()
            assert len(app.canvas.find_all()) >= 13, "Preview or region overlays are missing"
            # Exercise the actual drag handler and its config persistence/reanalysis.
            app.region_choice.current(1)
            x, y, w, h = app.preview_geometry
            left, top, right, bottom = app.settings.regions["target_hp"]
            app.begin_selection(SimpleNamespace(x=x+left*w, y=y+top*h))
            app.update_selection(SimpleNamespace(x=x+right*w, y=y+bottom*h))
            app.finish_selection(SimpleNamespace(x=x+right*w, y=y+bottom*h))
            wait_for_result(root, app)
            assert app.config_path.is_file(), "Calibration did not save config.json"
            assert app.observation.target_state == "dead"
            app.pause()
            gui.messagebox.showinfo = lambda *args: None
            app.export()
            assert len(list((Path(directory)/"diagnostics").glob("*.zip"))) == 1
            assert len(list((Path(directory)/"runs").glob("*.jsonl"))) == 1
            assert not errors, errors
            if args.screenshot:
                import mss
                root.update()
                with mss.mss() as capture:
                    bounds = {"left": root.winfo_rootx(), "top": root.winfo_rooty(),
                              "width": root.winfo_width(), "height": root.winfo_height()}
                    shot = capture.grab(bounds)
                    Image.frombytes("RGB", shot.size, shot.rgb).save(args.screenshot)
            print("PASS: Tk UI, OCR worker, preview, drag calibration, diagnostic export and session log")
        finally:
            app.close()


if __name__ == "__main__":
    main()
