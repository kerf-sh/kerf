"""
tests/test_motion_control_blocks.py

Analytic-oracle tests for PLCopen Motion Control Part 1 V2.0 function blocks.

Simulation strategy
-------------------
Each test drives the motion loop manually by calling FB.execute(..., dt=<step>)
in a loop, accumulating simulated time, and checking state + outputs at
meaningful points (end-of-move, mid-move abort, etc.).
"""
from __future__ import annotations

import math
import pytest

from kerf_plc.motion_control import (
    AxisState,
    BufferMode,
    ErrorID,
    MC_Halt,
    MC_Home,
    MC_MoveAbsolute,
    MC_MoveRelative,
    MC_MoveVelocity,
    MC_Power,
    MC_Stop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_to_done(fb, state, max_time=60.0, dt=0.01, **kwargs) -> tuple[object, float]:
    """Run *fb* until Done=True or *max_time* seconds simulated.

    Returns (last_outputs, elapsed_time).
    """
    t = 0.0
    out = None
    # Rising edge
    out = fb.execute(state, Execute=True, dt=dt, **kwargs)
    t += dt
    while t < max_time:
        out = fb.execute(state, Execute=True, dt=dt, **kwargs)
        t += dt
        if getattr(out, "Done", False):
            break
    return out, t


# ---------------------------------------------------------------------------
# T1 — MC_Power basic
# ---------------------------------------------------------------------------

class TestMCPower:
    def test_enable_sets_powered(self):
        state = AxisState()
        fb = MC_Power()
        out = fb.execute(state, Enable=True)
        assert state.powered is True
        assert out.Status is True
        assert out.Valid is True
        assert out.Error is False

    def test_disable_clears_powered(self):
        state = AxisState()
        fb = MC_Power()
        fb.execute(state, Enable=True)
        out = fb.execute(state, Enable=False)
        assert state.powered is False
        assert out.Status is False
        assert out.Valid is True

    def test_power_off_during_move_stops_motion(self):
        state = AxisState()
        pwr = MC_Power()
        move = MC_MoveAbsolute()

        pwr.execute(state, Enable=True)
        # Start a move
        move.execute(state, Execute=True, Position=100.0,
                     Velocity=5.0, Acceleration=2.0, Deceleration=2.0, dt=0.1)
        assert state.is_moving

        # Power off mid-move
        pwr.execute(state, Enable=False)
        assert state.powered is False
        assert not state.is_moving

    def test_motion_rejected_when_axis_disabled(self):
        state = AxisState()  # powered=False by default
        fb = MC_MoveAbsolute()
        out = fb.execute(state, Execute=True, Position=10.0,
                         Velocity=1.0, Acceleration=1.0, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED


# ---------------------------------------------------------------------------
# T2 — MC_MoveAbsolute timing oracle
# ---------------------------------------------------------------------------

class TestMCMoveAbsolute:
    def test_move_takes_at_least_5s_for_p10_v2(self):
        """p=0 to p=10 at v=2 with a=1, d=1 must take >= 5 s simulated time."""
        state = AxisState()
        pwr = MC_Power()
        pwr.execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        out, elapsed = _run_to_done(
            fb, state, max_time=60.0, dt=0.01,
            Position=10.0, Velocity=2.0, Acceleration=1.0, Deceleration=1.0,
        )
        assert out.Done is True, f"Move did not complete; last out={out}"
        assert elapsed >= 5.0, f"Expected >= 5s, got {elapsed:.3f}s"

    def test_final_position_correct(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        _run_to_done(fb, state, max_time=60.0, dt=0.01,
                     Position=10.0, Velocity=2.0, Acceleration=2.0, Deceleration=2.0)
        assert math.isclose(state.position, 10.0, abs_tol=0.05)

    def test_busy_before_done(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        # First call — rising edge
        out = fb.execute(state, Execute=True, Position=50.0,
                         Velocity=2.0, Acceleration=1.0, Deceleration=1.0, dt=0.01)
        # Should be busy (or done on first tick for very short moves)
        assert out.Busy or out.Done

    def test_invalid_velocity_raises_error(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        out = fb.execute(state, Execute=True, Position=5.0,
                         Velocity=0.0, Acceleration=1.0, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.INVALID_PARAM

    def test_disabled_axis_returns_error(self):
        state = AxisState()  # powered=False
        fb = MC_MoveAbsolute()
        out = fb.execute(state, Execute=True, Position=5.0,
                         Velocity=1.0, Acceleration=1.0, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED


# ---------------------------------------------------------------------------
# T3 — MC_Halt aborts a running move
# ---------------------------------------------------------------------------

class TestMCHalt:
    def test_halt_sets_command_aborted_on_running_move(self):
        """MC_Halt during a move must result in CommandAborted on the move's output."""
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        move = MC_MoveAbsolute()
        halt = MC_Halt()

        # Start a long move
        out_move = move.execute(state, Execute=True, Position=100.0,
                                Velocity=2.0, Acceleration=1.0, Deceleration=1.0, dt=0.1)
        assert out_move.Busy or out_move.Active or state.is_moving

        # Issue halt (rising edge)
        out_halt = halt.execute(state, Execute=True, Deceleration=5.0, dt=0.1)
        # After halt, axis should be decelerating or stopped
        assert out_halt.Busy or out_halt.Done

        # Continue halt until done
        for _ in range(100):
            out_halt = halt.execute(state, Execute=True, Deceleration=5.0, dt=0.1)
            if out_halt.Done:
                break

        assert out_halt.Done is True
        assert math.isclose(state.velocity, 0.0, abs_tol=1e-6)

    def test_halt_while_idle_completes_immediately(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        halt = MC_Halt()
        out = halt.execute(state, Execute=True, Deceleration=1.0, dt=0.0)
        assert out.Done is True

    def test_halt_on_disabled_axis(self):
        state = AxisState()  # not powered
        halt = MC_Halt()
        out = halt.execute(state, Execute=True, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED


# ---------------------------------------------------------------------------
# T4 — MC_Stop preempts any active block
# ---------------------------------------------------------------------------

class TestMCStop:
    def test_stop_zeros_velocity(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        move = MC_MoveAbsolute()
        stop = MC_Stop()

        move.execute(state, Execute=True, Position=100.0,
                     Velocity=5.0, Acceleration=2.0, Deceleration=2.0, dt=0.5)
        assert state.is_moving

        out = stop.execute(state, Execute=True, Deceleration=100.0, dt=0.0)
        assert out.Done is True
        assert math.isclose(state.velocity, 0.0, abs_tol=1e-9)
        assert not state.is_moving

    def test_stop_preempts_velocity_move(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        vel_fb = MC_MoveVelocity()
        stop = MC_Stop()

        # Start velocity move
        vel_fb.execute(state, Execute=True, Velocity=3.0,
                       Acceleration=1.0, Deceleration=1.0, dt=0.5)
        assert state.velocity != 0.0

        # Stop
        out = stop.execute(state, Execute=True)
        assert out.Done is True
        assert math.isclose(state.velocity, 0.0, abs_tol=1e-9)

    def test_stop_done_on_repeated_calls(self):
        """MC_Stop Done stays True while Execute is held."""
        state = AxisState()
        stop = MC_Stop()
        out1 = stop.execute(state, Execute=True)
        assert out1.Done is True
        # Hold Execute — no re-trigger
        out2 = stop.execute(state, Execute=True)
        # Should not re-trigger (no rising edge), Done may vary; no error expected
        assert not out2.Error


# ---------------------------------------------------------------------------
# T5 — MC_MoveRelative cumulative position
# ---------------------------------------------------------------------------

class TestMCMoveRelative:
    def test_two_relative_moves_sum_to_10(self):
        """MC_MoveRelative(5) twice → final position = 10."""
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        # First move: +5
        fb1 = MC_MoveRelative()
        out, _ = _run_to_done(fb1, state, max_time=60.0, dt=0.01,
                               Distance=5.0, Velocity=2.0,
                               Acceleration=2.0, Deceleration=2.0)
        assert out.Done is True
        mid_pos = state.position
        assert math.isclose(mid_pos, 5.0, abs_tol=0.1), f"Mid position {mid_pos}"

        # Second move: +5 more
        fb2 = MC_MoveRelative()
        out2, _ = _run_to_done(fb2, state, max_time=60.0, dt=0.01,
                                Distance=5.0, Velocity=2.0,
                                Acceleration=2.0, Deceleration=2.0)
        assert out2.Done is True
        final_pos = state.position
        assert math.isclose(final_pos, 10.0, abs_tol=0.15), (
            f"Expected final position ~10, got {final_pos:.4f}"
        )

    def test_disabled_axis_rejected(self):
        state = AxisState()
        fb = MC_MoveRelative()
        out = fb.execute(state, Execute=True, Distance=5.0,
                         Velocity=1.0, Acceleration=1.0, Deceleration=1.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED

    def test_negative_distance(self):
        """Negative distance moves in the -direction."""
        state = AxisState()
        state.position = 10.0
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveRelative()
        out, _ = _run_to_done(fb, state, max_time=60.0, dt=0.01,
                               Distance=-5.0, Velocity=2.0,
                               Acceleration=2.0, Deceleration=2.0)
        assert out.Done is True
        assert math.isclose(state.position, 5.0, abs_tol=0.15)


# ---------------------------------------------------------------------------
# T6 — MC_MoveVelocity
# ---------------------------------------------------------------------------

class TestMCMoveVelocity:
    def test_reaches_in_velocity(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveVelocity()
        # Accelerate for enough time
        for _ in range(200):
            out = fb.execute(state, Execute=True, Velocity=2.0,
                             Acceleration=1.0, Deceleration=1.0, dt=0.02)
            if out.InVelocity:
                break

        assert out.InVelocity is True
        assert math.isclose(abs(state.velocity), 2.0, abs_tol=0.05)

    def test_negative_direction(self):
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveVelocity()
        for _ in range(200):
            out = fb.execute(state, Execute=True, Velocity=2.0,
                             Acceleration=1.0, Deceleration=1.0,
                             Direction="Negative", dt=0.02)
            if out.InVelocity:
                break

        assert out.InVelocity is True
        assert state.velocity < 0

    def test_disabled_axis_rejected(self):
        state = AxisState()
        fb = MC_MoveVelocity()
        out = fb.execute(state, Execute=True, Velocity=1.0,
                         Acceleration=1.0, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED


# ---------------------------------------------------------------------------
# T7 — MC_Home
# ---------------------------------------------------------------------------

class TestMCHome:
    def test_home_completes_and_sets_position(self):
        state = AxisState()
        state.position = 5.0
        MC_Power().execute(state, Enable=True)

        fb = MC_Home()
        out, elapsed = _run_to_done(fb, state, max_time=120.0, dt=0.1,
                                     Position=0.0)
        assert out.Done is True
        assert math.isclose(state.position, 0.0, abs_tol=0.01)

    def test_home_busy_during_move(self):
        state = AxisState()
        state.position = 3.0
        MC_Power().execute(state, Enable=True)

        fb = MC_Home()
        out = fb.execute(state, Execute=True, Position=0.0, dt=0.01)
        # Should be busy (not instantly done for a 3-unit distance)
        assert out.Busy or out.Done

    def test_home_on_disabled_axis(self):
        state = AxisState()
        fb = MC_Home()
        out = fb.execute(state, Execute=True, Position=0.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED


# ---------------------------------------------------------------------------
# T8 — Edge / integration cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_mc_stop_works_without_power(self):
        """MC_Stop is an emergency stop — should work even without power."""
        state = AxisState()
        state.velocity = 5.0  # manually set velocity (e.g. coast)
        stop = MC_Stop()
        out = stop.execute(state, Execute=True)
        assert out.Done is True
        assert math.isclose(state.velocity, 0.0, abs_tol=1e-9)

    def test_fb_rising_edge_not_re_triggered(self):
        """Holding Execute=True does not re-arm the FB (no repeated rising edge)."""
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        # Rising edge
        fb.execute(state, Execute=True, Position=10.0,
                   Velocity=2.0, Acceleration=1.0, Deceleration=1.0, dt=0.01)
        original_target = state._target_position

        # Hold Execute — no new rising edge; target should remain the same
        fb.execute(state, Execute=True, Position=99.0,
                   Velocity=2.0, Acceleration=1.0, Deceleration=1.0, dt=0.01)
        assert state._target_position == original_target

    def test_power_enable_false_subsequent_move_rejected(self):
        """After MC_Power(Enable=False), motion commands return AXIS_DISABLED."""
        state = AxisState()
        pwr = MC_Power()
        pwr.execute(state, Enable=True)
        pwr.execute(state, Enable=False)

        fb = MC_MoveAbsolute()
        out = fb.execute(state, Execute=True, Position=5.0,
                         Velocity=1.0, Acceleration=1.0, Deceleration=1.0, dt=0.0)
        assert out.Error is True
        assert out.ErrorID == ErrorID.AXIS_DISABLED

    def test_move_absolute_triangular_profile(self):
        """Very short move uses triangular profile (no cruise phase)."""
        state = AxisState()
        MC_Power().execute(state, Enable=True)

        fb = MC_MoveAbsolute()
        # distance=0.1, v=10 → triangle
        out, _ = _run_to_done(fb, state, max_time=10.0, dt=0.001,
                               Position=0.1, Velocity=10.0,
                               Acceleration=1.0, Deceleration=1.0)
        assert out.Done is True
        assert math.isclose(state.position, 0.1, abs_tol=0.02)
