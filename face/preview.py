#!/usr/bin/env python3
"""Independent V4L2 preview and face detection (NOT authentication).

How it differs from howdy test:
 - the acquisition thread never waits for detection;
 - the detector analyzes only the newest frame, dropping older frames;
 - the GUI runs on the main thread and remains responsive.
No models are written, no PAM configuration is touched.
"""
import argparse
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

try:
    import dlib
except ImportError:
    dlib = None


class LatestFrame:
    """Single latest frame slot. Copies to avoid concurrent buffer mutation."""

    def __init__(self):
        self.cv = threading.Condition()
        self.number = 0
        self.frame = None
        self.arrived_at = 0.0
        self.closed = False

    def publish(self, image):
        with self.cv:
            self.frame = image.copy()
            self.number += 1
            self.arrived_at = time.monotonic()
            self.cv.notify_all()

    def get(self, last_number=-1, wait=0.1):
        with self.cv:
            if self.number == last_number and not self.closed:
                self.cv.wait_for(lambda: self.number != last_number or self.closed, timeout=wait)
            if self.frame is None or self.number == last_number:
                return None
            return self.number, self.arrived_at, self.frame.copy()

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()


@dataclass
class Detection:
    boxes: tuple = ()
    duration_ms: float = 0.0
    frame_number: int = 0
    received_at: float = 0.0
    error: str = ""


class LatestResult:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = Detection()

    def publish(self, result):
        with self.lock:
            self.value = result

    def get(self):
        with self.lock:
            return self.value


def capture_loop(cap, slot, stop, stats):
    try:
        while not stop.is_set():
            ok, frame = cap.read()
            if not ok:
                stats["capture_error"] = "Camera read failed — is the bridge running?"
                stop.set()
                break
            slot.publish(frame)
    finally:
        slot.close()
        cap.release()


def detect_loop(slot, result, stop, detector_type='auto', delay=0.0):
    try:
        if detector_type in ('dlib', 'auto') and dlib is not None:
            detect = dlib.get_frontal_face_detector()
            method = 'dlib/HOG'
        elif detector_type == 'dlib':
            result.publish(Detection(error='dlib is not installed'))
            return
        else:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            cascade = cv2.CascadeClassifier(cascade_path)
            if cascade.empty():
                result.publish(Detection(error='Cannot load OpenCV face detector'))
                return
            detect = cascade
            method = 'OpenCV/Haar'

        last = -1
        while not stop.is_set():
            packet = slot.get(last, 0.2)
            if packet is None:
                continue
            number, arrived, frame = packet
            last = number
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
            start = time.monotonic()
            if method == 'dlib/HOG':
                faces = detect(gray, 0)
                boxes = tuple((f.left(), f.top(), f.right(), f.bottom()) for f in faces)
            else:
                faces = detect.detectMultiScale(gray, scaleFactor=1.10, minNeighbors=4, minSize=(55, 55))
                boxes = tuple((int(x), int(y), int(x+w), int(y+h)) for x, y, w, h in faces)
            if delay:
                time.sleep(delay)  # only for automated concurrency tests
            elapsed = (time.monotonic()-start)*1000.0
            result.publish(Detection(boxes, elapsed, number, time.monotonic()))
    except Exception as ex:
        result.publish(Detection(error=f'{type(ex).__name__}: {ex}'))
        stop.set()


def run(device, backend):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open {device}. Run ./kinect2 run in another terminal.')
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    slot, result, stop = LatestFrame(), LatestResult(), threading.Event()
    stats = {"capture_error": ""}
    worker = threading.Thread(target=capture_loop, args=(cap, slot, stop, stats), daemon=True)
    analyzer = threading.Thread(target=detect_loop, args=(slot, result, stop, backend), daemon=True)
    worker.start()
    analyzer.start()
    window_name = 'Kinect2-Linux - IR preview (experimental)'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
    cv2.resizeWindow(window_name, 900, 745)
    print('Live IR preview + independent face DETECTION (not authentication).')
    print('Press Q or Esc in the preview window to stop. Other keys are ignored.')
    seen = -1
    shown = 0
    start = time.monotonic()
    fps = 0.0
    try:
        while not stop.is_set():
            item = slot.get(seen, 0.05)
            if item is not None:
                seen, _, frame = item
                shown += 1
                elapsed = time.monotonic() - start
                if elapsed >= 1.0:
                    fps = shown / elapsed
                    shown, start = 0, time.monotonic()
                state = result.get()
                # Only draw a recent detection; stale boxes could mislead.
                if time.monotonic() - state.received_at < 0.7:
                    for x1, y1, x2, y2 in state.boxes:
                        cv2.rectangle(frame, (x1,y1), (x2,y2), (0, 200, 0), 2)
                caption = f'PREVIEW {fps:.1f} fps | ANALYSIS {state.duration_ms:.0f} ms'
                cv2.putText(frame, caption, (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                            0.48, (0, 220, 220), 1, cv2.LINE_AA)
                cv2.putText(frame, 'Face detected != face authenticated', (8, frame.shape[0]-12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,220,220), 1, cv2.LINE_AA)
                if state.error:
                    cv2.putText(frame, state.error[:62], (8, 44),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1, cv2.LINE_AA)
                cv2.imshow(window_name, frame)
            # waitKey processes GUI events but must not end on arbitrary keystrokes.
            if (cv2.waitKey(1) & 0xFF) in (ord('q'), 27):
                break
    finally:
        stop.set()
        slot.close()
        worker.join(timeout=3)
        analyzer.join(timeout=3)
        cv2.destroyAllWindows()
    if stats["capture_error"]:
        raise RuntimeError(stats["capture_error"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='/dev/video10')
    parser.add_argument('--detector', choices=('auto','dlib','haar'), default='auto')
    args = parser.parse_args()
    if args.detector == 'haar':
        args.detector = 'opencv'
    try:
        run(args.device, args.detector)
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
