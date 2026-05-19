"""saif_parser.py — IEEE 1801 SAIF (Switching Activity Interchange Format) parser.

SAIF is a simple S-expression-like nested text format produced by gate-level
simulation tools.  It records per-net toggle counts and time-spent-at-logic-0/1
over a simulation window, from which activity factors (alpha) can be derived.

Minimal grammar handled (v1)
-----------------------------
A SAIF file is structured as nested parenthesised blocks::

    (SAIF <version>)
    (TIMESCALE <value> <unit>)
    (DURATION <cycles>)
    (INSTANCE [<path>]
        (NET
            (<net_name>
                (T0 <value>)
                (T1 <value>)
                (TX <value>)
                (TZ <value>)
                (TB <value>)
                (TC <value>)
                (IG <value>)
            )
        )
    )

Key fields per net:
  T0  — time spent at logic-0 (simulation ticks)
  T1  — time spent at logic-1 (simulation ticks)
  TX  — time spent at logic-X (unknown)
  TC  — toggle count (number of 0→1 or 1→0 transitions)

Activity factor:
    alpha = TC / (2 × DURATION)   (each full cycle has 2 transitions at α=1)

This parser is intentionally lenient: unknown fields are silently skipped.

References
----------
- IEEE Std 1801-2015, Annex C (SAIF grammar)
- Synopsys "Power Compiler User Guide" — SAIF format appendix
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NetActivity:
    """Switching-activity record for one net.

    Attributes
    ----------
    name:
        Net or signal name (may include hierarchy, e.g. ``top/clk``).
    T0:
        Simulation ticks spent at logic-0.
    T1:
        Simulation ticks spent at logic-1.
    TC:
        Toggle count (each 0→1 or 1→0 is one toggle).
    TX:
        Simulation ticks spent at logic-X (optional, default 0).
    alpha:
        Derived activity factor: ``TC / (2 × duration)`` where *duration*
        is the total simulation window from the enclosing SAIF file.
        Set to ``None`` if duration is unavailable (zero or not parsed).
    """
    name: str
    T0: int = 0
    T1: int = 0
    TC: int = 0
    TX: int = 0
    alpha: Optional[float] = None


@dataclass
class SaifData:
    """Top-level object returned by :func:`parse_saif`.

    Attributes
    ----------
    duration:
        Simulation duration in ticks (from the ``DURATION`` statement).
    timescale:
        Timescale string (e.g. ``"1 ns"``).
    nets:
        Mapping of net name → :class:`NetActivity`.
    """
    duration: int = 0
    timescale: str = ""
    nets: dict[str, NetActivity] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \(              # open paren
    | \)            # close paren
    | "(?:[^"\\]|\\.)*"   # double-quoted string
    | [^\s()]+      # bare token (identifier / number)
    """,
    re.VERBOSE,
)


def _tokenise(text: str) -> list[str]:
    """Return a flat list of SAIF tokens (parens + bare atoms + strings)."""
    return _TOKEN_RE.findall(text)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _SaifParser:
    """Recursive-descent SAIF parser operating on a token list."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Optional[str]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> str:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, value: str) -> None:
        tok = self._consume()
        if tok != value:
            raise ValueError(f"SAIF parse error: expected {value!r}, got {tok!r}")

    def _parse_sexp(self) -> list:
        """Parse one S-expression (paren-delimited list or atom).

        Returns either a string atom or a list.
        """
        tok = self._peek()
        if tok is None:
            raise ValueError("SAIF parse error: unexpected end of input")
        if tok == "(":
            return self._parse_list()
        else:
            return self._consume()

    def _parse_list(self) -> list:
        """Parse ``( item ... )``."""
        self._expect("(")
        items = []
        while self._peek() != ")":
            if self._peek() is None:
                raise ValueError("SAIF parse error: unterminated list")
            items.append(self._parse_sexp())
        self._expect(")")
        return items

    def _parse_top_level(self) -> SaifData:
        """Parse the entire token stream as a sequence of top-level S-exprs."""
        data = SaifData()
        while self._peek() is not None:
            if self._peek() == "(":
                sexp = self._parse_list()
                self._handle_top_sexp(sexp, data)
            else:
                self._consume()  # skip stray atoms
        return data

    def _handle_top_sexp(self, sexp: list, data: SaifData) -> None:
        if not sexp:
            return
        keyword = sexp[0].upper() if isinstance(sexp[0], str) else ""

        if keyword == "DURATION":
            if len(sexp) >= 2:
                try:
                    data.duration = int(sexp[1])
                except (ValueError, TypeError):
                    pass

        elif keyword == "TIMESCALE":
            # TIMESCALE may be (TIMESCALE 1 ns) or (TIMESCALE "1 ns")
            parts = [str(x) for x in sexp[1:] if isinstance(x, str)]
            data.timescale = " ".join(parts).strip('"')

        elif keyword == "INSTANCE":
            # Recurse into the INSTANCE block looking for NET sub-blocks
            self._handle_instance(sexp, data)

    def _handle_instance(self, sexp: list, data: SaifData) -> None:
        """Walk an INSTANCE S-expr tree extracting NET blocks."""
        # sexp[0] = "INSTANCE", sexp[1] (optional) = path string
        # remaining items may be sub-instances or NET blocks
        for item in sexp[1:]:
            if not isinstance(item, list):
                continue
            if not item:
                continue
            keyword = item[0].upper() if isinstance(item[0], str) else ""
            if keyword == "NET":
                self._handle_net_block(item, data)
            elif keyword == "INSTANCE":
                # Nested instance — recurse
                self._handle_instance(item, data)

    def _handle_net_block(self, net_sexp: list, data: SaifData) -> None:
        """Parse a NET block: (NET (<name> T0 T1 TC ...) ...)."""
        # net_sexp = ["NET", (<net_name> ...), ...]
        for item in net_sexp[1:]:
            if not isinstance(item, list) or not item:
                continue
            # item[0] is the net name; remaining items are field lists
            net_name = item[0]
            if not isinstance(net_name, str):
                continue
            activity = NetActivity(name=net_name)
            for field_item in item[1:]:
                if not isinstance(field_item, list) or len(field_item) < 2:
                    continue
                fname = field_item[0].upper() if isinstance(field_item[0], str) else ""
                try:
                    fval = int(field_item[1])
                except (ValueError, TypeError, IndexError):
                    fval = 0
                if fname == "T0":
                    activity.T0 = fval
                elif fname == "T1":
                    activity.T1 = fval
                elif fname == "TC":
                    activity.TC = fval
                elif fname == "TX":
                    activity.TX = fval
            data.nets[net_name] = activity

    def parse(self) -> SaifData:
        return self._parse_top_level()


# ---------------------------------------------------------------------------
# Post-processing — compute alpha
# ---------------------------------------------------------------------------

def _compute_alpha(data: SaifData) -> SaifData:
    """Derive alpha = TC / (2 × duration) for every net in *data* (in-place)."""
    if data.duration > 0:
        for activity in data.nets.values():
            activity.alpha = activity.TC / (2 * data.duration)
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_saif(text: str) -> SaifData:
    """Parse SAIF text and return a :class:`SaifData` object.

    The ``alpha`` field of each :class:`NetActivity` is computed as
    ``TC / (2 × DURATION)`` when ``DURATION > 0``.

    Parameters
    ----------
    text:
        Raw SAIF file contents as a string.

    Returns
    -------
    SaifData
        ``.duration`` — simulation window (ticks)
        ``.timescale`` — timescale string
        ``.nets``      — ``{net_name: NetActivity}``
    """
    tokens = _tokenise(text)
    parser = _SaifParser(tokens)
    data = parser.parse()
    return _compute_alpha(data)


def parse_saif_file(path: str | os.PathLike) -> SaifData:
    """Convenience wrapper: read *path* then call :func:`parse_saif`."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return parse_saif(text)
