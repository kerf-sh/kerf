"""
kerf_composites LLM tools — layup_analysis.

Registered via plugin.py at startup.
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
