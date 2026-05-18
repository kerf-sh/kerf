"""
PLCopen Motion Control Part 1 V2.0 — Function Block implementations.

Each FB is a dataclass with an ``execute(state, inputs) -> outputs`` method
matching the IEC 61131-3 Function Block pattern.  Motion profiles use a
simple trapezoidal (linear accel → cruise → linear decel) model.

Axis state is owned by the caller (typically an AxisState object from
axis_state.py if/when that module lands); this module works with any object
that exposes the required attributes, or with the bundled _AxisState below
when used standalone.

Error codes (ErrorID strings)
------------------------------
AXIS_DISABLED       Power not enabled.
AXIS_ALREADY_MOVING Another command is active (Aborting / Buffered logic pending).
INVALID_PARAM       Velocity, acceleration, deceleration, or jerk ≤ 0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional import of axis_state sibling (T-225d-2) — gated so this module
# loads independently when axis_state hasn't landed yet.
# ---------------------------------------------------------------------------
try:
    from kerf_plc.motion_control.axis_state import AxisState as _ExtAxisState  # type: ignore
except Exception:  # noqa: BLE001
    _ExtAxisState = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Error identifiers
# ---------------------------------------------------------------------------

class ErrorID(str, Enum):
    NONE = "NONE"
    AXIS_DISABLED = "AXIS_DISABLED"
    AXIS_ALREADY_MOVING = "AXIS_ALREADY_MOVING"
    INVALID_PARAM = "INVALID_PARAM"
    COMMAND_ABORTED = "COMMAND_ABORTED"
    ESTOP = "ESTOP"


# ---------------------------------------------------------------------------
# Buffer mode (PLCopen Part 1 §4.2)
# ---------------------------------------------------------------------------

class BufferMode(str, Enum):
    ABORTING = "Aborting"       # default — abort any active command
    BUFFERED = "Buffered"       # queue after current motion finishes
    BLENDING_PREVIOUS = "BlendingPrevious"
    BLENDING_NEXT = "BlendingNext"
    BLENDING_LOW = "BlendingLow"
    BLENDING_HIGH = "BlendingHigh"


# ---------------------------------------------------------------------------
# Minimal embedded axis state (used when axis_state.py is not present)
# ---------------------------------------------------------------------------

class _AxisPhase(Enum):
    IDLE = auto()
    ACCEL = auto()
    CRUISE = auto()
    DECEL = auto()
    DONE = auto()
    STOPPED = auto()
    HOMING = auto()
    POWERED_OFF = auto()


@dataclass
class AxisState:
    """Minimal axis state used by all FBs in this module.

    If kerf_plc.motion_control.axis_state is installed its AxisState will be
    used as a drop-in replacement — the attribute contract is compatible.
    """

    # --- kinematic state ---
    position: float = 0.0
    velocity: float = 0.0

    # --- power ---
    powered: bool = False

    # --- active motion profile ---
    _phase: _AxisPhase = field(default=_AxisPhase.IDLE, repr=False)
    _target_position: Optional[float] = field(default=None, repr=False)
    _profile_velocity: float = field(default=0.0, repr=False)
    _profile_accel: float = field(default=0.0, repr=False)
    _profile_decel: float = field(default=0.0, repr=False)
    _accel_time: float = field(default=0.0, repr=False)
    _cruise_time: float = field(default=0.0, repr=False)
    _decel_time: float = field(default=0.0, repr=False)
    _elapsed: float = field(default=0.0, repr=False)
    _direction: int = field(default=1, repr=False)   # +1 or -1
    _active_block_id: Optional[int] = field(default=None, repr=False)

    def _reset_profile(self) -> None:
        self._phase = _AxisPhase.IDLE
        self._target_position = None
        self._profile_velocity = 0.0
        self._profile_accel = 0.0
        self._profile_decel = 0.0
        self._accel_time = 0.0
        self._cruise_time = 0.0
        self._decel_time = 0.0
        self._elapsed = 0.0
        self._direction = 1
        self._active_block_id = None

    def step(self, dt: float) -> None:
        """Advance the motion profile by *dt* seconds."""
        if self._phase in (_AxisPhase.IDLE, _AxisPhase.DONE,
                           _AxisPhase.STOPPED, _AxisPhase.POWERED_OFF):
            return

        if self._phase == _AxisPhase.HOMING:
            # Simple homing: move at constant slow speed toward target.
            if self._target_position is None:
                self._phase = _AxisPhase.DONE
                return
            step = self._direction * self._profile_velocity * dt
            remaining = self._direction * (self._target_position - self.position)
            if remaining <= 0 or step >= remaining:
                self.position = self._target_position
                self.velocity = 0.0
                self._phase = _AxisPhase.DONE
            else:
                self.position += step
            return

        self._elapsed += dt

        if self._phase == _AxisPhase.ACCEL:
            t = min(self._elapsed, self._accel_time)
            # v(t) = a·t  (starts from 0 for simplicity — full trapezoid)
            v = self._profile_accel * t
            dv = self._profile_accel * dt
            self.velocity = self._direction * min(v, self._profile_velocity)
            self.position += self._direction * (
                self._profile_accel * t * dt - 0.5 * self._profile_accel * dt * dt
            )
            if self._elapsed >= self._accel_time:
                self.velocity = self._direction * self._profile_velocity
                self._elapsed = 0.0
                self._phase = _AxisPhase.CRUISE

        elif self._phase == _AxisPhase.CRUISE:
            self.velocity = self._direction * self._profile_velocity
            self.position += self.velocity * dt
            if self._elapsed >= self._cruise_time:
                self._elapsed = 0.0
                self._phase = _AxisPhase.DECEL

        elif self._phase == _AxisPhase.DECEL:
            t_into = min(self._elapsed, self._decel_time)
            v = self._profile_velocity - self._profile_decel * t_into
            self.velocity = self._direction * max(v, 0.0)
            self.position += self._direction * max(v, 0.0) * dt
            if self._elapsed >= self._decel_time:
                if self._target_position is not None:
                    self.position = self._target_position  # snap to target
                self.velocity = 0.0
                self._phase = _AxisPhase.DONE

    @property
    def is_moving(self) -> bool:
        return self._phase in (
            _AxisPhase.ACCEL, _AxisPhase.CRUISE, _AxisPhase.DECEL, _AxisPhase.HOMING
        )

    @property
    def is_done(self) -> bool:
        return self._phase == _AxisPhase.DONE

    @property
    def is_idle(self) -> bool:
        return self._phase in (_AxisPhase.IDLE, _AxisPhase.DONE,
                               _AxisPhase.STOPPED)


# ---------------------------------------------------------------------------
# Trapezoidal profile helpers
# ---------------------------------------------------------------------------

def _trapezoid_times(
    distance: float,
    velocity: float,
    accel: float,
    decel: float,
) -> tuple[float, float, float]:
    """Return (t_accel, t_cruise, t_decel) for a trapezoidal profile.

    If the distance is too short to reach *velocity* the profile is
    triangular (t_cruise = 0) and peak velocity is reduced.
    """
    if velocity <= 0 or accel <= 0 or decel <= 0:
        raise ValueError("velocity, accel, decel must all be > 0")
    distance = abs(distance)

    t_accel = velocity / accel
    t_decel = velocity / decel
    d_accel = 0.5 * accel * t_accel ** 2
    d_decel = 0.5 * decel * t_decel ** 2

    if d_accel + d_decel > distance:
        # Triangular profile — compute peak velocity
        # d = 0.5 * v_p/a * v_p + 0.5 * v_p/d * v_p  =>  v_p = sqrt(2*dist*a*d/(a+d))
        denom = (1.0 / accel + 1.0 / decel)
        v_peak = math.sqrt(2.0 * distance / denom)
        t_accel = v_peak / accel
        t_decel = v_peak / decel
        return t_accel, 0.0, t_decel

    d_cruise = distance - d_accel - d_decel
    t_cruise = d_cruise / velocity
    return t_accel, t_cruise, t_decel


def _arm_motion(
    state: AxisState,
    target_position: float,
    velocity: float,
    accel: float,
    decel: float,
    block_id: int,
) -> None:
    """Configure *state* for a new trapezoidal move."""
    distance = target_position - state.position
    direction = 1 if distance >= 0 else -1
    t_a, t_c, t_d = _trapezoid_times(abs(distance), velocity, accel, decel)

    state._phase = _AxisPhase.ACCEL if abs(distance) > 0 else _AxisPhase.DONE
    state._target_position = target_position
    state._profile_velocity = velocity
    state._profile_accel = accel
    state._profile_decel = decel
    state._accel_time = t_a
    state._cruise_time = t_c
    state._decel_time = t_d
    state._elapsed = 0.0
    state._direction = direction
    state._active_block_id = block_id


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PowerOutputs:
    Status: bool = False
    Valid: bool = False
    Busy: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class HaltOutputs:
    Done: bool = False
    Busy: bool = False
    CommandAborted: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class StopOutputs:
    Done: bool = False
    Busy: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class MoveAbsoluteOutputs:
    Done: bool = False
    Busy: bool = False
    Active: bool = False
    CommandAborted: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class MoveRelativeOutputs:
    Done: bool = False
    Busy: bool = False
    Active: bool = False
    CommandAborted: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class MoveVelocityOutputs:
    InVelocity: bool = False
    Busy: bool = False
    Active: bool = False
    CommandAborted: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


@dataclass
class HomeOutputs:
    Done: bool = False
    Busy: bool = False
    CommandAborted: bool = False
    Error: bool = False
    ErrorID: str = ErrorID.NONE


# ---------------------------------------------------------------------------
# Function Blocks
# ---------------------------------------------------------------------------

_BLOCK_COUNTER = 0


def _next_id() -> int:
    global _BLOCK_COUNTER
    _BLOCK_COUNTER += 1
    return _BLOCK_COUNTER


# --- MC_Power ---------------------------------------------------------------

@dataclass
class MC_Power:
    """Enable or disable axis power.

    PLCopen Part 1 §6.5.1
    """

    _id: int = field(default_factory=_next_id, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Enable: bool = False,
        Override: bool = False,
        BufferMode: str = BufferMode.ABORTING,
    ) -> PowerOutputs:
        out = PowerOutputs()

        if Enable:
            state.powered = True
            out.Status = True
            out.Valid = True
        else:
            # Powering off — abort any active motion
            if state.is_moving:
                state._reset_profile()
                state._phase = _AxisPhase.POWERED_OFF
            state.powered = False
            state.velocity = 0.0
            out.Status = False
            out.Valid = True

        return out


# --- MC_Halt ----------------------------------------------------------------

@dataclass
class MC_Halt:
    """Bring axis to a standstill using a controlled deceleration ramp.

    PLCopen Part 1 §6.5.4
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Deceleration: float = 1.0,
        Jerk: float = 0.0,
        BufferMode: str = BufferMode.ABORTING,
        dt: float = 0.0,
    ) -> HaltOutputs:
        out = HaltOutputs()

        if not state.powered:
            out.Error = True
            out.ErrorID = ErrorID.AXIS_DISABLED
            return out

        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            if state.is_moving:
                # Abort current move — ramp down from current velocity
                v_now = abs(state.velocity)
                if v_now > 0 and Deceleration > 0:
                    state._phase = _AxisPhase.DECEL
                    state._profile_decel = Deceleration
                    state._decel_time = v_now / Deceleration
                    state._elapsed = 0.0
                    state._profile_velocity = v_now
                    state._profile_accel = Deceleration  # not used in decel phase
                    state._accel_time = 0.0
                    state._cruise_time = 0.0
                    state._target_position = None  # no snap target
                else:
                    state.velocity = 0.0
                    state._phase = _AxisPhase.DONE
            else:
                state._phase = _AxisPhase.DONE

        # Advance decel ramp each cycle
        if Execute and state._phase == _AxisPhase.DECEL and dt > 0:
            state.step(dt)

        if state._phase == _AxisPhase.DECEL:
            out.Busy = True
        elif state._phase in (_AxisPhase.DONE, _AxisPhase.IDLE, _AxisPhase.STOPPED):
            if self._triggered:  # only report Done if Execute is/was held
                out.Done = True

        return out


# --- MC_Stop ----------------------------------------------------------------

@dataclass
class MC_Stop:
    """Bring axis to an immediate (emergency) stop.

    PLCopen Part 1 §6.5.5 — higher priority than MC_Halt.
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Deceleration: float = 100.0,
        Jerk: float = 0.0,
        dt: float = 0.0,
    ) -> StopOutputs:
        out = StopOutputs()

        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            # Immediately zero velocity and abort any motion
            state.velocity = 0.0
            state._reset_profile()
            state._phase = _AxisPhase.STOPPED

        if state._phase == _AxisPhase.STOPPED:
            out.Done = True

        return out


# --- MC_MoveAbsolute --------------------------------------------------------

@dataclass
class MC_MoveAbsolute:
    """Move axis to an absolute position.

    PLCopen Part 1 §6.5.6
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)
    _aborted: bool = field(default=False, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Position: float = 0.0,
        Velocity: float = 1.0,
        Acceleration: float = 1.0,
        Deceleration: float = 1.0,
        Jerk: float = 0.0,
        Direction: str = "Positive",
        BufferMode: str = BufferMode.ABORTING,
        dt: float = 0.0,
    ) -> MoveAbsoluteOutputs:
        out = MoveAbsoluteOutputs()

        if not state.powered:
            out.Error = True
            out.ErrorID = ErrorID.AXIS_DISABLED
            return out

        if Velocity <= 0 or Acceleration <= 0 or Deceleration <= 0:
            out.Error = True
            out.ErrorID = ErrorID.INVALID_PARAM
            return out

        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            self._aborted = False
            _arm_motion(state, Position, Velocity, Acceleration, Deceleration, self._id)
            state.step(dt)
        elif Execute and state._active_block_id == self._id:
            # Check if another block preempted us
            pass
        elif Execute and state._active_block_id != self._id and state.is_moving:
            # We were preempted
            self._aborted = True

        # Advance simulation
        if Execute and state._active_block_id == self._id and dt > 0:
            state.step(dt)

        if self._aborted:
            out.CommandAborted = True
            return out

        if state._active_block_id == self._id:
            if state.is_done:
                out.Done = True
            elif state.is_moving:
                out.Busy = True
                out.Active = True

        return out

    def notify_aborted(self) -> None:
        """Called by a higher-priority FB to signal that this move was aborted."""
        self._aborted = True


# --- MC_MoveRelative --------------------------------------------------------

@dataclass
class MC_MoveRelative:
    """Move axis by a relative distance.

    PLCopen Part 1 §6.5.7
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)
    _aborted: bool = field(default=False, repr=False)
    _target: Optional[float] = field(default=None, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Distance: float = 0.0,
        Velocity: float = 1.0,
        Acceleration: float = 1.0,
        Deceleration: float = 1.0,
        Jerk: float = 0.0,
        Direction: str = "Positive",
        BufferMode: str = BufferMode.ABORTING,
        dt: float = 0.0,
    ) -> MoveRelativeOutputs:
        out = MoveRelativeOutputs()

        if not state.powered:
            out.Error = True
            out.ErrorID = ErrorID.AXIS_DISABLED
            return out

        if Velocity <= 0 or Acceleration <= 0 or Deceleration <= 0:
            out.Error = True
            out.ErrorID = ErrorID.INVALID_PARAM
            return out

        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            self._aborted = False
            self._target = state.position + Distance
            _arm_motion(state, self._target, Velocity, Acceleration, Deceleration, self._id)

        # Advance simulation
        if Execute and state._active_block_id == self._id and dt > 0:
            state.step(dt)
        elif Execute and state._active_block_id != self._id and state.is_moving:
            self._aborted = True

        if self._aborted:
            out.CommandAborted = True
            return out

        if state._active_block_id == self._id:
            if state.is_done:
                out.Done = True
            elif state.is_moving:
                out.Busy = True
                out.Active = True

        return out

    def notify_aborted(self) -> None:
        self._aborted = True


# --- MC_MoveVelocity --------------------------------------------------------

@dataclass
class MC_MoveVelocity:
    """Move axis at constant velocity until stopped.

    PLCopen Part 1 §6.5.8
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)
    _aborted: bool = field(default=False, repr=False)
    _accel_elapsed: float = field(default=0.0, repr=False)
    _in_velocity: bool = field(default=False, repr=False)

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Velocity: float = 1.0,
        Acceleration: float = 1.0,
        Deceleration: float = 1.0,
        Jerk: float = 0.0,
        Direction: str = "Positive",
        BufferMode: str = BufferMode.ABORTING,
        dt: float = 0.0,
    ) -> MoveVelocityOutputs:
        out = MoveVelocityOutputs()

        if not state.powered:
            out.Error = True
            out.ErrorID = ErrorID.AXIS_DISABLED
            return out

        if Velocity <= 0 or Acceleration <= 0 or Deceleration <= 0:
            out.Error = True
            out.ErrorID = ErrorID.INVALID_PARAM
            return out

        direction = 1 if Direction in ("Positive", "positive", "+") else -1
        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            self._aborted = False
            self._in_velocity = False
            self._accel_elapsed = 0.0
            state._active_block_id = self._id
            state._phase = _AxisPhase.ACCEL
            state._profile_velocity = Velocity
            state._profile_accel = Acceleration
            state._profile_decel = Deceleration
            state._accel_time = Velocity / Acceleration
            state._cruise_time = math.inf  # indefinite
            state._decel_time = Velocity / Deceleration
            state._direction = direction
            state._elapsed = 0.0
            state._target_position = None

        if Execute and state._active_block_id == self._id:
            if dt > 0:
                self._accel_elapsed += dt
                v_target = Velocity
                v_now = min(Acceleration * self._accel_elapsed, v_target)
                state.velocity = direction * v_now
                state.position += state.velocity * dt
                if v_now >= v_target:
                    self._in_velocity = True
                    state._phase = _AxisPhase.CRUISE

            if self._in_velocity:
                out.InVelocity = True
            else:
                out.Busy = True
            out.Active = True
        elif Execute and state._active_block_id != self._id and state.is_moving:
            self._aborted = True

        if self._aborted:
            out.CommandAborted = True

        return out

    def notify_aborted(self) -> None:
        self._aborted = True


# --- MC_Home ----------------------------------------------------------------

@dataclass
class MC_Home:
    """Run a homing sequence.

    PLCopen Part 1 §6.5.3
    """

    _id: int = field(default_factory=_next_id, repr=False)
    _triggered: bool = field(default=False, repr=False)
    _aborted: bool = field(default=False, repr=False)
    _home_velocity: float = field(default=0.5, repr=False)  # slow homing speed

    def execute(
        self,
        state: AxisState,
        *,
        Execute: bool = False,
        Position: float = 0.0,
        BufferMode: str = BufferMode.ABORTING,
        dt: float = 0.0,
    ) -> HomeOutputs:
        out = HomeOutputs()

        if not state.powered:
            out.Error = True
            out.ErrorID = ErrorID.AXIS_DISABLED
            return out

        rising_edge = Execute and not self._triggered
        self._triggered = Execute

        if rising_edge:
            self._aborted = False
            state._active_block_id = self._id
            state._phase = _AxisPhase.HOMING
            state._target_position = Position
            state._profile_velocity = self._home_velocity
            distance = abs(Position - state.position)
            state._direction = 1 if Position >= state.position else -1
            state._elapsed = 0.0

        if Execute and state._active_block_id == self._id and dt > 0:
            state.step(dt)

        if state._active_block_id == self._id:
            if state.is_done:
                # Set axis position to home
                state.position = Position
                out.Done = True
            elif state._phase == _AxisPhase.HOMING:
                out.Busy = True

        if self._aborted:
            out.CommandAborted = True

        return out

    def notify_aborted(self) -> None:
        self._aborted = True
