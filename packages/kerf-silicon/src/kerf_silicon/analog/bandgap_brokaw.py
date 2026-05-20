"""bandgap_brokaw.py — Brokaw bandgap voltage reference.

SKY130A cell: ``bandgap_brokaw_sky130``

Topology (reference: Brokaw, IEEE JSSC 1974)
--------------------------------------------
Two BJTs (Q1, Q2) operating at different current densities produce a ΔVBE
proportional to absolute temperature (PTAT).  An error amplifier forces equal
collector currents through resistors R1/R2 such that:

    VREF = VBE + (R2/R1) * 2 * (kT/q) * ln(n)

where n = emitter-area ratio, kT/q = thermal voltage (~26 mV at 300 K).
VREF ≈ 1.25 V (silicon bandgap) independent of temperature to first order.

Status
------
v1 ships a **stub** — the JSON descriptor contains the bounding-box outlines
and port list but the full transistor-level sizing, R1/R2 values, and routing
are TODO.

TODO (next iteration)
---------------------
- Transistor sizing and R1/R2 selection oracle: iref_ua → VBE + ΔVBE balance.
- Full layout in the JSON descriptor.
- Ngspice temperature sweep (−40 °C … +125 °C): measure VREF TC.
- LVS golden netlist (bandgap_brokaw_sky130.lvs.json).

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
_CELL_JSON = _CELLS_DIR / "bandgap_brokaw_sky130.json"


# ---------------------------------------------------------------------------
# Result data model
# ---------------------------------------------------------------------------

@dataclass
class CellCharacterisation:
    """Characterisation summary for the Brokaw bandgap reference.

    Attributes
    ----------
    iref_ua:
        Reference current in µA.
    vref_target_v:
        Target output voltage (typically 1.25 V).
    oracle_path:
        ``"stub"`` (no simulation yet).
    notes:
        Human-readable notes.
    """
    iref_ua: float
    vref_target_v: float
    oracle_path: str
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(params: dict[str, Any] | None = None) -> Any:
    """Load and return the Brokaw bandgap cell descriptor (stub).

    Parameters
    ----------
    params:
        Optional dict:
        - ``iref_ua`` (float): reference current in µA (default 10).
        - ``pdk`` (str): PDK selector. Only ``"sky130"`` supported.

    Returns
    -------
    AnalogCell (imported from library to avoid circular import)
    """
    from kerf_silicon.analog.library import AnalogCell  # noqa: PLC0415

    if params is None:
        params = {}
    pdk = params.get("pdk", "sky130")
    if pdk != "sky130":
        raise ValueError(
            f"bandgap_brokaw: unsupported PDK '{pdk}'. Only 'sky130' available."
        )

    descriptor = json.loads(_CELL_JSON.read_text())

    return AnalogCell(
        name="bandgap_brokaw_sky130",
        pdk=pdk,
        descriptor=descriptor,
        lvs_reference={},   # TODO: ship bandgap_brokaw_sky130.lvs.json
        params=dict(params),
    )


def characterise(params: dict[str, Any] | None = None) -> CellCharacterisation:
    """Return a stub characterisation for the Brokaw bandgap.

    TODO: implement ngspice temperature sweep + VREF TC calculation.
    """
    if params is None:
        params = {}
    iref_ua = float(params.get("iref_ua", 10.0))

    return CellCharacterisation(
        iref_ua=iref_ua,
        vref_target_v=1.25,
        oracle_path="stub",
        notes=[
            "Brokaw bandgap characterisation is a stub (T-258 v1).",
            "TODO: ngspice temperature sweep −40…+125 °C, VREF TC extraction.",
        ],
    )
