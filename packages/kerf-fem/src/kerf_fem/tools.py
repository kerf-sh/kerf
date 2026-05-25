import json
import uuid

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_fem._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


fem_run_spec = ToolSpec(
    name="fem_run",
    description="Run a finite-element stress analysis on a STEP file. Returns max von-Mises stress, displacement, FoS, and modal frequencies.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "material_props": {
                "type": "object",
                "properties": {
                    "E": {"type": "number"},
                    "nu": {"type": "number"},
                    "rho": {"type": "number"},
                    "yield_strength": {"type": "number"},
                },
                "required": ["E", "nu", "rho", "yield_strength"],
            },
            "boundary_conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["fixed", "displacement"]},
                        "face_tags": {"type": "array", "items": {"type": "number"}},
                        "ux": {"type": "number"},
                        "uy": {"type": "number"},
                        "uz": {"type": "number"},
                    },
                    "required": ["type", "face_tags"],
                },
            },
            "loads": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["pressure", "force"]},
                        "face_tags": {"type": "array", "items": {"type": "number"}},
                        "value": {"type": "number"},
                    },
                    "required": ["type", "face_tags", "value"],
                },
            },
            "mesh_size": {"type": "number"},
            "solver": {"type": "string", "enum": ["fenicsx", "calculix"]},
            "analysis_type": {"type": "string", "enum": ["linear_static", "modal", "thermal", "nonlinear_plastic"]},
        },
        "required": ["file_id", "material_props", "boundary_conditions", "loads"],
    },
)


@register(fem_run_spec, write=True)
async def run_fem_run(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    material_props = a.get("material_props")
    boundary_conditions = a.get("boundary_conditions", [])
    loads = a.get("loads", [])

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not material_props:
        return err_payload("material_props is required", "BAD_ARGS")
    if not boundary_conditions:
        return err_payload("at least one boundary_conditions entry is required", "BAD_ARGS")
    if not loads:
        return err_payload("at least one load entry is required", "BAD_ARGS")

    spec = {
        "material_props": material_props,
        "boundary_conditions": boundary_conditions,
        "loads": loads,
        "mesh_size": a.get("mesh_size", 0.01),
        "solver": a.get("solver", "fenicsx"),
        "analysis_type": a.get("analysis_type", "linear_static"),
    }
    spec_json = json.dumps(spec)

    row = await ctx.pool.fetchrow(
        """INSERT INTO fem_jobs (file_id, project_id, input_spec)
           VALUES ($1, $2, $3)
           ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
           DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
               started_at = NULL, finished_at = NULL
           RETURNING id""",
        file_id, ctx.project_id, spec_json,
    )

    if not row:
        return err_payload("failed to enqueue FEM job", "ERROR")

    return ok_payload({
        "job_id": str(row["id"]),
        "status": "queued",
        "message": "FEM job enqueued. Poll fem_job_status(file_id) for results.",
    })


fem_job_status_spec = ToolSpec(
    name="fem_job_status",
    description="Poll the status of a FEM analysis job. Returns the job status, and when complete the result JSON.",
    input_schema={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)


@register(fem_job_status_spec)
async def run_fem_job_status(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        """SELECT status, result_json, error FROM fem_jobs
           WHERE file_id = $1 AND project_id = $2
           ORDER BY created_at DESC LIMIT 1""",
        file_id, ctx.project_id,
    )

    if not row:
        return err_payload("fem job not found", "NOT_FOUND")

    resp = {"file_id": file_id, "status": row["status"]}
    if row["status"] == "done" and row["result_json"]:
        try:
            result = json.loads(row["result_json"])
            resp["result"] = result
        except Exception:
            pass
    elif row["status"] == "error" and row["error"]:
        resp["error"] = row["error"]

    return ok_payload(resp)


# ---------------------------------------------------------------------------
# fem_nonlinear_bar  — uniaxial J2 isotropic-hardening bar
# ---------------------------------------------------------------------------

fem_nonlinear_bar_spec = ToolSpec(
    name="fem_nonlinear_bar",
    description=(
        "Simulate a uniaxial bar under incremental loading using J2 "
        "isotropic-hardening plasticity (von Mises return mapping). "
        "Returns stress, strain, and plastic-strain history per load step. "
        "Useful for material-point / coupon-level nonlinear material verification."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "E": {
                "type": "number",
                "description": "Young's modulus [Pa]",
            },
            "sigma_y0": {
                "type": "number",
                "description": "Initial yield stress [Pa]",
            },
            "H": {
                "type": "number",
                "description": "Isotropic hardening modulus [Pa]. Use 0 for perfect plasticity.",
            },
            "load_steps": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Sequence of target values for each load step. "
                    "If force_controlled=false (default) these are total strain targets; "
                    "if force_controlled=true these are stress targets."
                ),
            },
            "force_controlled": {
                "type": "boolean",
                "description": "If true, load_steps are stress targets; otherwise strain targets.",
                "default": False,
            },
            "max_iter": {
                "type": "integer",
                "description": "Max Newton iterations per step (default 50).",
                "default": 50,
            },
            "tol": {
                "type": "number",
                "description": "Relative convergence tolerance (default 1e-10).",
                "default": 1e-10,
            },
        },
        "required": ["E", "sigma_y0", "H", "load_steps"],
    },
)


@register(fem_nonlinear_bar_spec)
async def run_fem_nonlinear_bar(ctx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    E = a.get("E")
    sigma_y0 = a.get("sigma_y0")
    H = a.get("H")
    load_steps = a.get("load_steps")

    if E is None or sigma_y0 is None or H is None or load_steps is None:
        return err_payload("E, sigma_y0, H, load_steps are required", "BAD_ARGS")
    if not isinstance(load_steps, list):
        return err_payload("load_steps must be a list", "BAD_ARGS")

    from kerf_fem.nonlinear_bar import run_nonlinear_bar

    result = run_nonlinear_bar(
        E=float(E),
        sigma_y0=float(sigma_y0),
        H=float(H),
        load_steps=[float(v) for v in load_steps],
        force_controlled=bool(a.get("force_controlled", False)),
        max_iter=int(a.get("max_iter", 50)),
        tol=float(a.get("tol", 1e-10)),
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# fem_truss_plastic  — small-strain 2-D truss with per-element plasticity
# ---------------------------------------------------------------------------

fem_truss_plastic_spec = ToolSpec(
    name="fem_truss_plastic",
    description=(
        "Nonlinear quasi-static analysis of a 2-D pin-jointed truss with "
        "J2 isotropic-hardening plasticity per bar element. "
        "Incremental load stepping + Newton-Raphson global equilibrium. "
        "Returns per-step displacements, element stresses, and plastic strains."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "List of [x, y] node coordinates [m].",
            },
            "elements": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "List of [node_i, node_j] element connectivity (0-based).",
            },
            "E": {"type": "number", "description": "Young's modulus [Pa]"},
            "area": {"type": "number", "description": "Cross-sectional area [m²]"},
            "sigma_y0": {"type": "number", "description": "Initial yield stress [Pa]"},
            "H": {"type": "number", "description": "Isotropic hardening modulus [Pa]"},
            "load_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "forces": {
                            "type": "object",
                            "description": "Map of node_index (string) → [Fx, Fy] [N]",
                        },
                        "fixed_dofs": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "DOF indices to fix (2*node for x, 2*node+1 for y).",
                        },
                    },
                },
                "description": "Sequence of load steps; BCs taken from first step.",
            },
            "max_iter": {"type": "integer", "default": 50},
            "tol": {"type": "number", "default": 1e-8},
        },
        "required": ["nodes", "elements", "E", "area", "sigma_y0", "H", "load_steps"],
    },
)


@register(fem_truss_plastic_spec)
async def run_fem_truss_plastic(ctx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    required = ["nodes", "elements", "E", "area", "sigma_y0", "H", "load_steps"]
    for key in required:
        if a.get(key) is None:
            return err_payload(f"{key} is required", "BAD_ARGS")

    from kerf_fem.nonlinear_bar import run_truss_plastic

    result = run_truss_plastic(
        nodes=[tuple(n) for n in a["nodes"]],
        elements=[tuple(e) for e in a["elements"]],
        E=float(a["E"]),
        area=float(a["area"]),
        sigma_y0=float(a["sigma_y0"]),
        H=float(a["H"]),
        load_steps=a["load_steps"],
        max_iter=int(a.get("max_iter", 50)),
        tol=float(a.get("tol", 1e-8)),
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# fem_buckling_linear  — linear eigenvalue (Euler) buckling
# ---------------------------------------------------------------------------

fem_buckling_linear_spec = ToolSpec(
    name="fem_buckling_linear",
    description=(
        "Solve the linear eigenvalue buckling problem K·φ = λ·Kg·φ for a "
        "beam/column under axial pre-stress. Returns buckling load factors λ_i "
        "and mode shapes. Supports pinned-pinned and fixed-free boundary "
        "conditions. Validated against Euler closed-form Pcr = π²EI/(KL)²."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "E": {"type": "number", "description": "Young's modulus [Pa]"},
            "I": {"type": "number", "description": "Second moment of area [m⁴]"},
            "A": {"type": "number", "description": "Cross-section area [m²]"},
            "L": {"type": "number", "description": "Column length [m]"},
            "P_ref": {
                "type": "number",
                "description": "Reference compressive load [N] for geometric stiffness assembly",
            },
            "supports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["pinned", "fixed"]},
                        "x": {"type": "number", "description": "Position along beam [m]"},
                    },
                    "required": ["type", "x"],
                },
                "description": "Boundary conditions: list of {type, x} dicts",
            },
            "n_elem": {
                "type": "integer",
                "description": "Number of beam elements (default 12)",
                "default": 12,
            },
            "n_modes": {
                "type": "integer",
                "description": "Number of buckling modes to return (default 3)",
                "default": 3,
            },
        },
        "required": ["E", "I", "A", "L", "P_ref", "supports"],
    },
)


@register(fem_buckling_linear_spec)
async def run_fem_buckling_linear(ctx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for key in ["E", "I", "A", "L", "P_ref", "supports"]:
        if a.get(key) is None:
            return err_payload(f"{key} is required", "BAD_ARGS")

    from kerf_fem.buckling import buckling_linear

    result = buckling_linear(
        E=float(a["E"]),
        I=float(a["I"]),
        A=float(a["A"]),
        L=float(a["L"]),
        P_ref=float(a["P_ref"]),
        supports=a["supports"],
        n_elem=int(a.get("n_elem", 12)),
        n_modes=int(a.get("n_modes", 3)),
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# fem_harmonic_response  — steady-state harmonic response (mode superposition)
# ---------------------------------------------------------------------------

fem_harmonic_response_spec = ToolSpec(
    name="fem_harmonic_response",
    description=(
        "Compute steady-state harmonic (frequency) response to F·e^(iωt) via "
        "mode superposition over a frequency sweep. Returns complex amplitude "
        "and phase vs frequency, plus SDOF dynamic amplification factor for "
        "validation. Supports modal damping ζ per mode."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modes": {
                "type": "object",
                "properties": {
                    "omega": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Natural circular frequencies [rad/s]",
                    },
                    "mode_shapes": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "Mode shape vectors, each of length n_dof",
                    },
                },
                "required": ["omega", "mode_shapes"],
                "description": "Modal data from a prior modal analysis",
            },
            "modal_damping": {
                "description": "Damping ratio ζ (scalar for all modes, or list per mode)",
                "oneOf": [
                    {"type": "number"},
                    {"type": "array", "items": {"type": "number"}},
                ],
            },
            "force_vector": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Nodal force vector F [N], length = n_dof",
            },
            "freq_range": {
                "type": "object",
                "properties": {
                    "f_min": {"type": "number", "description": "Min frequency [Hz]"},
                    "f_max": {"type": "number", "description": "Max frequency [Hz]"},
                    "n_pts": {"type": "integer", "description": "Number of sweep points (default 200)"},
                },
                "required": ["f_min", "f_max"],
                "description": "Frequency sweep parameters",
            },
            "dof_index": {
                "type": "integer",
                "description": "Output DOF index (default 0)",
                "default": 0,
            },
        },
        "required": ["modes", "modal_damping", "force_vector", "freq_range"],
    },
)


@register(fem_harmonic_response_spec)
async def run_fem_harmonic_response(ctx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for key in ["modes", "modal_damping", "force_vector", "freq_range"]:
        if a.get(key) is None:
            return err_payload(f"{key} is required", "BAD_ARGS")

    from kerf_fem.harmonic import harmonic_response

    result = harmonic_response(
        modes=a["modes"],
        modal_damping=a["modal_damping"],
        force_vector=a["force_vector"],
        freq_range=a["freq_range"],
        dof_index=int(a.get("dof_index", 0)),
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# fem_random_vibration_psd  — random vibration response to input PSD
# ---------------------------------------------------------------------------

fem_random_vibration_psd_spec = ToolSpec(
    name="fem_random_vibration_psd",
    description=(
        "Compute random-vibration RMS response to a shaped input acceleration PSD "
        "via the modal method. Returns 1σ/3σ response, per-mode RMS contributions, "
        "and Miles' equation approximation. Implements GRMS = √((π/2)·fn·Q·PSD) "
        "for SDOF validation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modes": {
                "type": "object",
                "properties": {
                    "omega": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Natural circular frequencies [rad/s]",
                    },
                    "mode_shapes": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "Mode shape vectors",
                    },
                },
                "required": ["omega", "mode_shapes"],
            },
            "modal_damping": {
                "description": "Damping ratio ζ (scalar or list per mode)",
                "oneOf": [
                    {"type": "number"},
                    {"type": "array", "items": {"type": "number"}},
                ],
            },
            "modal_participation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Modal participation factors Γ_i for base-excitation direction",
            },
            "psd_table": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "Input acceleration PSD as [[freq_Hz, PSD_value], ...] pairs. Units: (m/s²)²/Hz or g²/Hz",
            },
            "dof_index": {
                "type": "integer",
                "description": "Output DOF index (default 0)",
                "default": 0,
            },
            "n_sigma": {
                "type": "integer",
                "description": "Sigma multiplier for peak response (default 3)",
                "default": 3,
            },
        },
        "required": ["modes", "modal_damping", "modal_participation", "psd_table"],
    },
)


@register(fem_random_vibration_psd_spec)
async def run_fem_random_vibration_psd(ctx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for key in ["modes", "modal_damping", "modal_participation", "psd_table"]:
        if a.get(key) is None:
            return err_payload(f"{key} is required", "BAD_ARGS")

    from kerf_fem.random_vibration import random_vibration_psd

    result = random_vibration_psd(
        modes=a["modes"],
        modal_damping=a["modal_damping"],
        modal_participation=a["modal_participation"],
        psd_table=a["psd_table"],
        dof_index=int(a.get("dof_index", 0)),
        n_sigma=int(a.get("n_sigma", 3)),
    )
    return ok_payload(result)
