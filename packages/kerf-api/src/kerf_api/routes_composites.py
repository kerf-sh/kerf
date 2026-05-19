"""routes_composites.py — /api/composites routes.

Endpoints:
  POST /api/composites/clt
      Classical Lamination Theory (CLT): full ABD matrix analysis for a
      stacking sequence.  Delegates to kerf_cad_core.composites.laminate.

  POST /api/composites/failure
      Per-ply failure index calculation (max-stress, Tsai-Hill, Tsai-Wu,
      max-strain).  Delegates to kerf_cad_core.composites.laminate.

Returns {status:"pending"} on ImportError (503).
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: sanitise dict for JSON serialisation
# Replace math.inf / -math.inf with None (JSON null).
# ---------------------------------------------------------------------------

def _sanitise_json(obj: Any) -> Any:
    """Recursively replace non-finite floats with None for JSON safety."""
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitise_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitise_json(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Shared ply definition
# ---------------------------------------------------------------------------

class PlyDef(BaseModel):
    E1: float = Field(..., description="Young's modulus in fibre direction (Pa). > 0.")
    E2: float = Field(..., description="Young's modulus transverse to fibre (Pa). > 0.")
    nu12: float = Field(..., description="Major Poisson's ratio. > 0.")
    G12: float = Field(..., description="In-plane shear modulus (Pa). > 0.")
    thickness: float = Field(..., description="Ply thickness (m). > 0.")
    angle_deg: float = Field(..., description="Fibre angle from laminate x-axis (degrees).")


# ---------------------------------------------------------------------------
# CLT endpoint
# ---------------------------------------------------------------------------

class CLTRequest(BaseModel):
    plies: List[PlyDef] = Field(
        ...,
        description="Ordered stacking sequence (bottom to top).  At least one ply required.",
        min_length=1,
    )
    N_M: Optional[List[float]] = Field(
        default=None,
        description=(
            "6-element load vector [Nx, Ny, Nxy, Mx, My, Mxy] "
            "(N/m for forces; N for moments).  "
            "If provided, mid-plane strains and curvatures are also computed."
        ),
    )


@router.post("/composites/clt")
def composites_clt(req: CLTRequest):
    """Classical Lamination Theory (CLT) ABD matrix analysis.

    Assembles the 6×6 ABD matrix for the stacking sequence and optionally
    solves the ABD system for mid-plane strains/curvatures under an applied
    load vector.

    Returns:
      ok              — True on success
      A               — in-plane stiffness matrix (9-element flat, N/m)
      B               — coupling matrix (9-element flat, N)
      D               — bending stiffness matrix (9-element flat, N·m)
      ABD             — combined 6×6 matrix (list of 6 lists of 6 floats)
      total_thickness — total laminate thickness (m)
      n_plies         — number of plies
      is_symmetric    — True if laminate is symmetric
      is_balanced     — True if A16=A26≈0
      z_coords        — ply interface z-coordinates (n_plies+1 elements)
      response        — (if N_M supplied) mid-plane strains/curvatures

    Degrades to {status:"pending"} if kerf-cad-core is not installed.
    """
    try:
        from kerf_cad_core.composites.laminate import abd_matrix, laminate_response  # type: ignore[import]
    except ImportError as exc:
        logger.warning("kerf_cad_core.composites not available: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "pending",
                "reason": "kerf-cad-core package not installed; CLT analysis unavailable.",
            },
        )

    plies_dicts = [p.model_dump() for p in req.plies]

    abd = abd_matrix(plies_dicts)
    if not abd.get("ok", True):
        return JSONResponse(status_code=422, content=abd)

    if req.N_M is not None:
        if len(req.N_M) != 6:
            return JSONResponse(
                status_code=422,
                content={"ok": False, "reason": "N_M must be a 6-element list [Nx,Ny,Nxy,Mx,My,Mxy]"},
            )
        resp = laminate_response(abd, req.N_M)
        if not resp.get("ok", True):
            return JSONResponse(status_code=422, content=resp)
        abd["response"] = resp
    else:
        abd["response"] = None

    return abd


# ---------------------------------------------------------------------------
# Failure index endpoint
# ---------------------------------------------------------------------------

class StrengthsModel(BaseModel):
    F1t: float = Field(..., description="Fibre tensile strength (Pa).")
    F1c: float = Field(..., description="Fibre compressive strength (Pa, positive value).")
    F2t: float = Field(..., description="Transverse tensile strength (Pa).")
    F2c: float = Field(..., description="Transverse compressive strength (Pa, positive value).")
    F12: float = Field(..., description="In-plane shear strength (Pa).")
    # Optional strain allowables for max-strain criterion
    e1t: Optional[float] = Field(default=None, description="Fibre tensile strain allowable.")
    e1c: Optional[float] = Field(default=None, description="Fibre compressive strain allowable.")
    e2t: Optional[float] = Field(default=None, description="Transverse tensile strain allowable.")
    e2c: Optional[float] = Field(default=None, description="Transverse compressive strain allowable.")
    g12_allow: Optional[float] = Field(default=None, description="Shear strain allowable.")


class FailureRequest(BaseModel):
    stress_material: List[float] = Field(
        ...,
        description="3-element list [σ1, σ2, τ12] in material (fibre) axes (Pa).",
        min_length=3,
        max_length=3,
    )
    strain_material: List[float] = Field(
        ...,
        description="3-element list [ε1, ε2, γ12] in material (fibre) axes.",
        min_length=3,
        max_length=3,
    )
    strengths: StrengthsModel = Field(
        ...,
        description="Ply strength properties.",
    )
    criteria: Optional[List[str]] = Field(
        default=None,
        description=(
            "Failure criteria to evaluate.  "
            "Options: 'max-stress', 'max-strain', 'tsai-hill', 'tsai-wu'.  "
            "Default: all four."
        ),
    )


@router.post("/composites/failure")
def composites_failure(req: FailureRequest):
    """Composite ply failure index analysis.

    Evaluates requested failure criteria (max-stress, max-strain, Tsai-Hill,
    Tsai-Wu) for the given ply stress/strain state and strength properties.

    Returns:
      ok          — True on success
      failed      — True if any criterion indicates failure (F.I. ≥ 1)
      max_stress  — {fi, failed} max-stress failure index
      max_strain  — {fi, failed} (null if no strain allowables)
      tsai_hill   — {fi_squared, failed}
      tsai_wu     — {fi, failed}

    Degrades to {status:"pending"} if kerf-cad-core is not installed.
    """
    try:
        from kerf_cad_core.composites.laminate import failure_indices  # type: ignore[import]
    except ImportError as exc:
        logger.warning("kerf_cad_core.composites not available: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "pending",
                "reason": "kerf-cad-core package not installed; failure analysis unavailable.",
            },
        )

    strengths_dict = req.strengths.model_dump(exclude_none=False)
    # Remove None values so max-strain criterion knows allowables are absent
    strengths_dict = {k: v for k, v in strengths_dict.items() if v is not None}

    result = failure_indices(
        stress_material=req.stress_material,
        strain_material=req.strain_material,
        strengths=strengths_dict,
        criteria=req.criteria,
    )

    if not result.get("ok", True):
        return JSONResponse(status_code=422, content=_sanitise_json(result))

    return _sanitise_json(result)
