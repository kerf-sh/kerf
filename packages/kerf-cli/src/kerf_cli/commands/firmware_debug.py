"""
kerf_cli.commands.firmware_debug — `kerf firmware debug attach` command.

Attaches to a running target via OpenOCD + arm-none-eabi-gdb and prints a
live RTOS task / mutex snapshot to stdout (JSON or human-readable table).

Usage
-----
  kerf firmware debug attach [--elf <path>] [--target stm32f4] [--json]

The command requires `openocd` and `arm-none-eabi-gdb` (or `gdb-multiarch`)
to be installed and on PATH.  On the cloud path (i.e. when invoked via the
web API without a local CLI) a sentinel is returned instead:

  "JTAG requires the local Kerf CLI"

This matches the sentinel documented in T-262.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Cloud sentinel
# ---------------------------------------------------------------------------

JTAG_CLOUD_SENTINEL = "JTAG requires the local Kerf CLI"


def cloud_sentinel_response() -> dict:
    """Return the standard cloud-path sentinel dict."""
    return {
        "ok": False,
        "error": "JTAG_LOCAL_ONLY",
        "message": JTAG_CLOUD_SENTINEL,
        "tasks": [],
        "sync_objects": [],
        "edges": [],
        "warnings": [JTAG_CLOUD_SENTINEL],
    }


# ---------------------------------------------------------------------------
# Attach logic
# ---------------------------------------------------------------------------

def attach_and_snapshot(
    elf_path: str = "",
    target: str = "stm32f4",
    rtos: str = "kerfrtos",
    gdb_port: int = 3333,
    _subprocess_factory=None,
) -> dict:
    """
    Attach to the target and return a DebugSnapshot as a dict.

    Parameters
    ----------
    elf_path : str
        Path to the ELF file.  Symbols are loaded from it.
    target : str
        OpenOCD target config (e.g. "stm32f4" → "target/stm32f4x.cfg").
    rtos : str
        "kerfrtos" or "freertos".
    gdb_port : int
        TCP port for GDB remote (default 3333).
    _subprocess_factory : callable, optional
        Injected for tests.

    Returns
    -------
    dict
        Serialised :class:`kerf_firmware.debug.rtos_inspect.DebugSnapshot`.
    """
    from kerf_firmware.debug.openocd import (
        OpenOCDSession,
        OpenOCDNotInstalledError,
        GDBNotInstalledError,
    )
    from kerf_firmware.debug.rtos_inspect import RTOSInspector

    # Build target-specific OpenOCD args
    openocd_args = _build_openocd_args(target)

    kwargs: dict = {}
    if _subprocess_factory is not None:
        kwargs["_subprocess_factory"] = _subprocess_factory

    try:
        with OpenOCDSession(
            openocd_args=openocd_args,
            elf_path=elf_path,
            gdb_port=gdb_port,
            **kwargs,
        ) as session:
            inspector = RTOSInspector(session, rtos=rtos)
            snap = inspector.snapshot()
            result = snap.as_dict()
            result["ok"] = True
            return result

    except OpenOCDNotInstalledError as exc:
        return _err(str(exc), "OPENOCD_NOT_INSTALLED")
    except GDBNotInstalledError as exc:
        return _err(str(exc), "GDB_NOT_INSTALLED")
    except Exception as exc:  # noqa: BLE001
        return _err(f"Debug attach failed: {exc}", "ATTACH_ERROR")


def _build_openocd_args(target: str) -> list[str]:
    """Map a short target name to OpenOCD config arguments."""
    cfg_map = {
        "stm32f4": "target/stm32f4x.cfg",
        "stm32f1": "target/stm32f1x.cfg",
        "stm32h7": "target/stm32h7x.cfg",
        "nrf52": "target/nrf52.cfg",
        "esp32": "target/esp32.cfg",
        "rp2040": "target/rp2040.cfg",
    }
    target_cfg = cfg_map.get(target.lower(), f"target/{target}.cfg")
    return [
        "-f", "interface/stlink.cfg",
        "-f", target_cfg,
        "-c", "init",
        "-c", "halt",
    ]


def _err(message: str, code: str) -> dict:
    return {
        "ok": False,
        "error": code,
        "message": message,
        "tasks": [],
        "sync_objects": [],
        "edges": [],
        "warnings": [message],
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def add_firmware_debug_parser(
    sub: "argparse._SubParsersAction",
) -> None:
    """Register `kerf firmware debug attach` onto an existing sub-parser."""
    fw_p = sub.add_parser(
        "firmware",
        help="Firmware debug and inspection commands",
    )
    fw_sub = fw_p.add_subparsers(dest="firmware_command", metavar="<firmware-command>")
    fw_sub.required = True

    debug_p = fw_sub.add_parser(
        "debug",
        help="RTOS-aware debugger commands",
    )
    debug_sub = debug_p.add_subparsers(dest="debug_command", metavar="<debug-command>")
    debug_sub.required = True

    attach_p = debug_sub.add_parser(
        "attach",
        help="Attach to a target and dump a live RTOS task/mutex snapshot",
        description=(
            "Connect to a target via OpenOCD + arm-none-eabi-gdb and print\n"
            "a structured RTOS snapshot (tasks, mutexes, dependency edges).\n\n"
            "Requires openocd and arm-none-eabi-gdb on PATH."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    attach_p.add_argument(
        "--elf",
        default="",
        metavar="PATH",
        help="Path to the ELF file (loads debug symbols).",
    )
    attach_p.add_argument(
        "--target",
        default="stm32f4",
        metavar="TARGET",
        help="OpenOCD target name (default: stm32f4).",
    )
    attach_p.add_argument(
        "--rtos",
        default="kerfrtos",
        choices=["kerfrtos", "freertos"],
        help="RTOS type (default: kerfrtos).",
    )
    attach_p.add_argument(
        "--port",
        type=int,
        default=3333,
        metavar="PORT",
        help="GDB remote TCP port (default: 3333).",
    )
    attach_p.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="Output raw JSON instead of a human-readable table.",
    )
    attach_p.set_defaults(func=_cmd_attach)


def _cmd_attach(args: argparse.Namespace) -> int:
    result = attach_and_snapshot(
        elf_path=getattr(args, "elf", ""),
        target=getattr(args, "target", "stm32f4"),
        rtos=getattr(args, "rtos", "kerfrtos"),
        gdb_port=getattr(args, "port", 3333),
    )

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    return 0 if result.get("ok") else 1


def _print_human(result: dict) -> None:
    """Print a human-readable table of RTOS tasks and sync objects."""
    if not result.get("ok"):
        msg = result.get("message") or result.get("error") or "Unknown error"
        print(f"Error: {msg}", file=sys.stderr)
        return

    tasks = result.get("tasks", [])
    print(f"\nTasks ({len(tasks)})")
    print(f"{'Name':<20} {'State':<12} {'Pri':>4} {'Stack HW':>10} {'Stack':>8} {'%Free':>7}")
    print("-" * 65)
    for t in tasks:
        warn = " !" if t.get("stack_warning") else ""
        print(
            f"{t['name']:<20} {t['state']:<12} {t['priority']:>4} "
            f"{t['stack_high_water']:>10} {t['stack_size']:>8} "
            f"{t.get('stack_pct_free', 0):>6.1f}%{warn}"
        )

    sync = result.get("sync_objects", [])
    if sync:
        print(f"\nSync Objects ({len(sync)})")
        print(f"{'Name':<24} {'Kind':<12} {'Held By':<20} {'Waiters'}")
        print("-" * 70)
        for s in sync:
            held = s.get("held_by") or "-"
            waiters = ", ".join(s.get("waiters") or []) or "-"
            print(f"{s['name']:<24} {s['kind']:<12} {held:<20} {waiters}")

    edges = result.get("edges", [])
    if edges:
        print(f"\nDependency Edges ({len(edges)})")
        for e in edges:
            print(f"  {e['from']} -> {e['to']}  [{e['label']}]")

    warnings = result.get("warnings", [])
    if warnings:
        print(f"\nWarnings")
        for w in warnings:
            print(f"  ! {w}")
