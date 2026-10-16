"""Experimental, hardware-independent protocol primitives for Kinect2-Linux.

No running sensor service or frame streaming API is implemented yet.
"""

from .ipc import (
    MAX_CONTROL_BYTES,
    PROTOCOL_VERSION,
    ProtocolError,
    encode_message,
    receive_message,
)

__all__ = [
    "MAX_CONTROL_BYTES",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "encode_message",
    "receive_message",
]
