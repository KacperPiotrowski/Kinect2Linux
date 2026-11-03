"""Pure 2D COCO-17 skeleton overlay geometry (no GUI/AI imports).

Input: normalized image-coordinate keypoints returned by the existing tracking
SDK. 3D depth and biometric identity are neither inferred nor fabricated.
"""
from __future__ import annotations

import math

# COCO-17; all segments must have two valid, confident detected joints.
BONES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
)


def visible(point, threshold: float = 0.45) -> bool:
    confidence = point.confidence
    return (
        confidence is not None and math.isfinite(confidence)
        and confidence >= threshold
        and math.isfinite(point.x) and math.isfinite(point.y)
        and 0.0 <= point.x <= 1.0 and 0.0 <= point.y <= 1.0
    )


def skeleton_geometry(result, *, threshold: float = 0.45):
    """Return (line segments, joints) in normalized frame coordinates.

    Only valid COCO-17 persons; virtual spine is a visualization midpoint,
    not a predicted joint. No extrapolation outside the image.
    """
    lines = []
    joints = []
    for subject in result.subjects:
        if subject.kind != "person" or len(subject.keypoints) != 17:
            continue
        points = subject.keypoints
        is_visible = [visible(p, threshold) for p in points]
        for i, point in enumerate(points):
            if is_visible[i]:
                joints.append((point.x, point.y))
        for a, b in BONES:
            if is_visible[a] and is_visible[b]:
                lines.append(((points[a].x, points[a].y),
                              (points[b].x, points[b].y)))
        # Illustration-only center spine; do not invent model joints.
        if all(is_visible[i] for i in (5, 6, 11, 12)):
            shoulders = ((points[5].x + points[6].x) / 2,
                         (points[5].y + points[6].y) / 2)
            hips = ((points[11].x + points[12].x) / 2,
                    (points[11].y + points[12].y) / 2)
            lines.append((shoulders, hips))
    return lines, joints
