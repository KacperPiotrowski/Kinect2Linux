#!/usr/bin/env python3
"""Kinect2-Linux Face3D stage 4: synchronized IR/Depth and experimental 5-landmark 3D pose.

ONE process owns the Kinect (C++ child); stdout is not used for the sensor protocol.
No identity recognition, liveness decision, PAM integration, or biometric recording.
The optical axis of IR/Depth is shared, but this preview does not replace calibration.
"""
import argparse
import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json

import cv2
import numpy as np

W, H = 512, 424
N = W * H
PLANE_BYTES = N * 4
HEADER = struct.Struct('<8sIIIIffff')
MAGIC = b'K2F3D002'
WINDOW = 'Kinect2-Linux | IR + Depth (preview only)'

try:
    import dlib
except ImportError:
    dlib = None


class LatestPair:
    """Single-slot buffer (new frames overwrite stale ones)."""
    def __init__(self):
        self.cond = threading.Condition()
        self.serial = -1
        self.gray = None
        self.depth = None
        self.seq = None
        self.arrived_at = 0.0
        self.intrinsics = None
        self.ir_raw = None
        self.ended = False
        self.error = ''

    def publish(self, gray, depth, seq, intrinsics=None, ir_raw=None):
        with self.cond:
            self.serial += 1
            self.gray = gray
            self.depth = depth
            self.seq = seq
            self.intrinsics = intrinsics
            self.ir_raw = ir_raw
            self.arrived_at = time.monotonic()
            self.cond.notify_all()

    def newest(self, last=-2, timeout=0.05):
        with self.cond:
            if self.serial == last and not self.ended:
                self.cond.wait_for(lambda: self.serial != last or self.ended, timeout)
            if self.gray is None or self.serial == last:
                return None
            return self.serial, self.gray, self.depth, self.seq, self.arrived_at, self.intrinsics, self.ir_raw

    def finish(self, error=''):
        with self.cond:
            self.error = error
            self.ended = True
            self.cond.notify_all()


def read_exact(file, number):
    """Return exactly number bytes, or None on clean end-of-stream."""
    chunks = bytearray()
    while len(chunks) < number:
        part = file.read(number - len(chunks))
        if not part:
            if chunks:
                raise EOFError('Truncated Face3D frame received')
            return None
        chunks.extend(part)
    return bytes(chunks)


def normalize_ir(ir):
    """Only the GUI/detector uses 8-bit; the IPC source has full float32 IR."""
    good = ir[np.isfinite(ir) & (ir > 0.0)]
    if good.size < 1000:
        return np.zeros((H, W), dtype=np.uint8)
    lo, hi = np.percentile(good, [2.0, 99.5])
    if hi <= lo + 1:
        hi = lo + 1
    scaled = (np.nan_to_num(ir, nan=0.0, posinf=hi, neginf=0.0) - lo) / (hi - lo)
    return (255 * np.sqrt(np.clip(scaled, 0.0, 1.0))).astype(np.uint8)


def depth_visual(depth):
    """False colors over a fixed physical interval: 450..3500 mm."""
    valid = np.isfinite(depth) & (depth >= 450) & (depth <= 4500)
    scaled = (np.clip(np.nan_to_num(depth, nan=450, posinf=4500, neginf=450),
                      450, 3500) - 450) / 3050.0
    shade = (255.0 * (1.0 - scaled)).astype(np.uint8)
    colored = cv2.applyColorMap(shade, cv2.COLORMAP_TURBO)
    colored[~valid] = (12, 12, 12)
    return colored


def face_depth(depth, box):
    """Exploratory face-center ROI; not an identity or liveness metric."""
    x1, y1, x2, y2 = (int(q) for q in box)
    x1, x2 = sorted((max(0, x1), min(W, x2)))
    y1, y2 = sorted((max(0, y1), min(H, y2)))
    bw, bh = x2 - x1, y2 - y1
    if bw < 12 or bh < 12:
        return None
    # Inner 40% avoids hair/background around detected bounding box.
    xa = x1 + int(0.30 * bw)
    xb = x1 + int(0.70 * bw)
    ya = y1 + int(0.30 * bh)
    yb = y1 + int(0.70 * bh)
    roi = depth[ya:yb, xa:xb]
    if roi.size == 0:
        return None
    good = roi[np.isfinite(roi) & (roi >= 450) & (roi <= 4500)]
    valid_ratio = float(good.size) / roi.size
    if good.size < 25:
        return 0.0, valid_ratio, 0.0
    median = float(np.median(good))
    spread = float(np.percentile(good, 90) - np.percentile(good, 10))
    return median, valid_ratio, spread


def depth_patch(depth, box, rx, ry):
    """Median depth in a small inner-face patch (millimetres) plus valid fraction."""
    x1, y1, x2, y2 = (int(n) for n in box)
    x1, x2 = max(0, min(W-1, x1)), max(1, min(W, x2))
    y1, y2 = max(0, min(H-1, y1)), max(1, min(H, y2))
    bw, bh = x2-x1, y2-y1
    if bw < 50 or bh < 50:
        return None
    x = x1 + round(rx*bw)
    y = y1 + round(ry*bh)
    rad = max(3, round(min(bw,bh)*0.055))
    region = depth[max(0,y-rad):min(H,y+rad+1),
                   max(0,x-rad):min(W,x+rad+1)]
    good = region[np.isfinite(region) & (region >= 500) & (region <= 4500)]
    if region.size == 0 or good.size < 12 or good.size/region.size < 0.65:
        return None
    return float(np.median(good))


def rotation_proxy(depth, box, intrinsics):
    """Experimental 3D face tilt proxy from four depth patches. NOT calibrated pose.

    Intrinsics make the X/Y baseline a real physical distance (mm). The sign
    convention depends on image orientation. This estimate is not identity,
    liveness, or high-trust registration evidence.
    """
    if intrinsics is None:
        return None
    fx, fy, cx, cy = intrinsics
    if not (200 <= fx <= 1500 and 200 <= fy <= 1500):
        return None
    x1, y1, x2, y2 = (int(n) for n in box)
    bw, bh = x2-x1, y2-y1
    left = depth_patch(depth, box, .31, .53)
    right = depth_patch(depth, box, .69, .53)
    top = depth_patch(depth, box, .50, .34)
    bottom = depth_patch(depth, box, .50, .68)
    if any(v is None for v in (left,right,top,bottom)):
        return None
    depths = (left, right, top, bottom)
    if max(depths)-min(depths) > 250:
        return None
    z = float(np.median(depths))
    baseline_x_mm = .38 * bw * z / fx
    baseline_y_mm = .34 * bh * z / fy
    if baseline_x_mm < 15 or baseline_y_mm < 12:
        return None
    yaw = math.degrees(math.atan2(right-left, baseline_x_mm))
    pitch = math.degrees(math.atan2(bottom-top, baseline_y_mm))
    return (yaw, pitch)



# The dlib 5-point predictor provides four eye-region points and the nose tip.
# Model weights are NOT distributed by Kinect2-Linux. They are read from a
# locally available installation (often Howdy), or from an explicit path.
LANDMARK_NAME = 'shape_predictor_5_face_landmarks.dat'


def locate_landmark_model(explicit=None):
    """Find a readable local model; never download models automatically."""
    if explicit:
        path = Path(explicit).expanduser()
        return str(path) if path.is_file() and os.access(path, os.R_OK) else None
    candidates = [os.environ.get('KINECT2_LANDMARK_MODEL')]
    candidates += [
        str(Path.home() / '.local/share/kinect2-linux/models' / LANDMARK_NAME),
        '/usr/lib/howdy/dlib-data/' + LANDMARK_NAME,
        '/usr/lib/security/howdy/dlib-data/' + LANDMARK_NAME,
        '/lib/security/howdy/dlib-data/' + LANDMARK_NAME,
        '/usr/etc/howdy/dlib-data/' + LANDMARK_NAME,
    ]
    for name in candidates:
        if not name:
            continue
        path = Path(name).expanduser()
        if path.is_file() and os.access(path, os.R_OK):
            return str(path)
    return None


def five_xyz_to_relative_angles(points_xyz):
    """Exploratory 5-landmark eye/nose 3D orientation, in camera axes.

    These are NOT true calibrated head pose angles. We use the eye line and
    eye-to-nose direction to create a face-local basis. A baseline FRONT pose
    is subtracted by the enrollment guide. Sign depends on sensor mirroring.
    """
    points = np.asarray(points_xyz, dtype=np.float64)
    if points.shape != (5, 3) or not np.all(np.isfinite(points)):
        return None
    if np.any((points[:, 2] < 450) | (points[:, 2] > 4500)):
        return None
    eye_a = (points[0] + points[1]) * 0.5
    eye_b = (points[2] + points[3]) * 0.5
    # The 5-point model returns two points around each eye and one nose point.
    # Positive horizontal orientation follows increasing camera X.
    horizontal = eye_a - eye_b
    span = float(np.linalg.norm(horizontal))
    if not 28.0 <= span <= 180.0:
        return None
    ex = horizontal / span
    center_eyes = (eye_a + eye_b) * 0.5
    nose = points[4]
    down = nose - center_eyes
    # Remove residual movement along the eye line (non-rigid landmarks).
    down = down - ex * np.dot(down, ex)
    length_down = float(np.linalg.norm(down))
    if not 12.0 <= length_down <= 160.0:
        return None
    ey = down / length_down
    normal = np.cross(ex, ey)
    norm = float(np.linalg.norm(normal))
    if norm < .8:
        return None
    normal /= norm
    # Choose the normal pointing approximately toward the camera's positive Z.
    # More side-on faces are rejected; frontal-face dlib is not a profile detector.
    if normal[2] < 0:
        normal = -normal
    if normal[2] < .3:
        return None
    yaw = math.degrees(math.atan2(float(normal[0]), float(normal[2])))
    pitch = math.degrees(math.atan2(float(-normal[1]),
                                   math.hypot(float(normal[0]), float(normal[2]))))
    if abs(yaw) > 70.0 or abs(pitch) > 80.0:
        return None
    return float(yaw), float(pitch)


def landmark_depth_xyz(depth, u, v, intrinsics, radius=4):
    """Median of a small patch near one facial landmark -> XYZ in millimetres."""
    if intrinsics is None:
        return None
    fx, fy, cx, cy = intrinsics
    if not all(math.isfinite(t) for t in (fx, fy, cx, cy)) or fx < 150 or fy < 150:
        return None
    ix, iy = int(round(u)), int(round(v))
    if ix < radius or ix >= W-radius or iy < radius or iy >= H-radius:
        return None
    patch = depth[iy-radius:iy+radius+1, ix-radius:ix+radius+1]
    good = patch[np.isfinite(patch) & (patch >= 450) & (patch <= 4500)]
    if good.size < patch.size * .60:
        return None
    z = float(np.median(good))
    # Large depth variation near an eye may indicate hair/background/edge.
    if float(np.percentile(good, 90) - np.percentile(good, 10)) > 100.0:
        return None
    return ((u-cx)*z/fx, (v-cy)*z/fy, z)


def landmark_pose_from_five(depth, landmark_pixels, intrinsics):
    """Return (relative-pose proxy, points) or (None, points) for debugging.

    Never interpolate invalid Depth; fail closed if any eye/nose landmark is
    missing. The 8-bit input is only for dlib's landmark localization.
    """
    if len(landmark_pixels) != 5:
        return None
    xyz = []
    for u, v in landmark_pixels:
        value = landmark_depth_xyz(depth, u, v, intrinsics)
        if value is None:
            return None
        xyz.append(value)
    return five_xyz_to_relative_angles(xyz)


class MotionGuide:
    """Exploratory motion coverage after the user explicitly sets FRONT."""
    def __init__(self, threshold=14.0):
        self.base = None
        self.threshold = threshold
        self.hits = set()
        self.streaks = {x: 0 for x in ('YAW-', 'YAW+', 'PITCH-', 'PITCH+')}

    def reset(self, pose):
        self.base = pose
        self.hits = {'FRONT'}
        self.streaks = {x: 0 for x in self.streaks}

    def consume(self, pose):
        if pose is None or self.base is None:
            return
        dyaw, dpitch = pose[0]-self.base[0], pose[1]-self.base[1]
        signals = {
            'YAW-': dyaw < -self.threshold and abs(dpitch) < 28,
            'YAW+': dyaw > self.threshold and abs(dpitch) < 28,
            'PITCH-': dpitch < -self.threshold and abs(dyaw) < 28,
            'PITCH+': dpitch > self.threshold and abs(dyaw) < 28,
        }
        for name, active in signals.items():
            self.streaks[name] = self.streaks[name] + 1 if active else 0
            if self.streaks[name] >= 3:
                self.hits.add(name)




ENROLL_STEPS = ('FRONT', 'YAW-', 'YAW+', 'PITCH-', 'PITCH+')


class GuidedEnrollment:
    """Experimental, automatic IR+Depth pose sampling; NOT an identity model.

    Uses a 5-landmark 3D relative orientation estimate. A turned head may be missed by a
    frontal-face detector.  Results must not be used for authentication.
    Only frames originating from the detector's exact acquisition sequence
    are saved.  No face data is written until all five poses are collected.
    """
    def __init__(self, threshold=12.0, min_samples=7, min_hold=0.40):
        self.threshold = float(threshold)
        self.min_samples = int(min_samples)
        self.min_hold = float(min_hold)
        self.reset()

    def reset(self):
        self.started = False
        self.step_index = 0
        self.base = None
        self.samples = []
        self.candidate = []
        self.last_seq = -1
        self.saved_at = None
        self.notice = 'Kliknij Rozpocznij, patrząc prosto w Kinecta.'

    def start(self):
        self.reset()
        self.started = True
        self.notice = 'Patrz prosto. Utrzymaj twarz nieruchomo przez chwilę.'

    @property
    def completed(self):
        return self.step_index == len(ENROLL_STEPS)

    @property
    def step(self):
        return 'DONE' if self.completed else ENROLL_STEPS[self.step_index]

    def _qualify(self, state):
        if len(state.boxes) != 1 or state.pose is None:
            return None
        if state.ir_raw is None or state.depth_raw is None or state.intrinsics is None:
            return None
        if not all(math.isfinite(p) for p in state.pose):
            return None
        x1,y1,x2,y2 = (int(v) for v in state.boxes[0])
        if not (8 <= x1 < x2 <= W-8 and 8 <= y1 < y2 <= H-8):
            return None
        if (x2-x1) < 75 or (y2-y1) < 75:
            return None
        val = face_depth(state.depth_raw, state.boxes[0])
        if val is None:
            return None
        z, coverage, spread = val
        if not (550 <= z <= 2200 and coverage >= .85 and spread <= 220):
            return None
        return (float(z), float(coverage), float(spread), (x1,y1,x2,y2))

    def _matches_step(self, pose):
        if self.step == 'FRONT':
            return True  # user instructed to look straight; no trusted frontal test yet
        dy, dp = pose[0]-self.base[0], pose[1]-self.base[1]
        t = self.threshold
        conditions = {
            'YAW-': dy <= -t and abs(dp) <= 22,
            'YAW+': dy >= t and abs(dp) <= 22,
            'PITCH-': dp <= -t and abs(dy) <= 22,
            'PITCH+': dp >= t and abs(dy) <= 22,
        }
        return conditions[self.step]

    def consume(self, state, now=None):
        """Process each detection sequence at most once. Return True on new capture."""
        if not self.started or self.completed or state.seq <= self.last_seq:
            return False
        self.last_seq = state.seq
        now = time.monotonic() if now is None else now
        if not (0 <= now-state.arrived_at <= 0.5):
            self.candidate.clear()
            self.notice = 'Zbyt stara klatka — czekam na świeży pomiar.'
            return False
        quality = self._qualify(state)
        if quality is None:
            self.candidate.clear()
            if len(state.boxes) == 0:
                self.notice = ('Nie wykrywam twarzy. Detektor frontalny moze gubic '
                               'twarz podczas obrotu — wroc nieco w strone kamery.')
            elif len(state.boxes) != 1:
                self.notice = 'Wykryto kilka twarzy; czekam na jedna osobe.'
            elif state.pose is None:
                self.notice = ('Twarz wykryta, ale pomiar Yaw/Pitch jest niewiarygodny. '
                               'Brak kompletu punktow oczu/nosa lub ich prawidlowej glebi.')
            else:
                self.notice = ('Twarz wykryta, ale nie przeszla kontroli jakosci '
                               '(obszar, odleglosc lub poprawne punkty Depth).')
            return False
        z, coverage, spread, box = quality
        if not self._matches_step(state.pose):
            self.candidate.clear()
            self.notice = {
                'YAW-': f'Obróć głowę do wartości Yaw poniżej -{self.threshold:g}°.',
                'YAW+': f'Obróć głowę do wartości Yaw powyżej +{self.threshold:g}°.',
                'PITCH-': f'Pochyl głowę do wartości Pitch poniżej -{self.threshold:g}°.',
                'PITCH+': f'Pochyl głowę do wartości Pitch powyżej +{self.threshold:g}°.',
            }.get(self.step, 'Spójrz prosto w Kinecta.')
            return False
        if self.candidate:
            first = self.candidate[0]
            pose0, z0, box0 = first['pose'], first['z'], first['box']
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
            cx0, cy0 = (box0[0]+box0[2])/2, (box0[1]+box0[3])/2
            if (max(abs(state.pose[i]-pose0[i]) for i in (0,1)) > 5.0
                    or abs(z-z0) > 70.0 or abs(cx-cx0) > 30 or abs(cy-cy0) > 30
                    or state.arrived_at-first['arrived'] > 3.0):
                self.candidate.clear()
        self.candidate.append({'pose': state.pose, 'z': z, 'box': box,
                               'arrived': state.arrived_at})
        count = len(self.candidate)
        duration = state.arrived_at - self.candidate[0]['arrived']
        self.notice = (f'{self.step}: stabilne pomiary {count}/{self.min_samples}, '
                       f'{max(0, duration):.1f}/{self.min_hold:.1f} s')
        if count < self.min_samples or duration < self.min_hold:
            return False
        x1,y1,x2,y2 = box
        # Save only the face ROI (not the entire room) and keep float32 precision.
        captured = {
            'name': self.step,
            'seq': int(state.seq),
            'pose': [float(q) for q in state.pose],
            'z_mm': z, 'valid': coverage, 'spread_mm': spread,
            'box': list(box),
            'intrinsics': [float(q) for q in state.intrinsics],
            'ir': np.array(state.ir_raw[y1:y2,x1:x2], dtype=np.float32, copy=True),
            'depth': np.array(state.depth_raw[y1:y2,x1:x2], dtype=np.float32, copy=True),
        }
        self.samples.append(captured)
        if self.step == 'FRONT':
            self.base = (float(np.median([s['pose'][0] for s in self.candidate])),
                         float(np.median([s['pose'][1] for s in self.candidate])))
        self.step_index += 1
        self.candidate.clear()
        self.notice = f'Zapisano próbkę {captured["name"]} ({self.step_index}/5).'
        return True

    def save(self, base_dir=None):
        """Persist all samples to a private directory only after full completion."""
        if not self.completed or len(self.samples) != len(ENROLL_STEPS):
            raise RuntimeError('Niekompletne próbki — nic nie zapisano.')
        if self.saved_at is not None:
            return self.saved_at
        root = (Path(base_dir) if base_dir is not None else
                Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share')) /
                'kinect2-linux' / 'enrollments')
        # Never follow an existing enrollment session directory.
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        old_umask = os.umask(0o077)
        try:
            prefix = datetime.now().strftime('face3d-%Y%m%d-%H%M%S')
            directory = None
            for i in range(100):
                candidate = root / (prefix if i == 0 else f'{prefix}-{i}')
                try:
                    candidate.mkdir(mode=0o700)
                except FileExistsError:
                    continue
                directory = candidate
                break
            if directory is None:
                raise FileExistsError('Nie można utworzyć nowego folderu sesji')
            manifest = {'kind': 'EXPERIMENTAL_FACE3D_SAMPLES_NOT_AUTHENTICATION',
                        'source': 'Kinect v2 IR+Depth float32',
                        'note': 'Pose is an uncalibrated 5-point 3D face orientation; not liveness or identity.',
                        'samples': []}
            for sample in self.samples:
                name = sample['name'].lower().replace('+', '_plus').replace('-', '_minus')
                filename = f'{name}.npz'
                np.savez_compressed(directory/filename,
                                    ir=sample['ir'], depth=sample['depth'])
                record = {key: value for key, value in sample.items()
                          if key not in ('ir', 'depth')}
                record['file'] = filename
                manifest['samples'].append(record)
            with (directory/'manifest.json').open('w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            self.saved_at = str(directory)
            return self.saved_at
        finally:
            os.umask(old_umask)

@dataclass(frozen=True)
class Result:
    boxes: tuple = ()
    analysis_ms: float = 0.0
    arrived_at: float = 0.0
    error: str = ''
    seq: int = -1
    pose: tuple = None
    landmarks: tuple = ()
    pose_error: str = ''
    ir_raw: object = None
    depth_raw: object = None
    intrinsics: tuple = None


class LatestDetection:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = Result()

    def publish(self, item):
        with self.lock:
            self.value = item

    def get(self):
        with self.lock:
            return self.value


def capture_worker(inherited_fd, slot):
    try:
        with os.fdopen(inherited_fd, 'rb', buffering=2 * PLANE_BYTES) as stream:
            while True:
                data = read_exact(stream, HEADER.size)
                if data is None:
                    break
                magic, seq, timestamp, width, height, fx, fy, cx, cy = HEADER.unpack(data)
                if magic != MAGIC or width != W or height != H:
                    raise ValueError('Incorrect Face3D stream header')
                ir_blob = read_exact(stream, PLANE_BYTES)
                dep_blob = read_exact(stream, PLANE_BYTES)
                if ir_blob is None or dep_blob is None:
                    raise EOFError('Incomplete IR/Depth pair')
                ir = np.frombuffer(ir_blob, dtype='<f4').reshape((H, W))
                dep = np.frombuffer(dep_blob, dtype='<f4').reshape((H, W))
                slot.publish(normalize_ir(ir), dep, seq, (fx, fy, cx, cy), ir)
    except (OSError, ValueError, EOFError) as exc:
        slot.finish(f'{type(exc).__name__}: {exc}')
        return
    except Exception as exc:
        slot.finish(f'Unexpected reader error: {type(exc).__name__}: {exc}')
        return
    slot.finish()


def detector_worker(slot, latest, stop, method, pose_enabled=False, predictor_path=None):
    try:
        predictor = dlib.shape_predictor(predictor_path) if predictor_path else None
        if method in ('auto', 'dlib') and dlib is not None:
            detector = dlib.get_frontal_face_detector()
            kind = 'dlib'
        elif method == 'dlib':
            raise RuntimeError('dlib is not installed; try --detector haar')
        else:
            detector = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if detector.empty():
                raise RuntimeError('OpenCV Haar detector not found')
            kind = 'haar'
        last = -2
        while not stop.is_set() and not slot.ended:
            pair = slot.newest(last, timeout=0.25)
            if pair is None:
                continue
            last, gray, dep, seq, arrived, intrinsics, ir_raw = pair
            start = time.monotonic()
            if kind == 'dlib':
                faces = detector(gray, 0)
                boxes = tuple((f.left(), f.top(), f.right(), f.bottom()) for f in faces)
            else:
                faces = detector.detectMultiScale(gray, scaleFactor=1.1,
                                                   minNeighbors=5, minSize=(60, 60))
                boxes = tuple((int(x), int(y), int(x+w), int(y+h)) for x, y, w, h in faces)
            pose = None
            landmarks = ()
            pose_error = ''
            if predictor is not None and pose_enabled and len(boxes) == 1:
                x1, y1, x2, y2 = boxes[0]
                shape = predictor(gray, dlib.rectangle(int(x1), int(y1), int(x2), int(y2)))
                if shape.num_parts == 5:
                    landmarks = tuple((float(shape.part(i).x), float(shape.part(i).y))
                                      for i in range(5))
                    pose = landmark_pose_from_five(dep, landmarks, intrinsics)
                    if pose is None:
                        pose_error = 'Brak poprawnej glebi dla 5 punktow oczu/nosa.'
                else:
                    pose_error = 'Predyktor nie zwrocil 5 punktow twarzy.'
            latest.publish(Result(boxes=boxes,
                                  analysis_ms=1000.0 * (time.monotonic()-start),
                                  arrived_at=arrived, seq=seq, pose=pose,
                                  landmarks=landmarks, pose_error=pose_error,
                                  ir_raw=ir_raw, depth_raw=dep, intrinsics=intrinsics))
    except Exception as exc:
        latest.publish(Result(error=f'{type(exc).__name__}: {exc}'))


def run(producer, method, pose_enabled=False, threshold=12.0, enroll=False, landmark_model=None):
    """Native, resizable Qt6 viewer; OpenCV remains only a pixel-processing library.

    Kinect acquisition and face detection run on their existing worker threads;
    Qt widgets are touched only from the GUI thread.
    """
    # Fail before the sensor starts if the predictor is unavailable.
    model_path = None
    if pose_enabled:
        if dlib is None:
            raise RuntimeError('Tryb pose/enroll wymaga python-dlib (Howdy juz go uzywa).')
        model_path = locate_landmark_model(landmark_model)
        if model_path is None:
            raise RuntimeError(
                'Brak dostepnego modelu dlib: shape_predictor_5_face_landmarks.dat. '
                'Podaj --landmark-model SCIEZKA lub ustaw KINECT2_LANDMARK_MODEL. '
                'Szukaj np. w /usr/lib/howdy/dlib-data/. '
                'Nie uruchamiam sensora bez modelu.')
        print('Face3D: 5-point 3D landmark model:', model_path, flush=True)
    try:
        from PyQt6.QtCore import Qt, QTimer, QLibraryInfo
        from PyQt6.QtGui import QImage, QPixmap
        from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel,
                                     QMainWindow, QPushButton, QVBoxLayout,
                                     QWidget, QSizePolicy)
    except ImportError as exc:
        raise RuntimeError('Brak PyQt6. Na Archu zainstaluj: '
                           'sudo pacman -S --needed python-pyqt6') from exc

    # OpenCV wheels may redirect Qt plugin lookup to their own (often Qt5)
    # plugin directory.  The GUI uses PyQt6, so always select the plugins
    # belonging to the Qt6 installation that PyQt6 actually loaded.
    qt_plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugins
    os.environ.pop('QT_QPA_FONTDIR', None)

    # Initialize the GUI BEFORE opening the Kinect.  If a Qt plugin is
    # missing, we now fail without leaving a USB streaming child alive.
    app = QApplication.instance() or QApplication(sys.argv)

    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen([producer, str(write_fd)], pass_fds=(write_fd,))
    finally:
        os.close(write_fd)

    slot = LatestPair()
    latest = LatestDetection()
    stop = threading.Event()
    reader = threading.Thread(target=capture_worker, args=(read_fd, slot), daemon=True)
    analyzer = threading.Thread(target=detector_worker,
                                args=(slot, latest, stop, method, pose_enabled, model_path),
                                daemon=True)
    reader.start()
    analyzer.start()
    guide = MotionGuide(threshold=threshold)
    enrollment = GuidedEnrollment(threshold=threshold) if enroll else None

    class FaceWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Kinect2-Linux — Face3D | IR + Depth' + (' | Rejestracja' if enroll else ''))
            self.resize(1420, 820)
            self.setMinimumSize(840, 610)
            self.previous = -2
            self.last_pose_seq = None
            self.last_left = None
            self.last_right = None
            self.count = 0
            self.started = time.monotonic()
            self.fps = 0.0
            self.failed = False

            root = QWidget()
            root.setStyleSheet('background-color: #171b22; color: #e5eaf3;')
            main_layout = QVBoxLayout(root)
            main_layout.setSpacing(10)
            main_layout.setContentsMargins(14, 14, 14, 14)

            title = QLabel('KINECT2 FACE3D  ·  PODGLĄD NA ŻYWO')
            title.setStyleSheet('font-size: 21px; font-weight: 700;')
            main_layout.addWidget(title)

            images = QHBoxLayout()
            images.setSpacing(12)
            self.left_label = self.make_image_label()
            self.right_label = self.make_image_label()
            for heading, image_label in (
                ('PODCZERWIEŃ · IR', self.left_label),
                ('ODLEGŁOŚĆ · DEPTH', self.right_label),
            ):
                col = QVBoxLayout()
                heading_label = QLabel(heading)
                heading_label.setStyleSheet('font-size: 16px; font-weight: 600;')
                col.addWidget(heading_label)
                col.addWidget(image_label, stretch=1)
                images.addLayout(col, stretch=1)
            main_layout.addLayout(images, stretch=1)

            self.info = QLabel('Czekam na obraz z Kinecta…')
            self.info.setStyleSheet('font-size: 18px; font-weight: 600;')
            main_layout.addWidget(self.info)

            self.pose_label = QLabel('Wskazania orientacji: oczekiwanie na dane')
            self.pose_label.setStyleSheet('font-size: 17px; color: #b8d5ff;')
            self.pose_label.setWordWrap(True)
            main_layout.addWidget(self.pose_label)

            self.progress = QLabel('FRONT: --     YAW-: --     YAW+: --     PITCH-: --     PITCH+: --')
            self.progress.setStyleSheet('font-size: 16px; color: #aee8c4;')
            main_layout.addWidget(self.progress)

            controls = QHBoxLayout()
            self.calibrate_btn = QPushButton('Rozpocznij rejestrację (C)' if enroll else 'Ustaw FRONT (C)')
            self.calibrate_btn.setEnabled(pose_enabled)
            self.calibrate_btn.clicked.connect(self.calibrate)
            self.calibrate_btn.setStyleSheet('font-size: 16px; padding: 10px;')
            controls.addWidget(self.calibrate_btn)
            exit_btn = QPushButton('Zakończ (Esc)')
            exit_btn.setStyleSheet('font-size: 16px; padding: 10px;')
            exit_btn.clicked.connect(self.close)
            controls.addWidget(exit_btn)
            main_layout.addLayout(controls)

            footer = QLabel(('PRÓBKI IR+Depth zapisane prywatnie po 5 pozycjach; '
                             'nie jest to model Howdy ani zabezpieczenie PAM.' if enroll else
                             'TEST: wykrywanie twarzy i orientacyjna głębia. '
                             'Nie jest to rozpoznawanie tożsamości ani zabezpieczenie PAM.'))
            footer.setWordWrap(True)
            footer.setStyleSheet('font-size: 13px; color: #9ca3af;')
            main_layout.addWidget(footer)
            self.setCentralWidget(root)

            self.timer = QTimer(self)
            self.timer.setInterval(30)
            self.timer.timeout.connect(self.update_view)
            self.timer.start()

        @staticmethod
        def make_image_label():
            label = QLabel('Oczekiwanie…')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet('background: #080b10; border: 1px solid #3d4654; '
                                'border-radius: 5px; font-size: 16px;')
            label.setMinimumSize(320, 270)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return label

        @staticmethod
        def to_qimage(bgr):
            """Copy pixels so QImage never outlives the NumPy frame allocation."""
            rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            h, w, _ = rgb.shape
            return QImage(rgb.data, w, h, rgb.strides[0],
                          QImage.Format.Format_RGB888).copy()

        @staticmethod
        def render(label, image):
            if image is None or label.width() < 1 or label.height() < 1:
                return
            pixmap = QPixmap.fromImage(image).scaled(
                label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pixmap)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self.last_left is not None:
                self.render(self.left_label, self.last_left)
                self.render(self.right_label, self.last_right)

        def keyPressEvent(self, event):
            if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
                self.close()
            elif event.key() == Qt.Key.Key_C and (pose_enabled or enroll):
                self.calibrate()
            else:
                super().keyPressEvent(event)

        def calibrate(self):
            if enroll:
                enrollment.start()
                self.pose_label.setText('Rejestracja: patrz prosto, przytrzymaj pozycję.')
                self.calibrate_btn.setText('Zacznij od nowa (C)')
                return
            state = latest.get()
            if (0 <= time.monotonic() - state.arrived_at < 0.5
                    and state.pose is not None):
                guide.reset(state.pose)
                self.pose_label.setText('Ustawiono FRONT. Obracaj głowę powoli.')
                print(f'3D tilt reference set at frame {state.seq}. (not enrollment)',
                      flush=True)
            else:
                self.pose_label.setText('Nie można ustawić FRONT: brak aktualnego pomiaru 3D.')

        def update_view(self):
            pair = slot.newest(self.previous, timeout=0)
            if pair is None:
                if slot.ended or proc.poll() is not None:
                    self.timer.stop()
                    msg = slot.error or f'Źródło obrazu zakończyło się (kod {proc.poll()}).'
                    self.info.setText(msg)
                    print('Face3D: ' + msg, file=sys.stderr)
                return

            self.previous, gray, dep, seq, arrived, intrinsics, ir_raw = pair
            left = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            right = depth_visual(dep)
            state = latest.get()
            fresh = (state.seq >= 0 and 0 <= seq - state.seq <= 12
                     and 0 <= time.monotonic() - state.arrived_at < 0.5)

            if fresh:
                for box in state.boxes:
                    x1, y1, x2, y2 = box
                    for image in (left, right):
                        cv2.rectangle(image, (x1, y1), (x2, y2), (35, 220, 80), 2)
                    measure = face_depth(dep, box)
                    if measure:
                        distance, ratio, spread = measure
                        cv2.putText(right,
                                    f'Twarz: {distance:.0f} mm | valid: {ratio*100:.0f}%',
                                    (12, 51), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                    (255, 255, 255), 2, cv2.LINE_AA)

            if fresh and pose_enabled:
                for px, py in state.landmarks:
                    cv2.circle(left, (int(round(px)), int(round(py))), 3,
                               (0, 210, 255), -1, cv2.LINE_AA)
                    cv2.circle(right, (int(round(px)), int(round(py))), 3,
                               (0, 210, 255), -1, cv2.LINE_AA)
            self.count += 1
            elapsed = time.monotonic() - self.started
            if elapsed >= 1.0:
                self.fps = self.count / elapsed
                self.count = 0
                self.started = time.monotonic()
            cv2.putText(left, f'IR {self.fps:.1f} FPS', (10, 23),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(right, f'DEPTH | detection {state.analysis_ms:.0f}ms',
                        (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.58,
                        (255, 255, 255), 2, cv2.LINE_AA)

            self.last_left = self.to_qimage(left)
            self.last_right = self.to_qimage(right)
            self.render(self.left_label, self.last_left)
            self.render(self.right_label, self.last_right)
            self.info.setText(f'Podgląd: {self.fps:.1f} FPS   |   '
                              f'Detekcja: {state.analysis_ms:.0f} ms   |   '
                              f'Klatka: {seq}')

            if enroll:
                if fresh:
                    enrollment.consume(state)
                if enrollment.completed and enrollment.saved_at is None:
                    try:
                        path = enrollment.save()
                        print('Face3D: zapisano eksperymentalne próbki w:', path, flush=True)
                    except (OSError, RuntimeError) as exc:
                        self.info.setText(f'Błąd zapisu próbek: {exc}')
                done = {s['name'] for s in enrollment.samples}
                self.progress.setText('    '.join(
                    f'{name}: {"OK" if name in done else "--"}' for name in ENROLL_STEPS))
                if not enrollment.started:
                    text = 'Kliknij Rozpocznij rejestrację (C).'
                elif enrollment.completed:
                    text = ('GOTOWE: próbki zapisane (NIE model Howdy): '
                            + str(enrollment.saved_at or 'błąd zapisu'))
                else:
                    pose_text = ''
                    if fresh and state.pose is not None and enrollment.base is not None:
                        pose_text = (f' Yaw {state.pose[0]-enrollment.base[0]:+.1f}°'
                                     f' Pitch {state.pose[1]-enrollment.base[1]:+.1f}°')
                    text = f'{enrollment.step_index+1}/5 | {enrollment.notice}{pose_text}'
                self.pose_label.setText(text)
            elif pose_enabled:
                if fresh and state.pose is not None:
                    if state.seq != self.last_pose_seq:
                        self.last_pose_seq = state.seq
                        guide.consume(state.pose)
                    if guide.base is None:
                        text = 'Spójrz prosto w kamerę i kliknij „Ustaw FRONT” (C).'
                    else:
                        yaw = state.pose[0] - guide.base[0]
                        pitch = state.pose[1] - guide.base[1]
                        text = (f'Yaw: {yaw:+.1f}°    Pitch: {pitch:+.1f}°   '
                                '[5 punktów 3D, orientacja względna; NIE biometria]')
                    self.pose_label.setText(text)
                else:
                    self.pose_label.setText(state.pose_error if fresh and state.pose_error else 'Brak pelnego pomiaru 5 punktow twarzy IR+Depth.')
                markers = '    '.join(
                    f'{name}: {"OK" if name in guide.hits else "--"}'
                    for name in ('FRONT', 'YAW-', 'YAW+', 'PITCH-', 'PITCH+'))
                if guide.base is None:
                    self.progress.setText('Ruchy: ustaw FRONT (C), gdy pomiar jest wiarygodny.')
                elif not (fresh and state.pose is not None):
                    self.progress.setText('BRAK BIEŻĄCEGO POMIARU 3D | poprzednio: ' + markers)
                else:
                    self.progress.setText('ZAREJESTROWANE RUCHY (DEMO): ' + markers)
            else:
                self.pose_label.setText('Tryb wykrywania — uruchom ./face3d --pose '
                                        'dla orientacyjnych obrotów głowy.')
                self.progress.setText('')
            if state.error:
                self.info.setText(f'Błąd analizatora: {state.error}')

        def closeEvent(self, event):
            self.timer.stop()
            super().closeEvent(event)

    window = FaceWindow()

    # Never let Python raise KeyboardInterrupt in a Qt slot (e.g. when NumPy
    # processes a depth frame). Unhandled exceptions crossing into Qt can
    # terminate the process with SIGABRT and a core dump.
    quit_requested = threading.Event()
    original_sigint = signal.getsignal(signal.SIGINT)

    def request_quit(_signum, _frame):
        quit_requested.set()  # Python signal handler must not touch Qt widgets.

    signal.signal(signal.SIGINT, request_quit)
    quit_timer = QTimer(window)
    quit_timer.setInterval(50)
    quit_timer.timeout.connect(
        lambda: window.close() if quit_requested.is_set() else None)
    quit_timer.start()
    try:
        print('Face3D native Qt6: one Kinect reader + independent face detector.')
        print('Podgląd IR + Depth, Ctrl+C lub Q/Esc zamyka okno; C uruchamia tryb.')
        print('Nie jest to uwierzytelnianie ani liveness verification.')
        window.show()
        # A real Qt window with a normal resize/maximize mechanism (no cv2.HighGUI).
        app.exec()
    finally:
        quit_timer.stop()
        stop.set()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        reader.join(timeout=2)
        analyzer.join(timeout=2)
        signal.signal(signal.SIGINT, original_sigint)
    print('Face3D stopped; sensor released.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', required=True)
    parser.add_argument('--detector', choices=('auto', 'dlib', 'haar'), default='auto')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--pose', action='store_true', help='experimental relative 3D head motion guide')
    mode.add_argument('--enroll', action='store_true', help='guided experimental 5-pose IR+Depth capture')
    parser.add_argument('--landmark-model', default=None,
                        help='ścieżka do lokalnego modelu dlib 5-point (bez pobierania)')
    parser.add_argument('--turn-threshold', type=float, default=12.0,
                        help='relative depth-tilt threshold in degrees (default 12)')
    args = parser.parse_args()
    if not 4 <= args.turn_threshold <= 30:
        parser.error('--turn-threshold must be between 4 and 30 degrees')
    try:
        run(args.producer, args.detector, args.pose or args.enroll, args.turn_threshold,
            enroll=args.enroll, landmark_model=args.landmark_model)
    except KeyboardInterrupt:
        print('\nStopped (Ctrl+C).')
    except Exception as exc:
        print(f'Face3D error: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
