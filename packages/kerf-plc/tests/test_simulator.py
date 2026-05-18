"""
tests/test_simulator.py
-----------------------
Pytest suite for the IEC 61131-3 scan-cycle simulator (T-223).

Covers:
  * TON on-delay timing (blinker oracle: 10 pulses in 5 s ± 1 tolerance)
  * CTU up-counter: 5 rising edges → CV=5
  * F_TRIG: fires exactly once per falling edge
  * R_TRIG: fires exactly once per rising edge
  * TOF off-delay
  * CTD down-counter
  * SR / RS flip-flops
  * ST compiled-assignment execution
  * ScanState snapshot isolation
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from kerf_plc.simulator import Simulator, ScanState
from kerf_plc.simulator.function_blocks import (
    CTD,
    CTU,
    F_TRIG,
    R_TRIG,
    RS,
    SR,
    TOF,
    TON,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ===========================================================================
# Helpers
# ===========================================================================

def _make_sim(program: dict[str, Any], tick_ms: float = 1.0) -> Simulator:
    return Simulator(program, tick_ms=tick_ms)


def _simple_program(variables: dict[str, Any], pous: list[dict]) -> dict[str, Any]:
    return {"variables": variables, "pous": pous}


# ===========================================================================
# ScanState unit tests
# ===========================================================================

class TestScanState:
    def test_get_default(self):
        s = ScanState()
        assert s.get("x") is False

    def test_set_and_get(self):
        s = ScanState({"a": 1})
        s.set("b", True)
        assert s.get("b") is True
        assert s.get("a") == 1

    def test_snapshot_is_copy(self):
        s = ScanState({"x": 10})
        snap = s.snapshot()
        s.set("x", 99)
        assert snap["x"] == 10   # original snapshot unaffected

    def test_update(self):
        s = ScanState()
        s.update({"a": 1, "b": 2})
        assert s.get("a") == 1
        assert s.get("b") == 2


# ===========================================================================
# TON — on-delay timer
# ===========================================================================

class TestTON:
    def _make(self, pt_ms: float = 100.0, tick_ms: float = 1.0) -> tuple[TON, ScanState]:
        fb = TON(in_var="IN", pt_var=pt_ms, q_var="Q", et_var="ET")
        state = ScanState({"IN": False, "Q": False, "ET": 0.0})
        return fb, state

    def test_q_false_before_pt(self):
        fb, state = self._make(pt_ms=100.0)
        state.set("IN", True)
        for _ in range(99):
            fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_q_true_at_pt(self):
        fb, state = self._make(pt_ms=100.0)
        state.set("IN", True)
        for _ in range(100):
            fb.execute(state, 1.0)
        assert state.get("Q") is True

    def test_et_resets_on_falling_edge(self):
        fb, state = self._make(pt_ms=50.0)
        state.set("IN", True)
        for _ in range(30):
            fb.execute(state, 1.0)
        state.set("IN", False)
        fb.execute(state, 1.0)
        assert state.get("ET") == 0.0
        assert state.get("Q") is False

    def test_et_clamps_at_pt(self):
        fb, state = self._make(pt_ms=10.0)
        state.set("IN", True)
        for _ in range(50):
            fb.execute(state, 1.0)
        assert state.get("ET") == 10.0


# ===========================================================================
# TOF — off-delay timer
# ===========================================================================

class TestTOF:
    def _make(self, pt_ms: float = 100.0) -> tuple[TOF, ScanState]:
        fb = TOF(in_var="IN", pt_var=pt_ms, q_var="Q", et_var="ET")
        state = ScanState({"IN": True, "Q": False, "ET": 0.0})
        return fb, state

    def test_q_true_while_in_true(self):
        fb, state = self._make()
        for _ in range(50):
            fb.execute(state, 1.0)
        assert state.get("Q") is True

    def test_q_stays_true_after_fall_within_pt(self):
        fb, state = self._make(pt_ms=100.0)
        fb.execute(state, 1.0)       # IN=True
        state.set("IN", False)
        for _ in range(50):          # 50 ticks < PT=100
            fb.execute(state, 1.0)
        assert state.get("Q") is True

    def test_q_goes_false_after_pt(self):
        fb, state = self._make(pt_ms=10.0)
        fb.execute(state, 1.0)       # IN=True
        state.set("IN", False)
        for _ in range(11):          # 11 ticks ≥ PT=10
            fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_et_zero_while_in_true(self):
        fb, state = self._make()
        for _ in range(20):
            fb.execute(state, 1.0)
        assert state.get("ET") == 0.0


# ===========================================================================
# CTU — up-counter
# ===========================================================================

class TestCTU:
    def _make(self, pv: int = 5) -> tuple[CTU, ScanState]:
        fb = CTU(cu_var="CU", r_var="R", pv_var=pv, q_var="Q", cv_var="CV")
        state = ScanState({"CU": False, "R": False, "Q": False, "CV": 0})
        return fb, state

    def test_five_rising_edges_cv_equals_5(self):
        fb, state = self._make(pv=10)
        for _ in range(5):
            state.set("CU", True)
            fb.execute(state, 1.0)
            state.set("CU", False)
            fb.execute(state, 1.0)
        assert state.get("CV") == 5

    def test_q_high_when_cv_reaches_pv(self):
        fb, state = self._make(pv=3)
        for _ in range(3):
            state.set("CU", True)
            fb.execute(state, 1.0)
            state.set("CU", False)
            fb.execute(state, 1.0)
        assert state.get("Q") is True

    def test_reset_clears_cv(self):
        fb, state = self._make(pv=10)
        for _ in range(5):
            state.set("CU", True)
            fb.execute(state, 1.0)
            state.set("CU", False)
            fb.execute(state, 1.0)
        state.set("R", True)
        fb.execute(state, 1.0)
        assert state.get("CV") == 0
        assert state.get("Q") is False

    def test_held_high_counts_once(self):
        """CU held high across multiple ticks counts only one edge."""
        fb, state = self._make(pv=10)
        state.set("CU", True)
        for _ in range(5):
            fb.execute(state, 1.0)
        assert state.get("CV") == 1


# ===========================================================================
# CTD — down-counter
# ===========================================================================

class TestCTD:
    def _make(self, pv: int = 5) -> tuple[CTD, ScanState]:
        fb = CTD(cd_var="CD", ld_var="LD", pv_var=pv, q_var="Q", cv_var="CV")
        state = ScanState({"CD": False, "LD": False, "Q": False, "CV": 0})
        return fb, state

    def test_load_sets_cv(self):
        fb, state = self._make(pv=5)
        state.set("LD", True)
        fb.execute(state, 1.0)
        assert state.get("CV") == 5

    def test_decrement_on_rising_edge(self):
        fb, state = self._make(pv=5)
        # Load first
        state.set("LD", True)
        fb.execute(state, 1.0)
        state.set("LD", False)
        fb.execute(state, 1.0)
        # Decrement 3 times
        for _ in range(3):
            state.set("CD", True)
            fb.execute(state, 1.0)
            state.set("CD", False)
            fb.execute(state, 1.0)
        assert state.get("CV") == 2

    def test_q_true_when_cv_zero_or_below(self):
        fb, state = self._make(pv=1)
        state.set("LD", True)
        fb.execute(state, 1.0)
        state.set("LD", False)
        fb.execute(state, 1.0)
        # One decrement brings CV to 0
        state.set("CD", True)
        fb.execute(state, 1.0)
        state.set("CD", False)
        fb.execute(state, 1.0)
        assert state.get("Q") is True


# ===========================================================================
# R_TRIG — rising-edge detector
# ===========================================================================

class TestRTRIG:
    def _make(self) -> tuple[R_TRIG, ScanState]:
        fb = R_TRIG(clk_var="CLK", q_var="Q")
        state = ScanState({"CLK": False, "Q": False})
        return fb, state

    def test_fires_once_on_0_to_1(self):
        fb, state = self._make()
        state.set("CLK", True)
        fb.execute(state, 1.0)
        assert state.get("Q") is True
        # Second tick: still high, Q must drop
        fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_no_fire_when_already_high(self):
        fb, state = self._make()
        # Pre-warm to high without triggering
        fb._prev = True
        state.set("CLK", True)
        fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_fires_again_after_low_high(self):
        fb, state = self._make()
        state.set("CLK", True)
        fb.execute(state, 1.0)   # rising: Q=True
        fb.execute(state, 1.0)   # sustained: Q=False
        state.set("CLK", False)
        fb.execute(state, 1.0)   # falling
        state.set("CLK", True)
        fb.execute(state, 1.0)   # rising again
        assert state.get("Q") is True


# ===========================================================================
# F_TRIG — falling-edge detector
# ===========================================================================

class TestFTRIG:
    def _make(self) -> tuple[F_TRIG, ScanState]:
        fb = F_TRIG(clk_var="CLK", q_var="Q")
        state = ScanState({"CLK": True, "Q": False})
        return fb, state

    def test_fires_once_per_falling_edge(self):
        fb, state = self._make()
        # Clock is high, _prev starts True — no spurious fire
        fb.execute(state, 1.0)
        assert state.get("Q") is False
        # Now falling edge
        state.set("CLK", False)
        fb.execute(state, 1.0)
        assert state.get("Q") is True
        # Sustained low — Q drops
        fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_fires_exactly_once_per_edge(self):
        fb, state = self._make()
        fired: list[bool] = []
        # Sequence: high×3, low×3, high×3, low×3
        pattern = [True] * 3 + [False] * 3 + [True] * 3 + [False] * 3
        for v in pattern:
            state.set("CLK", v)
            fb.execute(state, 1.0)
            fired.append(bool(state.get("Q")))
        # Should see exactly 2 TRUE values (one per falling edge)
        assert sum(fired) == 2

    def test_no_fire_on_sustained_low(self):
        fb, state = self._make()
        state.set("CLK", False)
        fb.execute(state, 1.0)    # falling edge → Q=True
        for _ in range(10):
            fb.execute(state, 1.0)
            assert state.get("Q") is False


# ===========================================================================
# SR / RS flip-flops
# ===========================================================================

class TestSR:
    def test_set_dominates(self):
        fb = SR(s1_var="S1", r_var="R", q_var="Q")
        state = ScanState({"S1": True, "R": True, "Q": False})
        fb.execute(state, 1.0)
        assert state.get("Q") is True   # set dominates

    def test_reset_clears(self):
        fb = SR(s1_var="S1", r_var="R", q_var="Q")
        state = ScanState({"S1": False, "R": True, "Q": True})
        fb.execute(state, 1.0)
        assert state.get("Q") is False

    def test_latches(self):
        fb = SR(s1_var="S1", r_var="R", q_var="Q")
        state = ScanState({"S1": True, "R": False, "Q": False})
        fb.execute(state, 1.0)
        assert state.get("Q") is True
        state.set("S1", False)
        fb.execute(state, 1.0)
        assert state.get("Q") is True  # latch holds


class TestRS:
    def test_reset_dominates(self):
        fb = RS(s_var="S", r1_var="R1", q_var="Q")
        state = ScanState({"S": True, "R1": True, "Q": True})
        fb.execute(state, 1.0)
        assert state.get("Q") is False   # reset dominates

    def test_set_sets(self):
        fb = RS(s_var="S", r1_var="R1", q_var="Q")
        state = ScanState({"S": True, "R1": False, "Q": False})
        fb.execute(state, 1.0)
        assert state.get("Q") is True

    def test_latches(self):
        fb = RS(s_var="S", r1_var="R1", q_var="Q")
        state = ScanState({"S": True, "R1": False, "Q": False})
        fb.execute(state, 1.0)
        state.set("S", False)
        fb.execute(state, 1.0)
        assert state.get("Q") is True   # latch holds


# ===========================================================================
# Simulator — LD blinker (TON 500ms, 5 s simulation → 10 pulses)
# ===========================================================================

class TestSimulatorBlinker:
    """Oracle: TON 500ms blinker over 5000ms → exactly 10 output pulses (±1)."""

    @pytest.fixture()
    def program(self):
        return json.loads((FIXTURES / "sim_blinker.json").read_text())

    def test_fixture_loads(self, program):
        assert "pous" in program
        assert len(program["pous"]) == 1

    def test_blinker_10_pulses_in_5s(self, program):
        """Run 5000 ticks at 1 ms/tick; count rising edges on blink_out."""
        sim = Simulator(program, tick_ms=1.0)
        pulses = 0
        prev_out = False
        for _ in range(5000):
            snap = sim.step({"enable": True})
            cur_out = bool(snap.get("blink_out", False))
            if cur_out and not prev_out:
                pulses += 1
            prev_out = cur_out
        # IEC spec: 10 pulses (one per 500 ms) ±1 tolerance
        assert abs(pulses - 10) <= 1, f"Expected ~10 pulses, got {pulses}"

    def test_blinker_pulse_interval_approx_500ms(self, program):
        """Verify individual inter-pulse intervals are within 500 ± 2 ms."""
        sim = Simulator(program, tick_ms=1.0)
        prev_out = False
        last_rising: int | None = None
        intervals: list[int] = []
        for tick in range(5000):
            snap = sim.step({"enable": True})
            cur_out = bool(snap.get("blink_out", False))
            if cur_out and not prev_out:
                if last_rising is not None:
                    intervals.append(tick - last_rising)
                last_rising = tick
            prev_out = cur_out
        assert len(intervals) >= 8, "Too few intervals to measure"
        for iv in intervals:
            assert abs(iv - 500) <= 2, f"Interval {iv} ms not within ±2 ms of 500 ms"


# ===========================================================================
# Simulator — CTU edge counting via Simulator.step
# ===========================================================================

class TestSimulatorCTU:
    """Five rising edges in 5 ticks → CV=5."""

    @pytest.fixture()
    def program(self):
        return _simple_program(
            variables={"CU": False, "R": False, "Q": False, "CV": 0},
            pous=[
                {
                    "kind": "LD",
                    "rungs": [
                        {
                            "elements": [
                                {
                                    "type": "fb_call",
                                    "fb_type": "CTU",
                                    "instance": "ctu1",
                                    "params": {
                                        "CU": "CU",
                                        "R":  "R",
                                        "PV": 10,
                                        "Q":  "Q",
                                        "CV": "CV",
                                    },
                                }
                            ]
                        }
                    ],
                }
            ],
        )

    def test_five_edges_cv_5(self, program):
        sim = _make_sim(program)
        for _ in range(5):
            sim.step({"CU": True})
            sim.step({"CU": False})
        snap = sim.step({})
        assert snap["CV"] == 5

    def test_reset_zeroes_cv(self, program):
        sim = _make_sim(program)
        for _ in range(3):
            sim.step({"CU": True})
            sim.step({"CU": False})
        sim.step({"R": True})
        snap = sim.step({"R": False})
        assert snap["CV"] == 0


# ===========================================================================
# Simulator — F_TRIG via Simulator.step
# ===========================================================================

class TestSimulatorFTRIG:
    @pytest.fixture()
    def program(self):
        return _simple_program(
            variables={"CLK": True, "Q": False},
            pous=[
                {
                    "kind": "LD",
                    "rungs": [
                        {
                            "elements": [
                                {
                                    "type": "fb_call",
                                    "fb_type": "F_TRIG",
                                    "instance": "ftrig1",
                                    "params": {"CLK": "CLK", "Q": "Q"},
                                }
                            ]
                        }
                    ],
                }
            ],
        )

    def test_fires_once_per_falling_edge(self, program):
        sim = _make_sim(program)
        fired: list[bool] = []
        # Pattern: high × 3, low × 3, high × 3, low × 3
        pattern = [True] * 3 + [False] * 3 + [True] * 3 + [False] * 3
        for v in pattern:
            snap = sim.step({"CLK": v})
            fired.append(bool(snap.get("Q", False)))
        # Exactly 2 TRUE values (one per falling edge)
        assert sum(fired) == 2, f"Expected 2 fires, got {sum(fired)}: {fired}"


# ===========================================================================
# Simulator — ST compiled assignments
# ===========================================================================

class TestSimulatorST:
    def test_simple_assignment(self):
        program = _simple_program(
            variables={"a": False, "b": False},
            pous=[
                {
                    "kind": "ST",
                    "statements": [
                        {"lhs": "b", "rhs": {"type": "var", "name": "a"}}
                    ],
                }
            ],
        )
        sim = _make_sim(program)
        snap = sim.step({"a": True})
        assert snap["b"] is True

    def test_not_expression(self):
        program = _simple_program(
            variables={"x": True, "y": False},
            pous=[
                {
                    "kind": "ST",
                    "statements": [
                        {
                            "lhs": "y",
                            "rhs": {"type": "not", "operand": {"type": "var", "name": "x"}},
                        }
                    ],
                }
            ],
        )
        sim = _make_sim(program)
        snap = sim.step({"x": True})
        assert snap["y"] is False

    def test_literal_assignment(self):
        program = _simple_program(
            variables={"c": 0},
            pous=[
                {
                    "kind": "ST",
                    "statements": [
                        {"lhs": "c", "rhs": {"type": "literal", "value": 42}}
                    ],
                }
            ],
        )
        sim = _make_sim(program)
        snap = sim.step({})
        assert snap["c"] == 42

    def test_and_expression(self):
        program = _simple_program(
            variables={"p": False, "q": False, "r": False},
            pous=[
                {
                    "kind": "ST",
                    "statements": [
                        {
                            "lhs": "r",
                            "rhs": {
                                "type": "and",
                                "left":  {"type": "var", "name": "p"},
                                "right": {"type": "var", "name": "q"},
                            },
                        }
                    ],
                }
            ],
        )
        sim = _make_sim(program)
        assert sim.step({"p": True, "q": False})["r"] is False
        assert sim.step({"p": True, "q": True})["r"] is True


# ===========================================================================
# Simulator — run_for helper
# ===========================================================================

class TestSimulatorRunFor:
    def test_trace_length(self):
        program = _simple_program(variables={"x": 0}, pous=[])
        sim = _make_sim(program, tick_ms=1.0)
        trace = sim.run_for(100, lambda t: {})
        assert len(trace) == 100

    def test_elapsed_increments(self):
        program = _simple_program(variables={}, pous=[])
        sim = _make_sim(program, tick_ms=5.0)
        sim.run_for(50, lambda t: {})
        assert sim._state.elapsed_ms == 50.0

    def test_input_provider_called(self):
        program = _simple_program(variables={"flag": False}, pous=[])
        sim = _make_sim(program)
        calls: list[float] = []

        def provider(t: float) -> dict:
            calls.append(t)
            return {"flag": True}

        sim.run_for(10, provider)
        assert len(calls) == 10
        assert all(v is True for snap in sim.run_for(1, lambda t: {}) for k, v in snap.items() if k == "flag")
