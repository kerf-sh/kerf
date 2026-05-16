"""
kerf_cad_core.robotics.tools — LLM tool wrappers for serial robot-arm kinematics.

Registers tools with the Kerf tool registry:

  robot_fk                     — Denavit-Hartenberg forward kinematics
  robot_end_effector_pose      — extract position + ZYX Euler from FK result
  robot_ik_2r_planar           — closed-form IK for planar 2R arm
  robot_ik_3r_planar           — closed-form IK for planar 3R arm
  robot_jacobian               — geometric Jacobian for an n-link chain
  robot_manipulability         — Yoshikawa manipulability measure
  robot_workspace              — workspace radius bounds
  robot_trajectory_trapezoidal — joint-space trapezoidal velocity trajectory

All tools are pure-Python; no OCC dependency.
Errors returned as {ok: false, reason: "..."} — tools never raise.

References
----------
Craig, J.J. "Introduction to Robotics: Mechanics and Control", 3rd ed.
Spong, M.W., Hutchinson, S., Vidyasagar, M. "Robot Modeling and Control", 2006.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.robotics.arm import (
    fk_chain,
    end_effector_pose,
    ik_2r_planar,
    ik_3r_planar,
    geometric_jacobian,
    manipulability,
    workspace_radius,
    joint_trajectory_trapezoidal,
)


# ---------------------------------------------------------------------------
# Tool: robot_fk
# ---------------------------------------------------------------------------

_robot_fk_spec = ToolSpec(
    name="robot_fk",
    description=(
        "Denavit-Hartenberg forward kinematics for a serial robot arm.\n"
        "\n"
        "Computes the 4×4 homogeneous end-effector transform T_0n by chaining "
        "individual DH matrices for each joint.\n"
        "\n"
        "Standard DH convention (Craig):\n"
        "  T_i = Rz(theta_i) · Tz(d_i) · Tx(a_i) · Rx(alpha_i)\n"
        "\n"
        "dh_params: list of n rows, each [a_i, alpha_i_deg, d_i, theta_offset_deg].\n"
        "joint_angles_deg: list of n joint angles (degrees) added to theta_offset.\n"
        "\n"
        "Returns the 4×4 transform matrix and any joint-limit warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for mismatched array lengths.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dh_params": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "description": (
                    "List of n DH rows: [[a_i, alpha_i_deg, d_i, theta_offset_deg], ...]."
                ),
            },
            "joint_angles_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "List of n joint angles (degrees).",
            },
            "joint_limits_deg": {
                "type": "array",
                "items": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                },
                "description": (
                    "Optional list of [lo_deg, hi_deg] per joint, or null to skip. "
                    "Warnings emitted for out-of-limit joints."
                ),
            },
        },
        "required": ["dh_params", "joint_angles_deg"],
    },
)


@register(_robot_fk_spec, write=False)
async def run_robot_fk(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dh_params") is None:
        return json.dumps({"ok": False, "reason": "dh_params is required"})
    if a.get("joint_angles_deg") is None:
        return json.dumps({"ok": False, "reason": "joint_angles_deg is required"})

    import math

    dh_raw = a["dh_params"]
    # Convert alpha and theta_offset from degrees to radians
    dh_params = [
        [float(row[0]), math.radians(float(row[1])), float(row[2]), math.radians(float(row[3]))]
        for row in dh_raw
    ]
    joint_angles = [math.radians(float(q)) for q in a["joint_angles_deg"]]

    joint_limits = None
    if "joint_limits_deg" in a and a["joint_limits_deg"] is not None:
        joint_limits = []
        for lim in a["joint_limits_deg"]:
            if lim is None:
                joint_limits.append(None)
            else:
                joint_limits.append((math.radians(float(lim[0])), math.radians(float(lim[1]))))

    result = fk_chain(dh_params, joint_angles, joint_limits)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_end_effector_pose
# ---------------------------------------------------------------------------

_robot_end_effector_pose_spec = ToolSpec(
    name="robot_end_effector_pose",
    description=(
        "Extract end-effector position and ZYX Euler angles from a 4×4 "
        "homogeneous transform matrix.\n"
        "\n"
        "ZYX convention: R = Rz(yaw) · Ry(pitch) · Rx(roll).\n"
        "\n"
        "Typically used after robot_fk to get the human-readable pose.\n"
        "\n"
        "Returns x, y, z (metres) and roll_deg, pitch_deg, yaw_deg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid matrix.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "matrix": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "minItems": 4,
                "maxItems": 4,
                "description": "4×4 homogeneous transform matrix (list of 4 rows × 4 columns).",
            },
        },
        "required": ["matrix"],
    },
)


@register(_robot_end_effector_pose_spec, write=False)
async def run_robot_end_effector_pose(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("matrix") is None:
        return json.dumps({"ok": False, "reason": "matrix is required"})

    T = a["matrix"]
    if len(T) != 4 or any(len(row) != 4 for row in T):
        return json.dumps({"ok": False, "reason": "matrix must be 4×4"})

    result = end_effector_pose(T)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_ik_2r_planar
# ---------------------------------------------------------------------------

_robot_ik_2r_planar_spec = ToolSpec(
    name="robot_ik_2r_planar",
    description=(
        "Closed-form inverse kinematics for a planar 2R robot arm.\n"
        "\n"
        "Solves for joint angles (q1, q2) such that the end-effector reaches "
        "(px, py) in the plane.\n"
        "\n"
        "Two solutions exist (elbow-up and elbow-down).  The requested solution "
        "is returned; if the target is outside the reachable workspace, the "
        "nearest boundary point is used and 'reachable: false' is set.\n"
        "\n"
        "Returns q1_deg, q2_deg (and radians), reachable flag, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "l1": {
                "type": "number",
                "description": "Length of link 1 (metres, > 0).",
            },
            "l2": {
                "type": "number",
                "description": "Length of link 2 (metres, > 0).",
            },
            "px": {
                "type": "number",
                "description": "Target x position (metres).",
            },
            "py": {
                "type": "number",
                "description": "Target y position (metres).",
            },
            "elbow_up": {
                "type": "boolean",
                "description": "True (default) for elbow-up; False for elbow-down.",
            },
            "joint_limits_deg": {
                "type": "array",
                "items": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                },
                "description": (
                    "Optional [[lo1,hi1],[lo2,hi2]] joint limits in degrees. "
                    "Warnings emitted for violations."
                ),
            },
        },
        "required": ["l1", "l2", "px", "py"],
    },
)


@register(_robot_ik_2r_planar_spec, write=False)
async def run_robot_ik_2r_planar(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("l1", "l2", "px", "py"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    import math

    kwargs: dict = {}
    if "elbow_up" in a:
        kwargs["elbow_up"] = bool(a["elbow_up"])
    if "joint_limits_deg" in a and a["joint_limits_deg"] is not None:
        lims = []
        for lim in a["joint_limits_deg"]:
            if lim is None:
                lims.append(None)
            else:
                lims.append((math.radians(float(lim[0])), math.radians(float(lim[1]))))
        kwargs["joint_limits"] = lims

    result = ik_2r_planar(
        float(a["l1"]), float(a["l2"]),
        float(a["px"]), float(a["py"]),
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_ik_3r_planar
# ---------------------------------------------------------------------------

_robot_ik_3r_planar_spec = ToolSpec(
    name="robot_ik_3r_planar",
    description=(
        "Closed-form inverse kinematics for a planar 3R robot arm.\n"
        "\n"
        "Solves for (q1, q2, q3) such that the end-effector reaches (px, py) "
        "with orientation phi_deg (total arm angle from x-axis, degrees).\n"
        "\n"
        "The problem is decomposed: the wrist centre (base of link 3) is "
        "found analytically, then a 2R sub-problem is solved.\n"
        "\n"
        "Returns q1_deg, q2_deg, q3_deg (and radians), reachable flag, warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "l1": {"type": "number", "description": "Link 1 length (metres, > 0)."},
            "l2": {"type": "number", "description": "Link 2 length (metres, > 0)."},
            "l3": {"type": "number", "description": "Link 3 length (metres, > 0)."},
            "px": {"type": "number", "description": "Target x position (metres)."},
            "py": {"type": "number", "description": "Target y position (metres)."},
            "phi_deg": {
                "type": "number",
                "description": "Desired end-effector angle from x-axis (degrees, default 0).",
            },
            "joint_limits_deg": {
                "type": "array",
                "items": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                },
                "description": "Optional joint limits [[lo,hi]×3] in degrees.",
            },
        },
        "required": ["l1", "l2", "l3", "px", "py"],
    },
)


@register(_robot_ik_3r_planar_spec, write=False)
async def run_robot_ik_3r_planar(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("l1", "l2", "l3", "px", "py"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    import math

    kwargs: dict = {}
    if "phi_deg" in a:
        kwargs["phi_deg"] = float(a["phi_deg"])
    if "joint_limits_deg" in a and a["joint_limits_deg"] is not None:
        lims = []
        for lim in a["joint_limits_deg"]:
            if lim is None:
                lims.append(None)
            else:
                lims.append((math.radians(float(lim[0])), math.radians(float(lim[1]))))
        kwargs["joint_limits"] = lims

    result = ik_3r_planar(
        float(a["l1"]), float(a["l2"]), float(a["l3"]),
        float(a["px"]), float(a["py"]),
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_jacobian
# ---------------------------------------------------------------------------

_robot_jacobian_spec = ToolSpec(
    name="robot_jacobian",
    description=(
        "Compute the 6×n geometric Jacobian for a serial robot arm.\n"
        "\n"
        "Maps joint velocities to end-effector spatial velocity [v; omega].\n"
        "For revolute joint i:\n"
        "  J_v_i = z_{i-1} × (p_n - p_{i-1})\n"
        "  J_w_i = z_{i-1}\n"
        "\n"
        "dh_params: [[a_i, alpha_i_deg, d_i, theta_offset_deg], ...]\n"
        "joint_angles_deg: n joint angles (degrees).\n"
        "\n"
        "Returns the 6×n Jacobian matrix, singularity flag, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for mismatched lengths.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dh_params": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "description": "DH parameter rows: [[a_i, alpha_i_deg, d_i, theta_offset_deg], ...].",
            },
            "joint_angles_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Joint angles (degrees).",
            },
        },
        "required": ["dh_params", "joint_angles_deg"],
    },
)


@register(_robot_jacobian_spec, write=False)
async def run_robot_jacobian(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dh_params") is None:
        return json.dumps({"ok": False, "reason": "dh_params is required"})
    if a.get("joint_angles_deg") is None:
        return json.dumps({"ok": False, "reason": "joint_angles_deg is required"})

    import math

    dh_raw = a["dh_params"]
    dh_params = [
        [float(row[0]), math.radians(float(row[1])), float(row[2]), math.radians(float(row[3]))]
        for row in dh_raw
    ]
    joint_angles = [math.radians(float(q)) for q in a["joint_angles_deg"]]

    result = geometric_jacobian(dh_params, joint_angles)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_manipulability
# ---------------------------------------------------------------------------

_robot_manipulability_spec = ToolSpec(
    name="robot_manipulability",
    description=(
        "Compute the Yoshikawa manipulability measure for a robot at a given "
        "configuration.\n"
        "\n"
        "w = sqrt(det(J · J^T))\n"
        "\n"
        "w = 0 indicates a singular configuration (no motion in some direction).\n"
        "Higher w indicates greater dexterity.\n"
        "\n"
        "Accepts the 6×n Jacobian directly (as returned by robot_jacobian).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid Jacobian.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "J": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "description": "6×n Jacobian matrix (list of 6 rows).",
            },
        },
        "required": ["J"],
    },
)


@register(_robot_manipulability_spec, write=False)
async def run_robot_manipulability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("J") is None:
        return json.dumps({"ok": False, "reason": "J is required"})

    result = manipulability(a["J"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_workspace
# ---------------------------------------------------------------------------

_robot_workspace_spec = ToolSpec(
    name="robot_workspace",
    description=(
        "Estimate workspace radius bounds for a serial robot arm from DH parameters.\n"
        "\n"
        "r_max = sum of effective link lengths (Euclidean of a_i and d_i).\n"
        "r_min = max(0, r_max - 2 × min_link), the inner void radius.\n"
        "\n"
        "dh_params: [[a_i, alpha_i_deg, d_i, theta_offset_deg], ...]\n"
        "\n"
        "Returns r_max and r_min in metres.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid input.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dh_params": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "description": "DH parameter rows: [[a_i, alpha_i_deg, d_i, theta_offset_deg], ...].",
            },
        },
        "required": ["dh_params"],
    },
)


@register(_robot_workspace_spec, write=False)
async def run_robot_workspace(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dh_params") is None:
        return json.dumps({"ok": False, "reason": "dh_params is required"})

    # alpha/theta in degrees — workspace only uses a_i and d_i (indices 0, 2)
    dh_raw = a["dh_params"]
    dh_params = [
        [float(row[0]), float(row[1]), float(row[2]), float(row[3])]
        for row in dh_raw
    ]

    result = workspace_radius(dh_params)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: robot_trajectory_trapezoidal
# ---------------------------------------------------------------------------

_robot_trajectory_trapezoidal_spec = ToolSpec(
    name="robot_trajectory_trapezoidal",
    description=(
        "Generate a joint-space trapezoidal velocity trajectory.\n"
        "\n"
        "All joints are time-scaled to the same duration T_sync (the joint "
        "requiring the longest motion drives the duration).  Each joint "
        "follows an individual trapezoidal or triangular velocity profile.\n"
        "\n"
        "Returns sampled times, positions, and velocities for all joints.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q_start_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Start joint angles (degrees).",
            },
            "q_end_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "End joint angles (degrees).",
            },
            "v_max_deg_s": {
                "type": "number",
                "description": "Maximum joint velocity (degrees/s, > 0).",
            },
            "a_max_deg_s2": {
                "type": "number",
                "description": "Maximum joint acceleration (degrees/s², > 0).",
            },
            "dt_s": {
                "type": "number",
                "description": "Time step (seconds, default 0.01).",
            },
        },
        "required": ["q_start_deg", "q_end_deg", "v_max_deg_s", "a_max_deg_s2"],
    },
)


@register(_robot_trajectory_trapezoidal_spec, write=False)
async def run_robot_trajectory_trapezoidal(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("q_start_deg", "q_end_deg", "v_max_deg_s", "a_max_deg_s2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    import math

    q_start = [math.radians(float(q)) for q in a["q_start_deg"]]
    q_end   = [math.radians(float(q)) for q in a["q_end_deg"]]
    v_max   = math.radians(float(a["v_max_deg_s"]))
    a_max   = math.radians(float(a["a_max_deg_s2"]))
    dt      = float(a.get("dt_s", 0.01))

    result = joint_trajectory_trapezoidal(q_start, q_end, v_max, a_max, dt)

    # Convert positions and velocities back to degrees for readability
    if result.get("ok") and "positions" in result:
        result["positions_deg"] = [
            [math.degrees(q) for q in row] for row in result["positions"]
        ]
        result["velocities_deg_s"] = [
            [math.degrees(v) for v in row] for row in result["velocities"]
        ]
        # Keep radians too
        result["positions_rad"] = result.pop("positions")
        result["velocities_rad_s"] = result.pop("velocities")

    return ok_payload(result)
