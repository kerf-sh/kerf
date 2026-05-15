"""
kerf_cad_core.pressvessel.tools — LLM tool wrappers for ASME BPVC VIII-1
pressure-vessel sizing.

Registers eight tools with the Kerf tool registry:

  pv_cylindrical_shell_thickness   — UG-27 cylindrical shell thickness
  pv_spherical_head_thickness      — UG-32(f) hemispherical head thickness
  pv_ellipsoidal_head_thickness    — UG-32(d) 2:1 ellipsoidal head thickness
  pv_torispherical_head_thickness  — UG-32(e) flanged-and-dished head thickness
  pv_external_pressure_check       — UG-28 external pressure / buckling check
  pv_mawp_cylindrical              — MAWP from given cylindrical shell thickness
  pv_nozzle_reinforcement          — UG-37 nozzle area-replacement check
  pv_hydrostatic_test_pressure     — UG-99(b) hydrostatic test pressure

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASME BPVC Section VIII Division 1, 2021 Edition (UG-27, UG-28, UG-32, UG-37, UG-99)

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.pressvessel.shell import (
    cylindrical_shell_thickness,
    spherical_head_thickness,
    ellipsoidal_head_thickness,
    torispherical_head_thickness,
    external_pressure_check,
    mawp_cylindrical,
    nozzle_reinforcement,
    hydrostatic_test_pressure,
)


# ---------------------------------------------------------------------------
# Tool: pv_cylindrical_shell_thickness
# ---------------------------------------------------------------------------

_cyl_shell_spec = ToolSpec(
    name="pv_cylindrical_shell_thickness",
    description=(
        "Compute the required minimum wall thickness for a cylindrical pressure-vessel "
        "shell under internal pressure per ASME BPVC VIII-1 UG-27(c).\n"
        "\n"
        "Circumferential (hoop) stress governs per UG-27(c)(1):\n"
        "    t = P·R / (S·E - 0.6·P) + c\n"
        "Longitudinal stress check UG-27(c)(2) also performed.\n"
        "\n"
        "Joint efficiency E and corrosion allowance c are parameters.\n"
        "Warnings (never raises) for thick-wall limit violations.\n"
        "Errors: {ok:false, reason} for invalid inputs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Internal design pressure (Pa, gauge). Must be >= 0.",
            },
            "R": {
                "type": "number",
                "description": "Inside radius of the shell (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": (
                    "Maximum allowable stress at design temperature (Pa). "
                    "From ASME BPVC VIII-1 Section II Part D tables. Must be > 0."
                ),
            },
            "E": {
                "type": "number",
                "description": (
                    "Joint efficiency factor (default 1.0). "
                    "1.0=full RT, 0.85=spot RT, 0.70=no RT. Must be in (0, 1]."
                ),
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m). Default 0.0. Must be >= 0.",
            },
        },
        "required": ["P", "R", "S"],
    },
)


@register(_cyl_shell_spec, write=False)
async def run_pv_cylindrical_shell_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "R", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = cylindrical_shell_thickness(a["P"], a["R"], a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_spherical_head_thickness
# ---------------------------------------------------------------------------

_sph_head_spec = ToolSpec(
    name="pv_spherical_head_thickness",
    description=(
        "Compute the required wall thickness for a hemispherical pressure-vessel "
        "head under internal pressure per ASME BPVC VIII-1 UG-32(f).\n"
        "\n"
        "    t = P·R / (2·S·E - 0.2·P) + c\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Internal design pressure (Pa, gauge). Must be >= 0.",
            },
            "R": {
                "type": "number",
                "description": "Inside radius of the spherical head (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": "Maximum allowable stress (Pa). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Joint efficiency (default 1.0). Must be in (0, 1].",
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m). Default 0.0.",
            },
        },
        "required": ["P", "R", "S"],
    },
)


@register(_sph_head_spec, write=False)
async def run_pv_spherical_head_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "R", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = spherical_head_thickness(a["P"], a["R"], a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_ellipsoidal_head_thickness
# ---------------------------------------------------------------------------

_ell_head_spec = ToolSpec(
    name="pv_ellipsoidal_head_thickness",
    description=(
        "Compute the required wall thickness for a standard 2:1 semi-ellipsoidal "
        "pressure-vessel head per ASME BPVC VIII-1 UG-32(d).\n"
        "\n"
        "Standard proportions: head depth h = D/4 (2:1 ratio).\n"
        "    t = P·D / (2·S·E - 0.2·P) + c\n"
        "\n"
        "D is the inside shell diameter (not radius).\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Internal design pressure (Pa, gauge). Must be >= 0.",
            },
            "D": {
                "type": "number",
                "description": "Inside diameter of the shell (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": "Maximum allowable stress (Pa). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Joint efficiency (default 1.0). Must be in (0, 1].",
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m). Default 0.0.",
            },
        },
        "required": ["P", "D", "S"],
    },
)


@register(_ell_head_spec, write=False)
async def run_pv_ellipsoidal_head_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "D", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = ellipsoidal_head_thickness(a["P"], a["D"], a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_torispherical_head_thickness
# ---------------------------------------------------------------------------

_tori_head_spec = ToolSpec(
    name="pv_torispherical_head_thickness",
    description=(
        "Compute the required wall thickness for a standard flanged-and-dished "
        "(torispherical) pressure-vessel head per ASME BPVC VIII-1 UG-32(e).\n"
        "\n"
        "Standard proportions: L_crown = D, r_knuckle = 0.06·D.\n"
        "    t = 0.885·P·L / (S·E - 0.1·P) + c\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Internal design pressure (Pa, gauge). Must be >= 0.",
            },
            "D": {
                "type": "number",
                "description": "Inside shell diameter (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": "Maximum allowable stress (Pa). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Joint efficiency (default 1.0). Must be in (0, 1].",
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m). Default 0.0.",
            },
            "L_crown": {
                "type": "number",
                "description": (
                    "Inside crown radius (m). Default = D (standard proportions). "
                    "Must be > 0 if provided."
                ),
            },
        },
        "required": ["P", "D", "S"],
    },
)


@register(_tori_head_spec, write=False)
async def run_pv_torispherical_head_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "D", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c", "L_crown"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = torispherical_head_thickness(a["P"], a["D"], a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_external_pressure_check
# ---------------------------------------------------------------------------

_ext_press_spec = ToolSpec(
    name="pv_external_pressure_check",
    description=(
        "Simplified UG-28 external pressure / buckling check for a cylindrical "
        "pressure-vessel shell under external pressure.\n"
        "\n"
        "Uses factor-A / factor-B approximation (elastic buckling regime):\n"
        "  A ≈ 0.125 / (L/D_o × D_o/t)\n"
        "  B = A·E/2 (capped at S_allow if provided)\n"
        "  P_allow = 4B / (3 × D_o/t)\n"
        "\n"
        "Valid for elastic regime (L/D_o >= 4). Short vessels flagged in warnings.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_ext": {
                "type": "number",
                "description": "External design pressure (Pa, gauge). Must be > 0.",
            },
            "D_o": {
                "type": "number",
                "description": "Outside diameter of the shell (m). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": (
                    "Unsupported length between stiffening rings or heads (m). Must be > 0."
                ),
            },
            "t": {
                "type": "number",
                "description": "Shell wall thickness (m). Must be > 0.",
            },
            "E_mod": {
                "type": "number",
                "description": (
                    "Young's modulus at design temperature (Pa). "
                    "Default 200e9 (carbon steel, ambient)."
                ),
            },
            "nu": {
                "type": "number",
                "description": "Poisson's ratio (default 0.3). Must be in (0, 0.5).",
            },
            "S_allow": {
                "type": "number",
                "description": (
                    "Allowable stress (Pa). If provided, factor B is capped at S_allow "
                    "(inelastic / yield-limited regime). Must be > 0 if provided."
                ),
            },
        },
        "required": ["P_ext", "D_o", "L", "t"],
    },
)


@register(_ext_press_spec, write=False)
async def run_pv_external_pressure_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P_ext", "D_o", "L", "t"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E_mod", "nu", "S_allow"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = external_pressure_check(a["P_ext"], a["D_o"], a["L"], a["t"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_mawp_cylindrical
# ---------------------------------------------------------------------------

_mawp_spec = ToolSpec(
    name="pv_mawp_cylindrical",
    description=(
        "Compute the Maximum Allowable Working Pressure (MAWP) for a cylindrical "
        "pressure-vessel shell of known thickness per ASME BPVC VIII-1 UG-27(c)(1).\n"
        "\n"
        "    MAWP = S·E·t_net / (R + 0.6·t_net)\n"
        "where t_net = t_nominal - c.\n"
        "\n"
        "Inverse of pv_cylindrical_shell_thickness.\n"
        "Returns MAWP in Pa, kPa, bar, and psi.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "t": {
                "type": "number",
                "description": "Nominal wall thickness (m). Must be > 0.",
            },
            "R": {
                "type": "number",
                "description": "Inside radius (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": "Maximum allowable stress (Pa). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Joint efficiency (default 1.0). Must be in (0, 1].",
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m). Default 0.0.",
            },
        },
        "required": ["t", "R", "S"],
    },
)


@register(_mawp_spec, write=False)
async def run_pv_mawp_cylindrical(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("t", "R", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = mawp_cylindrical(a["t"], a["R"], a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_nozzle_reinforcement
# ---------------------------------------------------------------------------

_nozzle_spec = ToolSpec(
    name="pv_nozzle_reinforcement",
    description=(
        "Check nozzle opening reinforcement per ASME BPVC VIII-1 UG-37 "
        "(area-replacement method).\n"
        "\n"
        "Required area: A_req = d × t_req × F\n"
        "Available areas:\n"
        "  A1 = excess shell area above required thickness\n"
        "  A2 = nozzle wall area within the reinforcement zone\n"
        "Pass if (A1 + A2) >= A_required.\n"
        "\n"
        "Returns required area, available areas, pass/fail, and shortfall.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Internal design pressure (Pa, gauge). Must be >= 0.",
            },
            "D_shell": {
                "type": "number",
                "description": "Inside diameter of the shell (m). Must be > 0.",
            },
            "t_shell": {
                "type": "number",
                "description": "Nominal shell wall thickness (m). Must be > 0.",
            },
            "d_nozzle": {
                "type": "number",
                "description": "Finished inside diameter of the nozzle bore (m). Must be > 0.",
            },
            "t_nozzle": {
                "type": "number",
                "description": "Nominal nozzle wall thickness (m). Must be > 0.",
            },
            "S": {
                "type": "number",
                "description": "Maximum allowable stress of shell material (Pa). Must be > 0.",
            },
            "E": {
                "type": "number",
                "description": "Joint efficiency of shell (default 1.0). Must be in (0, 1].",
            },
            "c": {
                "type": "number",
                "description": "Corrosion allowance (m, applied to shell and nozzle). Default 0.0.",
            },
            "F": {
                "type": "number",
                "description": (
                    "Correction factor for nozzle inclination (default 1.0 = perpendicular). "
                    "Must be in [0.5, 1.0]."
                ),
            },
        },
        "required": ["P", "D_shell", "t_shell", "d_nozzle", "t_nozzle", "S"],
    },
)


@register(_nozzle_spec, write=False)
async def run_pv_nozzle_reinforcement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "D_shell", "t_shell", "d_nozzle", "t_nozzle", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("E", "c", "F"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = nozzle_reinforcement(
        a["P"], a["D_shell"], a["t_shell"],
        a["d_nozzle"], a["t_nozzle"], a["S"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_hydrostatic_test_pressure
# ---------------------------------------------------------------------------

_hyd_test_spec = ToolSpec(
    name="pv_hydrostatic_test_pressure",
    description=(
        "Compute the required hydrostatic test pressure per ASME BPVC VIII-1 UG-99(b).\n"
        "\n"
        "    P_test = 1.3 × MAWP × (S_test / S_design)\n"
        "\n"
        "S_test / S_design is the allowable-stress ratio between test temperature "
        "(usually ambient) and design temperature.  If both are omitted the ratio "
        "defaults to 1.0.\n"
        "\n"
        "Returns P_test in Pa, kPa, bar, and psi.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "MAWP": {
                "type": "number",
                "description": "Maximum Allowable Working Pressure (Pa). Must be > 0.",
            },
            "S_test": {
                "type": "number",
                "description": (
                    "Allowable stress at test temperature (Pa). "
                    "Must be > 0 if provided. Supply with S_design for the ratio correction."
                ),
            },
            "S_design": {
                "type": "number",
                "description": (
                    "Allowable stress at design temperature (Pa). "
                    "Must be > 0 if provided."
                ),
            },
        },
        "required": ["MAWP"],
    },
)


@register(_hyd_test_spec, write=False)
async def run_pv_hydrostatic_test_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("MAWP") is None:
        return json.dumps({"ok": False, "reason": "MAWP is required"})

    kwargs: dict = {}
    for opt in ("S_test", "S_design"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = hydrostatic_test_pressure(a["MAWP"], **kwargs)
    return ok_payload(result)
