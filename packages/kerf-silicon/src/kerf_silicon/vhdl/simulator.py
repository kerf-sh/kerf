"""Event-driven VHDL behavioural simulator with delta cycles.

Architecture overview
---------------------
* Time is tracked in picoseconds (int).  Delta cycles are sub-time steps:
  each physical time can have an unbounded number of delta steps, all
  sharing the same ``now`` timestamp.
* A ``Signal`` holds the current *driving* value and the *next* (scheduled)
  value.  Whenever a process writes to a signal the assignment is scheduled
  into the event queue at (time + delta, delta+1) or at (time + delay, 0)
  for a real delay.
* The ``Scheduler`` runs the event loop: wake every process that is sensitive
  to a signal that changed, apply delta updates, repeat until stable, then
  advance physical time.

Usage example
-------------
    from kerf_silicon.vhdl.simulator import Simulator, Signal

    # Build a process manually (no parser dependency):
    sim = Simulator()
    a = sim.add_signal("a", "0")
    b = sim.add_signal("b", "1")
    out = sim.add_signal("out", "U")

    def and_gate():
        from kerf_silicon.vhdl.std_logic import and2
        out.drive(and2(a.value, b.value))

    sim.add_process(and_gate, sensitivity=[a, b])
    sim.run_until(0)          # settle at T=0 (delta cycles)
    assert out.value == "0"
"""
from __future__ import annotations

import heapq
from collections import defaultdict
from typing import Callable, Iterable

from kerf_silicon.vhdl.std_logic import resolve, StdLogic


class Signal:
    """A single VHDL signal with an IEEE 1164 std_logic type.

    Driving the signal schedules a future update in the owning simulator.
    Multiple concurrent drivers are resolved via IEEE 1164 bus resolution.
    """

    def __init__(self, name: str, initial: StdLogic = "U") -> None:
        self.name = name
        self._value: StdLogic = initial
        # Pending drivers scheduled for the *next* delta cycle.
        self._pending_drivers: list[StdLogic] = []
        # Back-reference to the simulator — set when add_signal() is called.
        self._sim: "Simulator | None" = None

    @property
    def value(self) -> StdLogic:
        return self._value

    def drive(self, new_value: StdLogic, delay_ps: int = 0) -> None:
        """Schedule an update to this signal.

        delay_ps=0  -> delta-cycle update (inertial, this delta)
        delay_ps>0  -> real-time transport delay in picoseconds
        """
        if self._sim is None:
            raise RuntimeError("Signal is not attached to a simulator")
        self._sim._schedule_drive(self, new_value, delay_ps)

    def _apply(self, new_value: StdLogic) -> bool:
        """Commit a resolved value. Returns True if the signal changed."""
        if new_value != self._value:
            self._value = new_value
            return True
        return False


class _Event:
    """An immutable timestamped event in the scheduler queue."""

    __slots__ = ("time_ps", "delta", "signal", "value", "_seq")

    def __init__(
        self,
        time_ps: int,
        delta: int,
        signal: Signal,
        value: StdLogic,
        seq: int,
    ) -> None:
        self.time_ps = time_ps
        self.delta = delta
        self.signal = signal
        self.value = value
        self._seq = seq  # tie-breaker for heap ordering

    def __lt__(self, other: "_Event") -> bool:
        return (self.time_ps, self.delta, self._seq) < (
            other.time_ps,
            other.delta,
            other._seq,
        )


class Simulator:
    """Behavioural VHDL event-driven simulator.

    Parameters
    ----------
    architecture:
        Optional opaque object (e.g. an AST node from the parser) for
        future use.  Currently unused by the simulator core; user code
        must wire up signals and processes manually or via a higher-level
        elaborator.
    max_delta:
        Maximum number of delta cycles at a single physical time before
        raising ``SimulationError``.  Protects against delta-cycle loops
        (oscillating combinational feedback).
    """

    def __init__(
        self,
        architecture: object = None,
        max_delta: int = 10_000,
    ) -> None:
        self.architecture = architecture
        self.max_delta = max_delta
        self.now: int = 0           # current simulation time in ps
        self._delta: int = 0        # current delta-cycle index
        self._signals: dict[str, Signal] = {}
        self._processes: list[tuple[Callable[[], None], set[Signal]]] = []
        # Sensitivity map: signal -> list of processes that wake on it
        self._sensitivity: dict[Signal, list[Callable[[], None]]] = defaultdict(list)
        self._event_queue: list[_Event] = []
        self._seq_counter: int = 0
        self._running = False
        # Buffered drives per signal for the current delta
        # (signal -> list of raw drive values before resolution)
        self._drive_buffer: dict[Signal, list[StdLogic]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_signal(self, name: str, initial: StdLogic = "U") -> Signal:
        """Create and register a new signal."""
        if name in self._signals:
            raise ValueError(f"Signal {name!r} already exists")
        sig = Signal(name, initial)
        sig._sim = self
        self._signals[name] = sig
        return sig

    def get_signal(self, name: str) -> Signal:
        """Retrieve a registered signal by name."""
        return self._signals[name]

    def add_process(
        self,
        fn: Callable[[], None],
        sensitivity: Iterable[Signal] | None = None,
    ) -> None:
        """Register a process function with an optional sensitivity list.

        If ``sensitivity`` is None or empty the process is treated as a
        *concurrent* process that runs once at T=0 delta=0 only.
        """
        sens_set: set[Signal] = set(sensitivity) if sensitivity else set()
        self._processes.append((fn, sens_set))
        for sig in sens_set:
            self._sensitivity[sig].append(fn)

    def run_until(self, end_time_ps: int) -> None:
        """Run the simulation up to (and including) *end_time_ps*.

        The simulator settles all delta cycles at each physical time step
        before advancing.
        """
        # Fire all processes once at time 0 to establish initial values
        if not self._running:
            self._running = True
            self._delta = 0
            for fn, _sens in self._processes:
                fn()
            # Flush any drives emitted during initialisation
            self._flush_drive_buffer(self.now, self._delta)

        # Main event loop
        while self._event_queue:
            # Peek at the soonest event
            next_time = self._event_queue[0].time_ps
            next_delta = self._event_queue[0].delta
            if next_time > end_time_ps:
                break

            # Advance time
            if next_time > self.now:
                self.now = next_time
                self._delta = 0
            else:
                self._delta = next_delta

            if self._delta > self.max_delta:
                raise SimulationError(
                    f"Delta-cycle limit ({self.max_delta}) exceeded at T={self.now} ps"
                )

            # Collect all events at (now, delta)
            changed: list[Signal] = []
            while (
                self._event_queue
                and self._event_queue[0].time_ps == self.now
                and self._event_queue[0].delta == self._delta
            ):
                evt = heapq.heappop(self._event_queue)
                self._drive_buffer[evt.signal].append(evt.value)

            # Resolve and commit
            for sig, drivers in self._drive_buffer.items():
                resolved = resolve(drivers)
                if sig._apply(resolved):
                    changed.append(sig)
            self._drive_buffer.clear()

            # Wake sensitive processes
            for sig in changed:
                for fn in self._sensitivity.get(sig, []):
                    fn()

            # Any drives emitted by woken processes go into the buffer
            # for the *next* delta cycle — flush schedules them.
            self._flush_drive_buffer(self.now, self._delta + 1)

    def _schedule_drive(
        self, signal: Signal, value: StdLogic, delay_ps: int
    ) -> None:
        """Insert a drive event into the queue."""
        if delay_ps == 0:
            # Delta-cycle scheduling: same physical time, next delta.
            # We buffer directly; flush will handle ordering.
            target_time = self.now
            target_delta = self._delta + 1
        else:
            target_time = self.now + delay_ps
            target_delta = 0

        seq = self._seq_counter
        self._seq_counter += 1
        evt = _Event(target_time, target_delta, signal, value, seq)
        heapq.heappush(self._event_queue, evt)

    def _flush_drive_buffer(self, time_ps: int, delta: int) -> None:
        """Flush any pending immediate drives as events at (time_ps, delta)."""
        # _schedule_drive already puts them in the queue; nothing more needed
        # here.  This hook exists for future extensions.
        pass

    # ------------------------------------------------------------------
    # VCD integration
    # ------------------------------------------------------------------

    def dump_vcd(self, writer: "VCDWriter") -> None:  # type: ignore[name-defined]  # noqa: F821
        """Dump current signal values to a VCD writer (used by tests)."""
        for name, sig in self._signals.items():
            writer.change(name, self.now, sig.value)


class SimulationError(Exception):
    """Raised when the simulator encounters an unrecoverable condition."""
