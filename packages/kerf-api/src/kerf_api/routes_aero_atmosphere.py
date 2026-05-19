"""routes_aero_atmosphere.py — /api/aero/atmosphere route.

Endpoint:
  POST /api/aero/atmosphere
      ISA 1976 standard atmosphere: T, p, ρ, a at a given altitude.
      Delegates to kerf_cad_core.aero.flow.isa_atmosphere.
      Returns {status:"pending"} on ImportError (503).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class AtmosphereRequest(BaseModel):
    altitude_m: float = Field(
        ...,
        description=(
            "Geometric/geopotential altitude in metres.  "
            "Valid range: 0 – 20 000 m (ISA troposphere + lower stratosphere).  "
            "Returns {ok:false} outside this range."
        ),
    )


@router.post("/aero/atmosphere")
def isa_atmosphere_route(req: AtmosphereRequest):
    """ICAO Standard Atmosphere (ISA 1976) at a given altitude.

    Returns:
      T_K         — temperature (K)
      p_Pa        — pressure (Pa)
      rho_kg_m3   — density (kg/m³)
      a_m_s       — speed of sound (m/s)
      altitude_m  — echo of input
      ok          — False if altitude is out of range

    Altitude domain: 0 – 20 000 m.
    Above 20 km or below 0 m the underlying function returns ok=False.
    """
    try:
        from kerf_cad_core.aero.flow import isa_atmosphere  # type: ignore[import]
    except ImportError as exc:
        logger.warning("kerf_cad_core not available: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "pending",
                "reason": "kerf-cad-core package not installed; atmosphere calculation unavailable.",
            },
        )

    result = isa_atmosphere(req.altitude_m)
    result["altitude_m"] = req.altitude_m

    if not result.get("ok", True):
        return JSONResponse(
            status_code=422,
            content=result,
        )

    return result
