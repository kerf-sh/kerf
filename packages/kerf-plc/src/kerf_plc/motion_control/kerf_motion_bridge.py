"""
kerf_plc.motion_control.kerf_motion_bridge — PLC ↔ kerf-motion bridge.

Bridges PLCopen motion-control function blocks (IEC 61131-3 MC_* blocks) to
the kerf-motion rigid-body / kinematic solver.  On each PLC scan tick the
bridge:

  1. Reads the function block's commanded position, commanded velocity, and
     status outputs.
  2. Propagates the command to the kerf-motion joint (sets ``target`` and
     ``cmd_vel`` on the joint object).
  3. Calls ``kerf_motion.integrator.simulate`` to advance the joint by one
     scan-tick time step.
  4. Reads the resulting actual position back from the joint and injects it
     into the PLC axis feedback slot.

This closed-loop wiring lets kerf-motion drive a simulation of the mechanical
system while the PLC logic remains unchanged.

Dependency gating
-----------------
All cross-package imports are wrapped in try/except so that this module can
be imported even if kerf_motion or kerf_plc.motion_control.blocks has not
yet landed in the working tree.  Tests that require those packages should
use ``pytest.importorskip``.

Public API
----------
    bridge = PlcAxisToJoint(
        axis_id   = "A1",
        joint_type = "revolute",          # or "prismatic"
        joint_ref  = my_revolute_joint,   # kerf_motion.joints.RevoluteJoint
    )

    # Each PLC scan cycle:
    bridge.tick(block=mc_move_abs_instance, dt=0.001)

    # Read actual position fed back to PLC:
    feedback = bridge.actual_position

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Optional dependency: kerf_motion
# ---------------------------------------------------------------------------

try:
    from kerf_motion.joints import RevoluteJoint, PrismaticJoint
    from kerf_motion.body import RigidBody
    from kerf_motion.integrator import simulate as _km_simulate

    _KERF_MOTION_AVAILABLE = True
except ImportError:
    _KERF_MOTION_AVAILABLE = False
    RevoluteJoint = None  # type: ignore[assignment,misc]
    PrismaticJoint = None  # type: ignore[assignment,misc]
    RigidBody = None  # type: ignore[assignment,misc]
    _km_simulate = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Optional dependency: PLC motion-control function blocks
# ---------------------------------------------------------------------------

try:
    from kerf_plc.motion_control.blocks import (
        MC_MoveAbsolute,
        MC_MoveRelative,
        MC_Power,
        MC_Halt,
        MC_Stop,
    )

    _BLOCKS_AVAILABLE = True
except ImportError:
    _BLOCKS_AVAILABLE = False
    MC_MoveAbsolute = None  # type: ignore[assignment,misc]
    MC_MoveRelative = None  # type: ignore[assignment,misc]
    MC_Power = None  # type: ignore[assignment,misc]
    MC_Halt = None  # type: ignore[assignment,misc]
    MC_Stop = None  # type: ignore[assignment,misc]

try:
    from kerf_plc.motion_control.axis_state import AxisStateMachine

    _AXIS_STATE_AVAILABLE = True
except ImportError:
    _AXIS_STATE_AVAILABLE = False
    AxisStateMachine = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Protocol: what the bridge expects from a motion block
# ---------------------------------------------------------------------------


class _BlockProtocol:
    """
    Structural interface expected of any MC_* block passed to ``tick()``.

    The bridge reads these attributes; duck typing is used so that real
    PLCopen blocks and lightweight test stubs both work.

    Attributes
    ----------
    Position      : float | None  — commanded target position (engineering units)
    Velocity      : float | None  — commanded velocity magnitude (EU/s)
    Done          : bool          — True once target has been reached
    Busy          : bool          — True while motion is in progress
    Error         : bool          — True if the block is in error state
    axis_feedback : float         — writable slot; bridge injects actual position
    """

    Position: float | None
    Velocity: float | None
    Done: bool
    Busy: bool
    Error: bool
    axis_feedback: float


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class PlcAxisToJoint:
    """
    Bridge that couples a PLC motion axis to a kerf-motion joint.

    Parameters
    ----------
    axis_id : str
        Identifier matching the joint's ``axis_id`` and the PLC axis tag.
    joint_type : {'revolute', 'prismatic'}
        Joint kind — used for validation and display.
    joint_ref : RevoluteJoint | PrismaticJoint
        Live joint object managed by the kerf-motion runtime.  The bridge
        writes ``target`` and ``cmd_vel`` and reads back ``position``/
        ``angle`` each tick.
    body_ref : RigidBody | None
        Optional enclosing body.  When provided, ``simulate`` is called on
        ``[body_ref]``; otherwise a single-joint body is created internally.

    Attributes
    ----------
    actual_position : float
        Most-recently read joint position (rad for revolute, m for prismatic).
        Updated by ``tick()``.
    commanded_position : float | None
        Last commanded target sent to the joint.
    commanded_velocity : float | None
        Last commanded velocity sent to the joint.
    """

    def __init__(
        self,
        axis_id: str,
        joint_type: Literal["revolute", "prismatic"],
        joint_ref: Any,
        body_ref: Any | None = None,
    ) -> None:
        if joint_type not in ("revolute", "prismatic"):
            raise ValueError(
                f"joint_type must be 'revolute' or 'prismatic', got {joint_type!r}"
            )

        self.axis_id = axis_id
        self.joint_type = joint_type
        self.joint_ref = joint_ref

        # Build an internal RigidBody wrapper if no external body is provided.
        if body_ref is not None:
            self._body = body_ref
        elif _KERF_MOTION_AVAILABLE:
            self._body = RigidBody(
                name=f"body_{axis_id}",
                mass=1.0,
                joints=[joint_ref],
            )
        else:
            self._body = None

        self.actual_position: float = self._read_joint_position()
        self.commanded_position: float | None = None
        self.commanded_velocity: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(self, block: Any, dt: float) -> None:
        """
        Execute one PLC scan-cycle bridge step.

        Steps
        -----
        1. Extract commanded position and velocity from *block*.
        2. Write them to the joint as ``target`` and ``cmd_vel``.
        3. Advance the joint by *dt* via the kerf-motion integrator.
        4. Read back the actual joint position.
        5. Inject the actual position into ``block.axis_feedback``.

        Parameters
        ----------
        block : duck-typed MC_* block
            Must expose ``Position``, ``Velocity``, ``Done``, ``Busy``,
            ``Error``, and writable ``axis_feedback``.
        dt : float
            Time step (seconds).  Must be > 0.
        """
        if dt <= 0.0:
            raise ValueError(f"dt must be positive, got {dt!r}")

        # ---- 1. Read commands from block --------------------------------
        cmd_pos = _safe_float(getattr(block, "Position", None), default=None)
        cmd_vel = _safe_float(getattr(block, "Velocity", None), default=0.0)

        self.commanded_position = cmd_pos
        self.commanded_velocity = cmd_vel

        # ---- 2. Write commands to joint --------------------------------
        if cmd_pos is not None:
            self.joint_ref.target = cmd_pos
        if cmd_vel is not None and cmd_vel > 0.0:
            self.joint_ref.cmd_vel = cmd_vel

        # ---- 3. Advance joint via integrator ---------------------------
        if _KERF_MOTION_AVAILABLE and self._body is not None:
            _km_simulate([self._body], dt)
        else:
            # Fallback: inline kinematic step (bridge usable without full kerf_motion install)
            _step_joint_inline(self.joint_ref, dt)

        # ---- 4. Read back actual position ------------------------------
        self.actual_position = self._read_joint_position()

        # ---- 5. Inject feedback into block -----------------------------
        try:
            block.axis_feedback = self.actual_position
        except AttributeError:
            pass  # block doesn't support feedback injection — no-op

        # ---- 6. Update block Done/Busy flags if block supports it ------
        _update_block_status(block, self.actual_position, cmd_pos)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_joint_position(self) -> float:
        """Read actual position from the joint reference."""
        joint = self.joint_ref
        if hasattr(joint, "angle"):
            # RevoluteJoint
            return float(joint.angle)
        if hasattr(joint, "position"):
            # PrismaticJoint
            return float(joint.position)
        return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float | None) -> float | None:
    """Convert *value* to float; return *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _step_joint_inline(joint: Any, dt: float) -> None:
    """
    Inline kinematic step used when kerf_motion.integrator is unavailable.

    Mirrors the logic in ``kerf_motion.integrator._step_joint``.
    """
    is_revolute = hasattr(joint, "angle")
    current = joint.angle if is_revolute else joint.position
    vel = abs(getattr(joint, "cmd_vel", 0.0))
    if vel <= 0.0:
        return
    error = joint.target - current
    max_step = vel * dt
    if abs(error) <= max_step:
        new_pos = joint.target
        joint.velocity = 0.0
    else:
        direction = 1.0 if error > 0.0 else -1.0
        new_pos = current + direction * max_step
        joint.velocity = direction * vel
    if is_revolute:
        joint.angle = new_pos
    else:
        joint.position = new_pos


def _update_block_status(block: Any, actual: float, target: float | None) -> None:
    """
    Update ``Done`` / ``Busy`` on *block* if those attributes are writable.

    A block is considered Done when the actual position is within a small
    tolerance (1e-9) of the target.  This mirrors PLCopen behaviour where
    ``Done`` is raised upon arrival.
    """
    if target is None:
        return
    at_target = abs(actual - target) < 1e-9
    try:
        block.Done = at_target
    except AttributeError:
        pass
    try:
        block.Busy = not at_target
    except AttributeError:
        pass
