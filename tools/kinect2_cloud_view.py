#!/usr/bin/env python3
"""Simple offline viewer for ASCII PLY XYZ clouds exported by kinect2_cloud.cpp.
Uses python-numpy and python-opencv; no network, ROS or OpenGL required.
Colors are artificial by depth, not true RGB. Escape or q quits.
"""
import argparse
import pathlib
import sys

import cv2
import numpy as np


def load_ascii_ply(path):
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("Not a PLY file")
        header = []
        while True:
            line = f.readline()
            if not line:
                raise ValueError("Missing end_header")
            header.append(line.strip().decode("ascii"))
            if line.strip() == b"end_header":
                break
        if "format ascii 1.0" not in header:
            raise ValueError("This viewer expects an ASCII PLY from kinect2_cloud")
        rows = np.loadtxt(f, dtype=np.float32, usecols=(0, 1, 2), ndmin=2)
    if rows.shape[0] == 0 or rows.shape[1] != 3:
        raise ValueError("No XYZ points")
    rows = rows[np.isfinite(rows).all(axis=1)]
    if not len(rows):
        raise ValueError("No finite points")
    return rows


def main():
    parser = argparse.ArgumentParser(description="Interactive Kinect 3D point cloud viewer")
    parser.add_argument("ply", type=pathlib.Path)
    args = parser.parse_args()
    xyz = load_ascii_ply(args.ply)
    # Keep input file intact. Decimation is for responsive preview only.
    step = max(1, len(xyz) // 35000)
    xyz = xyz[::step].copy()
    center = np.median(xyz, axis=0)
    xyz -= center
    base_span = max(0.25, float(np.percentile(np.linalg.norm(xyz[:, :2], axis=1), 97)))
    title = "Kinect2-Linux Spatial Preview - Q/Esc to close"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, 1060, 760)
    for name, value, maximum in (("Yaw", 180, 360), ("Pitch", 180, 360), ("Zoom", 110, 240)):
        cv2.createTrackbar(name, title, value, maximum, lambda _v: None)
    latest = None
    while True:
        settings = tuple(cv2.getTrackbarPos(name, title) for name in ("Yaw", "Pitch", "Zoom"))
        if settings != latest:
            latest = settings
            yaw = np.deg2rad(settings[0] - 180)
            pitch = np.deg2rad(settings[1] - 180)
            sy, cy = np.sin(yaw), np.cos(yaw)
            sx, cx = np.sin(pitch), np.cos(pitch)
            ry = np.array([[cy, 0., sy], [0., 1., 0.], [-sy, 0., cy]], dtype=np.float32)
            rx = np.array([[1., 0., 0.], [0., cx, -sx], [0., sx, cx]], dtype=np.float32)
            rot = xyz @ (rx @ ry).T
            h, w = 700, 1040
            zoom = max(0.1, settings[2] / 100.0)
            scale = min(h, w) * 0.36 * zoom / base_span
            px = np.rint(w / 2 + rot[:, 0] * scale).astype(np.int32)
            py = np.rint(h / 2 + rot[:, 1] * scale).astype(np.int32)
            valid = (px >= 1) & (px < w - 1) & (py >= 1) & (py < h - 1)
            px, py = px[valid], py[valid]
            depths = rot[valid, 2]
            order = np.argsort(depths)[::-1]  # draw far points first
            px, py, depths = px[order], py[order], depths[order]
            img = np.full((h, w, 3), (25, 24, 23), dtype=np.uint8)
            if len(px):
                dmin, dmax = np.percentile(depths, [3, 97])
                levels = (np.clip((depths - dmin) / max(1e-4, dmax - dmin), 0, 1) * 220).astype(np.uint8)
                colors = cv2.applyColorMap(levels.reshape(-1, 1), cv2.COLORMAP_TURBO)[:, 0, :]
                img[py, px] = colors
                img[py + 1, px] = colors
                img[py, px + 1] = colors
            cv2.putText(img, f"3D POINT CLOUD | {len(xyz):,} points sampled", (16, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (240, 240, 240), 1, cv2.LINE_AA)
            cv2.putText(img, "Yaw / Pitch / Zoom: sliders | Q or Esc: exit", (16, h - 22),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (230, 230, 230), 1, cv2.LINE_AA)
            cv2.putText(img, "False depth colours (not RGB) | coordinates in metres", (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, .46, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.imshow(title, img)
        key = cv2.waitKey(30) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break
        if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        sys.exit(1)
