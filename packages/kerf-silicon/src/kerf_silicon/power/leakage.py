"""leakage.py — Liberty cell_leakage_power sum.

Leakage power = Σ cell.cell_leakage_power  (summed over all cells in a library
or over a specific list of instantiated cells).

This module imports the T-241 Liberty AST types from
``kerf_silicon.liberty``.

References
----------
- Synopsys Liberty Reference, §4.6 (leakage_power / cell_leakage_power)
- Rabaey, Chandrakasan & Nikolic, "Digital Integrated Circuits", §5.5
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from kerf_silicon.liberty.ast import Cell, LibertyLibrary


# ---------------------------------------------------------------------------
# Per-cell result
# ---------------------------------------------------------------------------

@dataclass
class CellLeakageEntry:
    """Leakage power for one cell type."""
    cell_name: str
    leakage_power_W: float
    instance_count: int = 1

    @property
    def total_W(self) -> float:
        """Total leakage for all instances of this cell (Watts)."""
        return self.leakage_power_W * self.instance_count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def leakage_per_cell(lib: LibertyLibrary) -> list[CellLeakageEntry]:
    """Return per-cell leakage power from a Liberty library.

    Cells whose ``cell_leakage_power`` attribute is absent (``None``) are
    returned with ``leakage_power_W = 0.0``.

    Parameters
    ----------
    lib:
        A :class:`kerf_silicon.liberty.ast.LibertyLibrary` as returned by
        ``kerf_silicon.liberty.parse`` or ``parse_file``.

    Returns
    -------
    list of CellLeakageEntry
        One entry per cell in declaration order.
    """
    entries: list[CellLeakageEntry] = []
    for cell in lib.cells:
        leak_W = cell.cell_leakage_power if cell.cell_leakage_power is not None else 0.0
        entries.append(CellLeakageEntry(cell_name=cell.name, leakage_power_W=leak_W))
    return entries


def leakage_power_sum(
    lib: LibertyLibrary,
    instance_counts: Optional[dict[str, int]] = None,
) -> float:
    """Sum ``cell_leakage_power`` over all cells in *lib*.

    Parameters
    ----------
    lib:
        Liberty library parsed by T-241's reader.
    instance_counts:
        Optional mapping of ``cell_name → count`` of instances in the
        design.  When provided, each cell's leakage is multiplied by its
        instance count.  Cells not present default to a count of 1.

    Returns
    -------
    float
        Total leakage power in Watts (the same unit Liberty stores it in,
        typically nW but the numeric value is returned as-is).

    Examples
    --------
    A library with a single ``sky130_fd_sc_hd__inv_1`` cell whose
    ``cell_leakage_power = 0.00314``::

        lib = parse_file("inv_1.lib")
        assert leakage_power_sum(lib) == pytest.approx(0.00314)
    """
    if instance_counts is None:
        instance_counts = {}

    total = 0.0
    for cell in lib.cells:
        leak_W = cell.cell_leakage_power if cell.cell_leakage_power is not None else 0.0
        count = instance_counts.get(cell.name, 1)
        total += leak_W * count
    return total
