"""sdc_reader.py — Minimal Tcl-subset SDC parser.

Supported commands
------------------
* ``create_clock -period <ns> [-name <name>] [<port>]``
* ``set_input_delay  -clock <clk> <delay_ns> [<port_list>]``
* ``set_output_delay -clock <clk> <delay_ns> [<port_list>]``
* ``set_max_delay    <delay_ns> -from <from> -to <to>``
* ``set_false_path   [-from <from>] [-to <to>]``

Only the single-statement form is supported (no Tcl variables, no procs,
no control flow).  Unknown commands are silently skipped so that real
SDC files with vendor extensions don't hard-fail.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


@dataclass
class ClockDef:
    """One ``create_clock`` statement."""
    period_ns: float
    name: str = ""
    port: str = ""


@dataclass
class InputDelay:
    """One ``set_input_delay`` statement."""
    delay_ns: float
    clock: str = ""
    ports: List[str] = field(default_factory=list)


@dataclass
class OutputDelay:
    """One ``set_output_delay`` statement."""
    delay_ns: float
    clock: str = ""
    ports: List[str] = field(default_factory=list)


@dataclass
class MaxDelay:
    """One ``set_max_delay`` statement."""
    delay_ns: float
    from_: str = ""
    to: str = ""


@dataclass
class FalsePath:
    """One ``set_false_path`` statement."""
    from_: str = ""
    to: str = ""


@dataclass
class SDCConstraints:
    """Collection of SDC constraints parsed from one file/string."""
    clocks: List[ClockDef] = field(default_factory=list)
    input_delays: List[InputDelay] = field(default_factory=list)
    output_delays: List[OutputDelay] = field(default_factory=list)
    max_delays: List[MaxDelay] = field(default_factory=list)
    false_paths: List[FalsePath] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tokeniser helpers
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"#[^\n]*")


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def _split_lines(text: str) -> list[str]:
    """Split SDC text into logical lines (handling backslash continuation)."""
    logical: list[str] = []
    buf = ""
    for raw_line in text.splitlines():
        stripped = raw_line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
        else:
            buf += stripped
            if buf.strip():
                logical.append(buf)
            buf = ""
    if buf.strip():
        logical.append(buf)
    return logical


def _tokenise(line: str) -> list[str]:
    """Split a single SDC line into tokens using shell-like quoting."""
    try:
        return shlex.split(line)
    except ValueError:
        # Fallback: split on whitespace, strip brackets/braces
        return [t.strip("{}[]") for t in line.split() if t.strip("{}[]")]


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Per-command parsers
# ---------------------------------------------------------------------------


def _parse_create_clock(tokens: list[str]) -> Optional[ClockDef]:
    """Parse ``create_clock -period <ns> [-name <n>] [<port>]``."""
    period: Optional[float] = None
    name: str = ""
    port: str = ""
    i = 1  # skip command name
    while i < len(tokens):
        t = tokens[i]
        if t == "-period" and i + 1 < len(tokens):
            try:
                period = float(tokens[i + 1])
            except ValueError:
                pass
            i += 2
        elif t == "-name" and i + 1 < len(tokens):
            name = tokens[i + 1].strip("[]")
            i += 2
        elif t == "-waveform" and i + 1 < len(tokens):
            # skip waveform list
            i += 2
        elif not t.startswith("-"):
            # positional port
            port = t.strip("[]")
            i += 1
        else:
            i += 1
    if period is None:
        return None
    if not name:
        name = port or "clk"
    return ClockDef(period_ns=period, name=name, port=port)


def _collect_port_list(tokens: list[str], start: int) -> tuple[list[str], int]:
    """Collect a port (or list of ports) starting at *start*.

    Handles both bare ``port`` and Tcl-list ``{p1 p2}`` / ``[list p1 p2]``
    forms.  Returns ``(ports, next_index)``.
    """
    if start >= len(tokens):
        return [], start
    t = tokens[start]
    # Already stripped by shlex — may be multi-token if user passed a list
    ports = [p.strip("{}[]") for p in t.split() if p.strip("{}[]")]
    return ports, start + 1


def _parse_set_input_delay(tokens: list[str]) -> Optional[InputDelay]:
    clock = ""
    delay: Optional[float] = None
    ports: list[str] = []
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-clock" and i + 1 < len(tokens):
            clock = tokens[i + 1].strip("[]")
            i += 2
        elif t == "-max" or t == "-min" or t == "-add_delay" or t == "-network_latency_included":
            i += 1  # boolean flags
        elif _is_float(t) and delay is None:
            delay = float(t)
            i += 1
        elif not t.startswith("-"):
            extra, i = _collect_port_list(tokens, i)
            ports.extend(extra)
        else:
            i += 1
    if delay is None:
        return None
    return InputDelay(delay_ns=delay, clock=clock, ports=ports)


def _parse_set_output_delay(tokens: list[str]) -> Optional[OutputDelay]:
    clock = ""
    delay: Optional[float] = None
    ports: list[str] = []
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-clock" and i + 1 < len(tokens):
            clock = tokens[i + 1].strip("[]")
            i += 2
        elif t in ("-max", "-min", "-add_delay"):
            i += 1
        elif _is_float(t) and delay is None:
            delay = float(t)
            i += 1
        elif not t.startswith("-"):
            extra, i = _collect_port_list(tokens, i)
            ports.extend(extra)
        else:
            i += 1
    if delay is None:
        return None
    return OutputDelay(delay_ns=delay, clock=clock, ports=ports)


def _parse_set_max_delay(tokens: list[str]) -> Optional[MaxDelay]:
    delay: Optional[float] = None
    from_: str = ""
    to: str = ""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-from" and i + 1 < len(tokens):
            from_ = tokens[i + 1].strip("[]")
            i += 2
        elif t == "-to" and i + 1 < len(tokens):
            to = tokens[i + 1].strip("[]")
            i += 2
        elif t in ("-datapath_only", "-ignore_clock_latency"):
            i += 1
        elif _is_float(t) and delay is None:
            delay = float(t)
            i += 1
        else:
            i += 1
    if delay is None:
        return None
    return MaxDelay(delay_ns=delay, from_=from_, to=to)


def _parse_set_false_path(tokens: list[str]) -> Optional[FalsePath]:
    from_: str = ""
    to: str = ""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-from" and i + 1 < len(tokens):
            from_ = tokens[i + 1].strip("[]")
            i += 2
        elif t == "-to" and i + 1 < len(tokens):
            to = tokens[i + 1].strip("[]")
            i += 2
        elif t in ("-setup", "-hold", "-rise", "-fall"):
            i += 1
        else:
            i += 1
    return FalsePath(from_=from_, to=to)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_sdc(text: str) -> SDCConstraints:
    """Parse *text* as a subset-SDC file and return :class:`SDCConstraints`.

    Unknown commands are silently ignored.
    """
    constraints = SDCConstraints()
    cleaned = _strip_comments(text)
    for line in _split_lines(cleaned):
        tokens = _tokenise(line)
        if not tokens:
            continue
        cmd = tokens[0]
        if cmd == "create_clock":
            result = _parse_create_clock(tokens)
            if result:
                constraints.clocks.append(result)
        elif cmd == "set_input_delay":
            result = _parse_set_input_delay(tokens)
            if result:
                constraints.input_delays.append(result)
        elif cmd == "set_output_delay":
            result = _parse_set_output_delay(tokens)
            if result:
                constraints.output_delays.append(result)
        elif cmd == "set_max_delay":
            result = _parse_set_max_delay(tokens)
            if result:
                constraints.max_delays.append(result)
        elif cmd == "set_false_path":
            result = _parse_set_false_path(tokens)
            if result:
                constraints.false_paths.append(result)
        # else: skip unknown commands silently
    return constraints
