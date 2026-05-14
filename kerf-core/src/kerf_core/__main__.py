"""CLI entry-point — boots the Kerf FastAPI app with uvicorn.

Usage::

    python -m kerf_core [--config kerf.toml] [--host 0.0.0.0] [--port 8080] [--reload]
    kerf-server [--config kerf.toml] [--host 0.0.0.0] [--port 8080] [--reload]
"""
from __future__ import annotations

import argparse
import os
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="kerf-server",
        description="Boot the Kerf backend (FastAPI + plugin loader).",
    )
    parser.add_argument("--config", default=os.environ.get("KERF_CONFIG", ""))
    parser.add_argument("--host", default=os.environ.get("KERF_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("KERF_PORT", "8080")))
    parser.add_argument("--reload", action="store_true", default=False)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required. Install with: pip install uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    if args.config:
        os.environ["KERF_CONFIG"] = args.config

    uvicorn.run(
        "kerf_core.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
