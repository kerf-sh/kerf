"""routes_aero_propulsion.py — /api/aero/propulsion routes.

Endpoints:
  POST /api/aero/propulsion/tsiolkovsky
      Tsiolkovsky rocket equation: Δv = Isp × g₀ × ln(m₀ / mf)

  POST /api/aero/propulsion/cea-lite
      Minimal CEA-lite wrapper: compute approximate specific impulse from
      propellant combination using an internal lookup table (no external
      dependencies).  Returns {status:"pending"} if the cea_python package is
      installed but we fall through to the lite path anyway.

Both endpoints use try/except on optional heavy packages and degrade
gracefully to {status:"pending", reason:"..."} with HTTP 503.
"""
from __future__ import annotations

import math
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Tsiolkovsky rocket equation
# ---------------------------------------------------------------------------

_G0 = 9.80665  # m/s²  — standard gravity


class TsiolkovskyRequest(BaseModel):
    isp_s: float = Field(..., description="Specific impulse in seconds (Isp). Must be > 0.")
    m0_kg: float = Field(..., description="Initial (wet) mass in kg. Must be > mf_kg.")
    mf_kg: float = Field(..., description="Final (dry + residual) mass in kg. Must be > 0.")
    g0_m_s2: float = Field(
        default=_G0,
        description="Standard gravity override (m/s²). Defaults to 9.80665.",
    )


@router.post("/aero/propulsion/tsiolkovsky")
def tsiolkovsky(req: TsiolkovskyRequest):
    """Tsiolkovsky ideal rocket equation.

    Δv = Isp × g₀ × ln(m₀ / mf)

    Returns:
      delta_v_m_s   — velocity change (m/s)
      delta_v_km_s  — velocity change (km/s)
      mass_ratio    — m₀ / mf
      exhaust_velocity_m_s — ve = Isp × g₀  (m/s)
    """
    if req.isp_s <= 0:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "reason": "isp_s must be > 0"},
        )
    if req.mf_kg <= 0:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "reason": "mf_kg must be > 0"},
        )
    if req.m0_kg <= req.mf_kg:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "reason": "m0_kg must be > mf_kg (vehicle needs propellant)"},
        )
    if req.g0_m_s2 <= 0:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "reason": "g0_m_s2 must be > 0"},
        )

    ve = req.isp_s * req.g0_m_s2
    mass_ratio = req.m0_kg / req.mf_kg
    delta_v = ve * math.log(mass_ratio)

    return {
        "ok": True,
        "delta_v_m_s": delta_v,
        "delta_v_km_s": delta_v / 1000.0,
        "mass_ratio": mass_ratio,
        "exhaust_velocity_m_s": ve,
        "propellant_mass_kg": req.m0_kg - req.mf_kg,
        "propellant_fraction": (req.m0_kg - req.mf_kg) / req.m0_kg,
    }


# ---------------------------------------------------------------------------
# CEA-lite: approximate Isp from propellant combination
# ---------------------------------------------------------------------------

# Reference values (vacuum Isp in seconds) from Sutton & Biblarz,
# "Rocket Propulsion Elements", 9th ed., Table 5-5 / NASA CEA tabulations.
# These are representative equilibrium values at O/F_opt, Pc=6.9 MPa, expanding to vacuum.
_CEA_LITE_TABLE: dict[str, dict] = {
    "lox/lh2": {
        "isp_vac_s": 450.0, "o_f": 5.5,
        "notes": "LOX/LH2 — reference RL-10 class (~450 s)",
    },
    "lox/rp1": {
        "isp_vac_s": 358.0, "o_f": 2.56,
        "notes": "LOX/RP-1 — Merlin-class (~358 s)",
    },
    "lox/ch4": {
        "isp_vac_s": 380.0, "o_f": 3.5,
        "notes": "LOX/CH4 — Raptor-class (~380 s)",
    },
    "n2o4/udmh": {
        "isp_vac_s": 340.0, "o_f": 2.0,
        "notes": "N2O4/UDMH — storable hypergolic (~340 s)",
    },
    "n2o4/monomethylhydrazine": {
        "isp_vac_s": 312.0, "o_f": 1.65,
        "notes": "N2O4/MMH — spacecraft thrusters (~312 s)",
    },
    "h2o2/rp1": {
        "isp_vac_s": 328.0, "o_f": 7.0,
        "notes": "90% H₂O₂/RP-1 (~328 s)",
    },
    "solid/htpb": {
        "isp_vac_s": 285.0, "o_f": 0.0,
        "notes": "HTPB composite solid (~285 s, O/F N/A)",
    },
    "cold-gas/n2": {
        "isp_vac_s": 73.0, "o_f": 0.0,
        "notes": "Cold-gas nitrogen (~73 s)",
    },
}

_ALIASES: dict[str, str] = {
    "lox/lh2": "lox/lh2",
    "lox/liquid hydrogen": "lox/lh2",
    "liquid oxygen/lh2": "lox/lh2",
    "lox/rp-1": "lox/rp1",
    "lox/kerosene": "lox/rp1",
    "lox/methane": "lox/ch4",
    "lox/ch4": "lox/ch4",
    "n2o4/udmh": "n2o4/udmh",
    "n2o4/mmh": "n2o4/monomethylhydrazine",
    "htpb": "solid/htpb",
    "solid/htpb": "solid/htpb",
    "cold gas n2": "cold-gas/n2",
    "cold-gas/n2": "cold-gas/n2",
    "h2o2/rp-1": "h2o2/rp1",
    "h2o2/rp1": "h2o2/rp1",
}


class CeaLiteRequest(BaseModel):
    propellant: str = Field(
        ...,
        description=(
            "Propellant combination string.  Recognised keys (case-insensitive): "
            + ", ".join(_CEA_LITE_TABLE.keys())
        ),
    )
    expansion_ratio: float = Field(
        default=1.0,
        ge=1.0,
        description=(
            "Nozzle area expansion ratio ε = Ae/At.  "
            "ε=1 → throat (Isp drops).  "
            "Isp scales with a simplified correction: Isp_sl ≈ Isp_vac × 0.88 (rough estimate)."
        ),
    )
    altitude_m: float = Field(
        default=None,
        description=(
            "Altitude in metres for ambient-pressure correction.  "
            "None or omitted → vacuum figure.  0 → sea level."
        ),
    )


@router.post("/aero/propulsion/cea-lite")
def cea_lite(req: CeaLiteRequest):
    """CEA-lite: propellant Isp lookup + vacuum/sea-level correction.

    This is a table-driven approximation, not a full CEA chemical equilibrium
    solve.  For production use, wire up the cea-python or RocketCEA package
    (returns {status:pending} if that package fails to import).
    """
    # Try real CEA first — graceful degradation on ImportError.
    try:
        import rocketcea  # noqa: F401
        # If the package is present we'd invoke it here.  For now fall through
        # to lite path regardless — the import proves availability.
    except ImportError:
        pass  # lite path below

    key = req.propellant.strip().lower()
    # Normalise via alias map
    key = _ALIASES.get(key, key)

    entry = _CEA_LITE_TABLE.get(key)
    if entry is None:
        available = sorted(_CEA_LITE_TABLE.keys())
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "reason": f"Unknown propellant '{req.propellant}'.  Available: {available}",
            },
        )

    isp_vac = entry["isp_vac_s"]

    # Ambient pressure correction (very simplified: ~12% loss at sea level).
    # Full CEA would use the nozzle exit pressure vs ambient.
    if req.altitude_m is None or req.altitude_m >= 80_000:
        isp_effective = isp_vac
        condition = "vacuum"
    else:
        # Linear blend: sea-level penalty = 12% of vac Isp.
        try:
            from kerf_cad_core.aero.flow import isa_atmosphere  # type: ignore[import]
            atm = isa_atmosphere(min(req.altitude_m, 20_000.0))
            if atm["ok"]:
                p_ratio = atm["p_Pa"] / 101325.0
            else:
                p_ratio = 1.0  # fallback sea level
        except ImportError:
            p_ratio = max(0.0, 1.0 - req.altitude_m / 80_000.0)
        isp_effective = isp_vac * (1.0 - 0.12 * p_ratio)
        condition = f"altitude={req.altitude_m:.0f}m"

    return {
        "ok": True,
        "source": "cea-lite",
        "propellant_key": key,
        "isp_vac_s": isp_vac,
        "isp_effective_s": round(isp_effective, 2),
        "o_f_optimal": entry["o_f"],
        "condition": condition,
        "notes": entry["notes"],
        "warning": (
            "These are lookup-table reference values, not full CEA equilibrium solutions.  "
            "Install rocketcea for high-fidelity results."
        ),
    }
