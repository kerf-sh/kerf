"""IEEE 1164 9-state std_logic type with resolution and truth tables.

States (in canonical index order):
  0 = U  Uninitialized
  1 = X  Forcing Unknown
  2 = 0  Forcing 0
  3 = 1  Forcing 1
  4 = Z  High Impedance
  5 = W  Weak Unknown
  6 = L  Weak 0
  7 = H  Weak 1
  8 = -  Don't Care
"""
from __future__ import annotations

from typing import Iterable

# Canonical state strings
STATES = ("U", "X", "0", "1", "Z", "W", "L", "H", "-")
_IDX = {s: i for i, s in enumerate(STATES)}

# Type alias — just a string from STATES
StdLogic = str


def _idx(v: StdLogic) -> int:
    """Return the canonical index for a std_logic value."""
    try:
        return _IDX[v]
    except KeyError:
        raise ValueError(f"Invalid std_logic value: {v!r}") from None


# ---------------------------------------------------------------------------
# IEEE 1164 resolution table (9x9) — row=drive-a, col=drive-b → resolved
# Taken directly from IEEE Std 1164-1993 Table 5.
# ---------------------------------------------------------------------------
_RESOLUTION_TABLE: tuple[tuple[str, ...], ...] = (
    # U    X    0    1    Z    W    L    H    -
    ("U", "U", "U", "U", "U", "U", "U", "U", "U"),  # U
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # X
    ("U", "X", "0", "X", "0", "0", "0", "0", "X"),  # 0
    ("U", "X", "X", "1", "1", "1", "1", "1", "X"),  # 1
    ("U", "X", "0", "1", "Z", "W", "L", "H", "X"),  # Z
    ("U", "X", "0", "1", "W", "W", "W", "W", "X"),  # W
    ("U", "X", "0", "1", "L", "W", "L", "W", "X"),  # L
    ("U", "X", "0", "1", "H", "W", "W", "H", "X"),  # H
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # -
)


def resolve(values: Iterable[StdLogic]) -> StdLogic:
    """IEEE 1164 bus resolution: reduce a list of drivers to a single value.

    - Single driver: return it unchanged (no resolution needed).
    - No drivers: return "Z" (undriven bus is high-impedance).
    - Multiple drivers: fold pairwise through the resolution table.

    Raises ValueError for any unrecognised std_logic value.
    """
    drivers = list(values)
    if not drivers:
        return "Z"
    # Validate all values first (raises ValueError for unrecognised inputs)
    for d in drivers:
        _idx(d)
    result = drivers[0]
    for d in drivers[1:]:
        result = _RESOLUTION_TABLE[_idx(result)][_idx(d)]
    return result


# ---------------------------------------------------------------------------
# AND truth table — IEEE 1164 Table 7
# ---------------------------------------------------------------------------
_AND_TABLE: tuple[tuple[str, ...], ...] = (
    # U    X    0    1    Z    W    L    H    -
    ("U", "U", "0", "U", "U", "U", "0", "U", "U"),  # U
    ("U", "X", "0", "X", "X", "X", "0", "X", "X"),  # X
    ("0", "0", "0", "0", "0", "0", "0", "0", "0"),  # 0
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # 1
    ("U", "X", "0", "X", "X", "X", "0", "X", "X"),  # Z
    ("U", "X", "0", "X", "X", "X", "0", "X", "X"),  # W
    ("0", "0", "0", "0", "0", "0", "0", "0", "0"),  # L
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # H
    ("U", "X", "0", "X", "X", "X", "0", "X", "X"),  # -
)


def and2(a: StdLogic, b: StdLogic) -> StdLogic:
    """Two-input AND for std_logic (IEEE 1164 Table 7)."""
    return _AND_TABLE[_idx(a)][_idx(b)]


# ---------------------------------------------------------------------------
# OR truth table — IEEE 1164 Table 8
# ---------------------------------------------------------------------------
_OR_TABLE: tuple[tuple[str, ...], ...] = (
    # U    X    0    1    Z    W    L    H    -
    ("U", "U", "U", "1", "U", "U", "U", "1", "U"),  # U
    ("U", "X", "X", "1", "X", "X", "X", "1", "X"),  # X
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # 0
    ("1", "1", "1", "1", "1", "1", "1", "1", "1"),  # 1
    ("U", "X", "X", "1", "X", "X", "X", "1", "X"),  # Z
    ("U", "X", "X", "1", "X", "X", "X", "1", "X"),  # W
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # L
    ("1", "1", "1", "1", "1", "1", "1", "1", "1"),  # H
    ("U", "X", "X", "1", "X", "X", "X", "1", "X"),  # -
)


def or2(a: StdLogic, b: StdLogic) -> StdLogic:
    """Two-input OR for std_logic (IEEE 1164 Table 8)."""
    return _OR_TABLE[_idx(a)][_idx(b)]


# ---------------------------------------------------------------------------
# XOR truth table — IEEE 1164 Table 9
# ---------------------------------------------------------------------------
_XOR_TABLE: tuple[tuple[str, ...], ...] = (
    # U    X    0    1    Z    W    L    H    -
    ("U", "U", "U", "U", "U", "U", "U", "U", "U"),  # U
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # X
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # 0
    ("U", "X", "1", "0", "X", "X", "1", "0", "X"),  # 1
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # Z
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # W
    ("U", "X", "0", "1", "X", "X", "0", "1", "X"),  # L
    ("U", "X", "1", "0", "X", "X", "1", "0", "X"),  # H
    ("U", "X", "X", "X", "X", "X", "X", "X", "X"),  # -
)


def xor2(a: StdLogic, b: StdLogic) -> StdLogic:
    """Two-input XOR for std_logic (IEEE 1164 Table 9)."""
    return _XOR_TABLE[_idx(a)][_idx(b)]


# ---------------------------------------------------------------------------
# NOT truth table — IEEE 1164 Table 10
# ---------------------------------------------------------------------------
_NOT_TABLE: tuple[str, ...] = (
    # U    X    0    1    Z    W    L    H    -
    "U", "X", "1", "0", "X", "X", "1", "0", "X",
)


def not1(a: StdLogic) -> StdLogic:
    """NOT for std_logic (IEEE 1164 Table 10)."""
    return _NOT_TABLE[_idx(a)]


def to_01(v: StdLogic, xmap: StdLogic = "X") -> StdLogic:
    """Convert a std_logic value to 0/1 with optional mapping for other states.

    'L' maps to '0', 'H' maps to '1', everything else maps to xmap.
    """
    if v in ("0", "L"):
        return "0"
    if v in ("1", "H"):
        return "1"
    return xmap
