#!/usr/bin/env python3
"""Explicitly provision two official ONNX model archives for Body Basic.

Default is READ-ONLY status. --download is a conscious network action; normal
tracking never downloads weights. No shell, package install, root, or USB.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
SOURCES = (
    ("rtmpose-body-det-tiny.onnx",
     "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
     "yolox_tiny_8xb8-300e_humanart-6f3252f9.zip"),
    ("rtmpose-body-pose-s.onnx",
     "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
     "rtmpose-s_simcc-body7_pt-body7_420e-256x192-acd4a1ef_20230504.zip"),
)
MAX_DOWNLOAD = 192 * 1024 * 1024
MAX_EXTRACT = 192 * 1024 * 1024


def download_one(url: str, dest: Path) -> None:
    if dest.exists() or dest.is_symlink():
        raise RuntimeError(f"Refusing to overwrite: {dest}")
    with tempfile.TemporaryDirectory(prefix="kinect2-model-") as tmp:
        archive = Path(tmp) / "model.zip"
        with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
            total = 0
            while part := response.read(1024 * 1024):
                total += len(part)
                if total > MAX_DOWNLOAD:
                    raise RuntimeError("Model download too large; refusing.")
                output.write(part)
        with ZipFile(archive) as src:
            choices = [
                entry for entry in src.infolist()
                if not entry.is_dir() and entry.filename.lower().endswith(".onnx")
            ]
            if len(choices) != 1 or not 1024 <= choices[0].file_size <= MAX_EXTRACT:
                raise RuntimeError("Expected one reasonably sized ONNX model in archive.")
            # Stream one member to a private temporary file. Never extract archive paths.
            staging = Path(tmp) / "model.onnx"
            with src.open(choices[0]) as source, staging.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        if dest.exists() or dest.is_symlink():
            raise RuntimeError(f"Destination appeared during download: {dest}")
        # Creates exactly one model file. No other files from ZIP are extracted.
        with dest.open("xb") as output, staging.open("rb") as source:
            shutil.copyfileobj(source, output, length=1024 * 1024)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true",
                        help="Explicitly fetch and extract two official OpenMMLab weights.")
    args = parser.parse_args(argv)
    if MODEL_DIR.is_symlink() or not MODEL_DIR.is_dir():
        print("Expected ordinary repo models/ directory.", file=sys.stderr)
        return 2
    for filename, url in SOURCES:
        dest = MODEL_DIR / filename
        if dest.is_symlink():
            print(f"Refusing symlink: {dest}", file=sys.stderr)
            return 2
        if dest.is_file():
            print(f"Already present: {filename}")
        elif not args.download:
            print(f"Missing: {filename}")
        else:
            print(f"Fetching from official OpenMMLab: {filename}", flush=True)
            try:
                download_one(url, dest)
            except (OSError, RuntimeError, BadZipFile, urllib.error.URLError) as exc:
                print(f"Cannot prepare {filename}: {exc}", file=sys.stderr)
                return 2
            print(f"Prepared: {filename}")
    print("Download completed; no model was loaded by Kinect2Linux." if args.download
          else "Read-only check. Use --download to explicitly fetch weights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
