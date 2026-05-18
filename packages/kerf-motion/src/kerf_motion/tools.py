"""
kerf_motion.tools
=================
LLM-callable tool surface for the motion plugin.

Tools
-----
simulate_motion   — run a multibody dynamics simulation
solve_ik          — inverse kinematics for a serial arm
compute_workspace — 2-D workspace cloud for a serial arm

All tools return JSON-serialisable dicts.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_motion._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# simulate_motion
# ---------------------------------------------------------------------------

simulate_motion_spec = ToolSpec(
    name="simulate_motion",
    description=(
        "Run a multibody rigid-body dynamics simulation using RK4 integration. "
        "Supports gravity, spring-damper, and applied force/torque fields. "
        "Returns time-series trajectories (position, velocity) for each body."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bodies": {
                "type": "array",
                "description": "List of rigid body definitions.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "mass": {"type": "number"},
                        "inertia": {
                            "type": "array",
                            "description": "3x3 inertia tensor as list of 3 rows, each with 3 values",
                            "items": {"type": "array", "items": {"type": "number"}},
                        },
                        "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                        "velocity": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    },
                    "required": ["mass"],
                },
            },
            "forces": {
                "type": "array",
                "description": "List of force field specifications.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["gravity", "applied", "spring_damper"]},
                        "g": {"type": "number"},
                        "body_idx": {"type": "integer"},
                        "force": {"type": "array", "items": {"type": "number"}},
                        "torque": {"type": "array", "items": {"type": "number"}},
                        "body_a": {"type": "integer"},
                        "body_b": {"type": "integer"},
                        "k": {"type": "number"},
                        "c": {"type": "number"},
                        "natural_length": {"type": "number"},
                    },
                    "required": ["type"],
                },
            },
            "dt": {"type": "number", "description": "Time step in seconds."},
            "n_steps": {"type": "integer", "description": "Number of integration steps."},
            "record_every": {"type": "integer", "default": 1},
        },
        "required": ["bodies", "dt", "n_steps"],
    },
)


async def run_simulate_motion(params: Dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_motion.body import RigidBody
        from kerf_motion.forces import gravity as gravity_ff, applied_force, spring_damper
        from kerf_motion.integrator import simulate

        # Build bodies
        bodies = []
        for bd in params["bodies"]:
            mass = bd["mass"]
            inertia_raw = bd.get("inertia", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
            I = tuple(tuple(float(v) for v in row) for row in inertia_raw)
            pos = tuple(bd.get("position", [0, 0, 0]))
            vel = tuple(bd.get("velocity", [0, 0, 0]))
            name = bd.get("name", f"body_{len(bodies)}")
            bodies.append(RigidBody(
                mass=mass,
                inertia_tensor=I,  # type: ignore[arg-type]
                position=pos,  # type: ignore[arg-type]
                velocity=vel,  # type: ignore[arg-type]
                name=name,
            ))

        # Build force fields
        force_fields = []
        for fspec in params.get("forces", []):
            ftype = fspec["type"]
            if ftype == "gravity":
                g_val = fspec.get("g", 9.80665)
                force_fields.append(gravity_ff(g=g_val, axis=1, sign=-1))
            elif ftype == "applied":
                bidx = fspec.get("body_idx", 0)
                fv = tuple(fspec.get("force", [0, 0, 0]))
                tv = tuple(fspec.get("torque", [0, 0, 0]))
                force_fields.append(applied_force(bidx, fv, tv))  # type: ignore[arg-type]
            elif ftype == "spring_damper":
                force_fields.append(spring_damper(
                    body_a_idx=fspec["body_a"],
                    body_b_idx=fspec.get("body_b", -1),
                    k=fspec["k"],
                    c=fspec.get("c", 0.0),
                    natural_length=fspec.get("natural_length", 1.0),
                ))

        dt = float(params["dt"])
        n_steps = int(params["n_steps"])
        record_every = int(params.get("record_every", 1))

        result = simulate(bodies, [], force_fields, dt, n_steps, record_every=record_every)

        if not result["ok"]:
            return err_payload(result.get("reason", "simulation failed"), "MOTION_SIM_ERROR")

        # Serialise trajectories
        traj_out = []
        for body_traj in result["trajectories"]:
            traj_out.append([
                {
                    "t": snap.t,
                    "position": list(snap.position),
                    "velocity": list(snap.velocity),
                }
                for snap in body_traj
            ])

        return ok_payload({
            "ok": True,
            "t": result["t"],
            "trajectories": traj_out,
            "n_steps": result["n_steps"],
            "dt": result["dt"],
        })

    except Exception as exc:
        return err_payload(str(exc), "MOTION_SIM_ERROR")


# ---------------------------------------------------------------------------
# solve_ik
# ---------------------------------------------------------------------------

solve_ik_spec = ToolSpec(
    name="solve_ik",
    description=(
        "Compute joint angles for a serial robot arm to reach a target end-effector position. "
        "Supports analytic 2-link planar arm or numerical Jacobian-transpose for n-DOF chains."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["analytic_2link", "jacobian_transpose"],
                "description": "IK solver method.",
            },
            "links": {
                "type": "array",
                "description": "Link lengths [l1, l2, ...] in metres.",
                "items": {"type": "number"},
            },
            "target": {
                "type": "array",
                "description": "Target end-effector position [x, y, z] in metres.",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 3,
            },
            "elbow_up": {"type": "boolean", "default": True},
            "tol": {"type": "number", "default": 1e-6},
            "max_iterations": {"type": "integer", "default": 1000},
        },
        "required": ["method", "links", "target"],
    },
)


async def run_solve_ik(params: Dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_motion.joints import RevoluteJoint
        from kerf_motion.inverse_kinematics import analytic_ik_2link, jacobian_transpose_ik

        method = params["method"]
        links = params["links"]
        target_raw = params["target"]
        target = (
            float(target_raw[0]),
            float(target_raw[1]),
            float(target_raw[2]) if len(target_raw) > 2 else 0.0,
        )

        if method == "analytic_2link":
            if len(links) < 2:
                return err_payload("analytic_2link requires at least 2 link lengths", "IK_ERROR")
            result = analytic_ik_2link(
                links[0], links[1],
                target[0], target[1],
                elbow_up=bool(params.get("elbow_up", True)),
            )
            if not result["ok"]:
                return err_payload(result.get("reason", "IK failed"), "IK_UNREACHABLE")
            return ok_payload(result)

        elif method == "jacobian_transpose":
            # Build revolute joints for each link, then a fixed offset for the
            # last link segment so the end-effector is at the tip of the last link.
            from kerf_motion.joints import FixedJoint

            joints = []
            offset = 0.0
            for i, l in enumerate(links):
                j = RevoluteJoint(
                    parent_idx=i,
                    child_idx=i + 1,
                    axis=(0.0, 0.0, 1.0),
                    parent_offset=(offset, 0.0, 0.0),
                    name=f"j{i}",
                )
                joints.append(j)
                offset = l  # next joint at end of this link
            # Final link segment: fixed offset = last link length along local X
            joints.append(FixedJoint(
                parent_idx=len(links),
                child_idx=len(links) + 1,
                parent_offset=(links[-1], 0.0, 0.0),
                name="ee",
            ))

            result = jacobian_transpose_ik(
                joints, target,
                tol=float(params.get("tol", 1e-6)),
                max_iterations=int(params.get("max_iterations", 1000)),
            )
            if not result["ok"]:
                return err_payload(
                    result.get("reason", "IK did not converge"),
                    "IK_NO_CONVERGENCE",
                )
            return ok_payload(result)

        else:
            return err_payload(f"Unknown IK method: {method}", "IK_BAD_METHOD")

    except Exception as exc:
        return err_payload(str(exc), "IK_ERROR")


# ---------------------------------------------------------------------------
# compute_workspace
# ---------------------------------------------------------------------------

compute_workspace_spec = ToolSpec(
    name="compute_workspace",
    description=(
        "Sample the reachable workspace of a serial robot arm by sweeping all joint angles. "
        "Returns a cloud of end-effector positions."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "links": {
                "type": "array",
                "description": "Link lengths in metres.",
                "items": {"type": "number"},
            },
            "n_samples": {
                "type": "integer",
                "default": 200,
                "description": "Approximate total number of sampled configurations.",
            },
            "limits": {
                "type": "array",
                "description": "Optional joint limits [[lo1,hi1], [lo2,hi2], ...] in radians.",
                "items": {"type": "array", "items": {"type": "number"}},
            },
        },
        "required": ["links"],
    },
)


async def run_compute_workspace(params: Dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_motion.joints import RevoluteJoint
        from kerf_motion.inverse_kinematics import compute_workspace_2d

        from kerf_motion.joints import FixedJoint

        links = params["links"]
        limits_raw = params.get("limits", [])

        joints = []
        offset = 0.0
        for i, l in enumerate(links):
            lim = None
            if i < len(limits_raw):
                lim = (float(limits_raw[i][0]), float(limits_raw[i][1]))
            j = RevoluteJoint(
                parent_idx=i,
                child_idx=i + 1,
                axis=(0.0, 0.0, 1.0),
                parent_offset=(offset, 0.0, 0.0),
                limits=lim,
                name=f"j{i}",
            )
            joints.append(j)
            offset = l
        # Final link segment
        joints.append(FixedJoint(
            parent_idx=len(links),
            child_idx=len(links) + 1,
            parent_offset=(links[-1], 0.0, 0.0),
            name="ee",
        ))

        n_samples = int(params.get("n_samples", 200))
        result = compute_workspace_2d(joints, n_samples=n_samples)

        if not result["ok"]:
            return err_payload(result.get("reason", "workspace failed"), "WORKSPACE_ERROR")

        return ok_payload({
            "ok": True,
            "count": result["count"],
            "points": [list(p) for p in result["points"]],
        })

    except Exception as exc:
        return err_payload(str(exc), "WORKSPACE_ERROR")
