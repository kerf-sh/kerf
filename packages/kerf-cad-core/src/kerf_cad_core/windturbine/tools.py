"""
kerf_cad_core.windturbine.tools — LLM tool wrappers for wind-turbine sizing.

Registers tools with the Kerf tool registry:

  wt_available_power       — P = ½·ρ·A·V³ available wind power
  wt_betz_limit            — Betz theoretical Cp_max = 16/27
  wt_air_density           — ISA air density at altitude & temperature
  wt_rotor_diameter        — rotor diameter from rated power & Cp
  wt_rotor_speed           — rotor RPM from tip-speed ratio
  wt_gearbox_ratio         — step-up gearbox ratio to generator speed
  wt_thrust_force          — axial rotor thrust force
  wt_overturning_moment    — tower base overturning moment
  wt_blade_element_momentum — simplified BEM Cp/Ct integration
  wt_power_curve           — power at a given wind speed (cut-in/rated/cut-out)
  wt_weibull_aep           — annual energy production via Weibull distribution
  wt_rayleigh_aep          — annual energy production via Rayleigh distribution
  wt_capacity_factor       — capacity factor from AEP & rated power
  wt_jensen_wake           — Jensen single-wake velocity deficit
  wt_sound_pressure        — turbine SPL at observer distance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Burton, T. et al., "Wind Energy Handbook", 2nd ed., Wiley (2011).
Jensen, N.O. (1983) — wake decay model (RISØ M-2411).
IEC 61400-1:2019 — Wind turbine design requirements.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.windturbine.rotor import (
    available_power,
    betz_limit,
    air_density,
    rotor_diameter,
    rotor_speed,
    gearbox_ratio,
    thrust_force,
    overturning_moment,
    blade_element_momentum,
    power_curve,
    weibull_aep,
    rayleigh_aep,
    capacity_factor,
    jensen_wake,
    sound_pressure_distance,
)


# ---------------------------------------------------------------------------
# Tool: wt_available_power
# ---------------------------------------------------------------------------

_available_power_spec = ToolSpec(
    name="wt_available_power",
    description=(
        "Compute available wind power from kinetic energy flux: P = ½·ρ·A·V³.\n"
        "\n"
        "This is the total power in the wind stream; the turbine can extract "
        "at most Cp_max = 16/27 (Betz limit) of this.\n"
        "\n"
        "Returns power_W and power_kW.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rho": {
                "type": "number",
                "description": "Air density (kg/m³). Standard sea-level = 1.225 kg/m³.",
            },
            "A": {
                "type": "number",
                "description": "Rotor swept area (m²). For diameter D: A = π·D²/4.",
            },
            "V": {
                "type": "number",
                "description": "Free-stream wind speed at hub height (m/s).",
            },
        },
        "required": ["rho", "A", "V"],
    },
)


@register(_available_power_spec, write=False)
async def run_wt_available_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rho", "A", "V"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = available_power(a["rho"], a["A"], a["V"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_betz_limit
# ---------------------------------------------------------------------------

_betz_limit_spec = ToolSpec(
    name="wt_betz_limit",
    description=(
        "Return the Betz theoretical maximum power coefficient Cp_max = 16/27 ≈ 0.5926.\n"
        "\n"
        "At the Betz optimum, the axial induction factor a = 1/3 and the wake "
        "velocity equals V/3.  No inputs required.\n"
        "\n"
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


@register(_betz_limit_spec, write=False)
async def run_wt_betz_limit(ctx: ProjectCtx, args: bytes) -> str:
    result = betz_limit()
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_air_density
# ---------------------------------------------------------------------------

_air_density_spec = ToolSpec(
    name="wt_air_density",
    description=(
        "Compute ISA air density corrected for altitude and temperature.\n"
        "\n"
        "Uses the barometric formula for pressure and the ideal gas law.  "
        "Wind turbine power varies directly with air density, so "
        "high-altitude or high-temperature sites see significant derating.\n"
        "\n"
        "Returns rho_kg_m3, pressure_Pa, temperature_K.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "altitude_m": {
                "type": "number",
                "description": "Altitude above sea level (m). Default 0.",
            },
            "temperature_c": {
                "type": "number",
                "description": "Ambient temperature (°C). Default 15.",
            },
        },
        "required": [],
    },
)


@register(_air_density_spec, write=False)
async def run_wt_air_density(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    if "altitude_m" in a:
        kwargs["altitude_m"] = a["altitude_m"]
    if "temperature_c" in a:
        kwargs["temperature_c"] = a["temperature_c"]

    result = air_density(**kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_rotor_diameter
# ---------------------------------------------------------------------------

_rotor_diameter_spec = ToolSpec(
    name="wt_rotor_diameter",
    description=(
        "Compute the rotor diameter required to achieve a rated power output.\n"
        "\n"
        "From P = ½·ρ·(π·D²/4)·V³·Cp  →  D = √(8·P / (π·ρ·V³·Cp)).\n"
        "\n"
        "Cp > 16/27 (Betz limit) is physically impossible — input is clamped "
        "and a warning is issued.\n"
        "\n"
        "Returns diameter_m and swept_area_m2.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_rated_W": {
                "type": "number",
                "description": "Rated electrical power output (W). Must be > 0.",
            },
            "Cp": {
                "type": "number",
                "description": (
                    "Power coefficient (dimensionless). Typical 0.35–0.50. "
                    "Capped at Betz limit 16/27 ≈ 0.5926."
                ),
            },
            "rho": {
                "type": "number",
                "description": "Air density (kg/m³). Use wt_air_density for site correction.",
            },
            "V_rated_ms": {
                "type": "number",
                "description": "Rated (design) wind speed (m/s). Typically 11–15 m/s.",
            },
        },
        "required": ["P_rated_W", "Cp", "rho", "V_rated_ms"],
    },
)


@register(_rotor_diameter_spec, write=False)
async def run_wt_rotor_diameter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P_rated_W", "Cp", "rho", "V_rated_ms"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = rotor_diameter(a["P_rated_W"], a["Cp"], a["rho"], a["V_rated_ms"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_rotor_speed
# ---------------------------------------------------------------------------

_rotor_speed_spec = ToolSpec(
    name="wt_rotor_speed",
    description=(
        "Compute rotor speed (RPM and rad/s) from tip-speed ratio and diameter.\n"
        "\n"
        "TSR = (blade tip speed) / (wind speed) = (ω·R) / V\n"
        "→ ω = TSR·V / R   [rad/s]\n"
        "→ n = ω·60 / (2π)  [RPM]\n"
        "\n"
        "Typical TSR values: 6–10 for 3-blade HAWT, 1–3 for Savonius.\n"
        "Tip speed > 80 m/s is flagged (noise/structural limit).\n"
        "\n"
        "Returns omega_rad_s, rpm, tip_speed_ms.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_ms": {
                "type": "number",
                "description": "Wind speed at hub height (m/s). Must be > 0.",
            },
            "tsr": {
                "type": "number",
                "description": "Tip-speed ratio (dimensionless). Typically 6–10.",
            },
            "diameter_m": {
                "type": "number",
                "description": "Rotor diameter (m). Must be > 0.",
            },
        },
        "required": ["V_ms", "tsr", "diameter_m"],
    },
)


@register(_rotor_speed_spec, write=False)
async def run_wt_rotor_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_ms", "tsr", "diameter_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = rotor_speed(a["V_ms"], a["tsr"], a["diameter_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_gearbox_ratio
# ---------------------------------------------------------------------------

_gearbox_ratio_spec = ToolSpec(
    name="wt_gearbox_ratio",
    description=(
        "Compute required gearbox step-up ratio from rotor to generator speed.\n"
        "\n"
        "ratio = generator_rpm / rotor_rpm  (rounded up to integer).\n"
        "\n"
        "Common generator speeds: 1500 RPM (4-pole, 50 Hz), "
        "1800 RPM (4-pole, 60 Hz), 750 RPM (8-pole, 50 Hz).\n"
        "\n"
        "Returns ratio_exact, ratio_integer, generator_rpm_actual.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rotor_rpm": {
                "type": "number",
                "description": "Rotor rotational speed (RPM). Must be > 0.",
            },
            "generator_rpm": {
                "type": "number",
                "description": "Target generator rotational speed (RPM). Must be > 0.",
            },
        },
        "required": ["rotor_rpm", "generator_rpm"],
    },
)


@register(_gearbox_ratio_spec, write=False)
async def run_wt_gearbox_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rotor_rpm", "generator_rpm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = gearbox_ratio(a["rotor_rpm"], a["generator_rpm"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_thrust_force
# ---------------------------------------------------------------------------

_thrust_force_spec = ToolSpec(
    name="wt_thrust_force",
    description=(
        "Compute axial thrust force on the rotor: T = ½·ρ·A·V²·Ct.\n"
        "\n"
        "At Betz optimum (a = 1/3): Ct = 8/9 ≈ 0.889 (default).\n"
        "Typical operating range: Ct ≈ 0.7–0.9.\n"
        "\n"
        "Returns thrust_N and thrust_kN.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rho": {
                "type": "number",
                "description": "Air density (kg/m³).",
            },
            "A": {
                "type": "number",
                "description": "Rotor swept area (m²).",
            },
            "V": {
                "type": "number",
                "description": "Wind speed at hub height (m/s).",
            },
            "Ct": {
                "type": "number",
                "description": (
                    "Thrust coefficient (dimensionless, 0–1). "
                    "Default 8/9 ≈ 0.889 (Betz optimum)."
                ),
            },
        },
        "required": ["rho", "A", "V"],
    },
)


@register(_thrust_force_spec, write=False)
async def run_wt_thrust_force(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rho", "A", "V"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "Ct" in a:
        kwargs["Ct"] = a["Ct"]

    result = thrust_force(a["rho"], a["A"], a["V"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_overturning_moment
# ---------------------------------------------------------------------------

_overturning_moment_spec = ToolSpec(
    name="wt_overturning_moment",
    description=(
        "Compute tower base overturning moment: M = Thrust × hub_height.\n"
        "\n"
        "First-order estimate only.  Full design must account for tower "
        "self-weight, wind load on the tower tube, dynamic amplification, "
        "and the 3P/2P tower-shadow pulsation load.\n"
        "\n"
        "Returns moment_Nm and moment_kNm.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thrust_N": {
                "type": "number",
                "description": "Axial rotor thrust force (N). Use wt_thrust_force.",
            },
            "hub_height_m": {
                "type": "number",
                "description": "Hub centreline height above ground (m). Must be > 0.",
            },
        },
        "required": ["thrust_N", "hub_height_m"],
    },
)


@register(_overturning_moment_spec, write=False)
async def run_wt_overturning_moment(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("thrust_N", "hub_height_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = overturning_moment(a["thrust_N"], a["hub_height_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_blade_element_momentum
# ---------------------------------------------------------------------------

_blade_element_momentum_spec = ToolSpec(
    name="wt_blade_element_momentum",
    description=(
        "Run simplified Blade Element Momentum (BEM) analysis.\n"
        "\n"
        "Iterates axial (a) and tangential (a′) induction factors per annulus "
        "and integrates to give rotor Cp and Ct.\n"
        "\n"
        "This is a first-order uniform-chord simplified BEM (Glauert 1935); "
        "no tip-loss correction, no Glauert correction for a > 0.4.  Use as "
        "a preliminary design tool only.\n"
        "\n"
        "Returns Cp, Ct, and per-annulus details.\n"
        "Cp > Betz limit is flagged as a numerical issue.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tsr": {
                "type": "number",
                "description": "Design tip-speed ratio. Typical 6–10 for 3-blade HAWT.",
            },
            "n_blades": {
                "type": "integer",
                "description": "Number of blades (default 3).",
            },
            "chord_r_ratio": {
                "type": "number",
                "description": "Uniform chord-to-radius ratio c/R (default 0.06).",
            },
            "n_annuli": {
                "type": "integer",
                "description": "Number of BEM annuli (default 20).",
            },
        },
        "required": ["tsr"],
    },
)


@register(_blade_element_momentum_spec, write=False)
async def run_wt_blade_element_momentum(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("tsr") is None:
        return json.dumps({"ok": False, "reason": "tsr is required"})

    kwargs: dict = {}
    for key in ("n_blades", "chord_r_ratio", "n_annuli"):
        if key in a:
            kwargs[key] = a[key]

    result = blade_element_momentum(a["tsr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_power_curve
# ---------------------------------------------------------------------------

_power_curve_spec = ToolSpec(
    name="wt_power_curve",
    description=(
        "Compute turbine power output at a given wind speed.\n"
        "\n"
        "Regions:\n"
        "  V < V_cutin              → P = 0 (parked)\n"
        "  V_cutin ≤ V < V_rated   → P = P_rated × (V³ − V_cutin³) / (V_rated³ − V_cutin³)\n"
        "  V_rated ≤ V ≤ V_cutout  → P = P_rated (pitch-regulated)\n"
        "  V > V_cutout             → P = 0 (furled)\n"
        "\n"
        "Returns power_W, power_kW, region, capacity_factor_instant.\n"
        "Warnings issued for below-cut-in and above-cut-out.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_ms": {
                "type": "number",
                "description": "Wind speed at hub height (m/s).",
            },
            "V_cutin": {
                "type": "number",
                "description": "Cut-in wind speed (m/s). Typically 3–4 m/s.",
            },
            "V_rated": {
                "type": "number",
                "description": "Rated wind speed (m/s). Typically 11–15 m/s.",
            },
            "V_cutout": {
                "type": "number",
                "description": "Cut-out wind speed (m/s). Typically 20–25 m/s.",
            },
            "P_rated_W": {
                "type": "number",
                "description": "Rated electrical power (W). Must be > 0.",
            },
        },
        "required": ["V_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"],
    },
)


@register(_power_curve_spec, write=False)
async def run_wt_power_curve(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = power_curve(
        a["V_ms"], a["V_cutin"], a["V_rated"], a["V_cutout"], a["P_rated_W"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_weibull_aep
# ---------------------------------------------------------------------------

_weibull_aep_spec = ToolSpec(
    name="wt_weibull_aep",
    description=(
        "Annual energy production (AEP) from Weibull wind-speed distribution.\n"
        "\n"
        "AEP = T × ∫ P(v)·f_Weibull(v) dv\n"
        "where f(v) = (k/c)·(v/c)^(k−1)·exp(−(v/c)^k).\n"
        "\n"
        "Capacity factor < 0.20 is flagged as a low-wind warning.\n"
        "\n"
        "Returns aep_kWh, aep_MWh, capacity_factor, weibull_mean_ms.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "k": {
                "type": "number",
                "description": (
                    "Weibull shape parameter (dimensionless). "
                    "k ≈ 1.5–3 for wind; k = 2 → Rayleigh distribution."
                ),
            },
            "c_ms": {
                "type": "number",
                "description": (
                    "Weibull scale parameter (m/s). "
                    "Mean wind speed ≈ c·Γ(1 + 1/k)."
                ),
            },
            "V_cutin": {
                "type": "number",
                "description": "Cut-in wind speed (m/s).",
            },
            "V_rated": {
                "type": "number",
                "description": "Rated wind speed (m/s).",
            },
            "V_cutout": {
                "type": "number",
                "description": "Cut-out wind speed (m/s).",
            },
            "P_rated_W": {
                "type": "number",
                "description": "Rated electrical power (W).",
            },
            "hours_per_year": {
                "type": "number",
                "description": "Hours per year (default 8760).",
            },
        },
        "required": ["k", "c_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"],
    },
)


@register(_weibull_aep_spec, write=False)
async def run_wt_weibull_aep(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("k", "c_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    pc_dict = {
        "V_cutin": a["V_cutin"],
        "V_rated": a["V_rated"],
        "V_cutout": a["V_cutout"],
        "P_rated_W": a["P_rated_W"],
    }
    kwargs: dict = {}
    if "hours_per_year" in a:
        kwargs["hours_per_year"] = a["hours_per_year"]

    result = weibull_aep(a["k"], a["c_ms"], pc_dict, **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_rayleigh_aep
# ---------------------------------------------------------------------------

_rayleigh_aep_spec = ToolSpec(
    name="wt_rayleigh_aep",
    description=(
        "Annual energy production using Rayleigh wind distribution.\n"
        "\n"
        "Rayleigh is Weibull with k = 2.  Scale c = 2·v_mean / √π.\n"
        "Simpler than Weibull — requires only the mean wind speed.\n"
        "\n"
        "Returns aep_kWh, aep_MWh, capacity_factor, rayleigh_c_ms.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_mean_ms": {
                "type": "number",
                "description": "Mean wind speed at hub height (m/s). Must be > 0.",
            },
            "V_cutin": {
                "type": "number",
                "description": "Cut-in wind speed (m/s).",
            },
            "V_rated": {
                "type": "number",
                "description": "Rated wind speed (m/s).",
            },
            "V_cutout": {
                "type": "number",
                "description": "Cut-out wind speed (m/s).",
            },
            "P_rated_W": {
                "type": "number",
                "description": "Rated electrical power (W).",
            },
        },
        "required": ["v_mean_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"],
    },
)


@register(_rayleigh_aep_spec, write=False)
async def run_wt_rayleigh_aep(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("v_mean_ms", "V_cutin", "V_rated", "V_cutout", "P_rated_W"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    pc_dict = {
        "V_cutin": a["V_cutin"],
        "V_rated": a["V_rated"],
        "V_cutout": a["V_cutout"],
        "P_rated_W": a["P_rated_W"],
    }
    result = rayleigh_aep(a["v_mean_ms"], pc_dict)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_capacity_factor
# ---------------------------------------------------------------------------

_capacity_factor_spec = ToolSpec(
    name="wt_capacity_factor",
    description=(
        "Compute capacity factor from annual energy production and rated power.\n"
        "\n"
        "CF = AEP / (P_rated × 8760 h)  [dimensionless, 0–1]\n"
        "\n"
        "Typical: onshore 0.25–0.40, offshore 0.35–0.55.\n"
        "CF < 0.20 flags a low-wind or oversized-turbine warning.\n"
        "\n"
        "Returns capacity_factor, capacity_factor_percent.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "aep_kWh": {
                "type": "number",
                "description": "Annual energy production (kWh). Must be >= 0.",
            },
            "P_rated_W": {
                "type": "number",
                "description": "Rated turbine power (W). Must be > 0.",
            },
            "hours_per_year": {
                "type": "number",
                "description": "Hours per year (default 8760).",
            },
        },
        "required": ["aep_kWh", "P_rated_W"],
    },
)


@register(_capacity_factor_spec, write=False)
async def run_wt_capacity_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("aep_kWh", "P_rated_W"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "hours_per_year" in a:
        kwargs["hours_per_year"] = a["hours_per_year"]

    result = capacity_factor(a["aep_kWh"], a["P_rated_W"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_jensen_wake
# ---------------------------------------------------------------------------

_jensen_wake_spec = ToolSpec(
    name="wt_jensen_wake",
    description=(
        "Jensen (1983) single-wake velocity deficit model.\n"
        "\n"
        "u/u0 = 1 − (1 − √(1 − Ct)) × (D / (D + 2·k_w·x))²\n"
        "\n"
        "Typical wake decay constants k_w:\n"
        "  onshore  : 0.04–0.06\n"
        "  offshore : 0.02–0.04\n"
        "\n"
        "Returns u_wake_ms, deficit_fraction, deficit_percent, power_ratio (u/u0)³.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "u0_ms": {
                "type": "number",
                "description": "Free-stream wind speed upstream (m/s). Must be > 0.",
            },
            "Ct": {
                "type": "number",
                "description": "Thrust coefficient of the upstream turbine (0–1).",
            },
            "x_m": {
                "type": "number",
                "description": "Downstream distance from rotor plane (m). Must be >= 0.",
            },
            "D_m": {
                "type": "number",
                "description": "Rotor diameter (m). Must be > 0.",
            },
            "k_w": {
                "type": "number",
                "description": "Wake decay constant (default 0.04 onshore).",
            },
        },
        "required": ["u0_ms", "Ct", "x_m", "D_m"],
    },
)


@register(_jensen_wake_spec, write=False)
async def run_wt_jensen_wake(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("u0_ms", "Ct", "x_m", "D_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "k_w" in a:
        kwargs["k_w"] = a["k_w"]

    result = jensen_wake(a["u0_ms"], a["Ct"], a["x_m"], a["D_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wt_sound_pressure
# ---------------------------------------------------------------------------

_sound_pressure_spec = ToolSpec(
    name="wt_sound_pressure",
    description=(
        "Compute sound pressure level (SPL) at a distance from a turbine.\n"
        "\n"
        "SPL = Lw − 10·log10(2π·r²)  [dB(A)]\n"
        "(hemispherical propagation over reflecting ground, ISO 9613-2 simplified)\n"
        "\n"
        "Note: full noise assessment requires octave-band calculations per "
        "IEC 61400-11.  Tower-shadow also generates infrasound at blade-passage "
        "frequency (3P for 3-bladed rotors) — typically < 20 Hz.\n"
        "\n"
        "Returns spl_dBA.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Lw_dB": {
                "type": "number",
                "description": (
                    "Turbine A-weighted sound power level (dB(A)). "
                    "Typical 95–110 dB(A) for MW-class turbines."
                ),
            },
            "distance_m": {
                "type": "number",
                "description": (
                    "Horizontal distance from turbine base to observer (m). "
                    "Must be > 0.  Model unreliable below 50 m."
                ),
            },
        },
        "required": ["Lw_dB", "distance_m"],
    },
)


@register(_sound_pressure_spec, write=False)
async def run_wt_sound_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Lw_dB", "distance_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = sound_pressure_distance(a["Lw_dB"], a["distance_m"])
    return ok_payload(result)
