"""
kerf_cad_core.aero.tools — LLM tool wrappers for applied aerodynamics.

Registers ten tools with the Kerf tool registry:

  aero_atmosphere         — ISA standard atmosphere (T, p, ρ, a vs altitude)
  aero_dynamic_pressure   — dynamic pressure q = ½ρV²
  aero_mach               — Mach number + transonic flag
  aero_thin_airfoil       — thin-airfoil Cl, Cm_c/4
  aero_finite_wing        — finite-wing CL, lift-curve slope
  aero_drag_buildup       — total CD = CD0 + induced; L/D; best-glide CL
  aero_level_flight       — required thrust, power, stall speed
  aero_climb_rate         — rate of climb from excess power
  aero_propeller          — actuator-disc thrust + ideal efficiency
  aero_breguet            — Breguet range and endurance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Anderson, J.D. — Introduction to Flight, 8th ed.
Anderson, J.D. — Fundamentals of Aerodynamics, 6th ed.
ICAO Doc 7488  — Manual of the ICAO Standard Atmosphere, 3rd ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.aero.flow import (
    isa_atmosphere,
    dynamic_pressure,
    mach_number,
    reynolds_number,
    prandtl_glauert_factor,
    thin_airfoil_cl,
    thin_airfoil_cm,
    finite_wing_lift_slope,
    finite_wing_cl,
    induced_drag_coefficient,
    total_drag_coefficient,
    ld_ratio,
    best_glide_cl,
    level_flight_thrust,
    level_flight_power,
    stall_speed,
    climb_rate,
    actuator_disc_thrust,
    propeller_ideal_efficiency,
    breguet_range,
    breguet_endurance,
)


# ---------------------------------------------------------------------------
# Tool: aero_atmosphere
# ---------------------------------------------------------------------------

_aero_atmosphere_spec = ToolSpec(
    name="aero_atmosphere",
    description=(
        "Compute ICAO Standard Atmosphere properties at a given altitude.\n"
        "\n"
        "Returns temperature T (K), pressure p (Pa), air density ρ (kg/m³), "
        "and speed of sound a (m/s).\n"
        "\n"
        "Covers troposphere (0–11 000 m, lapse rate −6.5 K/km) and "
        "isothermal stratosphere (11 000–20 000 m, T = 216.65 K).\n"
        "\n"
        "Errors: {ok:false, reason} for out-of-range or invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "altitude_m": {
                "type": "number",
                "description": (
                    "Geopotential altitude (m).  Range: 0 – 20 000 m."
                ),
            },
        },
        "required": ["altitude_m"],
    },
)


@register(_aero_atmosphere_spec, write=False)
async def run_aero_atmosphere(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("altitude_m") is None:
        return json.dumps({"ok": False, "reason": "altitude_m is required"})
    result = isa_atmosphere(a["altitude_m"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: aero_dynamic_pressure
# ---------------------------------------------------------------------------

_aero_dyn_q_spec = ToolSpec(
    name="aero_dynamic_pressure",
    description=(
        "Compute dynamic pressure q = ½ ρ V²  (Pa).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rho": {
                "type": "number",
                "description": "Air density (kg/m³). Must be > 0.",
            },
            "V": {
                "type": "number",
                "description": "Airspeed (m/s). Must be >= 0.",
            },
        },
        "required": ["rho", "V"],
    },
)


@register(_aero_dyn_q_spec, write=False)
async def run_aero_dynamic_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("rho", "V"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = dynamic_pressure(a["rho"], a["V"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: aero_mach
# ---------------------------------------------------------------------------

_aero_mach_spec = ToolSpec(
    name="aero_mach",
    description=(
        "Compute Mach number M = V / a and Prandtl-Glauert compressibility "
        "correction factor β = √(1 − M²).\n"
        "\n"
        "Issues a transonic flag when M > 0.7 (PG correction degrades).\n"
        "\n"
        "Tip: use aero_atmosphere to get the local speed of sound 'a' at altitude.\n"
        "\n"
        "Errors: {ok:false, reason} for M >= 1 or invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V": {
                "type": "number",
                "description": "Airspeed (m/s). Must be >= 0.",
            },
            "a": {
                "type": "number",
                "description": (
                    "Speed of sound (m/s). Must be > 0. "
                    "Use aero_atmosphere to get local a."
                ),
            },
        },
        "required": ["V", "a"],
    },
)


@register(_aero_mach_spec, write=False)
async def run_aero_mach(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("V", "a"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    M_res = mach_number(a["V"], a["a"])
    if not M_res["ok"]:
        return json.dumps(M_res)
    # Also compute PG factor if subsonic
    M_val = M_res["M"]
    if M_val < 1.0:
        pg_res = prandtl_glauert_factor(M_val)
        if pg_res["ok"]:
            M_res["beta"] = pg_res["beta"]
    return ok_payload(M_res)


# ---------------------------------------------------------------------------
# Tool: aero_thin_airfoil
# ---------------------------------------------------------------------------

_aero_thin_airfoil_spec = ToolSpec(
    name="aero_thin_airfoil",
    description=(
        "Thin-airfoil theory: section lift coefficient and quarter-chord "
        "pitching moment coefficient.\n"
        "\n"
        "  Cl      = 2π (α − α₀)          [dCl/dα = 2π rad⁻¹]\n"
        "  Cm_c/4  = −(π/2)(α − α₀)       [about aerodynamic centre]\n"
        "\n"
        "A stall warning is issued when |Cl| > 1.4.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alpha_deg": {
                "type": "number",
                "description": "Angle of attack (degrees).  Converted to radians internally.",
            },
            "alpha0_deg": {
                "type": "number",
                "description": (
                    "Zero-lift angle of attack (degrees).  "
                    "0 for symmetric airfoils; typically negative for cambered.  "
                    "Default 0."
                ),
            },
        },
        "required": ["alpha_deg"],
    },
)


@register(_aero_thin_airfoil_spec, write=False)
async def run_aero_thin_airfoil(ctx: ProjectCtx, args: bytes) -> str:
    import math as _math
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("alpha_deg") is None:
        return json.dumps({"ok": False, "reason": "alpha_deg is required"})
    try:
        alpha_rad = _math.radians(float(a["alpha_deg"]))
        alpha0_rad = _math.radians(float(a.get("alpha0_deg", 0.0)))
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"invalid angle: {exc}"})
    cl_res = thin_airfoil_cl(alpha_rad, alpha0_rad)
    if not cl_res["ok"]:
        return json.dumps(cl_res)
    cm_res = thin_airfoil_cm(alpha_rad, alpha0_rad)
    if not cm_res["ok"]:
        return json.dumps(cm_res)
    result = {
        "ok": True,
        "Cl": cl_res["Cl"],
        "Cm_c4": cm_res["Cm_c4"],
        "alpha_deg": a["alpha_deg"],
        "alpha0_deg": a.get("alpha0_deg", 0.0),
        "stall_warning": cl_res["stall_warning"],
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: aero_finite_wing
# ---------------------------------------------------------------------------

_aero_finite_wing_spec = ToolSpec(
    name="aero_finite_wing",
    description=(
        "Prandtl lifting-line finite-wing analysis.\n"
        "\n"
        "Computes:\n"
        "  a_wing  — finite-wing lift-curve slope (rad⁻¹)\n"
        "              a = a₀ / (1 + a₀/(π AR e))\n"
        "  CL      — wing lift coefficient\n"
        "  CDi     — induced drag coefficient  CL²/(π AR e)\n"
        "\n"
        "A stall warning is issued when |CL| > 1.6.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alpha_deg": {
                "type": "number",
                "description": "Angle of attack (degrees).",
            },
            "alpha0_deg": {
                "type": "number",
                "description": "Zero-lift angle of attack (degrees).  Default 0.",
            },
            "AR": {
                "type": "number",
                "description": "Wing aspect ratio b²/S.  Must be > 0.",
            },
            "e": {
                "type": "number",
                "description": (
                    "Oswald span efficiency factor (0 < e ≤ 1).  "
                    "Typical values: 0.75–0.95.  Default 0.85."
                ),
            },
            "a0": {
                "type": "number",
                "description": (
                    "Section lift-curve slope (rad⁻¹).  "
                    "Default 2π ≈ 6.283 (thin-airfoil theory)."
                ),
            },
        },
        "required": ["alpha_deg", "AR"],
    },
)


@register(_aero_finite_wing_spec, write=False)
async def run_aero_finite_wing(ctx: ProjectCtx, args: bytes) -> str:
    import math as _math
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("alpha_deg") is None:
        return json.dumps({"ok": False, "reason": "alpha_deg is required"})
    if a.get("AR") is None:
        return json.dumps({"ok": False, "reason": "AR is required"})
    try:
        alpha_rad = _math.radians(float(a["alpha_deg"]))
        alpha0_rad = _math.radians(float(a.get("alpha0_deg", 0.0)))
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"invalid angle: {exc}"})
    kwargs: dict = {}
    if "e" in a:
        kwargs["e_planform"] = a["e"]
    else:
        kwargs["e_planform"] = 0.85
    if "a0" in a:
        kwargs["a0"] = a["a0"]
    fw_res = finite_wing_cl(
        alpha_rad=alpha_rad,
        alpha0_rad=alpha0_rad,
        AR=a["AR"],
        **kwargs,
    )
    if not fw_res["ok"]:
        return json.dumps(fw_res)
    cdi_res = induced_drag_coefficient(
        CL=fw_res["CL"],
        AR=a["AR"],
        e=kwargs["e_planform"],
    )
    if not cdi_res["ok"]:
        return json.dumps(cdi_res)
    result = {
        "ok": True,
        "CL": fw_res["CL"],
        "a_wing_rad_inv": fw_res["a_rad_inv"],
        "CDi": cdi_res["CDi"],
        "AR": fw_res["AR"],
        "e": fw_res["e_planform"],
        "alpha_deg": a["alpha_deg"],
        "alpha0_deg": a.get("alpha0_deg", 0.0),
        "stall_warning": fw_res["stall_warning"],
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: aero_drag_buildup
# ---------------------------------------------------------------------------

_aero_drag_buildup_spec = ToolSpec(
    name="aero_drag_buildup",
    description=(
        "Total drag buildup: parasite + induced; L/D; best-glide condition.\n"
        "\n"
        "  CD      = CD0 + CL² / (π AR e)\n"
        "  L/D     = CL / CD\n"
        "  CL_best = √(π AR e CD0)   (CL for maximum L/D)\n"
        "  (L/D)_max = CL_best / (2 CD0)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CD0": {
                "type": "number",
                "description": "Zero-lift (parasite) drag coefficient.  Must be >= 0.",
            },
            "CL": {
                "type": "number",
                "description": "Lift coefficient at the flight condition.",
            },
            "AR": {
                "type": "number",
                "description": "Wing aspect ratio.  Must be > 0.",
            },
            "e": {
                "type": "number",
                "description": (
                    "Oswald span efficiency factor (0 < e ≤ 1).  Default 0.85."
                ),
            },
        },
        "required": ["CD0", "CL", "AR"],
    },
)


@register(_aero_drag_buildup_spec, write=False)
async def run_aero_drag_buildup(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("CD0", "CL", "AR"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    e = a.get("e", 0.85)
    td_res = total_drag_coefficient(CD0=a["CD0"], CL=a["CL"], AR=a["AR"], e=e)
    if not td_res["ok"]:
        return json.dumps(td_res)
    ld_res = ld_ratio(CL=a["CL"], CD=td_res["CD"])
    if not ld_res["ok"]:
        return json.dumps(ld_res)
    bg_res = best_glide_cl(CD0=a["CD0"], AR=a["AR"], e=e)
    if not bg_res["ok"]:
        return json.dumps(bg_res)
    result = {
        "ok": True,
        "CD": td_res["CD"],
        "CD0": td_res["CD0"],
        "CDi": td_res["CDi"],
        "LD": ld_res["LD"],
        "CL_best_glide": bg_res["CL_best"],
        "LD_max": bg_res["LD_max"],
        "CL": td_res["CL"],
        "AR": float(a["AR"]),
        "e": float(e),
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: aero_level_flight
# ---------------------------------------------------------------------------

_aero_level_flight_spec = ToolSpec(
    name="aero_level_flight",
    description=(
        "Level-flight performance: required thrust, shaft power, and stall speed.\n"
        "\n"
        "  T_req   = W × CD/CL           (N)\n"
        "  P_req   = T_req × V            (W)\n"
        "  V_stall = √(2W / (ρ S CLmax)) (m/s)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W": {
                "type": "number",
                "description": "Aircraft weight (N).  Must be > 0.",
            },
            "CL": {
                "type": "number",
                "description": "Lift coefficient at flight condition.  Must be > 0.",
            },
            "CD": {
                "type": "number",
                "description": "Drag coefficient at flight condition.  Must be > 0.",
            },
            "V": {
                "type": "number",
                "description": "True airspeed (m/s).  Must be > 0.",
            },
            "rho": {
                "type": "number",
                "description": (
                    "Air density (kg/m³).  Required for stall speed.  Must be > 0."
                ),
            },
            "S": {
                "type": "number",
                "description": (
                    "Wing reference area (m²).  Required for stall speed.  Must be > 0."
                ),
            },
            "CLmax": {
                "type": "number",
                "description": (
                    "Maximum lift coefficient.  Required for stall speed.  Must be > 0."
                ),
            },
        },
        "required": ["W", "CL", "CD", "V"],
    },
)


@register(_aero_level_flight_spec, write=False)
async def run_aero_level_flight(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("W", "CL", "CD", "V"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    T_res = level_flight_thrust(W=a["W"], CL=a["CL"], CD=a["CD"])
    if not T_res["ok"]:
        return json.dumps(T_res)
    P_res = level_flight_power(T=T_res["T_req_N"], V=a["V"])
    if not P_res["ok"]:
        return json.dumps(P_res)
    result: dict = {
        "ok": True,
        "T_req_N": T_res["T_req_N"],
        "P_req_W": P_res["P_req_W"],
        "LD": T_res["LD"],
        "W": float(a["W"]),
        "CL": float(a["CL"]),
        "CD": float(a["CD"]),
        "V": float(a["V"]),
    }
    if all(k in a for k in ("rho", "S", "CLmax")):
        vs_res = stall_speed(
            W=a["W"], rho=a["rho"], S=a["S"], CLmax=a["CLmax"]
        )
        if vs_res["ok"]:
            result["V_stall_m_s"] = vs_res["V_stall_m_s"]
        else:
            result["V_stall_error"] = vs_res.get("reason")
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: aero_climb_rate
# ---------------------------------------------------------------------------

_aero_climb_rate_spec = ToolSpec(
    name="aero_climb_rate",
    description=(
        "Rate of climb from excess-power method.\n"
        "\n"
        "  RC = (T − D) × V / W   (m/s)\n"
        "\n"
        "A negative-climb warning is issued when T ≤ D.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T": {
                "type": "number",
                "description": "Available thrust (N).  Must be >= 0.",
            },
            "D": {
                "type": "number",
                "description": "Drag at climb airspeed (N).  Must be >= 0.",
            },
            "V": {
                "type": "number",
                "description": "True airspeed (m/s).  Must be > 0.",
            },
            "W": {
                "type": "number",
                "description": "Aircraft weight (N).  Must be > 0.",
            },
        },
        "required": ["T", "D", "V", "W"],
    },
)


@register(_aero_climb_rate_spec, write=False)
async def run_aero_climb_rate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("T", "D", "V", "W"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = climb_rate(T=a["T"], D=a["D"], V=a["V"], W=a["W"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: aero_propeller
# ---------------------------------------------------------------------------

_aero_propeller_spec = ToolSpec(
    name="aero_propeller",
    description=(
        "Ideal propeller (actuator-disc) thrust and efficiency.\n"
        "\n"
        "Actuator-disc (Froude momentum theory):\n"
        "  T      = 2 ρ A (V_inf + w) w   (N)\n"
        "  P_in   = T × (V_inf + w)        (W)\n"
        "  η      = V_inf / (V_inf + w)    (dimensionless)\n"
        "\n"
        "Disc area: A = π r² for propeller radius r.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rho": {
                "type": "number",
                "description": "Air density (kg/m³).  Must be > 0.",
            },
            "A_disc": {
                "type": "number",
                "description": (
                    "Propeller disc area (m²) = π r².  Must be > 0."
                ),
            },
            "V_inf": {
                "type": "number",
                "description": "Freestream velocity (m/s).  Must be >= 0.",
            },
            "w": {
                "type": "number",
                "description": "Induced velocity at disc (m/s).  Must be > 0.",
            },
        },
        "required": ["rho", "A_disc", "V_inf", "w"],
    },
)


@register(_aero_propeller_spec, write=False)
async def run_aero_propeller(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("rho", "A_disc", "V_inf", "w"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    T_res = actuator_disc_thrust(
        rho=a["rho"], A_disc=a["A_disc"],
        V_inf=a["V_inf"], w=a["w"],
    )
    if not T_res["ok"]:
        return json.dumps(T_res)
    eta_res = propeller_ideal_efficiency(V_inf=a["V_inf"], w=a["w"])
    if not eta_res["ok"]:
        return json.dumps(eta_res)
    result = {
        "ok": True,
        "T_N": T_res["T_N"],
        "P_in_W": T_res["P_in_W"],
        "eta_ideal": eta_res["eta_ideal"],
        "rho": T_res["rho"],
        "A_disc": T_res["A_disc"],
        "V_inf": T_res["V_inf"],
        "w": T_res["w"],
        "static_thrust_note": eta_res["static_thrust_note"],
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: aero_breguet
# ---------------------------------------------------------------------------

_aero_breguet_spec = ToolSpec(
    name="aero_breguet",
    description=(
        "Breguet range and endurance equations for propeller-driven aircraft.\n"
        "\n"
        "Range:     R = (η_p / c) × (L/D) × ln(W_i / W_f)          (m)\n"
        "Endurance: E = (η_p / c) × (CL/CD) × (1/g) × ln(W_i / W_f) (s)\n"
        "\n"
        "c_specific — specific fuel consumption (kg/(N·s)).\n"
        "  Typical piston: ~8e-8 kg/(N·s); turboprop: ~5e-8 kg/(N·s).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "eta_p": {
                "type": "number",
                "description": "Propeller efficiency (0 < η_p ≤ 1).",
            },
            "c_specific": {
                "type": "number",
                "description": "Specific fuel consumption (kg/(N·s)).  Must be > 0.",
            },
            "CL": {
                "type": "number",
                "description": "Lift coefficient at cruise.  Must be > 0.",
            },
            "CD": {
                "type": "number",
                "description": "Drag coefficient at cruise.  Must be > 0.",
            },
            "W_initial": {
                "type": "number",
                "description": "Take-off weight (N).  Must be > W_final.",
            },
            "W_final": {
                "type": "number",
                "description": "Landing weight (N).  Must be > 0.",
            },
        },
        "required": ["eta_p", "c_specific", "CL", "CD", "W_initial", "W_final"],
    },
)


@register(_aero_breguet_spec, write=False)
async def run_aero_breguet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("eta_p", "c_specific", "CL", "CD", "W_initial", "W_final"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    CL_f = float(a["CL"])
    CD_f = float(a["CD"])
    if CD_f <= 0.0:
        return json.dumps({"ok": False, "reason": "CD must be > 0"})
    LD = CL_f / CD_f
    R_res = breguet_range(
        eta_p=a["eta_p"],
        c_specific=a["c_specific"],
        LD=LD,
        W_initial=a["W_initial"],
        W_final=a["W_final"],
    )
    if not R_res["ok"]:
        return json.dumps(R_res)
    E_res = breguet_endurance(
        eta_p=a["eta_p"],
        c_specific=a["c_specific"],
        CL=a["CL"],
        CD=a["CD"],
        W_initial=a["W_initial"],
        W_final=a["W_final"],
    )
    if not E_res["ok"]:
        return json.dumps(E_res)
    result = {
        "ok": True,
        "range_m": R_res["range_m"],
        "range_km": R_res["range_km"],
        "endurance_s": E_res["endurance_s"],
        "endurance_hr": E_res["endurance_hr"],
        "LD": LD,
        "eta_p": float(a["eta_p"]),
        "c_specific": float(a["c_specific"]),
        "CL": CL_f,
        "CD": CD_f,
        "W_initial": float(a["W_initial"]),
        "W_final": float(a["W_final"]),
    }
    return ok_payload(result)
