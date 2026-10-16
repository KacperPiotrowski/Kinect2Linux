"""Versioned framing for *control* messages over a local Unix stream socket.

Raw video/audio bytes must never be embedded in control JSON. This module does
not connect to a sensor or provide a client for the future C++ broker.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from typing import Any, Protocol

PROTOCOL_VERSION = 1
MAX_CONTROL_BYTES = 65536
_LENGTH = struct.Struct(">I")


class ProtocolError(ValueError):
    """Invalid, unsupported, or incomplete IPC control message."""


class ReadableSocket(Protocol):
    def recv(self, bufsize: int) -> bytes: ...


def _check_message(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ProtocolError("IPC control message must be a JSON object")
    version = message.get("protocol_version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported or missing protocol_version")
    return message


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Encode a control object as 4-byte big-endian length + UTF-8 JSON."""
    if not isinstance(message, Mapping):
        raise ProtocolError("IPC control message must be a mapping")
    value = _check_message(dict(message))
    try:
        payload = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ProtocolError("IPC control message cannot be JSON-encoded") from exc
    if not payload or len(payload) > MAX_CONTROL_BYTES:
        raise ProtocolError("IPC control message exceeds size limit")
    return _LENGTH.pack(len(payload)) + payload


def _receive_exact(sock: ReadableSocket, size: int) -> bytes:
    parts: list[bytes] = []
    remaining = size
    while remaining:
        try:
            chunk = sock.recv(remaining)
        except (OSError, TimeoutError) as exc:
            raise ProtocolError("socket read failed or timed out") from exc
        if not chunk:
            raise ProtocolError("unexpected EOF in IPC message")
        if len(chunk) > remaining:
            raise ProtocolError("socket returned more data than requested")
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def receive_message(sock: ReadableSocket) -> dict[str, Any]:
    """Read exactly one bounded message; handles short reads and rejects EOF."""
    (length,) = _LENGTH.unpack(_receive_exact(sock, _LENGTH.size))
    if not 0 < length <= MAX_CONTROL_BYTES:
        raise ProtocolError("invalid IPC control message size")
    payload = _receive_exact(sock, length)

    def reject_constant(value: str) -> None:
        raise ProtocolError(f"non-finite JSON number is forbidden: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProtocolError("invalid IPC control message JSON") from exc
    return _check_message(value)
