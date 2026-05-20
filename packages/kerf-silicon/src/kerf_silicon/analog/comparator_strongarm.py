"""comparator_strongarm.py — Strong-arm latched comparator (clocked).

SKY130A cell: ``comparator_strongarm_sky130``

Topology (reference: Razavi "Design of Analog CMOS Integrated Circuits", Ch. 13)
---------------------------------------------------------------------------------
Reset phase  (CLK=0): tail switch MT off; PMOS pre-charge devices MP1/MP2 pull
                      OUTP and OUTN to VDD.
Evaluation phase (CLK=1): tail switch MT on; input pair MN1/MN2 steers current
                           according to ΔVin; cross-coupled latch (ML1/ML2)
                           regenerates the imbalance to rail.

Input-referred offset (analytic model)
---------------------------------------
The dominant offset mechanism in the strong-arm latch is transistor mismatch in
the input pair (MN1 / MN2).  For matched NMOS devices operating in saturation
the input-referred offset due to threshold-voltage mismatch is:

    σ_Vos = A_VT / sqrt(W * L)

where A_VT is the SKY130 NMOS threshold-voltage mismatch coefficient (Pelgrom
model).  For sky130_fd_pr__nfet_01v8 the SKY130 documentation quotes:

    A_VT_n ≈ 4 mV·µm  (1-sigma mismatch coefficient for 1µm × 1µm device)

For a device of area W × L (µm²), the 1-sigma RMS mismatch is:

    σ_Vos(W, L) = A_VT / sqrt(W * L)      [V]

Given the nominal sizing (W=4 µm, L=0.15 µm, nf=1):

    σ_Vos_nom = 4e-3 / sqrt(4.0 * 0.15) = 4e-3 / sqrt(0.6) ≈ 5.16 mV (1σ)

The characterise() oracle:
- accepts an ``offset_mv`` target (= desired 1-sigma offset budget in mV).
- sizes W (keeping L=0.15 µm) so that σ_Vos ≤ offset_mv.
- returns the achieved 1-sigma offset and whether it is within the target.
- oracle_path = "analytic".

Public API
----------
    generate(params: dict) -> AnalogCell
    characterise(params: dict) -> CellCharacterisation

Parameters accepted
-------------------
    offset_mv   : float — target input-referred offset (1-sigma, mV). Default 5.
    pdk         : str   — "sky130" only (default "sky130").
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CELLS_DIR = Path(__file__).parent / "cells"
_CELL_JSON  = _CELLS_DIR / "comparator_strongarm_sky130.json"
_LVS_JSON   = _CELLS_DIR / "comparator_strongarm_sky130.lvs.json"

# ---------------------------------------------------------------------------
# SKY130 NMOS Pelgrom mismatch coefficient (A_VT for nfet_01v8)
# Reference: SKY130 PDK device characterisation notes.
# ---------------------------------------------------------------------------
_A_VT_N_MV_UM = 4.0   # mV·µm  (1-sigma threshold mismatch per √(WL))
_L_NOM_UM     = 0.15  # µm     (minimum drawn L for nfet_01v8)
_W_MIN_UM     = 0.42  # µm     (minimum W for sky130 nfet_01v8)
_W_MAX_UM     = 20.0  # µm     (practical max for the cell footprint)


@dataclass
class CellCharacterisation:
    """Characterisation summary for the strong-arm latched comparator.

    Attributes
    ----------
    offset_target_mv:
        Input-referred 1-sigma offset target in mV (from params).
    offset_achieved_mv:
        Analytic 1-sigma offset achieved by the sized device (mV).
    within_target:
        True iff offset_achieved_mv <= offset_target_mv.
    oracle_path:
        ``"analytic"`` or ``"ngspice"``.
    w_um:
        Input-pair device width (µm) selected to meet the offset target.
    l_um:
        Input-pair device length (µm).
    notes:
        Human-readable notes.
    """
    offset_target_mv: float
    offset_achieved_mv: float
    within_target: bool
    oracle_path: str
    w_um: float
    l_um: float
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ngspice_available() -> bool:
    return shutil.which("ngspice") is not None


def _pelgrom_offset_mv(w_um: float, l_um: float) -> float:
    """Return 1-sigma VT mismatch (mV) for given W/L (µm) via Pelgrom model.

        σ_Vos = A_VT / sqrt(W * L)    [mV]
    """
    return _A_VT_N_MV_UM / math.sqrt(w_um * l_um)


def _size_for_offset(offset_mv: float) -> dict[str, float]:
    """Choose minimum W (L fixed at _L_NOM_UM) to achieve σ_Vos ≤ offset_mv.

    From σ_Vos = A_VT / sqrt(W * L) → W = (A_VT / offset_mv)² / L.
    """
    w_ideal = (_A_VT_N_MV_UM / offset_mv) ** 2 / _L_NOM_UM
    w = max(_W_MIN_UM, min(_W_MAX_UM, w_ideal))
    achieved_mv = _pelgrom_offset_mv(w, _L_NOM_UM)
    return {"w_um": w, "l_um": _L_NOM_UM, "achieved_mv": achieved_mv}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(params: dict[str, Any] | None = None) -> "AnalogCell":
    """Load and return the strong-arm comparator cell descriptor.

    Parameters
    ----------
    params:
        Optional dict with any of:
        - ``offset_mv`` (float): input-referred offset target (mV). Default 5.
        - ``pdk``       (str)  : PDK selector. Only ``"sky130"`` supported.

    Returns
    -------
    AnalogCell
    """
    from kerf_silicon.analog.library import AnalogCell  # noqa: PLC0415

    if params is None:
        params = {}
    pdk = params.get("pdk", "sky130")
    if pdk != "sky130":
        raise ValueError(
            f"comparator_strongarm: unsupported PDK '{pdk}'. Only 'sky130' available."
        )

    descriptor  = json.loads(_CELL_JSON.read_text())
    lvs_ref     = json.loads(_LVS_JSON.read_text())

    return AnalogCell(
        name="comparator_strongarm_sky130",
        pdk=pdk,
        descriptor=descriptor,
        lvs_reference=lvs_ref,
        params=dict(params),
    )


def characterise(params: dict[str, Any] | None = None) -> CellCharacterisation:
    """Characterise the strong-arm comparator via the analytic Pelgrom oracle.

    The analytic oracle uses the Pelgrom threshold-voltage mismatch model to
    compute the input-referred offset for the NMOS input pair and sizes W to
    meet the requested target:

        σ_Vos = A_VT_n / sqrt(W · L)

    with A_VT_n = 4 mV·µm (SKY130 nfet_01v8 Pelgrom coefficient).

    If ngspice is on PATH, a Monte-Carlo transient simulation would normally
    run; in the absence of ngspice (the common case), the analytic oracle is
    used directly and oracle_path is set to ``"analytic"``.

    Parameters
    ----------
    params:
        Optional dict.  Keys:
        - ``offset_mv`` (float): 1-sigma input-referred offset target (mV).
                                  Default 5.
        - ``pdk``       (str)  : PDK selector (default ``"sky130"``).

    Returns
    -------
    CellCharacterisation
    """
    if params is None:
        params = {}

    offset_target_mv = float(params.get("offset_mv", 5.0))
    notes: list[str] = []

    if _ngspice_available():
        # A full Monte-Carlo transient sweep would measure offset statistics.
        # We fall back to the analytic oracle (ngspice Monte-Carlo is left as
        # a future enhancement; the analytic Pelgrom oracle is sufficient for
        # the ±20% level of accuracy required by the DoD).
        notes.append(
            "ngspice found on PATH; analytic Pelgrom oracle used as primary "
            "(Monte-Carlo transient sweep is a future enhancement)."
        )
        oracle_path = "analytic"
    else:
        notes.append(
            "ngspice not on PATH — analytic Pelgrom mismatch oracle used: "
            "σ_Vos = A_VT_n / √(W·L), A_VT_n = 4 mV·µm (sky130 nfet_01v8)."
        )
        oracle_path = "analytic"

    sizing = _size_for_offset(offset_target_mv)
    w_um          = sizing["w_um"]
    l_um          = sizing["l_um"]
    achieved_mv   = sizing["achieved_mv"]
    within_target = achieved_mv <= offset_target_mv

    notes.append(
        f"Pelgrom sizing: W={w_um:.2f} µm, L={l_um:.3f} µm → "
        f"σ_Vos={achieved_mv:.2f} mV (1σ). "
        f"Target={offset_target_mv:.1f} mV. "
        f"{'PASS' if within_target else 'FAIL (W clamped to max)'}"
    )
    notes.append(
        "Topology: PMOS pre-charge (MP1/MP2) + NMOS input pair (MN1/MN2) + "
        "cross-coupled NMOS latch (ML1/ML2) + NMOS tail switch (MT). "
        "CLKb = complement of CLK (generated externally or via local inverter)."
    )

    return CellCharacterisation(
        offset_target_mv=offset_target_mv,
        offset_achieved_mv=achieved_mv,
        within_target=within_target,
        oracle_path=oracle_path,
        w_um=w_um,
        l_um=l_um,
        notes=notes,
    )
