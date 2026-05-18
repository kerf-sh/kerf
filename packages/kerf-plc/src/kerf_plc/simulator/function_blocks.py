"""
kerf_plc.simulator.function_blocks
-----------------------------------
IEC 61131-3 standard function-block implementations.

Each class is a *stateful* FB instance.  The host simulator creates one
instance per FB call-site in the program and calls ``execute()`` once per
scan cycle, passing a reference to the current :class:`~.state.ScanState`.

Semantics follow IEC 61131-3 ed. 3 exactly:

* **TON**  — on-delay timer
* **TOF**  — off-delay timer
* **CTU**  — up-counter
* **CTD**  — down-counter
* **R_TRIG** — rising-edge detector
* **F_TRIG** — falling-edge detector
* **SR**   — set-dominant flip-flop
* **RS**   — reset-dominant flip-flop
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .state import ScanState


class FunctionBlock(ABC):
    """Abstract base for all standard FBs."""

    @abstractmethod
    def execute(self, state: ScanState, tick_ms: float) -> None:
        """Run one scan for this FB instance, read/write *state* as needed."""


# ---------------------------------------------------------------------------
# Timers
# ---------------------------------------------------------------------------

class TON(FunctionBlock):
    """On-delay timer.

    Inputs  (read from *state* via ``in_var`` / ``pt_var``):
      IN  — BOOL activation signal
      PT  — REAL preset time [ms]

    Outputs (written to *state* via ``q_var`` / ``et_var``):
      Q   — BOOL output (true when ET ≥ PT and IN is true)
      ET  — REAL elapsed time [ms]
    """

    def __init__(
        self,
        in_var: str,
        pt_var: str | float,
        q_var: str,
        et_var: str,
    ) -> None:
        self.in_var = in_var
        self.pt_var = pt_var      # may be a literal ms value or a var name
        self.q_var = q_var
        self.et_var = et_var
        self._et: float = 0.0

    def execute(self, state: ScanState, tick_ms: float) -> None:
        in_val: bool = bool(state.get(self.in_var, False))
        pt_val: float = (
            float(self.pt_var)
            if isinstance(self.pt_var, (int, float))
            else float(state.get(self.pt_var, 0))
        )

        if in_val:
            self._et = min(self._et + tick_ms, pt_val)
        else:
            self._et = 0.0

        q_val = in_val and self._et >= pt_val
        state.set(self.q_var, q_val)
        state.set(self.et_var, self._et)


class TOF(FunctionBlock):
    """Off-delay timer.

    Q is TRUE while IN is TRUE *or* while ET < PT after IN fell.
    ET accumulates only while IN is FALSE (after a falling edge).

    Inputs:  IN (BOOL), PT (ms, literal or var)
    Outputs: Q (BOOL), ET (REAL ms)
    """

    def __init__(
        self,
        in_var: str,
        pt_var: str | float,
        q_var: str,
        et_var: str,
    ) -> None:
        self.in_var = in_var
        self.pt_var = pt_var
        self.q_var = q_var
        self.et_var = et_var
        self._et: float = 0.0
        self._prev_in: bool = False
        self._timing: bool = False   # true while counting down after fall

    def execute(self, state: ScanState, tick_ms: float) -> None:
        in_val: bool = bool(state.get(self.in_var, False))
        pt_val: float = (
            float(self.pt_var)
            if isinstance(self.pt_var, (int, float))
            else float(state.get(self.pt_var, 0))
        )

        if in_val:
            # Rising or sustained: reset timer, output on
            self._et = 0.0
            self._timing = False
        else:
            if self._prev_in:
                # Falling edge detected: start timing
                self._timing = True
            if self._timing:
                self._et = min(self._et + tick_ms, pt_val)

        q_val = in_val or (self._timing and self._et < pt_val)
        state.set(self.q_var, q_val)
        state.set(self.et_var, self._et)
        self._prev_in = in_val


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

class CTU(FunctionBlock):
    """Up-counter.

    Inputs:  CU (BOOL rising-edge), R (BOOL reset), PV (INT preset value or var)
    Outputs: Q (BOOL: CV ≥ PV), CV (INT current value)
    """

    def __init__(
        self,
        cu_var: str,
        r_var: str,
        pv_var: str | int,
        q_var: str,
        cv_var: str,
    ) -> None:
        self.cu_var = cu_var
        self.r_var = r_var
        self.pv_var = pv_var
        self.q_var = q_var
        self.cv_var = cv_var
        self._cv: int = 0
        self._prev_cu: bool = False

    def execute(self, state: ScanState, tick_ms: float) -> None:
        cu_val: bool = bool(state.get(self.cu_var, False))
        r_val: bool = bool(state.get(self.r_var, False))
        pv_val: int = (
            int(self.pv_var)
            if isinstance(self.pv_var, (int, float))
            else int(state.get(self.pv_var, 0))
        )

        if r_val:
            self._cv = 0
        elif cu_val and not self._prev_cu:
            # Rising edge of CU
            self._cv += 1

        self._prev_cu = cu_val
        state.set(self.q_var, self._cv >= pv_val)
        state.set(self.cv_var, self._cv)


class CTD(FunctionBlock):
    """Down-counter.

    Inputs:  CD (BOOL falling-edge trigger), LD (BOOL load/preset), PV (INT)
    Outputs: Q (BOOL: CV ≤ 0), CV (INT current value)

    On rising edge of LD, CV is loaded from PV.
    On each rising edge of CD, CV is decremented.
    """

    def __init__(
        self,
        cd_var: str,
        ld_var: str,
        pv_var: str | int,
        q_var: str,
        cv_var: str,
    ) -> None:
        self.cd_var = cd_var
        self.ld_var = ld_var
        self.pv_var = pv_var
        self.q_var = q_var
        self.cv_var = cv_var
        self._cv: int = 0
        self._prev_cd: bool = False
        self._prev_ld: bool = False

    def execute(self, state: ScanState, tick_ms: float) -> None:
        cd_val: bool = bool(state.get(self.cd_var, False))
        ld_val: bool = bool(state.get(self.ld_var, False))
        pv_val: int = (
            int(self.pv_var)
            if isinstance(self.pv_var, (int, float))
            else int(state.get(self.pv_var, 0))
        )

        if ld_val and not self._prev_ld:
            # Rising edge of LD: load preset
            self._cv = pv_val
        elif cd_val and not self._prev_cd:
            # Rising edge of CD: decrement
            self._cv -= 1

        self._prev_cd = cd_val
        self._prev_ld = ld_val
        state.set(self.q_var, self._cv <= 0)
        state.set(self.cv_var, self._cv)


# ---------------------------------------------------------------------------
# Edge detectors
# ---------------------------------------------------------------------------

class R_TRIG(FunctionBlock):
    """Rising-edge detector.

    Q is TRUE for exactly one scan after CLK transitions 0→1.
    """

    def __init__(self, clk_var: str, q_var: str) -> None:
        self.clk_var = clk_var
        self.q_var = q_var
        self._prev: bool = False

    def execute(self, state: ScanState, tick_ms: float) -> None:
        clk_val: bool = bool(state.get(self.clk_var, False))
        q_val = clk_val and not self._prev
        self._prev = clk_val
        state.set(self.q_var, q_val)


class F_TRIG(FunctionBlock):
    """Falling-edge detector.

    Q is TRUE for exactly one scan after CLK transitions 1→0.
    """

    def __init__(self, clk_var: str, q_var: str) -> None:
        self.clk_var = clk_var
        self.q_var = q_var
        self._prev: bool = True   # assume previously high so first-tick fall is detected

    def execute(self, state: ScanState, tick_ms: float) -> None:
        clk_val: bool = bool(state.get(self.clk_var, False))
        q_val = not clk_val and self._prev
        self._prev = clk_val
        state.set(self.q_var, q_val)


# ---------------------------------------------------------------------------
# Flip-flops
# ---------------------------------------------------------------------------

class SR(FunctionBlock):
    """Set-dominant (SR) flip-flop.

    Truth table:
      S1=0, R=0 → Q unchanged
      S1=1, R=0 → Q=1
      S1=0, R=1 → Q=0
      S1=1, R=1 → Q=1   (set dominates)
    """

    def __init__(self, s1_var: str, r_var: str, q_var: str) -> None:
        self.s1_var = s1_var
        self.r_var = r_var
        self.q_var = q_var
        self._q: bool = False

    def execute(self, state: ScanState, tick_ms: float) -> None:
        s1 = bool(state.get(self.s1_var, False))
        r = bool(state.get(self.r_var, False))
        if s1:
            self._q = True
        elif r:
            self._q = False
        state.set(self.q_var, self._q)


class RS(FunctionBlock):
    """Reset-dominant (RS) flip-flop.

    Truth table:
      S=0, R1=0 → Q unchanged
      S=1, R1=0 → Q=1
      S=0, R1=1 → Q=0
      S=1, R1=1 → Q=0   (reset dominates)
    """

    def __init__(self, s_var: str, r1_var: str, q_var: str) -> None:
        self.s_var = s_var
        self.r1_var = r1_var
        self.q_var = q_var
        self._q: bool = False

    def execute(self, state: ScanState, tick_ms: float) -> None:
        s = bool(state.get(self.s_var, False))
        r1 = bool(state.get(self.r1_var, False))
        if r1:
            self._q = False
        elif s:
            self._q = True
        state.set(self.q_var, self._q)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Map from IEC type-name string → class, for use by the program loader.
FB_REGISTRY: dict[str, type[FunctionBlock]] = {
    "TON": TON,
    "TOF": TOF,
    "CTU": CTU,
    "CTD": CTD,
    "R_TRIG": R_TRIG,
    "F_TRIG": F_TRIG,
    "SR": SR,
    "RS": RS,
}
