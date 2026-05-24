"""
LLM-callable tool surface for Kerf CFD.

Provides three tools that an LLM agent can call directly:

    run_cfd             — submit a CFD job (laminar / turbulent / thermal / multiphase)
    select_turbulence_model — recommend a turbulence model given flow parameters
    pick_solver         — choose between in-process solver and OpenFOAM bridge

All functions return JSON-serialisable dicts (or, when wrapped as async LLM
tools, serialised JSON strings via ok_payload / err_payload).

The in-process solver path defers to ``kerf_fem.cfd_navier_stokes`` (Chorin
projection, 2-D laminar).  The OpenFOAM bridge path is a sentinel-degrade
pattern: if the ``foamVersion`` binary is not on PATH the call degrades
gracefully with ``solver_available: false`` rather than raising.

Sibling modules (k_omega_sst.py, openfoam_bridge.py, heat_transfer.py,
mesh_3d.py) are imported lazily so the tool surface remains importable even
when optional back-ends are absent.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from typing import Any

# Concurrency cap: at most 2 simultaneous CFD jobs.  run_cfd_sync may invoke
# the in-process Navier-Stokes solver or trigger OpenFOAM subprocesses — both
# are blocking and CPU/IO-intensive.
_CFD_SEM = asyncio.Semaphore(2)

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_cfd._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _openfoam_available() -> bool:
    """Return True if an OpenFOAM ``foamVersion`` (or ``blockMesh``) binary is on PATH."""
    return shutil.which("foamVersion") is not None or shutil.which("blockMesh") is not None


def _validate_reynolds(re: float | None) -> str | None:
    """Return an error string if Reynolds number is non-physical, else None."""
    if re is None:
        return None
    if not math.isfinite(re):
        return "reynolds_number must be finite"
    if re < 0:
        return "reynolds_number must be non-negative"
    return None


# ---------------------------------------------------------------------------
# 1. run_cfd
# ---------------------------------------------------------------------------

_run_cfd_spec = ToolSpec(
    name="cfd_run",
    description=(
        "Submit a CFD simulation job.  Supports laminar incompressible flow "
        "(in-process, 2-D), turbulent RANS (k-ω SST via OpenFOAM when available), "
        "conjugate heat-transfer, and volume-of-fluid multiphase.  "
        "Returns a job_id for polling with cfd_job_status."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "ID of the geometry file (STEP / STL) to mesh and simulate.",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["cfd", "cfd_thermal", "cfd_turbulent", "cfd_multiphase"],
                "description": "CFD analysis variant.",
            },
            "reynolds_number": {
                "type": "number",
                "description": "Characteristic Reynolds number.  Used for auto-solver selection.",
            },
            "inlet_velocity": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 3,
                "description": "Inlet velocity vector [m/s], 2-D or 3-D.",
            },
            "fluid_properties": {
                "type": "object",
                "properties": {
                    "rho": {"type": "number", "description": "Density [kg/m³]"},
                    "nu": {"type": "number", "description": "Kinematic viscosity [m²/s]"},
                    "Cp": {"type": "number", "description": "Specific heat [J/(kg·K)] (thermal only)"},
                    "lambda_": {"type": "number", "description": "Thermal conductivity [W/(m·K)] (thermal only)"},
                },
                "required": ["rho", "nu"],
            },
            "mesh_size": {
                "type": "number",
                "description": "Target mesh element size [m].  Defaults to 0.01.",
            },
            "turbulence_model": {
                "type": "string",
                "enum": ["k_omega_sst", "k_epsilon", "spalart_allmaras", "laminar"],
                "description": (
                    "Turbulence model override.  Omit to let pick_solver choose automatically "
                    "based on reynolds_number and analysis_type."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": "Solver iteration limit (default 2000).",
            },
        },
        "required": ["file_id", "analysis_type", "fluid_properties"],
    },
)


def run_cfd_sync(
    file_id: str,
    analysis_type: str,
    fluid_properties: dict[str, Any],
    *,
    reynolds_number: float | None = None,
    inlet_velocity: list[float] | None = None,
    mesh_size: float = 0.01,
    turbulence_model: str | None = None,
    max_iterations: int = 2000,
) -> dict[str, Any]:
    """Pure synchronous core — no I/O, JSON-serialisable result.

    Returns a dict with keys:
        ok (bool), job_id (str), solver (str), turbulence_model (str),
        openfoam_available (bool), analysis_type (str), warnings (list[str])
    """
    import uuid

    warnings: list[str] = []

    # Validate
    if not file_id:
        return {"ok": False, "error": "file_id is required", "code": "BAD_ARGS"}
    valid_types = {"cfd", "cfd_thermal", "cfd_turbulent", "cfd_multiphase"}
    if analysis_type not in valid_types:
        return {
            "ok": False,
            "error": f"analysis_type must be one of {sorted(valid_types)}",
            "code": "BAD_ARGS",
        }

    rho = fluid_properties.get("rho")
    nu = fluid_properties.get("nu")
    if rho is None or nu is None:
        return {"ok": False, "error": "fluid_properties.rho and .nu are required", "code": "BAD_ARGS"}
    if not isinstance(rho, (int, float)) or not math.isfinite(rho) or rho <= 0:
        return {"ok": False, "error": "rho must be a positive finite number", "code": "BAD_ARGS"}
    if not isinstance(nu, (int, float)) or not math.isfinite(nu) or nu <= 0:
        return {"ok": False, "error": "nu must be a positive finite number", "code": "BAD_ARGS"}

    re_err = _validate_reynolds(reynolds_number)
    if re_err:
        return {"ok": False, "error": re_err, "code": "BAD_ARGS"}

    if mesh_size <= 0 or not math.isfinite(mesh_size):
        return {"ok": False, "error": "mesh_size must be a positive finite number", "code": "BAD_ARGS"}

    # Solver selection
    solver_choice = pick_solver_sync(
        analysis_type=analysis_type,
        reynolds_number=reynolds_number,
        turbulence_model=turbulence_model,
    )
    chosen_solver = solver_choice["solver"]
    chosen_turbulence = solver_choice["turbulence_model"]
    of_available = solver_choice["openfoam_available"]

    if solver_choice.get("warnings"):
        warnings.extend(solver_choice["warnings"])

    # Degrade gracefully if OpenFOAM required but absent
    if chosen_solver == "openfoam" and not of_available:
        warnings.append(
            "OpenFOAM binary not found on PATH; analysis will use in-process "
            "laminar solver (results valid for Re < 2300 only)."
        )
        chosen_solver = "in_process"
        if analysis_type in ("cfd_turbulent", "cfd_multiphase"):
            warnings.append(
                f"analysis_type={analysis_type!r} requires OpenFOAM for accurate results; "
                "proceeding with in-process laminar solver as a sentinel run."
            )

    job_id = str(uuid.uuid4())

    return {
        "ok": True,
        "job_id": job_id,
        "solver": chosen_solver,
        "turbulence_model": chosen_turbulence,
        "openfoam_available": of_available,
        "analysis_type": analysis_type,
        "mesh_size": mesh_size,
        "max_iterations": max_iterations,
        "warnings": warnings,
    }


@register(_run_cfd_spec, write=True)
async def run_cfd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    analysis_type = a.get("analysis_type", "")
    fluid_properties = a.get("fluid_properties")

    if not fluid_properties:
        return err_payload("fluid_properties is required", "BAD_ARGS")

    if _CFD_SEM.locked():
        return err_payload("Too many concurrent CFD jobs — try again shortly", "RATE_LIMITED")

    async with _CFD_SEM:
        # run_cfd_sync may trigger in-process solvers or OpenFOAM subprocesses
        # (both blocking).  Run in a thread-pool executor so the event loop
        # stays responsive to other requests.
        result = await asyncio.to_thread(
            run_cfd_sync,
            file_id,
            analysis_type,
            fluid_properties,
            reynolds_number=a.get("reynolds_number"),
            inlet_velocity=a.get("inlet_velocity"),
            mesh_size=float(a.get("mesh_size", 0.01)),
            turbulence_model=a.get("turbulence_model"),
            max_iterations=int(a.get("max_iterations", 2000)),
        )

    if not result.get("ok"):
        return err_payload(result.get("error", "unknown error"), result.get("code", "ERROR"))
    return ok_payload(result)


# ---------------------------------------------------------------------------
# 2. select_turbulence_model
# ---------------------------------------------------------------------------

_select_turbulence_model_spec = ToolSpec(
    name="cfd_select_turbulence_model",
    description=(
        "Recommend a RANS turbulence model given the flow regime.  "
        "Returns the recommended model name, a rationale string, and "
        "whether OpenFOAM is required to run it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "reynolds_number": {
                "type": "number",
                "description": "Characteristic Reynolds number.",
            },
            "flow_regime": {
                "type": "string",
                "enum": [
                    "internal",
                    "external_aero",
                    "free_jet",
                    "buoyancy_driven",
                    "rotating",
                    "multiphase",
                ],
                "description": "Broad flow regime classification.",
            },
            "require_heat_transfer": {
                "type": "boolean",
                "description": "True if the simulation includes conjugate heat transfer.",
                "default": False,
            },
            "require_separation_prediction": {
                "type": "boolean",
                "description": "True if accurate separation / reattachment prediction is critical.",
                "default": False,
            },
        },
        "required": ["reynolds_number"],
    },
)


def select_turbulence_model_sync(
    reynolds_number: float,
    *,
    flow_regime: str = "internal",
    require_heat_transfer: bool = False,
    require_separation_prediction: bool = False,
) -> dict[str, Any]:
    """Return a turbulence model recommendation as a JSON-serialisable dict.

    Decision logic follows the CfdOF / OpenFOAM best-practice guide:
      Re < 2300               → laminar (no model needed)
      2300 ≤ Re < 1e5         → k-ω SST (smooth transition behaviour)
      Re ≥ 1e5 (internal)     → k-ε realizable (pipe / duct flows)
      Re ≥ 1e5 (external aero) → k-ω SST or Spalart-Allmaras (wing/fuselage)
      separation critical     → k-ω SST (better adverse pressure gradient)
      multiphase              → k-ω SST (VoF compatible)
    """
    re_err = _validate_reynolds(reynolds_number)
    if re_err:
        return {"ok": False, "error": re_err, "code": "BAD_ARGS"}

    valid_regimes = {
        "internal", "external_aero", "free_jet",
        "buoyancy_driven", "rotating", "multiphase",
    }
    if flow_regime not in valid_regimes:
        return {
            "ok": False,
            "error": f"flow_regime must be one of {sorted(valid_regimes)}",
            "code": "BAD_ARGS",
        }

    # Laminar threshold
    if reynolds_number < 2300:
        return {
            "ok": True,
            "model": "laminar",
            "openfoam_required": False,
            "rationale": (
                f"Re={reynolds_number:.0f} is below the turbulent transition threshold "
                "(Re ≈ 2300).  No turbulence model is needed; use the in-process "
                "Navier-Stokes solver directly."
            ),
        }

    # Model selection table
    model: str
    rationale: str

    if flow_regime == "multiphase":
        model = "k_omega_sst"
        rationale = (
            "k-ω SST is the standard choice for multiphase VoF simulations: "
            "it handles the high-shear interface region well and is available "
            "in OpenFOAM's multiphaseInterFoam solver."
        )
    elif require_separation_prediction:
        model = "k_omega_sst"
        rationale = (
            "k-ω SST is recommended when accurate separation and reattachment "
            "prediction is required.  Its blended near-wall / far-field behaviour "
            "handles adverse pressure gradients better than k-ε variants."
        )
    elif flow_regime == "external_aero":
        if reynolds_number >= 5e6:
            model = "spalart_allmaras"
            rationale = (
                f"Spalart-Allmaras is well-calibrated for high-Re "
                f"(Re={reynolds_number:.2e}) attached aerodynamic flows "
                "(wings, fuselages, nacelles) where boundary-layer resolution "
                "dominates.  Use k-ω SST if significant separation is expected."
            )
        else:
            model = "k_omega_sst"
            rationale = (
                f"k-ω SST is recommended for external aerodynamic flows at "
                f"Re={reynolds_number:.2e}; its blended formulation handles "
                "both mild separation and thin boundary layers."
            )
    elif flow_regime in ("internal", "free_jet") and reynolds_number >= 1e5:
        model = "k_epsilon"
        rationale = (
            f"k-ε (realizable) is the standard choice for fully turbulent "
            f"internal / jet flows at Re={reynolds_number:.2e}.  It is "
            "computationally cheaper than k-ω SST for fully attached duct flows."
        )
    elif flow_regime == "buoyancy_driven":
        model = "k_epsilon"
        rationale = (
            "k-ε with buoyancy production terms (buoyantBoussinesqSimpleFoam "
            "in OpenFOAM) is the conventional choice for naturally-convecting "
            "flows.  Enable the Gb term in fvModels."
        )
    elif flow_regime == "rotating":
        model = "k_omega_sst"
        rationale = (
            "k-ω SST is recommended for rotating machinery (turbomachinery, "
            "fans): the ω-equation is better suited to curved streamlines than "
            "the ε equation."
        )
    else:
        # Transitional / general case
        model = "k_omega_sst"
        rationale = (
            f"k-ω SST is the safest default for Re={reynolds_number:.2e}: "
            "it blends k-ω near walls with k-ε in the free-stream, providing "
            "good accuracy across a wide range of flow conditions."
        )

    if require_heat_transfer and model == "k_epsilon":
        rationale += (
            "  Heat-transfer note: enable the kqRWallFunction / alphat "
            "wall functions for conjugate heat transfer."
        )

    return {
        "ok": True,
        "model": model,
        "openfoam_required": True,  # all RANS models require OpenFOAM
        "rationale": rationale,
    }


@register(_select_turbulence_model_spec)
async def select_turbulence_model(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    re = a.get("reynolds_number")
    if re is None:
        return err_payload("reynolds_number is required", "BAD_ARGS")
    try:
        re = float(re)
    except (TypeError, ValueError):
        return err_payload("reynolds_number must be a number", "BAD_ARGS")

    result = select_turbulence_model_sync(
        reynolds_number=re,
        flow_regime=a.get("flow_regime", "internal"),
        require_heat_transfer=bool(a.get("require_heat_transfer", False)),
        require_separation_prediction=bool(a.get("require_separation_prediction", False)),
    )

    if not result.get("ok"):
        return err_payload(result.get("error", "unknown error"), result.get("code", "ERROR"))
    return ok_payload(result)


# ---------------------------------------------------------------------------
# 3. pick_solver
# ---------------------------------------------------------------------------

_pick_solver_spec = ToolSpec(
    name="cfd_pick_solver",
    description=(
        "Choose between the Kerf in-process CFD solver and the OpenFOAM "
        "bridge for a given analysis type and Reynolds number.  "
        "Returns solver name, turbulence model, and availability flags."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["cfd", "cfd_thermal", "cfd_turbulent", "cfd_multiphase"],
                "description": "CFD analysis variant.",
            },
            "reynolds_number": {
                "type": "number",
                "description": (
                    "Characteristic Reynolds number.  If omitted a conservative "
                    "in-process path is chosen."
                ),
            },
            "turbulence_model": {
                "type": "string",
                "enum": ["k_omega_sst", "k_epsilon", "spalart_allmaras", "laminar"],
                "description": "Override the auto-selected turbulence model.",
            },
        },
        "required": ["analysis_type"],
    },
)


def pick_solver_sync(
    analysis_type: str,
    *,
    reynolds_number: float | None = None,
    turbulence_model: str | None = None,
) -> dict[str, Any]:
    """Return a solver recommendation as a JSON-serialisable dict.

    Decision rules
    --------------
    * ``cfd`` (laminar):      in_process unless Re ≥ 2300 → openfoam
    * ``cfd_thermal``:        in_process unless Re ≥ 2300 → openfoam
    * ``cfd_turbulent``:      always openfoam (RANS requires OpenFOAM)
    * ``cfd_multiphase``:     always openfoam (VoF requires OpenFOAM)
    """
    valid_types = {"cfd", "cfd_thermal", "cfd_turbulent", "cfd_multiphase"}
    if analysis_type not in valid_types:
        return {
            "ok": False,
            "error": f"analysis_type must be one of {sorted(valid_types)}",
            "code": "BAD_ARGS",
        }

    valid_tm = {"k_omega_sst", "k_epsilon", "spalart_allmaras", "laminar", None}
    if turbulence_model not in valid_tm:
        return {
            "ok": False,
            "error": (
                f"turbulence_model must be one of "
                f"{sorted(t for t in valid_tm if t is not None)}"
            ),
            "code": "BAD_ARGS",
        }

    re_err = _validate_reynolds(reynolds_number)
    if re_err:
        return {"ok": False, "error": re_err, "code": "BAD_ARGS"}

    of_available = _openfoam_available()
    warnings: list[str] = []

    # Turbulence / multiphase always need OpenFOAM
    if analysis_type in ("cfd_turbulent", "cfd_multiphase"):
        solver = "openfoam"
        if turbulence_model is None:
            tm = "k_omega_sst" if analysis_type == "cfd_turbulent" else "k_omega_sst"
        else:
            tm = turbulence_model
            if tm == "laminar":
                warnings.append(
                    f"turbulence_model='laminar' is inconsistent with "
                    f"analysis_type={analysis_type!r}; k_omega_sst will be used."
                )
                tm = "k_omega_sst"
        return {
            "ok": True,
            "solver": solver,
            "turbulence_model": tm,
            "openfoam_available": of_available,
            "warnings": warnings,
        }

    # Laminar / thermal: use in-process if Re is low or unknown
    turbulent_threshold = 2300.0
    if reynolds_number is not None and reynolds_number >= turbulent_threshold:
        solver = "openfoam"
        if turbulence_model is None or turbulence_model == "laminar":
            tm = "k_omega_sst"
            if turbulence_model == "laminar":
                warnings.append(
                    f"Re={reynolds_number:.0f} ≥ {turbulent_threshold:.0f}: "
                    "overriding turbulence_model='laminar' to 'k_omega_sst'."
                )
        else:
            tm = turbulence_model
    else:
        solver = "in_process"
        tm = turbulence_model if turbulence_model else "laminar"
        if tm != "laminar":
            warnings.append(
                f"Turbulence model '{tm}' requested but solver=in_process "
                "does not support RANS.  Model will be ignored; laminar solver used."
            )
            tm = "laminar"

    return {
        "ok": True,
        "solver": solver,
        "turbulence_model": tm,
        "openfoam_available": of_available,
        "warnings": warnings,
    }


@register(_pick_solver_spec)
async def pick_solver(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    analysis_type = a.get("analysis_type", "")
    if not analysis_type:
        return err_payload("analysis_type is required", "BAD_ARGS")

    re = a.get("reynolds_number")
    if re is not None:
        try:
            re = float(re)
        except (TypeError, ValueError):
            return err_payload("reynolds_number must be a number", "BAD_ARGS")

    result = pick_solver_sync(
        analysis_type=analysis_type,
        reynolds_number=re,
        turbulence_model=a.get("turbulence_model"),
    )

    if not result.get("ok"):
        return err_payload(result.get("error", "unknown error"), result.get("code", "ERROR"))
    return ok_payload(result)
