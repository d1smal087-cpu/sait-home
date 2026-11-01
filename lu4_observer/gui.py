from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .capture import CaptureUnavailable, WindowsCapture
from .config import OCR_REGIONS, REGION_LABELS, ROOT, Settings
from .diagnostics import save_bundle
from .recognition import Analyzer, LocalOCR, Observation, Resource


COLORS = ("#ffca68", "#ff808b", "#80e6a6", "#87caff", "#c3a1ff", "#67e6db")
STATES = {"alive": "Живая", "dead": "Мёртвая", "unknown": "Не удалось определить",
          "uncalibrated": "Требуется настройка областей"}


class ObserverApp:
    def __init__(self, root: tk.Tk, settings: Settings, config_path: Path | None) -> None:
        self.root, self.settings = root, settings
        self.config_path = config_path or ROOT / "config.json"
        self.running = False
        self.busy = False
        self.generation = 0
        self.analyzer_generation = -1
        self.analyzer: Analyzer | None = None
        self.messages: queue.Queue = queue.Queue()
        self.windows = []
        self.frame: Image.Image | None = None
        self.observation: Observation | None = None
        self.observation_settings: Settings | None = None
        self.preview_image = None
        self.preview_geometry = (0, 0, 1, 1)
        self.drag_start = None
        self.selection_id = None
        self.last_job = 0.0
        self.session_log: Path | None = None
        self.capture: WindowsCapture | None = None
        try:
            self.capture = WindowsCapture()
        except CaptureUnavailable:
            pass
        self._build_ui()
        self.refresh_windows()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.tick)

    def _build_ui(self) -> None:
        self.root.title("LU4 Observer 0.1 — только наблюдение")
        self.root.geometry("1250x850")
        self.root.minsize(920, 720)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", padding=(8, 6))
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill="x")
        self.window_choice = ttk.Combobox(toolbar, state="readonly", width=32)
        self.window_choice.pack(side="left", padx=(0, 6))
        self.window_choice.bind("<<ComboboxSelected>>", lambda _: self.pause())
        ttk.Button(toolbar, text="Обновить окна", command=self.refresh_windows).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Начать", command=self.start).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Пауза", command=self.pause).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Открыть снимок", command=self.open_image).pack(side="left", padx=3)
        self.status = tk.StringVar(value="Выбери окно, нажми «Начать» и переключись в LU4.")
        ttk.Label(self.root, textvariable=self.status, wraplength=1200, padding=(12, 4)).pack(fill="x")
        ttk.Label(self.root, text="Программа только читает экран. Игровые клавиши не отправляются.",
                  padding=(12, 2), foreground="#315b44").pack(fill="x")

        self.canvas = tk.Canvas(self.root, background="#171b22", highlightthickness=0, height=420)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=8)
        self.canvas.bind("<Configure>", lambda _: self.draw_preview())
        self.canvas.bind("<ButtonPress-1>", self.begin_selection)
        self.canvas.bind("<B1-Motion>", self.update_selection)
        self.canvas.bind("<ButtonRelease-1>", self.finish_selection)

        calibration = ttk.Frame(self.root, padding=(12, 0))
        calibration.pack(fill="x")
        ttk.Label(calibration, text="Область:").pack(side="left")
        self.region_choice = ttk.Combobox(calibration, state="readonly", values=list(REGION_LABELS.values()), width=24)
        self.region_choice.current(0)
        self.region_choice.pack(side="left", padx=6)
        ttk.Label(calibration, text="Поставь паузу и обведи нужную область на кадре мышью.").pack(side="left", padx=4)
        ttk.Button(calibration, text="Сохранить диагностику", command=self.export).pack(side="right")

        details = ttk.LabelFrame(self.root, text="Последний разобранный кадр", padding=8)
        details.pack(fill="x", padx=12, pady=8)
        self.readings = tk.StringVar(value="Нет данных. Поля появятся после первого захвата.")
        ttk.Label(details, textvariable=self.readings, justify="left", wraplength=1180).pack(anchor="w")
        self.raw_text = tk.StringVar(value="OCR: —")
        ttk.Label(details, textvariable=self.raw_text, foreground="#555555", wraplength=1180).pack(anchor="w", pady=(4, 0))
        self.calibration_status = tk.StringVar()
        ttk.Label(self.root, textvariable=self.calibration_status, padding=(12, 0), wraplength=1200).pack(fill="x")
        ttk.Label(self.root, text="Миникарта и журнал пока сохраняются как изображения; навигация и чтение журнала ещё не подключены.",
                  padding=(12, 6), wraplength=1200).pack(fill="x")

    def refresh_windows(self) -> None:
        self.pause(silent=True)
        try:
            self.windows = self.capture.windows(self.settings.window_title_prefix) if self.capture else []
        except Exception as error:
            self.status.set(f"Поиск окна: {error}")
            return
        self.window_choice["values"] = [f"{w.title}  [0x{w.handle:x}]" for w in self.windows]
        if self.windows:
            self.window_choice.current(0)
            self.status.set("Выбери окно, нажми «Начать» и переключись в LU4. Захват идёт только при активном окне игры.")
        else:
            self.window_choice.set("")
            self.status.set("Окно LU4 не найдено. Запусти игру и обнови список. Или открой сохранённый снимок.")

    def start(self) -> None:
        if self.capture is None or not self.windows or self.window_choice.current() < 0:
            messagebox.showinfo("Нет окна", "Запусти оконный LU4 на Windows и нажми «Обновить окна».")
            return
        self.generation += 1
        self.running = True
        self.last_job = 0
        self.status.set("Переключись в LU4. Для просмотра результатов вернись сюда; захват будет ждать активного окна игры.")

    def pause(self, silent: bool = False) -> None:
        self.running = False
        self.generation += 1
        if not silent:
            self.status.set("Пауза. Показан последний кадр, а не текущее состояние игры.")

    def tick(self) -> None:
        while True:
            try:
                generation, kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            if generation != self.generation:
                continue
            if kind == "result":
                self.frame, self.observation, self.observation_settings = payload
                self.show_observation()
                self.draw_preview()
                if self.running:
                    self.status.set("Кадр распознан. При переключении из LU4 новые кадры не считываются.")
                else:
                    self.status.set("Снимок разобран. Это сохранённое изображение, не живая игра.")
            else:
                self.status.set(str(payload))
        if self.running and not self.busy and time.monotonic() - self.last_job >= self.settings.interval_seconds:
            index = self.window_choice.current()
            if 0 <= index < len(self.windows) and self.capture:
                window = self.windows[index]
                try:
                    self.capture.bounds(window.handle)
                except Exception as error:
                    self.status.set(str(error))
                    self.last_job = time.monotonic()
                else:
                    self.launch_job(window.handle, None)
        self.root.after(150, self.tick)

    def launch_job(self, handle: int | None, image: Image.Image | None) -> None:
        if self.busy:
            return
        self.busy = True
        self.last_job = time.monotonic()
        generation = self.generation
        settings = Settings(**asdict(self.settings))
        self.status.set("Захват и распознавание… Первый запуск OCR может занять несколько секунд.")

        def work() -> None:
            try:
                if image is None:
                    assert self.capture is not None and handle is not None
                    frame = self.capture.grab(handle)
                    source = f"window:0x{handle:x}"
                else:
                    frame, source = image.copy(), "saved-image"
                captured_at = datetime.now(timezone.utc).isoformat()
                if self.analyzer is None:
                    self.analyzer = Analyzer(LocalOCR())
                if self.analyzer_generation != generation:
                    self.analyzer.reset()
                    self.analyzer_generation = generation
                result = self.analyzer.analyze(frame, settings, source, captured_at)
                self.messages.put((generation, "result", (frame, result, settings)))
            except Exception as error:
                if self.analyzer:
                    self.analyzer.reset()
                self.messages.put((generation, "error", f"Нет свежих данных: {error}"))

        threading.Thread(target=work, daemon=True).start()

    def open_image(self) -> None:
        if self.busy:
            messagebox.showinfo("Подожди", "Дождись завершения текущего распознавания.")
            return
        path = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp"), ("Все файлы", "*.*")])
        if not path:
            return
        self.pause(silent=True)
        try:
            with Image.open(path) as source:
                image = source.convert("RGB")
            self.launch_job(None, image)
        except Exception as error:
            messagebox.showerror("Не удалось открыть снимок", str(error))

    @staticmethod
    def resource_label(resource: Resource | None) -> str:
        return f"{resource.current}/{resource.maximum} ({resource.percent}%)" if resource else "не распознано"

    def show_observation(self) -> None:
        assert self.observation is not None
        value = self.observation
        stamp = datetime.fromisoformat(value.captured_at).astimezone().strftime("%H:%M:%S")
        allowed = "да" if value.allowed_target and value.calibrated else "нет / не определено"
        self.readings.set(
            f"Кадр: {stamp}  |  {value.image_size[0]}×{value.image_size[1]}  |  {value.source}\n"
            f"Цель: {value.target_name or 'не распознана'}  |  В списке разрешённых: {allowed}  |  "
            f"Состояние: {STATES[value.target_state]}  |  Повторное подтверждение: {'да' if value.stable else 'нет'}\n"
            f"HP цели: {self.resource_label(value.target_hp)}  |  HP персонажа: {self.resource_label(value.player_hp)}  |  "
            f"MP: {self.resource_label(value.player_mp)}")
        self.raw_text.set("OCR: " + "  |  ".join(f"{REGION_LABELS[k]}: {v.text or '—'} [{v.confidence:.0%}]" for k, v in value.raw.items()))
        self.update_calibration_label()
        try:
            if self.session_log is None:
                folder = ROOT / "runs"
                folder.mkdir(parents=True, exist_ok=True)
                self.session_log = folder / (datetime.now(timezone.utc).strftime("session-%Y%m%dT%H%M%S%fZ") + ".jsonl")
            with self.session_log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(value.to_dict(), ensure_ascii=False) + "\n")
        except OSError as error:
            messagebox.showerror("Журнал не сохранён", str(error))

    def update_calibration_label(self) -> None:
        if self.frame is None:
            return
        if self.settings.calibrated_for(self.frame.size):
            self.calibration_status.set("Размер соответствует настройкам. Проверь рамки; при необходимости подстрой их мышью.")
        else:
            missing = set(OCR_REGIONS) - set(self.settings.calibrated_regions) if list(self.frame.size) == self.settings.reference_size else set(OCR_REGIONS)
            names = ", ".join(REGION_LABELS[name] for name in OCR_REGIONS if name in missing)
            self.calibration_status.set(f"Другой размер или неполная настройка. Обведи области: {names}. Затем настрой миникарту и журнал.")

    def draw_preview(self) -> None:
        if self.frame is None:
            return
        width, height = max(self.canvas.winfo_width(), 2), max(self.canvas.winfo_height(), 2)
        scale = min(width / self.frame.width, height / self.frame.height)
        w, h = max(1, int(self.frame.width * scale)), max(1, int(self.frame.height * scale))
        x, y = (width - w) // 2, (height - h) // 2
        self.preview_geometry = x, y, w, h
        self.preview_image = ImageTk.PhotoImage(self.frame.resize((w, h), Image.Resampling.LANCZOS))
        self.canvas.delete("all")
        self.canvas.create_image(x, y, anchor="nw", image=self.preview_image)
        for (name, rect), color in zip(self.settings.regions.items(), COLORS):
            x1, y1, x2, y2 = rect
            self.canvas.create_rectangle(x + x1 * w, y + y1 * h, x + x2 * w, y + y2 * h, outline=color, width=2)
            self.canvas.create_text(x + x1 * w + 2, max(y + y1 * h - 2, y + 12), anchor="sw", text=REGION_LABELS[name], fill=color, font=("Segoe UI", 9, "bold"))

    def normalized_point(self, event) -> tuple[float, float]:
        x, y, w, h = self.preview_geometry
        return min(1, max(0, (event.x - x) / w)), min(1, max(0, (event.y - y) / h))

    def begin_selection(self, event) -> None:
        if self.frame is None or self.running or self.busy:
            self.status.set("Для настройки сначала нажми «Пауза» и дождись завершения распознавания.")
            return
        self.drag_start = self.normalized_point(event)
        self.selection_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="white", width=2, dash=(4, 3))

    def update_selection(self, event) -> None:
        if self.drag_start is not None and self.selection_id is not None:
            x, y, w, h = self.preview_geometry
            self.canvas.coords(self.selection_id, x + self.drag_start[0] * w, y + self.drag_start[1] * h, event.x, event.y)

    def finish_selection(self, event) -> None:
        if self.drag_start is None or self.frame is None:
            return
        start, end = self.drag_start, self.normalized_point(event)
        self.drag_start = None
        rect = [min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])]
        if (rect[2] - rect[0]) * self.frame.width < 8 or (rect[3] - rect[1]) * self.frame.height < 8:
            self.draw_preview()
            return
        name = list(REGION_LABELS)[self.region_choice.current()]
        try:
            self.settings.set_region(name, rect, self.frame.size)
            self.settings.save(self.config_path)
            self.generation += 1
            self.draw_preview()
            self.update_calibration_label()
            self.launch_job(None, self.frame)
        except Exception as error:
            messagebox.showerror("Настройка не сохранена", str(error))

    def export(self) -> None:
        if self.frame is None or self.observation is None or self.observation_settings is None:
            messagebox.showinfo("Нет кадра", "Сначала захвати окно или открой снимок.")
            return
        try:
            path = save_bundle(ROOT / "diagnostics", self.frame, self.observation, self.observation_settings)
            messagebox.showinfo("Диагностика сохранена", f"{path}\n\nВ архиве последний разобранный кадр, области и результаты OCR. "
                                "Автоматической отправки нет. Если нужна помощь, прикрепи этот ZIP в чат.")
        except Exception as error:
            messagebox.showerror("Не удалось сохранить диагностику", str(error))

    def close(self) -> None:
        self.running = False
        self.generation += 1
        self.root.destroy()


def run(settings: Settings, config_path: Path | None = None) -> None:
    root = tk.Tk()
    ObserverApp(root, settings, config_path)
    root.mainloop()
