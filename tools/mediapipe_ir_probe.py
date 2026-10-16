#!/usr/bin/env python3
"""Kinect2-Linux: isolated MediaPipe Face Landmarker smoke test on saved Kinect IR.

No camera access, no Qt, no Howdy/PAM changes, no model or raw biometric uploads.
MediaPipe pose angles below are illustrative (canonical -> image transform), NOT
trusted metric 3D pose or liveness measurements. Depth integration comes later.
"""
import argparse
from pathlib import Path
import sys
import time

import numpy as np


def load_ir(path: Path, fmt: str):
    from PIL import Image

    if fmt == 'f32' or (fmt == 'auto' and path.suffix.lower() == '.f32'):
        raw = np.fromfile(path, dtype='<f4')
        if raw.size != 512 * 424:
            raise ValueError(f'IR float32 must contain 512x424 values, got {raw.size}')
        arr = raw.reshape(424, 512)
        good = arr[np.isfinite(arr) & (arr > 0)]
        if good.size < 1000:
            raise ValueError('Not enough valid IR samples')
        lo, hi = np.percentile(good, [2.0, 99.5])
        if hi <= lo:
            raise ValueError('IR intensity range is constant')
        safe = np.nan_to_num(arr, nan=0., posinf=hi, neginf=0.)
        intensity = np.clip((safe - lo) / (hi - lo), 0.0, 1.0)
        gray = np.asarray(255.0 * np.sqrt(intensity), dtype=np.uint8)
        return Image.fromarray(gray, mode='L')
    return Image.open(path).convert('L')


def make_variants(image):
    from PIL import ImageOps

    # Never discard original IR source. These are only input adaptations for ML.
    native = np.asarray(image, dtype=np.uint8)
    auto = np.asarray(ImageOps.autocontrast(image, cutoff=1), dtype=np.uint8)
    gamma = np.asarray(np.clip(255.0 * (auto / 255.0) ** 0.65, 0, 255), dtype=np.uint8)
    return {'original': native, 'autocontrast': auto, 'gamma': gamma}


def approx_pose(matrix):
    """ZYX Euler decomposition of the Face Landmarker canonical transform.

    These are NOT Kinect-calibrated physical head angles; use frontal calibration
    and actual Depth for any future enrollment decision.
    """
    r = np.asarray(matrix, dtype=np.float64)[:3, :3]
    if r.shape != (3, 3) or not np.isfinite(r).all():
        return None
    u, _, vt = np.linalg.svd(r)
    rot = u @ vt
    if np.linalg.det(rot) < 0:
        u[:, -1] *= -1
        rot = u @ vt
    # For R = Rz(roll) @ Ry(yaw) @ Rx(pitch)
    yaw = np.degrees(np.arcsin(np.clip(-rot[2, 0], -1.0, 1.0)))
    pitch = np.degrees(np.arctan2(rot[2, 1], rot[2, 2]))
    roll = np.degrees(np.arctan2(rot[1, 0], rot[0, 0]))
    return float(yaw), float(pitch), float(roll)


def annotate(gray, landmarks, pose, label, destination):
    from PIL import Image, ImageDraw
    rgb = Image.fromarray(gray, mode='L').convert('RGB')
    draw = ImageDraw.Draw(rgb)
    w, h = rgb.size
    if landmarks:
        # High-contrast tiny dots; all returned landmarks are shown.
        for lm in landmarks:
            x, y = int(round(lm.x * w)), int(round(lm.y * h))
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse((x-1, y-1, x+1, y+1), fill=(60, 235, 120))
        # A few recognizable facial anchors: eyes, nose tip, lips.
        for ix in (1, 4, 13, 14, 33, 263):
            if ix < len(landmarks):
                lm = landmarks[ix]
                x, y = int(round(lm.x * w)), int(round(lm.y * h))
                if 0 <= x < w and 0 <= y < h:
                    draw.ellipse((x-4, y-4, x+4, y+4), outline=(255, 195, 55), width=2)
    draw.rectangle((0, 0, w, 39), fill=(10, 15, 23))
    draw.text((8, 5), f'MediaPipe Kinect IR | {label}', fill=(255, 255, 255))
    if pose is None:
        draw.text((8, 21), 'Pose unavailable / no detection', fill=(255, 195, 55))
    else:
        draw.text((8, 21), f'Yaw {pose[0]:+.1f}  Pitch {pose[1]:+.1f}  Roll {pose[2]:+.1f} (approx)', fill=(255, 195, 55))
    destination.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(destination)


def main():
    parser = argparse.ArgumentParser(description='Test MediaPipe on a saved Kinect v2 IR frame (no camera/PAM/Qt)')
    parser.add_argument('--input', type=Path, required=True, help='8-bit IR PGM/PNG or float32 .f32 (512x424)')
    parser.add_argument('--model', type=Path, default=Path('models/face_landmarker.task'))
    parser.add_argument('--output', type=Path, default=Path('research-data/mediapipe-ir-result.png'))
    parser.add_argument('--format', choices=('auto', 'f32', 'image'), default='auto')
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f'No input file: {args.input}')
    if not args.model.is_file() or args.model.stat().st_size < 100000:
        parser.error(f'MediaPipe model missing or too small: {args.model}. Download official face_landmarker.task first.')

    try:
        from PIL import Image  # noqa: F401
        import mediapipe as mp
        image = load_ir(args.input, args.format)
        variants = make_variants(image)
        print(f'Input: {args.input} | {image.width}x{image.height} | mediapipe {mp.__version__}', flush=True)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        winner = None
        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as landmarker:
            for name, gray in variants.items():
                rgb = np.ascontiguousarray(np.repeat(gray[:, :, None], 3, axis=2))
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                started = time.perf_counter()
                result = landmarker.detect(mp_image)
                elapsed = (time.perf_counter() - started) * 1000
                faces = len(result.face_landmarks)
                count = len(result.face_landmarks[0]) if faces else 0
                print(f'{name}: faces={faces}, landmarks={count}, processing={elapsed:.0f}ms', flush=True)
                if faces and winner is None:
                    pose = None
                    if result.facial_transformation_matrixes:
                        pose = approx_pose(result.facial_transformation_matrixes[0])
                    winner = (name, gray, result.face_landmarks[0], pose)
        if winner is None:
            print('No face detected in any variant. This can happen on IR; it does not mean Kinect is broken.')
            annotate(variants['original'], None, None, 'no face detected', args.output)
            print(f'Saved diagnostic image: {args.output.resolve()}')
            return 2
        name, gray, landmarks, pose = winner
        annotate(gray, landmarks, pose, name, args.output)
        print(f'FOUND FACE using {name}; {len(landmarks)} landmarks')
        if pose is not None:
            print(f'Approx matrix angles (NOT calibrated): yaw={pose[0]:+.1f}, pitch={pose[1]:+.1f}, roll={pose[2]:+.1f} deg')
        print(f'Saved annotated image: {args.output.resolve()}')
        print('Reminder: MediaPipe transform is not Kinect metric XYZ or spoof/liveness protection.')
        return 0
    except ImportError as exc:
        print(f'Python dependency unavailable: {exc}. Use your .venv-mediapipe Python; install Pillow if missing.', file=sys.stderr)
        return 3
    except Exception as exc:
        print(f'Analysis error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
