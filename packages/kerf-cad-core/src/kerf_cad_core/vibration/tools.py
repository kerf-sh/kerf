"""
kerf_cad_core.vibration.tools — LLM tool wrappers for vibration analysis.

Registers tools with the Kerf tool registry:

  vibration_sdof_natural_frequency     — ωn and fn for SDOF
  vibration_sdof_damped_frequency      — ωd and ζ for damped SDOF
  vibration_sdof_log_decrement         — damping ratio from peak amplitudes
  vibration_sdof_free_response         — x(t) for free vibration
  vibration_sdof_harmonic              — magnification factor and phase
  vibration_sdof_transmissibility      — base-excitation transmissibility
  vibration_sdof_rotating_unbalance    — rotating unbalance steady-state amplitude
  vibration_2dof_eigen                 — 2-DOF eigenfrequencies and mode shapes
  vibration_beam_frequency             — Euler-Bernoulli beam natural frequencies
  vibration_shaft_whirl_rayleigh       — shaft whirl by Rayleigh's method
  vibration_isolator_stiffness         — isolator stiffness for target TR

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Rao, S.S. "Mechanical Vibrations", 5th ed.
Inman, D.J. "Engineering Vibration", 4th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_cad_core._compat import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.vibration.dynamics import (
    sdof_natural_frequency,
    sdof_damped_frequency,
    sdof_damping_ratio_log_decrement,
    sdof_free_response,
    sdof_harmonic_magnification,
    sdof_base_transmissibility,
    sdof_rotating_unbalance,
    dof2_eigen,
    beam_natural_frequency,
    shaft_whirl_rayleigh,
    isolator_stiffness,
)


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_natural_frequency
# ---------------------------------------------------------------------------

_sdof_natfreq_spec = ToolSpec(
    name="vibration_sdof_natural_frequency",
    description=(
        "Compute the undamped natural frequency of a single-degree-of-freedom "
        "(SDOF) spring-mass system.\n\n"
        "Returns ωn (rad/s) and fn (Hz).\n\n"
        "Formula: ωn = √(k/m),  fn = ωn / (2π)\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m": {
                "type": "number",
                "description": "Mass (kg). Must be > 0.",
            },
            "k": {
                "type": "number",
                "description": "Spring stiffness (N/m). Must be > 0.",
            },
        },
        "required": ["m", "k"],
    },
)


@register(_sdof_natfreq_spec, write=False)
async def run_sdof_natural_frequency(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    m = a.get("m")
    k = a.get("k")
    if m is None:
        return json.dumps({"ok": False, "reason": "m is required"})
    if k is None:
        return json.dumps({"ok": False, "reason": "k is required"})

    return ok_payload(sdof_natural_frequency(m, k))


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_damped_frequency
# ---------------------------------------------------------------------------

_sdof_dampedfreq_spec = ToolSpec(
    name="vibration_sdof_damped_frequency",
    description=(
        "Compute the damped natural frequency and damping ratio of a SDOF "
        "viscously-damped spring-mass system.\n\n"
        "Returns ωd (rad/s), ζ (damping ratio), c_cr (critical damping), "
        "regime (underdamped/critically_damped/overdamped).\n\n"
        "Formula: c_cr = 2√(km),  ζ = c/c_cr,  ωd = ωn√(1-ζ²)\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m": {"type": "number", "description": "Mass (kg). Must be > 0."},
            "k": {"type": "number", "description": "Stiffness (N/m). Must be > 0."},
            "c": {
                "type": "number",
                "description": "Viscous damping coefficient (N·s/m). Must be >= 0.",
            },
        },
        "required": ["m", "k", "c"],
    },
)


@register(_sdof_dampedfreq_spec, write=False)
async def run_sdof_damped_frequency(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("m", "k", "c"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(sdof_damped_frequency(a["m"], a["k"], a["c"]))


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_log_decrement
# ---------------------------------------------------------------------------

_log_decrement_spec = ToolSpec(
    name="vibration_sdof_log_decrement",
    description=(
        "Estimate damping ratio ζ from measured free-vibration peak amplitudes "
        "using the logarithmic decrement method.\n\n"
        "Returns δ (log decrement), ζ (exact), and ζ_approx ≈ δ/(2π).\n\n"
        "Formula: δ = (1/n) ln(x1/xn),  ζ = δ / √(4π² + δ²)\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "x1": {
                "type": "number",
                "description": "Amplitude of first peak. Must be > 0.",
            },
            "xn": {
                "type": "number",
                "description": (
                    "Amplitude of the n-th peak. Must be > 0 and < x1."
                ),
            },
            "n": {
                "type": "integer",
                "description": "Number of cycles between x1 and xn. Must be >= 1.",
            },
        },
        "required": ["x1", "xn", "n"],
    },
)


@register(_log_decrement_spec, write=False)
async def run_sdof_log_decrement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("x1", "xn", "n"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(
        sdof_damping_ratio_log_decrement(a["x1"], a["xn"], a["n"])
    )


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_free_response
# ---------------------------------------------------------------------------

_free_response_spec = ToolSpec(
    name="vibration_sdof_free_response",
    description=(
        "Compute free-vibration displacement x(t) for a SDOF system given "
        "initial conditions.\n\n"
        "Handles underdamped (ζ < 1), critically damped (ζ = 1), and "
        "overdamped (ζ > 1) cases.\n\n"
        "Returns x(t) (m), zeta, omega_n, regime.\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m": {"type": "number", "description": "Mass (kg). Must be > 0."},
            "k": {"type": "number", "description": "Stiffness (N/m). Must be > 0."},
            "c": {
                "type": "number",
                "description": "Viscous damping (N·s/m). Must be >= 0.",
            },
            "x0": {
                "type": "number",
                "description": "Initial displacement (m). Any finite value.",
            },
            "v0": {
                "type": "number",
                "description": "Initial velocity (m/s). Any finite value.",
            },
            "t": {
                "type": "number",
                "description": "Evaluation time (s). Must be >= 0.",
            },
        },
        "required": ["m", "k", "c", "x0", "v0", "t"],
    },
)


@register(_free_response_spec, write=False)
async def run_sdof_free_response(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("m", "k", "c", "x0", "v0", "t"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(
        sdof_free_response(a["m"], a["k"], a["c"], a["x0"], a["v0"], a["t"])
    )


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_harmonic
# ---------------------------------------------------------------------------

_harmonic_spec = ToolSpec(
    name="vibration_sdof_harmonic",
    description=(
        "Compute the dynamic magnification factor M and phase angle φ for "
        "harmonic forced excitation of a SDOF system.\n\n"
        "r = ω / ωn is the frequency ratio.  Warns if near resonance.\n\n"
        "Formula: M = 1/√[(1-r²)²+(2ζr)²],  φ = arctan[2ζr/(1-r²)]\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "zeta": {
                "type": "number",
                "description": "Damping ratio ζ. Must be >= 0.",
            },
            "r": {
                "type": "number",
                "description": "Frequency ratio r = ω/ωn. Must be > 0.",
            },
        },
        "required": ["zeta", "r"],
    },
)


@register(_harmonic_spec, write=False)
async def run_sdof_harmonic(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("zeta", "r"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(sdof_harmonic_magnification(a["zeta"], a["r"]))


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_transmissibility
# ---------------------------------------------------------------------------

_transmissibility_spec = ToolSpec(
    name="vibration_sdof_transmissibility",
    description=(
        "Compute base-excitation transmissibility TR for a SDOF system.\n\n"
        "TR < 1 indicates vibration isolation (requires r > √2 ≈ 1.414).\n\n"
        "Formula: TR = √[(1+(2ζr)²) / ((1-r²)²+(2ζr)²)]\n\n"
        "Warns if not in isolation zone (r < √2).\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "zeta": {
                "type": "number",
                "description": "Damping ratio ζ. Must be >= 0.",
            },
            "r": {
                "type": "number",
                "description": "Frequency ratio r = ω/ωn. Must be > 0.",
            },
        },
        "required": ["zeta", "r"],
    },
)


@register(_transmissibility_spec, write=False)
async def run_sdof_transmissibility(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("zeta", "r"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(sdof_base_transmissibility(a["zeta"], a["r"]))


# ---------------------------------------------------------------------------
# Tool: vibration_sdof_rotating_unbalance
# ---------------------------------------------------------------------------

_rotating_unbalance_spec = ToolSpec(
    name="vibration_sdof_rotating_unbalance",
    description=(
        "Compute steady-state response amplitude for a rotating-unbalance "
        "excitation on a SDOF system.\n\n"
        "Returns amplitude X (m) and non-dimensional MX/(m_u·e).\n\n"
        "Formula: X = (m_u·e/m) · r²/√[(1-r²)²+(2ζr)²]\n\n"
        "Warns if near resonance.\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m": {
                "type": "number",
                "description": "Total machine mass including unbalance mass (kg). Must be > 0.",
            },
            "k": {
                "type": "number",
                "description": "Support stiffness (N/m). Must be > 0.",
            },
            "c": {
                "type": "number",
                "description": "Viscous damping (N·s/m). Must be >= 0.",
            },
            "m_u": {
                "type": "number",
                "description": "Unbalance mass (kg). Must be > 0.",
            },
            "e": {
                "type": "number",
                "description": "Eccentricity (m). Must be > 0.",
            },
            "omega": {
                "type": "number",
                "description": "Excitation angular frequency (rad/s). Must be > 0.",
            },
        },
        "required": ["m", "k", "c", "m_u", "e", "omega"],
    },
)


@register(_rotating_unbalance_spec, write=False)
async def run_sdof_rotating_unbalance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("m", "k", "c", "m_u", "e", "omega"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(
        sdof_rotating_unbalance(
            a["m"], a["k"], a["c"], a["m_u"], a["e"], a["omega"]
        )
    )


# ---------------------------------------------------------------------------
# Tool: vibration_2dof_eigen
# ---------------------------------------------------------------------------

_dof2_eigen_spec = ToolSpec(
    name="vibration_2dof_eigen",
    description=(
        "Compute the natural frequencies and mode shapes of an undamped 2-DOF "
        "spring-mass system via exact 2×2 closed-form solution.\n\n"
        "System: m1·ẍ1 + (k1+k2)x1 - k2·x2 = 0,  m2·ẍ2 - k2·x1 + (k2+k3)x2 = 0\n\n"
        "Returns ω1, ω2 (rad/s), fn1, fn2 (Hz), and mode shapes [1, u2].\n\n"
        "k3 = 0 (default) for a free second mass (only two springs k1 and k2).\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m1": {"type": "number", "description": "First mass (kg). Must be > 0."},
            "m2": {"type": "number", "description": "Second mass (kg). Must be > 0."},
            "k1": {
                "type": "number",
                "description": "Spring stiffness from ground to m1 (N/m). Must be > 0.",
            },
            "k2": {
                "type": "number",
                "description": "Coupling spring stiffness between m1 and m2 (N/m). Must be > 0.",
            },
            "k3": {
                "type": "number",
                "description": (
                    "Spring stiffness from m2 to ground (N/m). Default 0. Must be >= 0."
                ),
            },
        },
        "required": ["m1", "m2", "k1", "k2"],
    },
)


@register(_dof2_eigen_spec, write=False)
async def run_2dof_eigen(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("m1", "m2", "k1", "k2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "k3" in a:
        kwargs["k3"] = a["k3"]

    return ok_payload(dof2_eigen(a["m1"], a["m2"], a["k1"], a["k2"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: vibration_beam_frequency
# ---------------------------------------------------------------------------

_beam_freq_spec = ToolSpec(
    name="vibration_beam_frequency",
    description=(
        "Compute the natural frequency of an Euler-Bernoulli beam for a given "
        "mode number and boundary condition.\n\n"
        "Boundary conditions: 'simply-supported' (βL = n·π) or "
        "'cantilever' (tabulated βL roots).\n\n"
        "Formula: ωn = (βL)² × √(EI / (μ L⁴))\n\n"
        "Returns ωn (rad/s), fn (Hz), and the βL eigenvalue used.\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "integer",
                "description": "Mode number (1 = fundamental). Must be >= 1.",
            },
            "length_m": {
                "type": "number",
                "description": "Beam length (m). Must be > 0.",
            },
            "mass_per_m": {
                "type": "number",
                "description": "Mass per unit length μ = ρA (kg/m). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Young's modulus (Pa). Must be > 0. Steel ≈ 200e9 Pa.",
            },
            "I": {
                "type": "number",
                "description": (
                    "Second moment of area (m⁴). Must be > 0. "
                    "Solid circle: π·d⁴/64."
                ),
            },
            "bc": {
                "type": "string",
                "enum": ["simply-supported", "cantilever"],
                "description": (
                    "Boundary condition: 'simply-supported' (default) or 'cantilever'."
                ),
            },
        },
        "required": ["mode", "length_m", "mass_per_m", "E", "I"],
    },
)


@register(_beam_freq_spec, write=False)
async def run_beam_frequency(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("mode", "length_m", "mass_per_m", "E", "I"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "bc" in a:
        kwargs["bc"] = a["bc"]

    return ok_payload(
        beam_natural_frequency(
            a["mode"], a["length_m"], a["mass_per_m"], a["E"], a["I"], **kwargs
        )
    )


# ---------------------------------------------------------------------------
# Tool: vibration_shaft_whirl_rayleigh
# ---------------------------------------------------------------------------

_shaft_whirl_spec = ToolSpec(
    name="vibration_shaft_whirl_rayleigh",
    description=(
        "Compute the first lateral whirl (critical) speed of a multi-disk shaft "
        "using Rayleigh's energy method.\n\n"
        "The shaft is modelled as a simply-supported uniform beam with disk masses "
        "at specified positions.  Static deflections under gravity are used as the "
        "assumed mode shape.\n\n"
        "Returns ω_cr (rad/s), n_cr (rpm), and static deflections at each disk.\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lengths_m": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Positions along the shaft of each disk, measured from the left "
                    "bearing (m).  All positions must be strictly between 0 and the "
                    "maximum position (shaft span)."
                ),
            },
            "masses_kg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Mass of each disk (kg). Same length as lengths_m.",
            },
            "E": {
                "type": "number",
                "description": "Young's modulus (Pa). Must be > 0.",
            },
            "I": {
                "type": "number",
                "description": (
                    "Second moment of area of shaft cross-section (m⁴). Must be > 0."
                ),
            },
            "span_m": {
                "type": "number",
                "description": (
                    "Total shaft span between bearings (m). "
                    "If omitted, the span is taken as max(lengths_m). "
                    "Provide when all disk positions are strictly interior."
                ),
            },
        },
        "required": ["lengths_m", "masses_kg", "E", "I"],
    },
)


@register(_shaft_whirl_spec, write=False)
async def run_shaft_whirl_rayleigh(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("lengths_m", "masses_kg", "E", "I"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "span_m" in a:
        kwargs["span_m"] = a["span_m"]

    return ok_payload(
        shaft_whirl_rayleigh(a["lengths_m"], a["masses_kg"], a["E"], a["I"], **kwargs)
    )


# ---------------------------------------------------------------------------
# Tool: vibration_isolator_stiffness
# ---------------------------------------------------------------------------

_isolator_spec = ToolSpec(
    name="vibration_isolator_stiffness",
    description=(
        "Compute the required undamped isolator stiffness to achieve a target "
        "transmissibility TR at a given excitation frequency.\n\n"
        "Assumes ζ = 0 (undamped isolator) and isolation zone r > √2.\n\n"
        "Returns required k (N/m), ωn (rad/s), frequency ratio r, and "
        "static deflection under mass weight.\n\n"
        "TR_target must be in (0, 1) — e.g. 0.1 for 90% isolation.\n\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m": {
                "type": "number",
                "description": "Isolated mass (kg). Must be > 0.",
            },
            "omega_exc": {
                "type": "number",
                "description": "Excitation angular frequency (rad/s). Must be > 0.",
            },
            "TR_target": {
                "type": "number",
                "description": (
                    "Target transmissibility (0 < TR < 1). "
                    "E.g. 0.1 for 90% isolation, 0.05 for 95% isolation."
                ),
            },
        },
        "required": ["m", "omega_exc", "TR_target"],
    },
)


@register(_isolator_spec, write=False)
async def run_isolator_stiffness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("m", "omega_exc", "TR_target"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    return ok_payload(
        isolator_stiffness(a["m"], a["omega_exc"], a["TR_target"])
    )
