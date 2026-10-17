"""Experimental synchronous client for the local C++ *control-only* broker.

This client does not expose raw frames or open the physical Kinect.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ipc import PROTOCOL_VERSION, ProtocolError, encode_message, receive_message


class BrokerError(RuntimeError):
    """The broker refused the operation or its response was invalid."""


class BrokerClient:
    def __init__(self, socket_path: str | os.PathLike[str] | None = None, *, timeout: float = 2.0):
        if socket_path is None:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if not runtime_dir:
                raise ValueError("XDG_RUNTIME_DIR is not set; supply socket_path")
            socket_path = Path(runtime_dir) / "kinect2-broker.sock"
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.socket_path = os.fspath(socket_path)
        self.timeout = timeout
        self._request_id = 0

    def request(self, op: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(op, str) or not op:
            raise ValueError("op must be a non-empty string")
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ValueError("params must be a mapping")
        self._request_id += 1
        request_id = self._request_id
        packet = encode_message({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "op": op,
            "params": dict(params),
        })
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)
                sock.sendall(packet)
                response = receive_message(sock)
        except (OSError, ProtocolError) as exc:
            raise BrokerError("cannot communicate with the Kinect2 control broker") from exc

        if type(response.get("request_id")) is not int or response["request_id"] != request_id:
            raise BrokerError("mismatched broker response request_id")
        if type(response.get("ok")) is not bool:
            raise BrokerError("invalid broker response status")
        if not response["ok"]:
            error = response.get("error")
            if not isinstance(error, dict) or not isinstance(error.get("code"), str):
                raise BrokerError("broker returned malformed error")
            raise BrokerError(f"broker error: {error['code']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise BrokerError("broker response result must be an object")
        return result

    def ping(self) -> bool:
        return self.request("ping").get("pong") is True

    def get_status(self) -> dict[str, Any]:
        return self.request("get_status")

    def list_devices(self) -> dict[str, Any]:
        """Read-only USB sysfs discovery; does not open the sensor."""
        return self.request("list_devices")

    def open_device(self) -> dict[str, Any]:
        """Explicitly claim USB (only when broker is started with hardware enabled)."""
        return self.request("open_device")

    def close_device(self) -> dict[str, Any]:
        """Release the USB handle and flock; safe to call repeatedly."""
        return self.request("close_device")

    def start_streams(self, *, rgb: bool = False, ir_depth: bool = False) -> dict[str, Any]:
        """Explicitly start native capture (no frame transport to Python yet)."""
        if type(rgb) is not bool or type(ir_depth) is not bool:
            raise TypeError("rgb and ir_depth must be booleans")
        if not rgb and not ir_depth:
            raise ValueError("select rgb, ir_depth, or both")
        return self.request("start_streams", {"rgb": rgb, "ir_depth": ir_depth})

    def stop_streams(self) -> dict[str, Any]:
        """Stop all active native capture without closing the USB device."""
        return self.request("stop_streams")
