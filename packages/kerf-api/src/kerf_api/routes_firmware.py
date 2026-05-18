"""
routes_firmware.py — HTTP routes wrapping the firmware build / upload / monitor pipeline.

Routes (all mounted under /api via plugin.py):
  POST /firmware/build   — compile a .fw.json project or .ino sketch
  POST /firmware/upload  — flash compiled artifact to a connected board
  POST /firmware/monitor — read a serial snapshot from the board

Response shape for all three endpoints:
  {
    "ok":     bool,
    "status": "success" | "error" | "pending",
    ...endpoint-specific fields...
  }

"pending" is returned when the required tool (arduino-cli / avrdude / pyserial)
is not installed or when no board is connected — never a 5xx.  The frontend
shows an install/connect prompt in that case.
"""
from __future__ import annotations

from fastapi import APIRouter

firmware_router = APIRouter()


# ── POST /firmware/build ──────────────────────────────────────────────────────

@firmware_router.post("/firmware/build")
async def firmware_build(req: dict) -> dict:
    """Compile a firmware project.

    Body:
      { "source_path": "<abs-path>", "fw_config": { ... } }   (fw_config optional)

    Returns:
      { "ok": bool, "status": str, "hex_path": str|null, "errors": [...], "warnings": [...] }
    """
    source_path = req.get("source_path", "")
    fw_config = req.get("fw_config") or None

    if not source_path or not isinstance(source_path, str):
        return {
            "ok": False,
            "status": "error",
            "hex_path": None,
            "errors": ["'source_path' must be a non-empty string"],
            "warnings": [],
        }

    try:
        from kerf_firmware.gcc_orchestrator import build
        result = build(source_path, fw_config)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "hex_path": None,
            "errors": [f"Unexpected error: {exc}"],
            "warnings": [],
        }

    return {
        "ok": result.ok,
        "status": result.status,
        "hex_path": result.hex_path,
        "errors": result.errors,
        "warnings": result.warnings,
    }


# ── POST /firmware/upload ─────────────────────────────────────────────────────

@firmware_router.post("/firmware/upload")
async def firmware_upload(req: dict) -> dict:
    """Flash a compiled firmware artifact to a connected board.

    Body:
      { "hex_path": "<abs-path>", "fw_config": { ... }, "port": "/dev/ttyUSB0" }
      (fw_config and port are optional)

    Returns:
      { "ok": bool, "status": str, "port": str|null, "errors": [...] }
    """
    hex_path = req.get("hex_path", "")
    fw_config = req.get("fw_config") or None
    port = req.get("port") or None

    if not hex_path or not isinstance(hex_path, str):
        return {
            "ok": False,
            "status": "error",
            "port": None,
            "errors": ["'hex_path' must be a non-empty string"],
        }

    try:
        from kerf_firmware.upload.router import upload
        result = upload(hex_path, fw_config, port)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "port": None,
            "errors": [f"Unexpected error: {exc}"],
        }

    return {
        "ok": result.ok,
        "status": result.status,
        "port": result.port,
        "errors": result.errors,
    }


# ── POST /firmware/monitor ────────────────────────────────────────────────────

@firmware_router.post("/firmware/monitor")
async def firmware_monitor(req: dict) -> dict:
    """Read a serial snapshot from the connected board.

    Body:
      { "fw_config": { ... }, "port": "/dev/ttyUSB0", "baud": 9600 }
      (all optional)

    Returns:
      { "ok": bool, "status": str, "port": str|null, "lines": [...], "errors": [...] }
    """
    fw_config = req.get("fw_config") or None
    port = req.get("port") or None
    baud = req.get("baud", 9600)

    if not isinstance(baud, int) or baud <= 0:
        baud = 9600

    try:
        from kerf_firmware.serial_monitor import snapshot
        result = snapshot(fw_config, port, baud)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "port": None,
            "lines": [],
            "errors": [f"Unexpected error: {exc}"],
        }

    return {
        "ok": result.ok,
        "status": result.status,
        "port": result.port,
        "lines": result.lines,
        "errors": result.errors,
    }
