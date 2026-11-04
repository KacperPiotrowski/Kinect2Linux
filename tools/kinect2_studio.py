#!/usr/bin/env python3
"""Kinect2 Studio MVP: non-invasive Qt RGB/IR/Depth and audio status viewer.

Uses the existing Kinect2Linux broker. Never opens sensor USB, manipulates
systemd/PipeWire, records a frame or uploads anything.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

try:
    import numpy as np
    from PySide6.QtCore import Qt, QPointF, QThread, QTimer, Signal
    from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
        QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget,
    )
except ImportError as exc:
    raise SystemExit(
        f"Kinect2 Studio import error: {exc}. "
        "If the missing module is PySide6 or numpy, install it in .venv-studio; "
        "see docs/KINECT2-STUDIO.md."
    ) from exc

from kinect2_linux import BrokerClient  # noqa: E402
from kinect2_linux.frame_client import (  # noqa: E402
    FrameClient, FrameTimeoutError,
)
from kinect2_studio_core import audio_presence, broker_summary  # noqa: E402
from kinect2_studio_pose import skeleton_geometry  # noqa: E402
from kinect2_linux.tracking import TrackingSession, TrackingUnavailable  # noqa: E402


def frame_image(kind: str, array) -> QImage:
    """Build an OWNED QImage. Borrowed arrays never outlive their frame mmap."""
    if kind == "rgb":
        # libfreenect2 broker RGB is BGRX, never raw RGB or packed BGR.
        bgr = np.ascontiguousarray(array[::2, ::2, :3])
        height, width = bgr.shape[:2]
        return QImage(
            bgr.data, width, height, bgr.strides[0],
            QImage.Format.Format_BGR888,
        ).copy()

    if kind == "ir":
        sample = array[::4, ::4]
        good = sample[np.isfinite(sample) & (sample > 0)]
        if good.size < 32:
            gray = np.zeros(array.shape, dtype=np.uint8)
        else:
            lo, hi = np.percentile(good, (2, 99.5))
            hi = max(float(hi), float(lo) + 1.0)
            safe = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
            normalized = np.clip((safe - lo) / (hi - lo), 0.0, 1.0)
            gray = np.ascontiguousarray(
                (255 * np.sqrt(normalized)).astype(np.uint8)
            )
        height, width = gray.shape
        return QImage(
            gray.data, width, height, gray.strides[0],
            QImage.Format.Format_Grayscale8,
        ).copy()

    # Raw depth is float32 millimetres. This is ONLY a false-colour preview,
    # not a calibrated RGB-to-depth projection or reconstructed 3D.
    valid = np.isfinite(array) & (array >= 500.0) & (array <= 4500.0)
    distance = np.clip(np.nan_to_num(array, nan=4500.0,
                                    posinf=4500.0, neginf=4500.0),
                       500.0, 4500.0)
    t = (distance - 500.0) / 4000.0
    red = (255.0 * (1.0 - t)).astype(np.uint8)
    green = (210.0 * (1.0 - abs(t - 0.5) * 2.0)).astype(np.uint8)
    blue = (255.0 * t).astype(np.uint8)
    rgb = np.ascontiguousarray(np.stack((red, green, blue), axis=-1))
    rgb[~valid] = 0
    height, width = rgb.shape[:2]
    return QImage(
        rgb.data, width, height, rgb.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


def overlay_geometry(image: QImage, lines, joints) -> QImage:
    """Draw an estimated 2D pose; source image timestamp may differ."""
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#56efbb"))
        pen.setWidth(3)
        painter.setPen(pen)
        width = image.width() - 1
        height = image.height() - 1
        for a, b in lines:
            painter.drawLine(QPointF(a[0] * width, a[1] * height),
                             QPointF(b[0] * width, b[1] * height))
        painter.setPen(QPen(QColor("#101923"), 1))
        painter.setBrush(QColor("#b6ff5b"))
        for x, y in joints:
            painter.drawEllipse(QPointF(x * width, y * height), 3.5, 3.5)
    finally:
        painter.end()
    return image


def overlay_body(image: QImage, result) -> QImage:
    """Draw a result on its originating frame (also used by offline tests)."""
    return overlay_geometry(image, *skeleton_geometry(result))


class PoseWorker(QThread):
    """Optional CPU analysis of a single, owned RGB snapshot.

    The overlay is rendered on precisely the frame that was inferred.
    Live RGB stays independent; this does not provide 3D tracking.
    """
    result_ready = Signal(object, float)
    state = Signal(str)

    def __init__(self):
        super().__init__()
        self._condition = threading.Condition()
        self._pending = None
        self._enabled = False

    def set_enabled(self, enabled: bool) -> None:
        with self._condition:
            self._enabled = bool(enabled)
            if not enabled:
                self._pending = None
            self._condition.notify_all()

    def is_enabled(self) -> bool:
        with self._condition:
            return self._enabled

    def offer(self, pixels, image: QImage, host_time_us: int,
              sequence: int) -> None:
        with self._condition:
            if not self._enabled or self.isInterruptionRequested():
                return
            # The BGR buffer and source QImage are owned by this subscriber.
            self._pending = (pixels, image, host_time_us, sequence)
            self._condition.notify_all()

    def stop(self) -> None:
        self.requestInterruption()
        with self._condition:
            self._pending = None
            self._condition.notify_all()

    def run(self):
        tracker = None
        try:
            while not self.isInterruptionRequested():
                with self._condition:
                    if self._enabled and self._pending is None:
                        self._condition.wait(timeout=0.2)
                    elif not self._enabled:
                        self._condition.wait(timeout=0.2)
                    enabled = self._enabled
                    pending = self._pending
                    self._pending = None
                if not enabled:
                    if tracker is not None:
                        tracker.close()
                        tracker = None
                    continue
                if pending is None:
                    continue
                if tracker is None:
                    tracker = TrackingSession("body", mode="basic")
                    self.state.emit("Ładowanie lokalnych modeli RTMPose-s…")
                pixels, source_image, published_us, seq = pending
                start = time.perf_counter()
                try:
                    result = tracker.process(pixels)
                except (TrackingUnavailable, ImportError, OSError,
                        RuntimeError, ValueError, TypeError) as exc:
                    self.state.emit("Śledzenie niedostępne: " + str(exc)[:140])
                    with self._condition:
                        self._enabled = False
                        self._pending = None
                    if tracker is not None:
                        tracker.close()
                        tracker = None
                    continue
                elapsed = (time.perf_counter() - start) * 1000.0
                with self._condition:
                    still_enabled = self._enabled
                if still_enabled and not self.isInterruptionRequested():
                    lines, joints = skeleton_geometry(result)
                    self.result_ready.emit(
                        (source_image, lines, joints, published_us, seq,
                         len(result.subjects)),
                        elapsed,
                    )
        finally:
            if tracker is not None:
                tracker.close()


class StreamWorker(QThread):
    state = Signal(str, str)
    def __init__(self, kind: str, *, pose_worker=None):
        super().__init__()
        self.kind = kind
        self.pose_worker = pose_worker if kind == "rgb" else None
        self._latest_lock = threading.Lock()
        self._latest = None

    def take_latest(self):
        """Return newest fully owned Qt image; older frames get dropped."""
        with self._latest_lock:
            newest = self._latest
            self._latest = None
            return newest

    def _publish(self, image: QImage, host_time_us: int, seq: int):
        with self._latest_lock:
            self._latest = (image, host_time_us, seq)

    def run(self):
        self._run_capture()

    def _run_capture(self):
        while not self.isInterruptionRequested():
            try:
                with FrameClient(self.kind, timeout=0.8) as camera:
                    self.state.emit(self.kind, "Połączono")
                    last_processed = 0.0
                    last_pose_offer = 0.0
                    while not self.isInterruptionRequested():
                        try:
                            frame, _skipped = camera.receive_latest(max_pending=16)
                        except FrameTimeoutError:
                            continue
                        moment = time.monotonic()
                        with frame:
                            # Avoid an unnecessary full-resolution frame copy.
                            # Any QImage crossing threads must own its bytes.
                            if moment - last_processed < 1.0 / 30.0:
                                continue
                            pixels = frame.as_numpy(copy=False)
                            try:
                                seq = frame.sequence
                                host_time_us = frame.host_time_us
                                if self.kind == "rgb":
                                    bgr = np.ascontiguousarray(
                                        pixels[::2, ::2, :3]
                                    )
                                    h, w = bgr.shape[:2]
                                    image = QImage(
                                        bgr.data, w, h, bgr.strides[0],
                                        QImage.Format.Format_BGR888,
                                    ).copy()
                                    pose = self.pose_worker
                                    if (pose is not None and pose.is_enabled()
                                            and moment - last_pose_offer >= 0.20):
                                        pose.offer(bgr, image.copy(),
                                                   host_time_us, seq)
                                        last_pose_offer = moment
                                else:
                                    image = frame_image(self.kind, pixels)
                            finally:
                                # Release the borrowed mmap view before close.
                                del pixels
                        last_processed = time.monotonic()
                        # Bounded single-slot mailbox: the Qt event queue
                        # never accumulates stale high-resolution frames.
                        self._publish(image, host_time_us, seq)
            except Exception as exc:
                if self.isInterruptionRequested():
                    break
                self.state.emit(self.kind, "Oczekiwanie: " + str(exc)[:110])
                # Reconnect only this subscriber. Never restart the broker.
                for _ in range(6):
                    if self.isInterruptionRequested():
                        break
                    self.msleep(150)
        self.state.emit(self.kind, "Zatrzymano")


class StatusWorker(QThread):
    report = Signal(object)

    def run(self):
        while not self.isInterruptionRequested():
            try:
                broker = broker_summary(BrokerClient(timeout=1.5).get_status())
            except (OSError, RuntimeError, ValueError) as exc:
                broker = "Broker niedostępny: " + str(exc)[:100]
            try:
                proc = subprocess.run(
                    ["pactl", "list", "short", "sources"],
                    capture_output=True, text=True, timeout=1.5, check=False,
                )
                audio = audio_presence(proc.stdout if proc.returncode == 0 else "")
            except (OSError, subprocess.TimeoutExpired):
                audio = audio_presence("")
            self.report.emit({"broker": broker, "audio": audio})
            for _ in range(20):
                if self.isInterruptionRequested():
                    break
                self.msleep(150)


class PreviewTile(QFrame):
    def __init__(self, title: str, placeholder: str):
        super().__init__()
        self.setObjectName("previewTile")
        self._image = None
        layout = QVBoxLayout(self)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("tileTitle")
        self.metrics = QLabel("—")
        self.metrics.setObjectName("small")
        heading.addWidget(name)
        heading.addStretch()
        heading.addWidget(self.metrics)
        layout.addLayout(heading)
        self.display = QLabel(placeholder)
        self.display.setMinimumSize(275, 190)
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display.setWordWrap(True)
        self.display.setObjectName("imageWell")
        layout.addWidget(self.display, 1)

    def show_frame(self, image: QImage, fps: float, age: float, seq: int):
        self._image = image
        self.metrics.setText(f"{fps:.1f} FPS · {age:.0f} ms · #{seq}")
        self._rescale()

    def show_state(self, message: str):
        self.metrics.setText(message)
        if self._image is None:
            self.display.setText(message)

    def reset(self):
        self._image = None
        self.metrics.setText("—")
        self.display.clear()
        self.display.setText("Podgląd zatrzymany")

    def _rescale(self):
        if self._image is None or self.display.width() <= 0:
            return
        pixmap = QPixmap.fromImage(self._image)
        self.display.setPixmap(pixmap.scaled(
            self.display.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


class StudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kinect2 Studio — eksperymentalne GUI")
        self.resize(1350, 870)
        self._quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self._quit_shortcut.activated.connect(self.close)
        self._workers: dict[str, StreamWorker] = {}
        self._stopping = False
        self._closing = False
        self._pose_worker = None
        self._pose_frame_stats = [time.monotonic(), 0, 0.0]
        self._present_counts = {}

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #111821; color: #e9eff7; font-size: 13px; }
            QLabel#hero { font-size: 29px; font-weight: 700; }
            QLabel#subtitle, QLabel#small { color: #8fa5bd; }
            QLabel#tileTitle { font-size: 16px; font-weight: 700; }
            QFrame#previewTile, QFrame#sidePanel {
                background: #1a2430; border: 1px solid #304255;
                border-radius: 12px;
            }
            QLabel#imageWell {
                background: #0b1119; color: #91a6b8;
                border: 1px solid #273443; border-radius: 8px;
            }
            QPushButton, QComboBox {
                background: #28394b; color: #f2f6fb; border: 1px solid #476077;
                border-radius: 7px; padding: 10px 13px;
            }
            QPushButton:hover { background: #345169; }
            QPushButton#start { background: #15795f; border-color: #22977a; }
            QPushButton#start:hover { background: #1a9976; }
            QPushButton:disabled { color: #627588; background: #25303a; }
            QSplitter::handle { background: #111821; }
        """)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        top = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Kinect2 Studio")
        title.setObjectName("hero")
        heading.addWidget(title)
        sub = QLabel("RGB · Infrared · Depth · Audio | Jeden broker USB")
        sub.setObjectName("subtitle")
        heading.addWidget(sub)
        top.addLayout(heading)
        top.addStretch()
        self.mode = QComboBox()
        self.mode.addItems(["Basic", "Advanced"])
        self.mode.currentIndexChanged.connect(self._set_mode)
        top.addWidget(self.mode)
        self.pose_check = QCheckBox("Szkielet 2D · CPU")
        self.pose_check.setToolTip(
            "Opcjonalny RTMPose-s (17 punktów COCO); wymaga lokalnych modeli. "
            "Możesz przełączać w trakcie podglądu. Bez 3D i bez pobierania modeli."
        )
        top.addWidget(self.pose_check)
        self.pose_check.toggled.connect(self._pose_toggled)
        self.start_btn = QPushButton("▶ Start podglądu")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.start_preview)
        top.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■ Zatrzymaj")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_preview)
        top.addWidget(self.stop_btn)
        outer.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        previews = QWidget()
        grid = QGridLayout(previews)
        grid.setSpacing(12)
        self.tiles = {
            "rgb": PreviewTile("RGB · 1920 × 1080", "Oczekiwanie na podgląd RGB"),
            "ir": PreviewTile("Infrared · 512 × 424", "Oczekiwanie na podgląd IR"),
            "depth": PreviewTile("Depth · 512 × 424", "Oczekiwanie na pomiary Depth"),
        }
        self._preview_grid = grid
        self.pose_tile = PreviewTile(
            "Szkielet 2D · analizowana klatka RGB",
            "Włącz Szkielet 2D · CPU, aby zobaczyć analizę"
        )
        grid.addWidget(self.tiles["rgb"], 0, 0, 1, 2)
        self.pose_tile.hide()
        grid.addWidget(self.tiles["ir"], 1, 0)
        grid.addWidget(self.tiles["depth"], 1, 1)
        grid.setRowStretch(0, 2)
        grid.setRowStretch(1, 1)
        splitter.addWidget(previews)

        side = QFrame()
        side.setObjectName("sidePanel")
        sidebar = QVBoxLayout(side)
        sidebar.setContentsMargins(20, 20, 20, 20)
        sidebar.setSpacing(14)
        def field(label):
            t = QLabel(label)
            t.setObjectName("small")
            v = QLabel("Sprawdzanie…")
            v.setWordWrap(True)
            sidebar.addWidget(t)
            sidebar.addWidget(v)
            return v

        section = QLabel("DIAGNOSTYKA")
        section.setObjectName("tileTitle")
        sidebar.addWidget(section)
        self.broker = field("Broker RGB / IR / Depth")
        self.raw_audio = field("Fizyczny Kinect 4ch")
        self.mono = field("Kinect2_Mono")
        self.stereo = field("Kinect2_Stereo")
        self.pose_result = field("Body Tracking 2D (CPU)")
        self.pose_result.setText("Wyłączony")
        self.info = QLabel(
            "Podgląd na żywo. Nie zapisujemy obrazu, dźwięku ani danych "
            "biometrycznych. Nie otwieramy fizycznego USB."
        )
        self.info.setWordWrap(True)
        self.info.setObjectName("small")
        sidebar.addWidget(self.info)
        self.advanced = QLabel(
            "Advanced: metryki FPS, sekwencja klatki i czas od publikacji "
            "przez brokera (to nie opóźnienie sensora). "
            "Dane RGB i Depth nie są tutaj rejestrowane przestrzennie."
        )
        self.advanced.setWordWrap(True)
        self.advanced.setObjectName("small")
        sidebar.addWidget(self.advanced)
        sidebar.addStretch()
        splitter.addWidget(side)
        splitter.setSizes([960, 325])
        outer.addWidget(splitter, 1)

        foot = QLabel(
            "Motion Capture: tylko 2D (COCO-17, z RGB). "
            "Pełne śledzenie 3D i nagrywanie sesji nie są jeszcze dostępne."
        )
        foot.setObjectName("small")
        outer.addWidget(foot)
        self._set_mode()
        self._status = StatusWorker()
        self._status.report.connect(self._update_status)
        self._status.start()
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(33)
        self._render_timer.timeout.connect(self._render_latest)
        self._render_timer.start()

    def _set_mode(self):
        is_advanced = self.mode.currentText() == "Advanced"
        self.advanced.setVisible(is_advanced)
        for tile in self.tiles.values():
            tile.metrics.setVisible(is_advanced)

    def _update_status(self, data):
        self.broker.setText(data["broker"])
        audio = data["audio"]
        self.raw_audio.setText("Dostępne" if audio["raw"] else "Brak / nieznane")
        self.mono.setText("Dostępne" if audio["mono"] else "Brak / nieznane")
        self.stereo.setText("Dostępne" if audio["stereo"] else "Brak / nieznane")

    def _spawn_stream(self, kind: str):
        tile = self.tiles[kind]
        tile.show_state("Łączenie z brokerem…")
        worker = StreamWorker(
            kind, pose_worker=self._pose_worker if kind == "rgb" else None
        )
        worker.state.connect(self._show_state)
        self._workers[kind] = worker
        self._present_counts[kind] = [time.monotonic(), 0, 0.0]
        worker.finished.connect(lambda key=kind: self._worker_finished(key))
        worker.start()

    def start_preview(self):
        if self._workers or self._stopping or self._closing:
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pose_result.setText(
            "Oczekiwanie na RGB" if self.pose_check.isChecked() else "Wyłączony"
        )
        self._pose_frame_stats = [time.monotonic(), 0, 0.0]
        self.pose_tile.reset()
        self._pose_worker = PoseWorker()
        self._pose_worker.state.connect(self._pose_state)
        self._pose_worker.result_ready.connect(self._pose_result_ready)
        self._pose_worker.finished.connect(self._pose_finished)
        self._pose_worker.set_enabled(self.pose_check.isChecked())
        self._pose_worker.start()
        for kind in self.tiles:
            self._spawn_stream(kind)

    def _pose_toggled(self, checked: bool):
        if self._stopping or self._closing:
            return
        self._set_pose_tile_visible(checked)
        self.pose_tile.reset()
        if self._pose_worker is not None:
            self._pose_worker.set_enabled(checked)
        self.pose_result.setText(
            "Oczekiwanie na analizę RGB…" if checked else "Wyłączony"
        )

    def _pose_state(self, message: str):
        if self.pose_check.isChecked() and not self._stopping:
            self.pose_result.setText(message)

    def _set_pose_tile_visible(self, show: bool):
        grid = self._preview_grid
        rgb = self.tiles["rgb"]
        grid.removeWidget(rgb)
        if show:
            grid.addWidget(rgb, 0, 0, 1, 1)
            grid.addWidget(self.pose_tile, 0, 1, 1, 1)
            self.pose_tile.show()
        else:
            grid.removeWidget(self.pose_tile)
            self.pose_tile.hide()
            grid.addWidget(rgb, 0, 0, 1, 2)

    def _pose_result_ready(self, result, elapsed_ms: float):
        if not self.pose_check.isChecked() or self._stopping:
            return
        source_image, lines, joints, published_us, seq, people = result
        annotated = overlay_geometry(source_image, lines, joints)
        now = time.monotonic()
        stats = self._pose_frame_stats
        stats[1] += 1
        if now - stats[0] >= 1.0:
            stats[2] = stats[1] / (now - stats[0])
            stats[0], stats[1] = now, 0
        age_ms = max(0.0, (time.monotonic_ns() // 1000 -
                            published_us) / 1000.0)
        self.pose_tile.show_frame(annotated, stats[2], age_ms, seq)
        self.pose_result.setText(
            f"{people} osób · inferencja {elapsed_ms:.0f} ms · "
            f"wynik {age_ms:.0f} ms od publikacji RGB"
        )

    def _pose_finished(self):
        if self._pose_worker is not None:
            self._pose_worker.wait()
            self._pose_worker = None
        self._complete_stop()

    def _render_latest(self):
        if self._stopping or self._closing:
            return
        for kind, worker in list(self._workers.items()):
            latest = worker.take_latest()
            if latest is None:
                continue
            image, host_time_us, seq = latest
            now = time.monotonic()
            stats = self._present_counts.get(kind)
            if stats is None:
                continue
            stats[1] += 1
            if now - stats[0] >= 1.0:
                stats[2] = stats[1] / (now - stats[0])
                stats[0], stats[1] = now, 0
            age_ms = max(
                0.0, (time.monotonic_ns() // 1000 - host_time_us) / 1000.0
            )
            self.tiles[kind].show_frame(image, stats[2], age_ms, seq)

    def _show_state(self, kind, message):
        if kind in self._workers:
            self.tiles[kind].show_state(message)

    def stop_preview(self):
        if (not self._workers and self._pose_worker is None) or self._stopping:
            return
        self._stopping = True
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.pose_check.setEnabled(False)
        self.pose_result.setText("Zatrzymywanie…")
        for worker in self._workers.values():
            worker.requestInterruption()
        if self._pose_worker is not None:
            self._pose_worker.stop()
        self._complete_stop()

    def _worker_finished(self, kind: str):
        worker = self._workers.get(kind)
        if worker is None:
            return
        worker.wait()
        del self._workers[kind]
        self._present_counts.pop(kind, None)
        self._complete_stop()

    def _complete_stop(self):
        if not self._stopping or self._workers or self._pose_worker is not None:
            return
        self._stopping = False
        for tile in self.tiles.values():
            tile.reset()
        self.pose_tile.reset()
        self.pose_result.setText("Wyłączony")
        self.start_btn.setEnabled(not self._closing)
        self.stop_btn.setEnabled(False)
        self.pose_check.setEnabled(not self._closing)
        if self._closing:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        self._closing = True
        if self._workers or self._pose_worker is not None:
            event.ignore()
            self.stop_preview()
            return
        self._render_timer.stop()
        self._status.requestInterruption()
        if not self._status.wait(100):
            event.ignore()
            # Keep the window and QThread object alive until status exits.
            QTimer.singleShot(200, self.close)
            return
        super().closeEvent(event)


def main() -> int:
    if os.geteuid() == 0:
        print("Run Kinect2 Studio as your regular desktop user, not root.", file=sys.stderr)
        return 2
    app = QApplication(sys.argv)
    app.setApplicationName("Kinect2 Studio")
    window = StudioWindow()

    # Python's default SIGINT turns Ctrl+C into KeyboardInterrupt. Unhandled
    # exceptions in slots can leave the Qt event loop in a broken state, and
    # repeated Ctrl+C then Ctrl+Z leads to an unresponsive suspended GUI.
    # Map terminal interrupts and SIGTERM to the very same asynchronous
    # cleanup as the window X / Ctrl+Q. We never call sys.exit in a slot.
    shutdown_queued = False

    def shutdown_from_terminal(_signum, _frame):
        nonlocal shutdown_queued
        if shutdown_queued or window._closing:
            return
        shutdown_queued = True
        # A POSIX signal may arrive in the middle of _render_latest().
        # Queue cleanup for the next Qt event-loop turn instead of closing
        # widgets re-entrantly from an interrupted Python callback.
        QTimer.singleShot(0, window.close)

    signal.signal(signal.SIGINT, shutdown_from_terminal)
    signal.signal(signal.SIGTERM, shutdown_from_terminal)

    # Qt runs a native event loop; this lightweight heartbeat makes pending
    # Python signals reliably dispatch even when no frame has arrived.
    heartbeat = QTimer(window)
    heartbeat.setInterval(100)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
