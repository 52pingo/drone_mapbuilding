"""Compatibility helpers for importing the legacy AirSim Python client."""

from __future__ import annotations

from pathlib import Path
import ssl
import sys
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]


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
