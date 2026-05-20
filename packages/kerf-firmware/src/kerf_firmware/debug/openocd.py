"""
kerf_firmware.debug.openocd — subprocess bridge to OpenOCD + arm-none-eabi-gdb.

Design
------
- OpenOCDSession spawns `openocd` (with a given interface/target config) as a
  subprocess and connects to its GDB stub on port 3333.
- GDB is invoked in MI2 mode (--interpreter=mi2) so all output is machine-
  parseable.
- Both processes are managed as context managers; .close() is idempotent.
- The whole layer is *subprocess-only*; no sockets are opened by this module
  directly — gdb speaks to openocd over the loopback TCP stub that openocd
  provides.

Mock contract (for tests)
-------------------------
If the ``_subprocess_factory`` kwarg is supplied to OpenOCDSession, it is
called instead of ``subprocess.Popen``.  Tests pass in a factory that returns
a mock Popen-compatible object with pre-programmed stdout lines.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Generator, IO, Optional


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------

class OpenOCDNotInstalledError(RuntimeError):
    """Raised when the `openocd` binary is not on PATH."""


class GDBNotInstalledError(RuntimeError):
    """Raised when the `arm-none-eabi-gdb` (or `gdb-multiarch`) binary is not on PATH."""


# ---------------------------------------------------------------------------
# GDB-MI record types
# ---------------------------------------------------------------------------

@dataclass
class MIRecord:
    """A single GDB/MI output record."""
    type: str          # "result", "async", "stream", "oob"
    class_: str        # e.g. "done", "running", "error", "stopped"
    payload: dict      # parsed key=value pairs (may be empty)
    raw: str           # original line, for debugging


def parse_mi_line(line: str) -> Optional[MIRecord]:
    """
    Parse a single GDB/MI output line into an MIRecord.

    MI output grammar (simplified):
      result-record   : token? "^" result-class ( "," result )* nl
      async-record    : token? ( "*" | "+" | "=" ) async-class ( "," result )* nl
      stream-record   : ( "~" | "@" | "&" ) c-string nl

    We only need a subset for RTOS inspection.
    """
    line = line.strip()
    if not line or line == "(gdb)":
        return None

    # Determine record kind from prefix character
    for prefix, rtype in (("^", "result"), ("*", "async"), ("+", "async"),
                           ("=", "notify"), ("~", "stream"), ("@", "target"),
                           ("&", "log")):
        idx = line.find(prefix)
        if idx != -1:
            rest = line[idx + 1:]
            # Split class from payload
            if "," in rest:
                cls, payload_str = rest.split(",", 1)
            else:
                cls, payload_str = rest, ""
            payload = _parse_mi_payload(payload_str)
            return MIRecord(type=rtype, class_=cls.strip(), payload=payload, raw=line)

    return MIRecord(type="unknown", class_="", payload={}, raw=line)


def _parse_mi_payload(payload_str: str) -> dict:
    """
    Best-effort key=value parser for GDB/MI result payloads.

    GDB/MI uses:  key="string"  or  key={...}  or  key=[...]
    We return a flat dict of string keys → string/list/dict values.
    This parser handles the common single-level and one-nested-level cases
    that are sufficient for RTOS task inspection.
    """
    result: dict = {}
    if not payload_str.strip():
        return result

    # Walk the string character by character
    pos = 0
    length = len(payload_str)

    def skip_whitespace() -> None:
        nonlocal pos
        while pos < length and payload_str[pos] in " \t":
            pos += 1

    def read_key() -> str:
        nonlocal pos
        start = pos
        while pos < length and payload_str[pos] not in "=,{[":
            pos += 1
        return payload_str[start:pos].strip()

    def read_string() -> str:
        """Read a GDB/MI c-string (starts after the opening quote)."""
        nonlocal pos
        buf = []
        while pos < length:
            ch = payload_str[pos]
            if ch == "\\":
                pos += 1
                if pos < length:
                    buf.append(payload_str[pos])
            elif ch == '"':
                pos += 1
                break
            else:
                buf.append(ch)
            pos += 1
        return "".join(buf)

    while pos < length:
        skip_whitespace()
        if pos >= length:
            break
        key = read_key()
        skip_whitespace()
        if pos >= length or payload_str[pos] != "=":
            # Skip unexpected characters
            if pos < length and payload_str[pos] == ",":
                pos += 1
            continue
        pos += 1  # consume '='
        skip_whitespace()
        if pos >= length:
            break
        ch = payload_str[pos]
        if ch == '"':
            pos += 1  # consume opening quote
            value = read_string()
        elif ch in "{[":
            # Nested structure — capture the raw bracketed content
            depth = 0
            start = pos
            while pos < length:
                if payload_str[pos] in "{[":
                    depth += 1
                elif payload_str[pos] in "}]":
                    depth -= 1
                    if depth == 0:
                        pos += 1
                        break
                pos += 1
            value = payload_str[start:pos]
        else:
            # Unquoted value (rare) — read until comma or end
            start = pos
            while pos < length and payload_str[pos] != ",":
                pos += 1
            value = payload_str[start:pos].strip()
        if key:
            result[key] = value
        skip_whitespace()
        if pos < length and payload_str[pos] == ",":
            pos += 1

    return result


# ---------------------------------------------------------------------------
# OpenOCD session
# ---------------------------------------------------------------------------

_DEFAULT_OPENOCD_ARGS = [
    "-f", "interface/stlink.cfg",
    "-f", "target/stm32f4x.cfg",
    "-c", "init",
    "-c", "halt",
]

_GDB_CANDIDATES = ["arm-none-eabi-gdb", "gdb-multiarch", "arm-linux-gnueabihf-gdb"]


def _find_gdb() -> Optional[str]:
    """Return the first GDB binary found on PATH, or None."""
    for candidate in _GDB_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return None


class OpenOCDSession:
    """
    Manages the OpenOCD + GDB-MI subprocess pair for JTAG/SWD debugging.

    Parameters
    ----------
    openocd_args : list[str]
        Command-line arguments for `openocd` (config files, init commands).
    elf_path : str
        Path to the ELF file to load symbols from.
    gdb_port : int
        TCP port that OpenOCD listens on for GDB connections (default 3333).
    _subprocess_factory : callable, optional
        Injected for tests — called with the same signature as
        ``subprocess.Popen``.  Must return an object with ``.stdout``,
        ``.returncode``, ``.communicate()``, ``.kill()``, and ``.wait()``.
    """

    def __init__(
        self,
        openocd_args: list[str] | None = None,
        elf_path: str = "",
        gdb_port: int = 3333,
        _subprocess_factory: Optional[Callable] = None,
    ) -> None:
        self.openocd_args = openocd_args or _DEFAULT_OPENOCD_ARGS
        self.elf_path = elf_path
        self.gdb_port = gdb_port
        self._popen = _subprocess_factory or subprocess.Popen
        self._openocd_proc: Optional[subprocess.Popen] = None
        self._gdb_proc: Optional[subprocess.Popen] = None
        self._mi_lines: list[str] = []

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "OpenOCDSession":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch OpenOCD and GDB-MI subprocesses."""
        # Check openocd is available (skip check when factory is injected)
        if self._popen is subprocess.Popen and not shutil.which("openocd"):
            raise OpenOCDNotInstalledError(
                "openocd not found on PATH.  "
                "Install it with: brew install open-ocd  (macOS) or "
                "apt-get install openocd  (Debian/Ubuntu)"
            )

        # Launch OpenOCD
        self._openocd_proc = self._popen(
            ["openocd"] + self.openocd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Check gdb is available
        if self._popen is subprocess.Popen:
            gdb_bin = _find_gdb()
            if gdb_bin is None:
                self._openocd_proc.kill()
                raise GDBNotInstalledError(
                    "arm-none-eabi-gdb / gdb-multiarch not found on PATH.  "
                    "Install the ARM toolchain (e.g. arm-none-eabi-gcc)."
                )
        else:
            gdb_bin = "arm-none-eabi-gdb"

        # Launch GDB in MI2 mode
        gdb_cmd = [
            gdb_bin,
            "--interpreter=mi2",
            "--batch-silent",
            f"--eval-command=target remote :{self.gdb_port}",
        ]
        if self.elf_path:
            gdb_cmd.extend(["--se", self.elf_path])

        self._gdb_proc = self._popen(
            gdb_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
        )

    def close(self) -> None:
        """Terminate OpenOCD and GDB subprocesses."""
        for proc in (self._gdb_proc, self._openocd_proc):
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    pass
        self._gdb_proc = None
        self._openocd_proc = None

    # ------------------------------------------------------------------
    # GDB-MI command interface
    # ------------------------------------------------------------------

    def send_mi_command(self, command: str) -> list[MIRecord]:
        """
        Send a GDB/MI command and collect the response records.

        Returns all MIRecord objects received until a ``^done``, ``^error``,
        or ``^running`` result record is seen.
        """
        if self._gdb_proc is None or self._gdb_proc.stdin is None:
            raise RuntimeError("GDB process is not running")

        self._gdb_proc.stdin.write(command.strip() + "\n")
        self._gdb_proc.stdin.flush()

        records: list[MIRecord] = []
        stdout: IO = self._gdb_proc.stdout  # type: ignore[assignment]
        for raw_line in stdout:
            rec = parse_mi_line(raw_line)
            if rec is None:
                continue
            records.append(rec)
            if rec.type == "result" and rec.class_ in ("done", "error", "running"):
                break

        return records

    def read_available_mi_lines(self) -> list[MIRecord]:
        """
        Drain all currently available output lines without blocking.
        Useful when stdout has been pre-loaded (mock / test scenario).
        """
        if self._gdb_proc is None or self._gdb_proc.stdout is None:
            return []
        records: list[MIRecord] = []
        for raw_line in self._gdb_proc.stdout:
            rec = parse_mi_line(raw_line)
            if rec is not None:
                records.append(rec)
        return records

    def evaluate_expression(self, expr: str) -> str:
        """
        Evaluate a GDB expression and return the string result.

        Uses -data-evaluate-expression in MI2.
        """
        records = self.send_mi_command(f"-data-evaluate-expression {expr}")
        for rec in records:
            if rec.type == "result" and rec.class_ == "done":
                return rec.payload.get("value", "")
        return ""

    def read_memory(self, address: str, count: int, unit: int = 4) -> list[str]:
        """
        Read *count* memory units starting at *address*.

        Returns a list of hex strings.
        """
        records = self.send_mi_command(
            f"-data-read-memory-bytes {address} {count * unit}"
        )
        for rec in records:
            if rec.type == "result" and rec.class_ == "done":
                raw = rec.payload.get("memory", "")
                # Very simplified: split by spaces
                return raw.split() if raw else []
        return []
