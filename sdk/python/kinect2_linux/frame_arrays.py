"""Opt-in NumPy views/copies of native broker frame buffers.

NumPy is imported only when this function is called: the SDK, broker and
OFF tracking mode do not depend on it merely by being imported.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frame_client import FrameSnapshot


def frame_to_numpy(frame: "FrameSnapshot", *, copy: bool = True):
    """Decode a validated raw FrameSnapshot without color/depth conversion.

    RGB is uint8 (height, width, 4) in **BGRX** byte order.
    IR is raw float32 (height, width); Depth is float32 **millimetres**.

    By default, own a copy that survives ``frame.close()``. With ``copy=False``
    the returned view borrows the frame's mmap. Release **all** derived views
    before closing the frame or Python may raise BufferError. Never store
    zero-copy arrays beyond their frame's lifetime.
    """
    if type(copy) is not bool:
        raise TypeError("copy must be a bool")

    from .frame_client import FrameProtocolError
    import numpy as np

    if (frame.width <= 0 or frame.height <= 0 or
            frame.bytes_per_pixel != 4):
        raise FrameProtocolError("invalid frame geometry")
    expected_bytes = frame.width * frame.height * 4
    if frame.kind == "rgb":
        dtype, shape = np.uint8, (frame.height, frame.width, 4)
    elif frame.kind in ("ir", "depth"):
        dtype, shape = np.dtype("<f4"), (frame.height, frame.width)
    else:
        raise FrameProtocolError("unsupported frame kind")

    try:
        if len(frame.mapping) != expected_bytes:
            raise FrameProtocolError("invalid mapped frame size")
        array = np.frombuffer(frame.mapping, dtype=dtype).reshape(shape)
    except (BufferError, ValueError, TypeError) as exc:
        raise FrameProtocolError("cannot view closed or invalid frame mapping") from exc
    return array.copy() if copy else array
