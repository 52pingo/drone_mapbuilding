"""Compatibility helpers for importing the legacy AirSim Python client."""

from __future__ import annotations

import gc
from pathlib import Path
import ssl
import sys
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]


class AirSimLink:
    """Keep an AirSim RPC session usable when a response is lost mid-stream.

    The vendored msgpack client appends every byte it reads to an unpacker
    buffer and only ever consumes complete messages.  When one request fails
    part way through -- a timeout on a large image, a stalled renderer -- the
    tail of the abandoned response stays in that buffer, so the next read
    misparses and the buffer keeps growing.  The process then dies with
    MemoryError somewhere inside the vendor, and on 2026-09-23 that cost a
    55-minute perception run every detection it had collected, because the
    crash landed before any results were written.

    Reconnecting is the only recovery available without patching the vendor:
    a fresh client starts with an empty buffer.  Callers get a working session
    back instead of a transport error they cannot act on.
    """

    def __init__(self, airsim_module, camera: str, vehicle: str = "") -> None:
        self.airsim = airsim_module
        self.camera = camera
        self.vehicle = vehicle
        self.client = None
        self.reconnects = 0
        self.connect()

    def connect(self) -> None:
        self.release()
        client = self.airsim.MultirotorClient()
        client.confirmConnection()
        self.client = client

    def release(self) -> None:
        client, self.client = self.client, None
        if client is None:
            return
        for name in ("close", "reset"):
            method = getattr(client, name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
                break
        del client
        gc.collect()

    def reconnect(self, reason: str) -> None:
        self.reconnects += 1
        try:
            self.connect()
        except Exception as error:
            raise RuntimeError(
                f"AirSim reconnect failed after {reason}: {error}") from error
        print(f"[airsim] reconnected (reason: {reason}, "
              f"total {self.reconnects})", flush=True)

    def camera_fov(self) -> float:
        return float(self.client.simGetCameraInfo(
            self.camera, vehicle_name=self.vehicle).fov)

    def grab(self, requests, attempts: int = 3):
        """Fetch images, rebuilding the session if a response is lost."""
        last = None
        for attempt in range(1, attempts + 1):
            try:
                return self.client.simGetImages(
                    requests, vehicle_name=self.vehicle)
            except Exception as error:  # includes MemoryError
                last = error
                if attempt == attempts:
                    break
                print(f"[airsim] simGetImages failed with "
                      f"{type(error).__name__}: {error}", flush=True)
                self.reconnect(type(error).__name__)
        raise last


def resolve_rpc_vendor(requested: str = "") -> Optional[Path]:
    """Find an optional vendored msgpack-rpc tree near the repository."""
    candidates = []
    if requested:
        candidates.append(Path(requested).expanduser())
    candidates.extend((
        REPO_ROOT / ".tools" / "airsim_rpc",
        REPO_ROOT.parent / ".tools" / "airsim_rpc",
    ))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def import_airsim(client_path: str, vendor_path: str = ""):
    """Import AirSim while avoiding an irrelevant legacy TLS initialization.

    AirSim 1.8.1 uses msgpack-rpc over plain TCP. Its Tornado 4 dependency
    nevertheless loads the Windows root certificate store at import time, and
    malformed legacy certificates can make that import fail. Temporarily use a
    certificate-free context only while importing this non-TLS client.
    """
    vendor = resolve_rpc_vendor(vendor_path)
    paths = [vendor, Path(client_path).expanduser() if client_path else None]
    for path in paths:
        if path is not None and str(path) not in sys.path:
            sys.path.insert(0, str(path))

    original_context = ssl.create_default_context

    def local_rpc_context(*_args, **_kwargs):
        protocol = getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS)
        context = ssl.SSLContext(protocol)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    ssl.create_default_context = local_rpc_context
    try:
        import airsim  # type: ignore
    finally:
        ssl.create_default_context = original_context
    return airsim
