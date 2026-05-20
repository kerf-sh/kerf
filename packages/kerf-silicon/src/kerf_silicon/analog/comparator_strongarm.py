"""comparator_strongarm.py — Strong-arm latched comparator (clocked).

SKY130A cell: ``comparator_strongarm_sky130``

Topology (reference: Razavi "Design of Analog CMOS Integrated Circuits")
------------------------------------------------------------------------
Reset phase  (CLK=0): tail switch off, cross-coupled inverters pre-charged.
Evaluation phase (CLK=1): tail switch on, differential pair amplifies ΔVin;
                 regeneration latch drives outputs to rail.

Status
------
v1 ships a **stub** — the JSON descriptor contains the bounding-box outlines
and port list but the full transistor-level sizing and poly routing are TODO.

The ``generate`` function loads the stub JSON descriptor so downstream tooling
(T-238 viewer, LVS) can exercise the interface without a fully routed cell.

TODO (next iteration)
---------------------
- Transistor sizing oracle: offset_target_mV → W/L ratios via mismatch model.
- Full poly + li1 + met1 routing in the JSON descriptor.
- Ngspice characterisation: transient clocked simulation, measure input-referred
  offset distribution over 100 Monte-Carlo corners.
- LVS golden netlist (comparator_strongarm_sky130.lvs.json).

Public API
----------
    generate(params: dict) -> AnalogCell
    characterise(params: dict) -> CellCharacterisation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CELLS_DIR = Path(__file__).parent / "cells"
_CELL_JSON = _CELLS_DIR / "comparator_strongarm_sky130.json"


# ---------------------------------------------------------------------------
# Result data model
# ---------------------------------------------------------------------------

@dataclass
class CellCharacterisation:
    """Characterisation summary for the strong-arm comparator.

    Attributes
    ----------
    offset_target_mv:
        Input-referred offset target in mV.
    oracle_path:
        ``"stub"`` (no simulation yet) or ``"ngspice"``.
    notes:
        Human-readable notes.
    """
    offset_target_mv: float
    oracle_path: str
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(params: dict[str, Any] | None = None) -> Any:
    """Load and return the strong-arm comparator cell descriptor (stub).

    Parameters
    ----------
    params:
        Optional dict:
        - ``offset_mv`` (float): input-referred offset target (mV). Default 5.
        - ``pdk`` (str): PDK selector. Only ``"sky130"`` supported.

    Returns
    -------
    AnalogCell (imported from library to avoid circular import)
    """
    # Import here to avoid circular dependency
    from kerf_silicon.analog.library import AnalogCell  # noqa: PLC0415

    if params is None:
        params = {}
    pdk = params.get("pdk", "sky130")
    if pdk != "sky130":
        raise ValueError(
            f"comparator_strongarm: unsupported PDK '{pdk}'. Only 'sky130' available."
        )

    descriptor = json.loads(_CELL_JSON.read_text())

    return AnalogCell(
        name="comparator_strongarm_sky130",
        pdk=pdk,
        descriptor=descriptor,
        lvs_reference={},   # TODO: ship comparator_strongarm_sky130.lvs.json
        params=dict(params),
    )


def characterise(params: dict[str, Any] | None = None) -> CellCharacterisation:
    """Return a stub characterisation for the comparator.

    TODO: implement ngspice Monte-Carlo offset sweep.
    """
    if params is None:
        params = {}
    offset_mv = float(params.get("offset_mv", 5.0))

    return CellCharacterisation(
        offset_target_mv=offset_mv,
        oracle_path="stub",
        notes=[
            "Strong-arm comparator characterisation is a stub (T-258 v1).",
            "TODO: ngspice Monte-Carlo transient + input-referred offset extraction.",
        ],
    )
