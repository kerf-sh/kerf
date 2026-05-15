"""
kerf_cad_core.pneumatics.tools — LLM tool wrappers for pneumatic circuit sizing.

Registers eight tools with the Kerf tool registry:

  pneu_cylinder         — cylinder theoretical & effective force with load-ratio
  pneu_air_consumption  — free-air consumption per cycle (Nl/min)
  pneu_valve_iso6358    — valve flow per ISO 6358 C & b (choked/subsonic)
  pneu_valve_cv         — valve flow via US Cv coefficient (compressible gas)
  pneu_receiver_sizing  — receiver hold-up time & minimum volume
  pneu_blowdown_time    — time to exhaust receiver through ISO 6358 orifice
  pneu_charge_time      — time to charge receiver from compressor
  pneu_frl_drop         — FRL filter-regulator-lubricator pressure drop

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ISO 6358-1:2013 — Pneumatic fluid power; Flow-rate characteristics
SMC Technical Data — Pneumatic Actuator Selection Guide
Parker Hannifin Pneumatics — P3E Actuator Catalogue

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.pneumatics.circuit import (
    cylinder,
    air_consumption,
    valve_flow_iso6358,
    valve_flow_cv,
    receiver_sizing,
    blowdown_time,
    charge_time,
    frl_pressure_drop,
)


# ---------------------------------------------------------------------------
# Tool: pneu_cylinder
# ---------------------------------------------------------------------------

_pneu_cylinder_spec = ToolSpec(
    name="pneu_cylinder",
    description=(
        "Compute pneumatic cylinder theoretical and effective extend/retract forces.\n"
        "\n"
        "Theoretical force (gauge pressure × area):\n"
        "  F_extend_th  = (P_supply − P_atm) × A_bore\n"
        "  F_retract_th = (P_supply − P_atm) × A_rod\n"
        "\n"
        "Effective force (accounting for back-pressure and friction):\n"
        "  F_extend_eff  = P_supply × A_bore − P_back × A_rod\n"
        "                  − friction_ratio × F_extend_th\n"
        "\n"
        "Load ratio = load_N / F_extend_eff; should be <= 0.70 for reliable "
        "operation. Warns if load ratio > 0.70 (UNDERSIZED) or if effective "
        "force is negative (cylinder will not move).\n"
        "\n"
        "All pressures are ABSOLUTE (Pa). Supply must be > 101325 Pa (1 atm).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bore_m": {
                "type": "number",
                "description": "Cylinder bore diameter (m). Must be > 0.",
            },
            "rod_m": {
                "type": "number",
                "description": "Piston rod diameter (m). Must be > 0 and < bore_m.",
            },
            "supply_pressure_Pa": {
                "type": "number",
                "description": (
                    "Supply pressure ABSOLUTE (Pa). Must be > 101325 (1 atm). "
                    "Example: 7 bar abs = 700000 Pa."
                ),
            },
            "load_N": {
                "type": "number",
                "description": "Applied load on extend stroke (N). Default 0.",
            },
            "friction_ratio": {
                "type": "number",
                "description": (
                    "Friction as fraction of theoretical force (0, 1]. "
                    "Default 0.05 (5%). Typical range 0.03–0.10."
                ),
            },
            "back_pressure_Pa": {
                "type": "number",
                "description": (
                    "Exhaust-side back pressure ABSOLUTE (Pa). "
                    "Default 101325 (open exhaust to atmosphere)."
                ),
            },
        },
        "required": ["bore_m", "rod_m", "supply_pressure_Pa"],
    },
)


@register(_pneu_cylinder_spec, write=False)
async def run_pneu_cylinder(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("bore_m", "rod_m", "supply_pressure_Pa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("load_N", "friction_ratio", "back_pressure_Pa"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = cylinder(a["bore_m"], a["rod_m"], a["supply_pressure_Pa"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_air_consumption
# ---------------------------------------------------------------------------

_pneu_air_consumption_spec = ToolSpec(
    name="pneu_air_consumption",
    description=(
        "Compute free-air consumption of a pneumatic cylinder in Nl/min.\n"
        "\n"
        "Compression ratio r = P_supply / P_atm.\n"
        "Volume per cycle (double-acting):\n"
        "  V_cycle = (A_bore + A_rod) × stroke × r  [actual m³]\n"
        "Corrected to normal conditions (P_N=101325 Pa, T_N=293.15 K):\n"
        "  V_free = V_cycle × T_N / T_K\n"
        "Free-air rate = V_free × cycles_per_min × 1000  [Nl/min]\n"
        "\n"
        "Warns if consumption > 1000 Nl/min or compression ratio > 12.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bore_m": {
                "type": "number",
                "description": "Cylinder bore (m). Must be > 0.",
            },
            "rod_m": {
                "type": "number",
                "description": "Rod diameter (m). Must be > 0 and < bore_m.",
            },
            "stroke_m": {
                "type": "number",
                "description": "Piston stroke (m). Must be > 0.",
            },
            "supply_pressure_Pa": {
                "type": "number",
                "description": "Supply pressure ABSOLUTE (Pa). Must be > P_atm.",
            },
            "cycles_per_min": {
                "type": "number",
                "description": "Complete cycles per minute. Must be > 0.",
            },
            "double_acting": {
                "type": "boolean",
                "description": (
                    "True (default) for double-acting cylinder; "
                    "False for single-acting (extend only)."
                ),
            },
            "T_K": {
                "type": "number",
                "description": "Supply air temperature (K). Default 293.15 (20 °C).",
            },
        },
        "required": ["bore_m", "rod_m", "stroke_m", "supply_pressure_Pa", "cycles_per_min"],
    },
)


@register(_pneu_air_consumption_spec, write=False)
async def run_pneu_air_consumption(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("bore_m", "rod_m", "stroke_m", "supply_pressure_Pa", "cycles_per_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "double_acting" in a:
        kwargs["double_acting"] = bool(a["double_acting"])
    if "T_K" in a:
        kwargs["T_K"] = a["T_K"]

    result = air_consumption(
        a["bore_m"], a["rod_m"], a["stroke_m"],
        a["supply_pressure_Pa"], a["cycles_per_min"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_valve_iso6358
# ---------------------------------------------------------------------------

_pneu_valve_iso6358_spec = ToolSpec(
    name="pneu_valve_iso6358",
    description=(
        "Compute volumetric flow through a pneumatic valve per ISO 6358.\n"
        "\n"
        "ISO 6358 flow model (compressible gas):\n"
        "  q_max (choked)   = C × P1 × √(T_N / T1)\n"
        "  q (subsonic)     = q_max × √(1 − ((P2/P1 − b) / (1 − b))²)\n"
        "\n"
        "Flow is CHOKED (sonic) when P2/P1 <= b. When choked, reducing P2 "
        "further does NOT increase flow — this is flagged as a warning.\n"
        "\n"
        "C is the sonic conductance (m³/(s·Pa)) from manufacturer datasheet.\n"
        "b is the critical pressure ratio (dimensionless), typically 0.2–0.5.\n"
        "\n"
        "Returns q_m3s_normal (m³/s at P_N, T_N), q_Nl_min, choked flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P1_Pa": {
                "type": "number",
                "description": "Upstream absolute pressure (Pa). Must be > 0.",
            },
            "P2_Pa": {
                "type": "number",
                "description": "Downstream absolute pressure (Pa). Must be <= P1_Pa.",
            },
            "T1_K": {
                "type": "number",
                "description": "Upstream temperature (K). Must be > 0.",
            },
            "C_m3s_Pa": {
                "type": "number",
                "description": (
                    "Sonic conductance (m³/(s·Pa)). > 0. "
                    "From manufacturer ISO 6358 datasheet."
                ),
            },
            "b": {
                "type": "number",
                "description": (
                    "Critical pressure ratio (dimensionless). In (0, 1). "
                    "Typical pneumatic valves: 0.2–0.5."
                ),
            },
        },
        "required": ["P1_Pa", "P2_Pa", "T1_K", "C_m3s_Pa", "b"],
    },
)


@register(_pneu_valve_iso6358_spec, write=False)
async def run_pneu_valve_iso6358(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P1_Pa", "P2_Pa", "T1_K", "C_m3s_Pa", "b"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = valve_flow_iso6358(
        a["P1_Pa"], a["P2_Pa"], a["T1_K"], a["C_m3s_Pa"], a["b"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_valve_cv
# ---------------------------------------------------------------------------

_pneu_valve_cv_spec = ToolSpec(
    name="pneu_valve_cv",
    description=(
        "Compute volumetric flow through a pneumatic valve using the US Cv "
        "coefficient for compressible gas.\n"
        "\n"
        "Choked flow (P2/P1 <= 0.528 for air, γ=1.4):\n"
        "  q_Nl_min = 417 × Cv × P1_bar × √(T_N / (SG × T_K))\n"
        "\n"
        "Subsonic flow (P2/P1 > 0.528):\n"
        "  q_Nl_min = 417 × Cv × √(ΔP_bar × P1_bar / (SG × T_K)) × √T_N\n"
        "\n"
        "Choked flow is flagged as a warning. If valve is near choked "
        "but not choked, a warning advises a larger Cv.\n"
        "\n"
        "Returns q_Nl_min, q_m3s_normal, q_max_Nl_min (choked), choked flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Cv": {
                "type": "number",
                "description": "US valve flow coefficient (gpm/√psi). Must be > 0.",
            },
            "P1_Pa": {
                "type": "number",
                "description": "Upstream absolute pressure (Pa). Must be > 0.",
            },
            "P2_Pa": {
                "type": "number",
                "description": "Downstream absolute pressure (Pa). Must be <= P1_Pa.",
            },
            "T_K": {
                "type": "number",
                "description": "Gas temperature at valve inlet (K). Must be > 0.",
            },
            "SG_gas": {
                "type": "number",
                "description": (
                    "Specific gravity of gas relative to air. Default 1.0 (air). "
                    "Must be > 0."
                ),
            },
        },
        "required": ["Cv", "P1_Pa", "P2_Pa", "T_K"],
    },
)


@register(_pneu_valve_cv_spec, write=False)
async def run_pneu_valve_cv(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Cv", "P1_Pa", "P2_Pa", "T_K"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "SG_gas" in a:
        kwargs["SG_gas"] = a["SG_gas"]

    result = valve_flow_cv(a["Cv"], a["P1_Pa"], a["P2_Pa"], a["T_K"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_receiver_sizing
# ---------------------------------------------------------------------------

_pneu_receiver_sizing_spec = ToolSpec(
    name="pneu_receiver_sizing",
    description=(
        "Compute receiver hold-up time and free-air storage for a pneumatic receiver.\n"
        "\n"
        "Available free-air between P_high and P_low:\n"
        "  ΔV_free = V × (P_high − P_low) / P_atm × (T_N / T_K)\n"
        "\n"
        "Hold-up time (no compressor, constant demand):\n"
        "  t_supply = ΔV_free / Q_demand_free\n"
        "\n"
        "Warns if hold-up < 5 s or pressure band < 5% of P_high.\n"
        "\n"
        "All pressures ABSOLUTE (Pa). P_low must be > P_atm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_receiver_m3": {
                "type": "number",
                "description": "Receiver volume (m³). Must be > 0.",
            },
            "P_high_Pa": {
                "type": "number",
                "description": "Upper cut-out pressure ABSOLUTE (Pa). Must be > P_low_Pa.",
            },
            "P_low_Pa": {
                "type": "number",
                "description": (
                    "Lower cut-in pressure ABSOLUTE (Pa). Must be > 101325 Pa (P_atm)."
                ),
            },
            "Q_demand_m3s_free": {
                "type": "number",
                "description": "System demand flow at normal conditions (m³/s). Must be > 0.",
            },
            "T_K": {
                "type": "number",
                "description": "Air temperature (K). Default 293.15.",
            },
        },
        "required": ["V_receiver_m3", "P_high_Pa", "P_low_Pa", "Q_demand_m3s_free"],
    },
)


@register(_pneu_receiver_sizing_spec, write=False)
async def run_pneu_receiver_sizing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_receiver_m3", "P_high_Pa", "P_low_Pa", "Q_demand_m3s_free"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_K" in a:
        kwargs["T_K"] = a["T_K"]

    result = receiver_sizing(
        a["V_receiver_m3"], a["P_high_Pa"], a["P_low_Pa"],
        a["Q_demand_m3s_free"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_blowdown_time
# ---------------------------------------------------------------------------

_pneu_blowdown_time_spec = ToolSpec(
    name="pneu_blowdown_time",
    description=(
        "Estimate time to exhaust a pneumatic receiver to atmosphere through a "
        "fixed ISO 6358 valve/orifice.\n"
        "\n"
        "Two phases per ISO 6358:\n"
        "  Phase 1 (Choked, P > P_atm/b): exponential decay\n"
        "    t_choked = V/(C·P_atm·√(T_N/T)) × ln(P_initial/P_choke_end)\n"
        "  Phase 2 (Subsonic, P <= P_atm/b): numerical integration\n"
        "\n"
        "Warns if total blowdown < 1 s (rapid depressurisation risk).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_m3": {
                "type": "number",
                "description": "Receiver/vessel volume (m³). Must be > 0.",
            },
            "P_initial_Pa": {
                "type": "number",
                "description": "Initial pressure ABSOLUTE (Pa). Must be > 101325.",
            },
            "P_final_Pa": {
                "type": "number",
                "description": (
                    "Final pressure ABSOLUTE (Pa). >= 101325 (P_atm). "
                    "Use 101325 to model full blowdown to atmosphere."
                ),
            },
            "C_m3s_Pa": {
                "type": "number",
                "description": (
                    "Sonic conductance of exhaust orifice/valve (m³/(s·Pa)). Must be > 0."
                ),
            },
            "b": {
                "type": "number",
                "description": "Critical pressure ratio (dimensionless). In (0, 1).",
            },
            "T_K": {
                "type": "number",
                "description": "Gas temperature (K). Default 293.15.",
            },
        },
        "required": ["V_m3", "P_initial_Pa", "P_final_Pa", "C_m3s_Pa", "b"],
    },
)


@register(_pneu_blowdown_time_spec, write=False)
async def run_pneu_blowdown_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_m3", "P_initial_Pa", "P_final_Pa", "C_m3s_Pa", "b"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_K" in a:
        kwargs["T_K"] = a["T_K"]

    result = blowdown_time(
        a["V_m3"], a["P_initial_Pa"], a["P_final_Pa"],
        a["C_m3s_Pa"], a["b"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_charge_time
# ---------------------------------------------------------------------------

_pneu_charge_time_spec = ToolSpec(
    name="pneu_charge_time",
    description=(
        "Estimate time to charge a pneumatic receiver from a compressor.\n"
        "\n"
        "Assumes isothermal process and constant compressor free-air delivery.\n"
        "\n"
        "  ΔV_free = V × (P_final − P_initial) / P_atm × (T_N / T_K)\n"
        "  t_charge = ΔV_free / Q_compressor_free\n"
        "\n"
        "Warns if charge time exceeds 10 minutes.\n"
        "\n"
        "All pressures ABSOLUTE (Pa).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_m3": {
                "type": "number",
                "description": "Receiver volume (m³). Must be > 0.",
            },
            "P_initial_Pa": {
                "type": "number",
                "description": "Starting pressure ABSOLUTE (Pa). >= P_atm (101325).",
            },
            "P_final_Pa": {
                "type": "number",
                "description": "Target pressure ABSOLUTE (Pa). Must be > P_initial.",
            },
            "Q_compressor_m3s_free": {
                "type": "number",
                "description": "Compressor free-air delivery (m³/s). Must be > 0.",
            },
            "T_K": {
                "type": "number",
                "description": "Air temperature (K). Default 293.15.",
            },
        },
        "required": ["V_m3", "P_initial_Pa", "P_final_Pa", "Q_compressor_m3s_free"],
    },
)


@register(_pneu_charge_time_spec, write=False)
async def run_pneu_charge_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_m3", "P_initial_Pa", "P_final_Pa", "Q_compressor_m3s_free"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_K" in a:
        kwargs["T_K"] = a["T_K"]

    result = charge_time(
        a["V_m3"], a["P_initial_Pa"], a["P_final_Pa"],
        a["Q_compressor_m3s_free"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pneu_frl_drop
# ---------------------------------------------------------------------------

_pneu_frl_drop_spec = ToolSpec(
    name="pneu_frl_drop",
    description=(
        "Compute total pressure drop across an FRL (Filter-Regulator-Lubricator) unit.\n"
        "\n"
        "  P_outlet = P_supply − (filter_dP + regulator_dP + lubricator_dP)\n"
        "\n"
        "Default component drops (10/20/10 kPa) are conservative typical values.\n"
        "Warns if FRL efficiency < 85% (outlet/supply) or if outlet <= P_atm.\n"
        "\n"
        "Supply pressure must be ABSOLUTE (Pa) and > P_atm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_free_m3s": {
                "type": "number",
                "description": "Free-air flow through FRL (m³/s). Must be > 0.",
            },
            "supply_pressure_Pa": {
                "type": "number",
                "description": "Supply pressure ABSOLUTE (Pa). Must be > 101325.",
            },
            "filter_dP_Pa": {
                "type": "number",
                "description": "Filter pressure drop (Pa). Default 10000. >= 0.",
            },
            "regulator_dP_Pa": {
                "type": "number",
                "description": "Regulator pressure drop (Pa). Default 20000. >= 0.",
            },
            "lubricator_dP_Pa": {
                "type": "number",
                "description": "Lubricator pressure drop (Pa). Default 10000. >= 0.",
            },
        },
        "required": ["Q_free_m3s", "supply_pressure_Pa"],
    },
)


@register(_pneu_frl_drop_spec, write=False)
async def run_pneu_frl_drop(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Q_free_m3s", "supply_pressure_Pa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("filter_dP_Pa", "regulator_dP_Pa", "lubricator_dP_Pa"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = frl_pressure_drop(a["Q_free_m3s"], a["supply_pressure_Pa"], **kwargs)
    return ok_payload(result)
