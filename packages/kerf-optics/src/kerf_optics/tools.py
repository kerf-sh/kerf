"""
kerf_optics LLM tools — paraxial ray-trace and lens design.

Registered via plugin.py at startup.

Tools
-----
optics_trace_ray    — trace a ray (or bundle) through a multi-element lens
                      system and return spot size / focal length.
optics_lens_design  — first-order design helper: given target EFL and object
                      distance, solve for element parameters.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_optics._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# optics_trace_ray
# ---------------------------------------------------------------------------

optics_trace_ray_spec = ToolSpec(
    name="optics_trace_ray",
    description=(
        "Trace a ray (or a ray bundle) through a multi-element paraxial lens "
        "system using the ABCD ray-transfer matrix formalism.  Returns ray "
        "heights at each surface, effective focal length, and RMS spot radius "
        "at the exit plane.  Supports thin lenses, free-space gaps, curved "
        "interfaces, mirrors, and aperture stops."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": (
                    "Ordered list of optical elements (first = closest to source). "
                    "Each element is a dict with a 'type' key and type-specific "
                    "parameters:\n"
                    "  {type:'thin_lens', f:<focal_length_m>}\n"
                    "  {type:'free_space', d:<distance_m>, n:<index, default 1.0>}\n"
                    "  {type:'curved_interface', R:<radius_m>, n1:<from_index>, n2:<to_index>}\n"
                    "  {type:'mirror', R:<radius_m>}\n"
                    "  {type:'aperture', diameter:<m>}\n"
                    "  {type:'detector'}"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                    },
                    "required": ["type"],
                },
                "minItems": 1,
            },
            "rays": {
                "type": "array",
                "description": (
                    "Ray bundle: list of [y0, nu0] initial ray states. "
                    "y0 = height (m), nu0 = reduced angle n*theta. "
                    "Default: [[0.001, 0.0]] (on-axis marginal ray, h=1 mm)."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        },
        "required": ["elements"],
    },
)


def _build_element(spec: dict):
    """Deserialise an element dict into the appropriate Element object."""
    from kerf_optics.lens_system import (
        ThinLens, FreeSpace, CurvedInterface, Mirror, Aperture, Detector
    )

    etype = spec.get("type", "").lower()
    if etype == "thin_lens":
        return ThinLens(f=float(spec["f"]))
    elif etype == "free_space":
        return FreeSpace(d=float(spec["d"]), n=float(spec.get("n", 1.0)))
    elif etype == "curved_interface":
        return CurvedInterface(
            R=float(spec["R"]),
            n1=float(spec["n1"]),
            n2=float(spec["n2"]),
        )
    elif etype == "mirror":
        return Mirror(R=float(spec["R"]))
    elif etype == "aperture":
        return Aperture(diameter=float(spec["diameter"]))
    elif etype == "detector":
        return Detector()
    else:
        raise ValueError(f"unknown element type: {spec.get('type')!r}")


async def run_optics_trace_ray(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_optics.lens_system import LensSystem

        raw_elements = args["elements"]
        elements = [_build_element(e) for e in raw_elements]

        raw_rays = args.get("rays")
        if raw_rays is None:
            rays = [(0.001, 0.0)]  # default: 1 mm marginal ray
        else:
            rays = [(float(r[0]), float(r[1])) for r in raw_rays]

        system = LensSystem(elements)
        M = system.system_matrix()
        histories = system.trace_bundle(rays)

        # Spot diagram
        spot = system.spot_diagram()

        # EFL if system has power
        C = M[1, 0]
        efl = (-1.0 / C) if abs(C) > 1e-14 else None

        # Format ray histories
        ray_data = []
        for i, hist in enumerate(histories):
            ray_data.append({
                "ray_index": i,
                "y0": hist[0][0],
                "nu0": hist[0][1],
                "surfaces": [
                    {"y": round(y, 8), "nu": round(nu, 8)}
                    for y, nu in hist[1:]
                ],
                "final_height": round(hist[-1][0], 8),
            })

        payload: dict[str, Any] = {
            "n_elements": len(elements),
            "efl": round(efl, 8) if efl is not None else None,
            "system_matrix": {
                "A": round(M[0, 0], 8),
                "B": round(M[0, 1], 8),
                "C": round(M[1, 0], 8),
                "D": round(M[1, 1], 8),
            },
            "rays": ray_data,
            "spot": {
                "rms_spot_m": round(spot["rms_spot"], 10),
                "n_rays": spot["n_rays"],
            },
        }
        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "OPTICS_ERROR")


# ---------------------------------------------------------------------------
# optics_lens_design
# ---------------------------------------------------------------------------

optics_lens_design_spec = ToolSpec(
    name="optics_lens_design",
    description=(
        "First-order paraxial lens design helper. Given a target effective "
        "focal length (EFL) and conjugate distances (object and image), "
        "solves for the lens arrangement and returns the thin-lens system "
        "parameters.  For a single-lens system, uses the thin-lens equation "
        "1/f = 1/di - 1/do. For a two-lens telephoto, computes the "
        "separation required to achieve the target EFL."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target_efl": {
                "type": "number",
                "description": "Target effective focal length in metres.",
            },
            "object_distance": {
                "type": "number",
                "description": "Object distance (m) — positive = real object to the left.",
            },
            "design_type": {
                "type": "string",
                "enum": ["single", "telephoto"],
                "description": "'single' (one thin lens) or 'telephoto' (two lenses). Default 'single'.",
            },
            "f1": {
                "type": "number",
                "description": "(telephoto only) Focal length of the first element (m).",
            },
            "f2": {
                "type": "number",
                "description": "(telephoto only) Focal length of the second element (m). "
                               "If omitted, solved from target_efl and f1.",
            },
        },
        "required": ["target_efl", "object_distance"],
    },
)


async def run_optics_lens_design(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_optics.lens_system import LensSystem, FreeSpace, ThinLens
        from kerf_optics.ray_transfer import focal_length as _efl, image_distance as _imgdist

        target_efl = float(args["target_efl"])
        do = float(args["object_distance"])
        design_type = args.get("design_type", "single")

        if design_type == "single":
            # Thin-lens equation: 1/di = 1/f + 1/do  (note: do is positive)
            # Using sign convention di = 1/(1/f - 1/do) for do positive
            f = target_efl
            # image distance from thin lens equation
            if abs(1.0 / f - 1.0 / do) < 1e-14:
                raise ValueError("object at the focal point; image at infinity")
            di = 1.0 / (1.0 / f - 1.0 / do)

            system = LensSystem([FreeSpace(do), ThinLens(f), FreeSpace(di)])
            M = system.system_matrix()

            payload = {
                "design_type": "single",
                "f": f,
                "object_distance": do,
                "image_distance": round(di, 6),
                "efl_achieved": round(_efl(ThinLens(f).matrices()[0]), 6),
                "magnification": round(di / do, 6),
                "elements": [
                    {"type": "free_space", "d": do},
                    {"type": "thin_lens", "f": f},
                    {"type": "free_space", "d": round(di, 6)},
                ],
            }

        elif design_type == "telephoto":
            f1 = float(args.get("f1", target_efl * 1.5))
            if "f2" in args:
                f2 = float(args["f2"])
                # Compute separation from EFL formula:
                #   1/EFL = 1/f1 + 1/f2 - d/(f1*f2)  →  d = (1/f1 + 1/f2 - 1/EFL) * f1*f2
                d = (1.0 / f1 + 1.0 / f2 - 1.0 / target_efl) * f1 * f2
            else:
                # Solve f2 from EFL formula with a default separation d = f1/4
                d = f1 / 4.0
                # 1/EFL = 1/f1 + 1/f2 - d/(f1*f2)
                # 1/f2 = 1/EFL - 1/f1 + d/(f1*f2) — needs rearrangement
                # 1/f2 * (1 - d/f1) = 1/EFL - 1/f1
                # (1/f2) = (1/EFL - 1/f1) / (1 - d/f1)
                denom = 1.0 - d / f1
                if abs(denom) < 1e-14:
                    raise ValueError(f"degenerate telephoto: d == f1 ({f1})")
                inv_f2 = (1.0 / target_efl - 1.0 / f1) / denom
                if abs(inv_f2) < 1e-14:
                    raise ValueError("f2 → infinity; unsolvable telephoto")
                f2 = 1.0 / inv_f2

            # Build system up to lens2 (no image plane yet) and find image distance
            pre_system = LensSystem([FreeSpace(do), ThinLens(f1), FreeSpace(d), ThinLens(f2)])
            M = pre_system.system_matrix()

            # Image is located where height of an on-axis ray = 0; for ABCD: di = -D/C
            C = M[1, 0]
            if abs(C) < 1e-14:
                raise ValueError("telephoto system has no power")
            achieved_efl = -1.0 / C
            di = -M[1, 1] / C  # image distance from last element

            payload = {
                "design_type": "telephoto",
                "f1": round(f1, 6),
                "f2": round(f2, 6),
                "separation": round(d, 6),
                "object_distance": do,
                "image_distance_from_lens2": round(di, 6),
                "efl_achieved": round(achieved_efl, 6),
                "elements": [
                    {"type": "free_space", "d": do},
                    {"type": "thin_lens", "f": round(f1, 6)},
                    {"type": "free_space", "d": round(d, 6)},
                    {"type": "thin_lens", "f": round(f2, 6)},
                    {"type": "free_space", "d": round(di, 6)},
                ],
            }

        else:
            return err_payload(f"unknown design_type: {design_type!r}", "BAD_ARGS")

        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "OPTICS_DESIGN_ERROR")


# ---------------------------------------------------------------------------
# optics_tolerancing
# ---------------------------------------------------------------------------

optics_tolerancing_spec = ToolSpec(
    name="optics_tolerancing",
    description=(
        "Optical tolerance analysis (sensitivity + Monte Carlo) for a multi-element "
        "paraxial lens system.  Perturbs each tolerance parameter one-at-a-time (OAT) "
        "and also runs Monte Carlo trials.  Merit function options: 'efl' (|EFL − target|), "
        "'bfd' (|BFD − target|).  Returns per-parameter sensitivities, RSS budget, and "
        "Monte Carlo statistics (mean, std, P05, P95, yield)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": "Lens system elements (same format as optics_trace_ray).",
                "items": {"type": "object"},
                "minItems": 1,
            },
            "tolerances": {
                "type": "array",
                "description": (
                    "List of tolerance parameters. Each: "
                    "{element_index: int, param_name: str, delta: float, "
                    "nominal: float (optional), description: str (optional)}."
                ),
                "items": {"type": "object"},
                "minItems": 1,
            },
            "merit_type": {
                "type": "string",
                "enum": ["efl", "bfd"],
                "description": "Merit function: 'efl' or 'bfd'. Default 'efl'.",
            },
            "target_value": {
                "type": "number",
                "description": "Target value for the merit function (m). Default = nominal EFL.",
            },
            "n_mc_trials": {
                "type": "integer",
                "description": "Number of Monte Carlo trials. Default 500.",
            },
            "mc_distribution": {
                "type": "string",
                "enum": ["uniform", "normal"],
                "description": "Monte Carlo distribution: 'uniform' (default) or 'normal' (±3σ).",
            },
            "mc_seed": {
                "type": "integer",
                "description": "Monte Carlo random seed. Default 42.",
            },
        },
        "required": ["elements", "tolerances"],
    },
)


async def run_optics_tolerancing(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_optics.lens_system import LensSystem
        from kerf_optics.tolerancing import (
            ToleranceParam,
            sensitivity_analysis,
            monte_carlo_tolerancing,
            merit_efl,
            merit_bfd,
        )

        # Build system
        raw_elements = args["elements"]
        from kerf_optics.tools import _build_element
        elements = [_build_element(e) for e in raw_elements]
        system = LensSystem(elements)

        # Build tolerance params
        raw_tols = args["tolerances"]
        params = []
        for t in raw_tols:
            params.append(ToleranceParam(
                element_index=int(t["element_index"]),
                param_name=str(t["param_name"]),
                nominal=float(t["nominal"]) if "nominal" in t else None,
                delta=float(t["delta"]),
                description=str(t.get("description", "")),
            ))

        # Merit function
        merit_type = str(args.get("merit_type", "efl")).lower()
        M = system.system_matrix()
        C = M[1, 0]
        nominal_efl = -1.0 / C if abs(C) > 1e-14 else 1.0
        target = float(args.get("target_value", nominal_efl))

        if merit_type == "efl":
            merit_fn = merit_efl(target)
        elif merit_type == "bfd":
            merit_fn = merit_bfd(target)
        else:
            return err_payload(f"unknown merit_type: {merit_type!r}", "BAD_ARGS")

        # Sensitivity
        sens = sensitivity_analysis(system, params, merit_fn)

        # Monte Carlo
        n_mc = int(args.get("n_mc_trials", 500))
        mc_dist = str(args.get("mc_distribution", "uniform"))
        mc_seed = int(args.get("mc_seed", 42))
        mc = monte_carlo_tolerancing(
            system, params, merit_fn,
            n_trials=n_mc, distribution=mc_dist, seed=mc_seed,
        )

        payload: dict[str, Any] = {
            "merit_type": merit_type,
            "target_value": target,
            "merit_nominal": round(sens.merit_nominal, 8),
            "rss_budget": round(sens.rss_budget, 8),
            "sensitivity_table": [
                {k: (round(v, 8) if isinstance(v, float) else v)
                 for k, v in row.items()}
                for row in sens.sensitivity_table()
            ],
            "monte_carlo": mc.summary(),
        }
        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "TOLERANCING_ERROR")


# ---------------------------------------------------------------------------
# optics_mtf
# ---------------------------------------------------------------------------

optics_mtf_spec = ToolSpec(
    name="optics_mtf",
    description=(
        "Compute the Modulation Transfer Function (MTF) for a paraxial lens system. "
        "Returns the diffraction-limited MTF (circular aperture, incoherent) and the "
        "geometric MTF (Gaussian spot approximation) as functions of spatial frequency "
        "(line pairs/mm at the image plane).  Also reports the diffraction cut-off "
        "frequency, f-number, wavelength, and RMS spot radius."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": "Lens system elements (same format as optics_trace_ray).",
                "items": {"type": "object"},
                "minItems": 1,
            },
            "object_distance_m": {
                "type": "number",
                "description": "Object distance in metres (positive = real object). Default 1.0.",
            },
            "f_number": {
                "type": "number",
                "description": "Aperture f/# = focal_length / aperture_diameter. Default 4.0.",
            },
            "lambda_nm": {
                "type": "number",
                "description": "Wavelength in nanometres. Default 550 nm (green).",
            },
            "max_freq_lpmm": {
                "type": "number",
                "description": "Maximum spatial frequency in lp/mm for the output curve. "
                               "Default: 1.2× diffraction cut-off.",
            },
            "n_freq_points": {
                "type": "integer",
                "description": "Number of spatial frequency points. Default 50.",
            },
        },
        "required": ["elements"],
    },
)


async def run_optics_mtf(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        import numpy as np_inner
        from kerf_optics.lens_system import LensSystem
        from kerf_optics.mtf import mtf_from_lens_system, diffraction_cutoff_lpmm
        from kerf_optics.tools import _build_element

        raw_elements = args["elements"]
        elements = [_build_element(e) for e in raw_elements]
        system = LensSystem(elements)

        do = float(args.get("object_distance_m", 1.0))
        f_num = float(args.get("f_number", 4.0))
        lam = float(args.get("lambda_nm", 550.0))
        n_pts = int(args.get("n_freq_points", 50))

        nu_c = diffraction_cutoff_lpmm(f_num, lam)
        max_freq = float(args.get("max_freq_lpmm", 1.2 * nu_c))
        freqs = list(np_inner.linspace(0.0, max_freq, n_pts))

        result = mtf_from_lens_system(
            system,
            object_distance_m=do,
            f_number=f_num,
            lambda_nm=lam,
            spatial_freqs_lpmm=freqs,
        )

        payload: dict[str, Any] = result.to_dict()
        payload["mtf_at_50lpmm"] = round(result.mtf_50lpmm, 6)
        payload["mtf_at_100lpmm"] = round(result.mtf_100lpmm, 6)
        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "MTF_ERROR")


# ---------------------------------------------------------------------------
# optics_pop_propagate
# ---------------------------------------------------------------------------

optics_pop_propagate_spec = ToolSpec(
    name="optics_pop_propagate",
    description=(
        "Physical-Optics Propagation (POP) / angular-spectrum + Fresnel/Fraunhofer "
        "scalar diffraction propagation of a monochromatic wavefront.  "
        "Generates a Gaussian TEM₀₀ source field, optionally applies a thin-lens "
        "or circular-aperture phase screen, then propagates by distance z.  "
        "Returns: intensity peak, beam waist (1/e² radius), energy conservation "
        "ratio, propagation method used, grid parameters, and Fresnel number.  "
        "Method auto-selects Angular Spectrum (near-field) or Fresnel (far-field)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lambda_um": {
                "type": "number",
                "description": "Wavelength in micrometres (e.g. 0.633 for HeNe, 1.064 for Nd:YAG). Default 0.633.",
            },
            "w0_mm": {
                "type": "number",
                "description": "Beam waist radius (1/e² field) in mm. Default 1.0.",
            },
            "z_mm": {
                "type": "number",
                "description": "Propagation distance in mm. Default 100.0.",
            },
            "grid_N": {
                "type": "integer",
                "description": "Grid size N×N pixels (power-of-2 recommended). Default 128.",
            },
            "dx_um": {
                "type": "number",
                "description": "Pixel pitch in micrometres. Default 20.0.",
            },
            "method": {
                "type": "string",
                "enum": ["auto", "asm", "fresnel"],
                "description": (
                    "Propagation method: 'auto' (Fresnel-number adaptive), "
                    "'asm' (Angular Spectrum — near-field), "
                    "'fresnel' (Fresnel TF — paraxial far-field). Default 'auto'."
                ),
            },
            "aperture_radius_mm": {
                "type": "number",
                "description": "Optional circular aperture radius (mm) applied before propagation. Omit = no aperture.",
            },
            "lens_focal_length_mm": {
                "type": "number",
                "description": "Optional thin-lens focal length (mm) applied before propagation. Omit = no lens.",
            },
        },
        "required": [],
    },
)


async def run_optics_pop_propagate(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        import math
        import numpy as np
        from kerf_optics.pop import (
            make_grid,
            gaussian_source,
            thin_lens_phase,
            circular_aperture,
            propagate,
            parseval_energy,
            gaussian_waist_analytic,
        )

        lambda_um = float(args.get("lambda_um", 0.633))
        w0_mm = float(args.get("w0_mm", 1.0))
        z_mm = float(args.get("z_mm", 100.0))
        N = int(args.get("grid_N", 128))
        dx_um = float(args.get("dx_um", 20.0))
        method = str(args.get("method", "auto"))

        # Convert to SI metres
        lambda_m = lambda_um * 1e-6
        w0_m = w0_mm * 1e-3
        z_m = z_mm * 1e-3
        dx_m = dx_um * 1e-6

        if lambda_m <= 0:
            return err_payload("lambda_um must be positive", "BAD_ARGS")
        if w0_m <= 0:
            return err_payload("w0_mm must be positive", "BAD_ARGS")
        if N < 16 or N > 1024:
            return err_payload("grid_N must be in [16, 1024]", "BAD_ARGS")
        if dx_m <= 0:
            return err_payload("dx_um must be positive", "BAD_ARGS")

        x, y = make_grid(N, dx_m)

        # Source field
        U = gaussian_source(x, y, w0=w0_m, lambda_m=lambda_m)

        E_in = parseval_energy(U, dx_m)

        # Optional lens
        lens_f = args.get("lens_focal_length_mm")
        if lens_f is not None:
            f_m = float(lens_f) * 1e-3
            if f_m != 0:
                lens_phase = thin_lens_phase(x, y, f=f_m, lambda_m=lambda_m)
                U = U * lens_phase

        # Optional aperture
        ap_r = args.get("aperture_radius_mm")
        if ap_r is not None:
            R_m = float(ap_r) * 1e-3
            mask = circular_aperture(x, y, radius=R_m)
            U = U * mask

        # Propagate
        U_out = propagate(U, dx=dx_m, z=z_m, lambda_m=lambda_m, method=method)

        # Determine actual method used
        if method == "auto":
            half_ap = (N * dx_m) / 2.0
            NF = half_ap ** 2 / (lambda_m * abs(z_m)) if z_m != 0 else float("inf")
            actual_method = "asm" if NF > 10.0 else "fresnel"
        else:
            actual_method = method
            NF = ((N * dx_m) / 2.0) ** 2 / (lambda_m * abs(z_m)) if z_m != 0 else float("inf")

        # Output field metrics
        I_out = np.abs(U_out) ** 2
        E_out = parseval_energy(U_out, dx_m)
        energy_ratio = float(E_out / E_in) if E_in > 0 else None

        I_peak = float(np.max(I_out))

        # Beam waist estimate: radius where I >= I_peak / e²
        I_threshold = I_peak / math.e ** 2
        r2 = x ** 2 + y ** 2
        beam_pixels = r2[I_out >= I_threshold]
        beam_waist_m = float(math.sqrt(float(np.max(beam_pixels)))) if len(beam_pixels) > 0 else None

        # Analytic beam waist for comparison (no lens)
        if lens_f is None and ap_r is None:
            w_analytic_m = gaussian_waist_analytic(w0=w0_m, lambda_m=lambda_m, z=z_m)
        else:
            w_analytic_m = None

        Rayleigh_m = math.pi * w0_m ** 2 / lambda_m

        payload: dict[str, Any] = {
            "lambda_um": lambda_um,
            "w0_mm": w0_mm,
            "z_mm": z_mm,
            "grid_N": N,
            "dx_um": dx_um,
            "method_requested": method,
            "method_used": actual_method,
            "fresnel_number": round(NF, 4) if math.isfinite(NF) else None,
            "Rayleigh_range_mm": round(Rayleigh_m * 1e3, 4),
            "intensity_peak": round(I_peak, 8),
            "energy_in": round(float(E_in), 8),
            "energy_out": round(float(E_out), 8),
            "energy_conservation_ratio": round(energy_ratio, 6) if energy_ratio is not None else None,
            "beam_waist_mm": round(beam_waist_m * 1e3, 4) if beam_waist_m is not None else None,
            "beam_waist_analytic_mm": round(w_analytic_m * 1e3, 4) if w_analytic_m is not None else None,
        }
        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "POP_ERROR")
