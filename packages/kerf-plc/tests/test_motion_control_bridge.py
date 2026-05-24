"""
tests/test_motion_control_bridge.py — oracle tests for PlcAxisToJoint.

Test oracle
-----------
A revolute joint driven by MC_MoveAbsolute(target=π/2, velocity=1) must:

  1. Reach π/2 rad within ±5 % of the analytic trapezoidal-profile arrival
     time  (for a pure constant-velocity profile: t_arrival = target / velocity
     = (π/2) / 1 ≈ 1.5708 s).
  2. Before reaching the target the joint angle linearly interpolates (grows
     at the commanded velocity).
  3. After reaching the target the joint holds at π/2 rad.

The module also tests:
  - prismatic joint driven to a position target
  - feedback injection into the block's axis_feedback slot
  - zero-velocity no-move guard
  - negative target (reverse direction)

Tests use lightweight stub joints so that the suite is runnable without the
full kerf_motion topology package.  The bridge's inline kinematic fallback
(_step_joint_inline) is exercised by setting _KERF_MOTION_AVAILABLE=False on
the bridge module.

Author: imranparuk
"""

from __future__ import annotations

import math
import pytest

from kerf_plc.motion_control.kerf_motion_bridge import PlcAxisToJoint


# ---------------------------------------------------------------------------
# Stub joints — duck-typed to match the bridge's _step_joint_inline protocol
# ---------------------------------------------------------------------------

class _StubRevoluteJoint:
    """Minimal revolute joint stub: exposes `angle`, `target`, `cmd_vel`, `velocity`."""

    def __init__(self, axis_id: str, angle: float = 0.0) -> None:
        self.axis_id = axis_id
        self.angle = angle
        self.target = angle
        self.cmd_vel = 0.0
        self.velocity = 0.0


class _StubPrismaticJoint:
    """Minimal prismatic joint stub: exposes `position`, `target`, `cmd_vel`, `velocity`."""

    def __init__(self, axis_id: str, position: float = 0.0) -> None:
        self.axis_id = axis_id
        self.position = position
        self.target = position
        self.cmd_vel = 0.0
        self.velocity = 0.0


# Convenience aliases so test code reads naturally
RevoluteJoint = _StubRevoluteJoint
PrismaticJoint = _StubPrismaticJoint


# ---------------------------------------------------------------------------
# Stub body — accepted by PlcAxisToJoint but not used by the inline fallback
# ---------------------------------------------------------------------------

class _StubBody:
    """Stub body reference; bridge uses inline fallback when _KERF_MOTION_AVAILABLE is False."""

    def __init__(self, name: str, joints: list) -> None:
        self.name = name
        self.joints = joints

    @property
    def mass(self) -> float:
        return 1.0


RigidBody = _StubBody


# ---------------------------------------------------------------------------
# Helpers that force the bridge to use the inline fallback regardless of
# whether kerf_motion is installed.
# ---------------------------------------------------------------------------

import kerf_plc.motion_control.kerf_motion_bridge as _bridge_mod


def _make_bridge(joint, joint_type: str, body=None):
    """
    Build a PlcAxisToJoint with _KERF_MOTION_AVAILABLE forced to False so that
    _step_joint_inline is always exercised, making the test environment-neutral.
    """
    old = _bridge_mod._KERF_MOTION_AVAILABLE
    _bridge_mod._KERF_MOTION_AVAILABLE = False
    try:
        bridge = PlcAxisToJoint(
            axis_id=joint.axis_id,
            joint_type=joint_type,
            joint_ref=joint,
            body_ref=body,
        )
    finally:
        _bridge_mod._KERF_MOTION_AVAILABLE = old
    return bridge


def _tick_bridge(bridge, block, dt: float) -> None:
    """Tick the bridge with _KERF_MOTION_AVAILABLE forced to False."""
    old = _bridge_mod._KERF_MOTION_AVAILABLE
    _bridge_mod._KERF_MOTION_AVAILABLE = False
    try:
        bridge.tick(block, dt)
    finally:
        _bridge_mod._KERF_MOTION_AVAILABLE = old


# ---------------------------------------------------------------------------
# MC_* stubs (duck-typed — no dependency on kerf_plc.motion_control.blocks)
# ---------------------------------------------------------------------------


class _MC_MoveAbsolute:
    """Minimal PLCopen MC_MoveAbsolute stub for bridge testing."""

    def __init__(self, target: float, velocity: float) -> None:
        self.Done: bool = False
        self.Busy: bool = True
        self.Error: bool = False
        self.axis_feedback: float = 0.0
        self.Position: float = target
        self.Velocity: float = velocity


class _MC_MoveRelative:
    """Minimal PLCopen MC_MoveRelative stub."""

    def __init__(self, distance: float, velocity: float, start_position: float = 0.0) -> None:
        self.Done: bool = False
        self.Busy: bool = True
        self.Error: bool = False
        self.axis_feedback: float = 0.0
        self.Position: float = start_position + distance
        self.Velocity: float = velocity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_simulation(
    joint,
    block,
    dt: float,
    n_steps: int,
    joint_type: str = "revolute",
) -> list[float]:
    """
    Run the bridge for *n_steps* steps of *dt* each.

    Returns a list of joint positions sampled after every tick.
    """
    body = RigidBody(name="test_body", joints=[joint])
    bridge = _make_bridge(joint, joint_type, body)
    positions = []
    for _ in range(n_steps):
        _tick_bridge(bridge, block, dt)
        positions.append(bridge.actual_position)
    return positions


# ---------------------------------------------------------------------------
# T1 — Trapezoidal-profile arrival time oracle (revolute joint)
# ---------------------------------------------------------------------------


class TestRevoluteArrivalTime:
    """
    Oracle: MC_MoveAbsolute(target=π/2, velocity=1) on a revolute joint.

    For a constant-velocity profile (no acceleration ramp) the analytic
    arrival time is:

        t_analytic = |target - start| / velocity = (π/2) / 1 ≈ 1.5708 s

    The bridge must reach the target within ±5 % of t_analytic.
    """

    TARGET = math.pi / 2       # rad
    VELOCITY = 1.0              # rad/s
    DT = 1e-3                   # 1 ms scan cycle
    TOLERANCE = 0.05            # 5 %

    def _analytic_arrival_time(self) -> float:
        return abs(self.TARGET) / self.VELOCITY  # π/2 ≈ 1.5708 s

    def test_reaches_target_within_tolerance(self):
        """Joint must reach π/2 within ±5 % of analytic arrival time."""
        joint = RevoluteJoint(axis_id="A1", angle=0.0)
        block = _MC_MoveAbsolute(target=self.TARGET, velocity=self.VELOCITY)

        t_analytic = self._analytic_arrival_time()
        # Run for 2× the analytic time to allow overshoot window
        n_steps = int(2.0 * t_analytic / self.DT)
        positions = _run_simulation(joint, block, self.DT, n_steps)

        # Find the first step at which the joint is within floating-point
        # tolerance of the target
        arrival_step = None
        for i, pos in enumerate(positions):
            if abs(pos - self.TARGET) < 1e-9:
                arrival_step = i + 1  # 1-indexed steps
                break

        assert arrival_step is not None, (
            f"Joint never reached target={self.TARGET:.4f} rad "
            f"(final position={positions[-1]:.6f} rad)"
        )

        t_actual = arrival_step * self.DT
        lower = t_analytic * (1.0 - self.TOLERANCE)
        upper = t_analytic * (1.0 + self.TOLERANCE)

        assert lower <= t_actual <= upper, (
            f"Arrival time {t_actual:.4f} s is outside [{lower:.4f}, {upper:.4f}] s "
            f"(analytic={t_analytic:.4f} s, tolerance={self.TOLERANCE*100:.0f} %)"
        )

    def test_linear_interpolation_before_arrival(self):
        """
        Before the target is reached the joint angle must grow linearly at
        the commanded velocity.

        Check at 10 %, 30 %, 50 %, and 70 % of the analytic arrival time.
        Tolerance: ±2 % of expected position at each checkpoint.
        """
        joint = RevoluteJoint(axis_id="A1", angle=0.0)
        block = _MC_MoveAbsolute(target=self.TARGET, velocity=self.VELOCITY)

        t_analytic = self._analytic_arrival_time()
        n_steps_full = int(t_analytic / self.DT)
        positions = _run_simulation(joint, block, self.DT, n_steps_full)

        checkpoints = [0.10, 0.30, 0.50, 0.70]
        for frac in checkpoints:
            idx = int(frac * n_steps_full) - 1
            if idx < 0:
                continue
            t_check = (idx + 1) * self.DT
            expected = self.VELOCITY * t_check  # linear ramp
            actual = positions[idx]
            rel_err = abs(actual - expected) / max(abs(expected), 1e-12)
            assert rel_err <= 0.02, (
                f"At t={t_check:.4f} s ({frac*100:.0f} % of t_analytic): "
                f"expected {expected:.6f} rad, got {actual:.6f} rad "
                f"(rel_err={rel_err*100:.2f} %)"
            )

    def test_holds_at_target_after_arrival(self):
        """
        After arriving at the target the joint must stay at π/2.
        Check for the entire duration of the post-arrival window.
        """
        joint = RevoluteJoint(axis_id="A1", angle=0.0)
        block = _MC_MoveAbsolute(target=self.TARGET, velocity=self.VELOCITY)

        t_analytic = self._analytic_arrival_time()
        # Run well past the arrival time
        n_steps = int(2.0 * t_analytic / self.DT)
        positions = _run_simulation(joint, block, self.DT, n_steps)

        # After the arrival step all positions must be TARGET
        arrival_step = None
        for i, pos in enumerate(positions):
            if abs(pos - self.TARGET) < 1e-9:
                arrival_step = i
                break

        assert arrival_step is not None, "Joint never reached target"

        post_arrival = positions[arrival_step:]
        for i, pos in enumerate(post_arrival):
            assert abs(pos - self.TARGET) < 1e-9, (
                f"Joint drifted from target after arrival: "
                f"step={arrival_step + i}, pos={pos:.9f}, target={self.TARGET:.9f}"
            )


# ---------------------------------------------------------------------------
# T2 — Feedback injection
# ---------------------------------------------------------------------------


class TestFeedbackInjection:
    """The bridge must inject actual_position into block.axis_feedback each tick."""

    def test_feedback_equals_actual_position(self):
        joint = RevoluteJoint(axis_id="B1", angle=0.0)
        block = _MC_MoveAbsolute(target=1.0, velocity=2.0)
        body = RigidBody(name="body_B1", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        _tick_bridge(bridge, block, dt=0.01)
        assert block.axis_feedback == pytest.approx(bridge.actual_position)

    def test_feedback_updates_each_tick(self):
        joint = RevoluteJoint(axis_id="B2", angle=0.0)
        block = _MC_MoveAbsolute(target=2.0, velocity=1.0)
        body = RigidBody(name="body_B2", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        prev_feedback = block.axis_feedback
        for _ in range(5):
            _tick_bridge(bridge, block, dt=0.1)
        # After 5 × 0.1 s = 0.5 s at 1 rad/s the joint should be at 0.5 rad
        assert block.axis_feedback != prev_feedback
        assert block.axis_feedback == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# T3 — Done / Busy flags
# ---------------------------------------------------------------------------


class TestDoneBusyFlags:
    """Bridge updates Done/Busy on the block when it reaches the target."""

    def test_busy_true_before_arrival(self):
        joint = RevoluteJoint(axis_id="C1", angle=0.0)
        block = _MC_MoveAbsolute(target=math.pi / 2, velocity=1.0)
        body = RigidBody(name="body_C1", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        # One small step — should still be busy
        _tick_bridge(bridge, block, dt=0.001)
        assert block.Busy is True
        assert block.Done is False

    def test_done_true_at_arrival(self):
        joint = RevoluteJoint(axis_id="C2", angle=0.0)
        target = 0.01  # very small target so we reach it in a few steps
        block = _MC_MoveAbsolute(target=target, velocity=1.0)
        body = RigidBody(name="body_C2", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        # Run enough steps to reach target (target/velocity = 0.01 s at dt=0.001)
        for _ in range(20):
            _tick_bridge(bridge, block, dt=0.001)

        assert block.Done is True
        assert block.Busy is False


# ---------------------------------------------------------------------------
# T4 — Prismatic joint
# ---------------------------------------------------------------------------


class TestPrismaticJoint:
    """Bridge works identically for prismatic (linear) axes."""

    def test_prismatic_reaches_target(self):
        joint = PrismaticJoint(axis_id="P1", position=0.0)
        block = _MC_MoveAbsolute(target=0.10, velocity=0.05)  # 10 cm at 5 cm/s
        body = RigidBody(name="body_P1", joints=[joint])
        bridge = _make_bridge(joint, "prismatic", body)

        t_analytic = 0.10 / 0.05  # 2.0 s
        n_steps = int(t_analytic / 0.001) + 10
        for _ in range(n_steps):
            _tick_bridge(bridge, block, dt=0.001)

        assert bridge.actual_position == pytest.approx(0.10, abs=1e-9)
        assert block.Done is True

    def test_prismatic_feedback_injected(self):
        joint = PrismaticJoint(axis_id="P2", position=0.0)
        block = _MC_MoveAbsolute(target=0.50, velocity=1.0)
        body = RigidBody(name="body_P2", joints=[joint])
        bridge = _make_bridge(joint, "prismatic", body)

        _tick_bridge(bridge, block, dt=0.1)
        assert block.axis_feedback == pytest.approx(bridge.actual_position)


# ---------------------------------------------------------------------------
# T5 — Zero-velocity guard
# ---------------------------------------------------------------------------


class TestZeroVelocityGuard:
    """A block with zero velocity must not move the joint."""

    def test_zero_velocity_no_movement(self):
        joint = RevoluteJoint(axis_id="D1", angle=0.5)
        block = _MC_MoveAbsolute(target=1.0, velocity=0.0)
        body = RigidBody(name="body_D1", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        initial_pos = bridge.actual_position
        for _ in range(100):
            _tick_bridge(bridge, block, dt=0.001)

        assert bridge.actual_position == pytest.approx(initial_pos)


# ---------------------------------------------------------------------------
# T6 — Negative / reverse-direction motion
# ---------------------------------------------------------------------------


class TestReverseDirection:
    """Joint can move in the negative direction."""

    def test_moves_to_negative_target(self):
        joint = RevoluteJoint(axis_id="E1", angle=0.0)
        target = -math.pi / 4
        block = _MC_MoveAbsolute(target=target, velocity=1.0)
        body = RigidBody(name="body_E1", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)

        t_analytic = abs(target) / 1.0
        n_steps = int(t_analytic / 0.001) + 10
        for _ in range(n_steps):
            _tick_bridge(bridge, block, dt=0.001)

        assert bridge.actual_position == pytest.approx(target, abs=1e-9)


# ---------------------------------------------------------------------------
# T7 — Bridge instantiation errors
# ---------------------------------------------------------------------------


class TestInstantiationErrors:
    """Invalid joint_type raises ValueError."""

    def test_invalid_joint_type_raises(self):
        joint = RevoluteJoint(axis_id="F1")
        with pytest.raises(ValueError, match="joint_type"):
            PlcAxisToJoint("F1", "linear", joint)  # type: ignore[arg-type]

    def test_negative_dt_raises(self):
        joint = RevoluteJoint(axis_id="F2")
        block = _MC_MoveAbsolute(target=1.0, velocity=1.0)
        body = RigidBody(name="body_F2", joints=[joint])
        bridge = _make_bridge(joint, "revolute", body)
        with pytest.raises(ValueError, match="dt"):
            _tick_bridge(bridge, block, dt=-0.001)
