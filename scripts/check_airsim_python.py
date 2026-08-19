#!/usr/bin/env python3
"""Check that the configured Python can import the selected AirSim client."""

import argparse
from pathlib import Path

try:
    from scripts.airsim_compat import import_airsim
except ImportError:
    from airsim_compat import import_airsim


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--airsim-client", required=True)
    parser.add_argument(
        "--airsim-rpc-vendor",
        default=str(Path(__file__).resolve().parents[1] / ".tools" / "airsim_rpc"),
    )
    args = parser.parse_args()
    module = import_airsim(args.airsim_client, args.airsim_rpc_vendor)
    if not hasattr(module, "MultirotorClient"):
        raise RuntimeError("AirSim client does not expose MultirotorClient")
    print(f"AirSim Python import ready: {module.__file__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
