"""
kerf_composites LLM tools — layup_analysis + orphan capabilities.

Registered via plugin.py at startup.

Tools
-----
layup_analysis          — Classical Laminate Theory A/B/D + failure indices
composites_drape        — geodesic drape of flat ply sheet onto 3D surface
composites_interlaminar — interlaminar shear stress (ILSS) at ply interfaces
composites_thermal      — thermal residual stress from cure cool-down
composites_failure_depth — extended failure criteria (Hashin, max-stress, max-strain)
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_composites._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# layup_analysis tool spec
# ---------------------------------------------------------------------------

layup_analysis_spec = ToolSpec(
    name="layup_analysis",
    description=(
        "Analyse a composite laminate using Classical Laminate Theory (CLT). "
        "Supply the ply stack as a list of {angle, E1, E2, G12, nu12, thickness} "
        "objects (plus optional strength properties for failure analysis). "
        "Returns A/B/D stiffness matrices, effective moduli (Ex, Ey, Gxy), and "
        "optional Tsai-Wu / Tsai-Hill failure indices for a given load state."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plies": {
                "type": "array",
                "description": (
                    "Ordered ply stack (bottom to top). Each ply is an object with "
                    "angle [deg], E1 [GPa], E2 [GPa], G12 [GPa], nu12 [-], "
                    "thickness [mm], and optional Xt, Xc, Yt, Yc, S12 [MPa]."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "angle":     {"type": "number", "description": "Fibre angle [deg]"},
                        "E1":        {"type": "number", "description": "Longitudinal modulus [GPa]"},
                        "E2":        {"type": "number", "description": "Transverse modulus [GPa]"},
                        "G12":       {"type": "number", "description": "Shear modulus [GPa]"},
                        "nu12":      {"type": "number", "description": "Major Poisson ratio"},
                        "thickness": {"type": "number", "description": "Ply thickness [mm]"},
                        "Xt":  {"type": "number", "description": "Long. tensile strength [MPa]"},
                        "Xc":  {"type": "number", "description": "Long. compressive strength [MPa]"},
                        "Yt":  {"type": "number", "description": "Trans. tensile strength [MPa]"},
                        "Yc":  {"type": "number", "description": "Trans. compressive strength [MPa]"},
                        "S12": {"type": "number", "description": "In-plane shear strength [MPa]"},
                    },
                    "required": ["angle", "E1", "E2", "G12", "nu12", "thickness"],
                },
                "minItems": 1,
            },
            "load": {
                "type": "object",
                "description": (
                    "Optional in-plane load resultants for failure analysis. "
                    "Nx, Ny [N/mm], Nxy [N/mm]. If omitted, failure analysis is skipped."
                ),
                "properties": {
                    "Nx":  {"type": "number", "description": "x-direction force resultant [N/mm]"},
                    "Ny":  {"type": "number", "description": "y-direction force resultant [N/mm]"},
                    "Nxy": {"type": "number", "description": "shear force resultant [N/mm]"},
                },
            },
            "name": {
                "type": "string",
                "description": "Optional laminate label.",
            },
        },
        "required": ["plies"],
    },
)


async def run_layup_analysis(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_composites.layup import Ply, PlyMaterial, LaminateLayup
        from kerf_composites.clt import abd_matrices, effective_moduli
        from kerf_composites.failure import (
            PlyStress, tsai_wu_index, tsai_hill_index,
        )

        raw_plies = args["plies"]
        name = args.get("name", "laminate")
        load_args = args.get("load")

        # Build ply objects
        plies = []
        for i, rp in enumerate(raw_plies):
            mat = PlyMaterial(
                name=f"ply_{i}",
                E1=float(rp["E1"]),
                E2=float(rp["E2"]),
                G12=float(rp["G12"]),
                nu12=float(rp["nu12"]),
                Xt=float(rp.get("Xt", 1.0)),
                Xc=float(rp.get("Xc", 1.0)),
                Yt=float(rp.get("Yt", 1.0)),
                Yc=float(rp.get("Yc", 1.0)),
                S12=float(rp.get("S12", 1.0)),
            )
            plies.append(Ply(
                angle=float(rp["angle"]),
                material=mat,
                thickness=float(rp["thickness"]),
            ))

        layup = LaminateLayup(plies=plies, name=name)
        A, B, D = abd_matrices(layup)
        moduli = effective_moduli(layup)

        def _mat_to_list(m):
            return [[round(v, 4) for v in row] for row in m.tolist()]

        payload: dict[str, Any] = {
            "name": layup.name,
            "num_plies": layup.num_plies,
            "total_thickness_mm": round(layup.total_thickness, 4),
            "is_symmetric": layup.is_symmetric,
            "A_matrix_N_per_mm": _mat_to_list(A),
            "B_matrix_N": _mat_to_list(B),
            "D_matrix_N_mm": _mat_to_list(D),
            "effective_moduli": {k: round(v, 6) for k, v in moduli.items()},
        }

        # Optional failure analysis
        if load_args is not None:
            import numpy as np
            Nx = float(load_args.get("Nx", 0.0))
            Ny = float(load_args.get("Ny", 0.0))
            Nxy = float(load_args.get("Nxy", 0.0))
            N_vec = np.array([Nx, Ny, Nxy])
            h = layup.total_thickness
            # Approximate: average membrane stress in each ply ≈ N / h
            # (full CLT requires strain from [A]^-1·N then back-calculating ply stress)
            import numpy as np
            A_inv = np.linalg.inv(A)
            eps0 = A_inv @ N_vec  # mid-plane strains
            z = layup.z_coords

            ply_failures = []
            has_strength = all(
                rp.get("Xt") and rp.get("Xc") and rp.get("Yt") and rp.get("Yc") and rp.get("S12")
                for rp in raw_plies
            )

            if has_strength:
                from kerf_composites.clt import ply_Qbar_matrix
                for k, ply in enumerate(plies):
                    # Mid-plane of this ply
                    z_mid = (z[k] + z[k + 1]) / 2.0
                    # Strain at ply mid-plane (membrane only, no bending)
                    strain_lam = eps0  # N/mm / N/mm → dimensionless
                    # Transform laminate strain to ply axes
                    import math
                    theta = math.radians(ply.angle)
                    c = math.cos(theta)
                    s = math.sin(theta)
                    # Transformation matrix T (stress)
                    T = np.array([
                        [c*c,   s*s,   2*c*s],
                        [s*s,   c*c,  -2*c*s],
                        [-c*s,  c*s,  c*c-s*s],
                    ])
                    Q = ply_Qbar_matrix(ply)
                    # Stress in laminate axes
                    stress_lam = Q @ strain_lam  # GPa * dimensionless → GPa
                    stress_lam_mpa = stress_lam * 1.0e3  # → MPa
                    # Rotate to ply principal axes
                    stress_ply = T @ stress_lam_mpa
                    ps = PlyStress(
                        sigma1=float(stress_ply[0]),
                        sigma2=float(stress_ply[1]),
                        tau12=float(stress_ply[2]),
                    )
                    fi_tw = tsai_wu_index(ps, ply.material)
                    fi_th = tsai_hill_index(ps, ply.material)
                    ply_failures.append({
                        "ply_index": k,
                        "angle": ply.angle,
                        "sigma1_MPa": round(float(stress_ply[0]), 4),
                        "sigma2_MPa": round(float(stress_ply[1]), 4),
                        "tau12_MPa":  round(float(stress_ply[2]), 4),
                        "tsai_wu_fi": round(fi_tw, 6),
                        "tsai_hill_fi": round(fi_th, 6),
                        "failed_tsai_wu": fi_tw >= 1.0,
                        "failed_tsai_hill": fi_th >= 1.0,
                    })
                payload["failure_analysis"] = ply_failures
            else:
                payload["failure_analysis"] = "skipped — strength properties (Xt,Xc,Yt,Yc,S12) not provided for all plies"

        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "COMPOSITES_ERROR")


# ---------------------------------------------------------------------------
# Helper: build LaminateLayup from raw ply list (shared by several tools)
# ---------------------------------------------------------------------------

def _build_layup(raw_plies: list[dict], name: str = "laminate"):
    """Parse raw ply dicts into a LaminateLayup.  Returns (layup, None) or (None, error_str)."""
    from kerf_composites.layup import Ply, PlyMaterial, LaminateLayup
    plies = []
    for i, rp in enumerate(raw_plies):
        try:
            mat = PlyMaterial(
                name=f"ply_{i}",
                E1=float(rp["E1"]),
                E2=float(rp["E2"]),
                G12=float(rp["G12"]),
                nu12=float(rp["nu12"]),
                Xt=float(rp.get("Xt", 1500.0)),
                Xc=float(rp.get("Xc", 1500.0)),
                Yt=float(rp.get("Yt", 40.0)),
                Yc=float(rp.get("Yc", 246.0)),
                S12=float(rp.get("S12", 68.0)),
            )
            plies.append(Ply(
                angle=float(rp["angle"]),
                material=mat,
                thickness=float(rp["thickness"]),
            ))
        except Exception as exc:
            return None, f"ply[{i}]: {exc}"
    layup = LaminateLayup(plies=plies, name=name)
    return layup, None


# ---------------------------------------------------------------------------
# Tool: composites_drape
# ---------------------------------------------------------------------------

composites_drape_spec = ToolSpec(
    name="composites_drape",
    description=(
        "Drape a flat rectangular ply sheet onto a 3D surface using the geodesic "
        "pin-jointed fishing-net algorithm. Supports 'flat', 'cylinder_x', and "
        "'cylinder_y' surface types. Returns a grid of draped 3D coordinates and "
        "local shear angles (deviation from 90°) at each quad cell."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "surface": {
                "type": "string",
                "enum": ["flat", "cylinder_x", "cylinder_y"],
                "description": (
                    "'flat' — trivial flat surface (identity mapping). "
                    "'cylinder_x' — circular cylinder, axis along X. "
                    "'cylinder_y' — circular cylinder, axis along Y."
                ),
            },
            "u_range": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "[u_min, u_max] parameter range in mm (or degrees for cylinder).",
            },
            "v_range": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "[v_min, v_max] parameter range in mm.",
            },
            "nu": {
                "type": "integer",
                "description": "Number of grid points in u direction (default 10).",
            },
            "nv": {
                "type": "integer",
                "description": "Number of grid points in v direction (default 10).",
            },
            "radius": {
                "type": "number",
                "description": "Cylinder radius in mm (required for cylinder surfaces; default 100).",
            },
            "flat_z": {
                "type": "number",
                "description": "Z height for flat surface (default 0).",
            },
        },
        "required": [],
    },
)


async def run_composites_drape(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_composites.drape import (
            drape_flat_to_surface, flat_surface, cylindrical_surface,
        )
        import numpy as np

        surface_type = str(args.get("surface", "flat"))
        u_range = tuple(float(x) for x in args.get("u_range", [0.0, 100.0]))
        v_range = tuple(float(x) for x in args.get("v_range", [0.0, 100.0]))
        nu = int(args.get("nu", 10))
        nv = int(args.get("nv", 10))
        radius = float(args.get("radius", 100.0))
        flat_z = float(args.get("flat_z", 0.0))

        if surface_type == "flat":
            sfn = flat_surface(z=flat_z)
        elif surface_type == "cylinder_x":
            sfn = cylindrical_surface(radius=radius, axis="x")
        elif surface_type == "cylinder_y":
            sfn = cylindrical_surface(radius=radius, axis="y")
        else:
            return err_payload(f"unknown surface {surface_type!r}", "BAD_ARGS")

        result = drape_flat_to_surface(sfn, u_range, v_range, nu=nu, nv=nv)

        # Summarise — don't return huge arrays verbatim; return shape + stats
        shear = result.shear_angles
        payload = {
            "surface": surface_type,
            "nu": result.nu,
            "nv": result.nv,
            "u_range": list(u_range),
            "v_range": list(v_range),
            "shear_angle_deg": {
                "mean": round(float(np.mean(shear)), 4),
                "max": round(float(np.max(shear)), 4),
                "min": round(float(np.min(shear)), 4),
            },
            "surf_coords_shape": list(result.surf_coords.shape),
            "corner_coords_mm": [
                [round(v, 3) for v in result.surf_coords[0, 0].tolist()],
                [round(v, 3) for v in result.surf_coords[-1, 0].tolist()],
                [round(v, 3) for v in result.surf_coords[-1, -1].tolist()],
            ],
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "COMPOSITES_ERROR")


# ---------------------------------------------------------------------------
# Tool: composites_interlaminar
# ---------------------------------------------------------------------------

composites_interlaminar_spec = ToolSpec(
    name="composites_interlaminar",
    description=(
        "Compute interlaminar shear stress (ILSS) distribution at ply interfaces "
        "using equilibrium integration (Pagano / Pipes-Pagano method). "
        "Models a unit-width laminate beam under an applied bending moment. "
        "Returns τ_xz at each interface, the peak ILSS, and its location."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plies": {
                "type": "array",
                "description": (
                    "Ordered ply stack. Each ply: {angle [deg], E1 [GPa], E2 [GPa], "
                    "G12 [GPa], nu12 [-], thickness [mm]}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "angle":     {"type": "number"},
                        "E1":        {"type": "number"},
                        "E2":        {"type": "number"},
                        "G12":       {"type": "number"},
                        "nu12":      {"type": "number"},
                        "thickness": {"type": "number"},
                    },
                    "required": ["angle", "E1", "E2", "G12", "nu12", "thickness"],
                },
                "minItems": 1,
            },
            "Mx_Nmm_per_mm": {
                "type": "number",
                "description": "Applied bending moment per unit width [N·mm/mm]. Default 1.",
            },
            "beam_length_mm": {
                "type": "number",
                "description": "Beam span [mm]. Default 100.",
            },
            "name": {"type": "string", "description": "Optional laminate label."},
        },
        "required": ["plies"],
    },
)


async def run_composites_interlaminar(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        layup, err = _build_layup(args["plies"], name=args.get("name", "laminate"))
        if layup is None:
            return err_payload(err, "BAD_ARGS")

        from kerf_composites.interlaminar import interlaminar_shear

        Mx = float(args.get("Mx_Nmm_per_mm", 1.0))
        beam_length = float(args.get("beam_length_mm", 100.0))

        result = interlaminar_shear(layup, Mx=Mx, beam_length=beam_length)

        payload = {
            "num_plies": layup.num_plies,
            "total_thickness_mm": round(layup.total_thickness, 4),
            "Mx_Nmm_per_mm": Mx,
            "beam_length_mm": beam_length,
            "tau_xz_MPa": [round(float(v), 6) for v in result.tau_xz.tolist()],
            "interface_z_mm": [round(float(v), 6) for v in result.interface_z.tolist()],
            "max_tau_xz_MPa": round(result.max_tau_xz, 6),
            "max_interface_index": result.max_interface_index,
            "max_interface_z_mm": round(result.max_interface_z, 6),
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "COMPOSITES_ERROR")


# ---------------------------------------------------------------------------
# Tool: composites_thermal
# ---------------------------------------------------------------------------

composites_thermal_spec = ToolSpec(
    name="composites_thermal",
    description=(
        "Compute thermal residual stresses in a composite laminate due to a temperature "
        "change (e.g. cool-down from cure temperature). Uses Classical Laminate Theory "
        "with hygrothermal resultants. Returns per-ply residual stresses in principal "
        "axes (σ₁, σ₂, τ₁₂ in MPa), mid-plane strains, and curvatures."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plies": {
                "type": "array",
                "description": (
                    "Ordered ply stack. Each ply: {angle [deg], E1 [GPa], E2 [GPa], "
                    "G12 [GPa], nu12 [-], thickness [mm], alpha1 [1/°C], alpha2 [1/°C]}. "
                    "Typical CFRP: alpha1≈0.02e-6, alpha2≈22.5e-6."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "angle":     {"type": "number"},
                        "E1":        {"type": "number"},
                        "E2":        {"type": "number"},
                        "G12":       {"type": "number"},
                        "nu12":      {"type": "number"},
                        "thickness": {"type": "number"},
                        "alpha1":    {"type": "number", "description": "Longitudinal CTE [1/°C]. Default 0.02e-6."},
                        "alpha2":    {"type": "number", "description": "Transverse CTE [1/°C]. Default 22.5e-6."},
                    },
                    "required": ["angle", "E1", "E2", "G12", "nu12", "thickness"],
                },
                "minItems": 1,
            },
            "delta_T": {
                "type": "number",
                "description": (
                    "Temperature change [°C]. Negative for cure cool-down "
                    "(delta_T = T_service − T_cure, typically −120 to −160 for CFRP)."
                ),
            },
            "name": {"type": "string", "description": "Optional laminate label."},
        },
        "required": ["plies", "delta_T"],
    },
)


async def run_composites_thermal(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        layup, err = _build_layup(args["plies"], name=args.get("name", "laminate"))
        if layup is None:
            return err_payload(err, "BAD_ARGS")

        from kerf_composites.thermal_residual import thermal_residual

        raw_plies = args["plies"]
        alpha1_list = [float(rp.get("alpha1", 0.02e-6)) for rp in raw_plies]
        alpha2_list = [float(rp.get("alpha2", 22.5e-6)) for rp in raw_plies]
        delta_T = float(args["delta_T"])

        result = thermal_residual(layup, alpha1_list, alpha2_list, delta_T)

        ply_data = [
            {
                "ply_index": ps.ply_index,
                "angle": ps.angle,
                "sigma1_MPa": round(ps.sigma1, 4),
                "sigma2_MPa": round(ps.sigma2, 4),
                "tau12_MPa": round(ps.tau12, 4),
            }
            for ps in result.ply_stresses
        ]
        payload = {
            "name": layup.name,
            "num_plies": layup.num_plies,
            "delta_T": delta_T,
            "mid_plane_strains": [round(float(v), 9) for v in result.mid_plane_strains.tolist()],
            "curvatures_per_mm": [round(float(v), 9) for v in result.curvatures.tolist()],
            "ply_thermal_stresses": ply_data,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "COMPOSITES_ERROR")


# ---------------------------------------------------------------------------
# Tool: composites_failure_depth
# ---------------------------------------------------------------------------

composites_failure_depth_spec = ToolSpec(
    name="composites_failure_depth",
    description=(
        "Extended ply failure criteria with mode discrimination. "
        "Evaluates Tsai-Wu, Tsai-Hill, Max-stress, and Hashin (1980) criteria "
        "for given ply principal-axis stresses and material allowables. "
        "Returns failure index (FI), margin of safety (MS = 1/FI−1), "
        "failed flag, and controlling failure mode for each criterion."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sigma1": {
                "type": "number",
                "description": "Longitudinal (fibre-direction) stress [MPa]. + = tension.",
            },
            "sigma2": {
                "type": "number",
                "description": "Transverse stress [MPa]. + = tension.",
            },
            "tau12": {
                "type": "number",
                "description": "In-plane shear stress [MPa].",
            },
            "Xt": {"type": "number", "description": "Longitudinal tensile strength [MPa]."},
            "Xc": {"type": "number", "description": "Longitudinal compressive strength [MPa]."},
            "Yt": {"type": "number", "description": "Transverse tensile strength [MPa]."},
            "Yc": {"type": "number", "description": "Transverse compressive strength [MPa]."},
            "S12": {"type": "number", "description": "In-plane shear strength [MPa]."},
            "E1": {"type": "number", "description": "Longitudinal modulus [GPa] (for max-strain)."},
            "E2": {"type": "number", "description": "Transverse modulus [GPa] (for max-strain)."},
            "G12": {"type": "number", "description": "Shear modulus [GPa] (for max-strain)."},
            "nu12": {"type": "number", "description": "Major Poisson ratio (for max-strain)."},
            "F12_star": {
                "type": "number",
                "description": "Tsai-Wu interaction coefficient (default −0.5).",
            },
        },
        "required": ["sigma1", "sigma2", "tau12", "Xt", "Xc", "Yt", "Yc", "S12"],
    },
)


async def run_composites_failure_depth(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_composites.failure_depth import tsai_wu, tsai_hill, max_stress, hashin
        from kerf_composites.layup import PlyMaterial

        s1 = float(args["sigma1"])
        s2 = float(args["sigma2"])
        t12 = float(args["tau12"])
        F12_star = float(args.get("F12_star", -0.5))

        mat = PlyMaterial(
            name="user_material",
            E1=float(args.get("E1", 181.0)),
            E2=float(args.get("E2", 10.3)),
            G12=float(args.get("G12", 7.17)),
            nu12=float(args.get("nu12", 0.28)),
            Xt=float(args["Xt"]),
            Xc=float(args["Xc"]),
            Yt=float(args["Yt"]),
            Yc=float(args["Yc"]),
            S12=float(args["S12"]),
        )

        def _fr(r):
            return {
                "failure_index": round(r.failure_index, 6),
                "margin_of_safety": round(r.margin_of_safety, 6)
                if r.margin_of_safety != float("inf") else "inf",
                "failed": r.failed,
                "mode": r.mode.value,
                "criterion": r.criterion,
            }

        tw = tsai_wu(s1, s2, t12, mat, F12_star=F12_star)
        th = tsai_hill(s1, s2, t12, mat)
        ms = max_stress(s1, s2, t12, mat)
        h = hashin(s1, s2, t12, mat)

        ms_dict = {
            "fi_sigma1": round(ms.fi_sigma1, 6),
            "fi_sigma2": round(ms.fi_sigma2, 6),
            "fi_tau12": round(ms.fi_tau12, 6),
            "failure_index": round(ms.failure_index, 6),
            "margin_of_safety": round(ms.margin_of_safety, 6)
            if ms.margin_of_safety != float("inf") else "inf",
            "failed": ms.failed,
            "mode": ms.mode.value,
            "criterion": ms.criterion,
        }
        h_dict = {
            "fi_fiber_tension": round(h.fi_fiber_tension, 6),
            "fi_fiber_compression": round(h.fi_fiber_compression, 6),
            "fi_matrix_tension": round(h.fi_matrix_tension, 6),
            "fi_matrix_compression": round(h.fi_matrix_compression, 6),
            "failure_index": round(h.failure_index, 6),
            "margin_of_safety": round(h.margin_of_safety, 6)
            if h.margin_of_safety != float("inf") else "inf",
            "failed": h.failed,
            "mode": h.mode.value,
            "criterion": h.criterion,
        }

        payload = {
            "stress": {"sigma1_MPa": s1, "sigma2_MPa": s2, "tau12_MPa": t12},
            "tsai_wu": _fr(tw),
            "tsai_hill": _fr(th),
            "max_stress": ms_dict,
            "hashin": h_dict,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "COMPOSITES_ERROR")
