"""test_formal_equiv.py — pytest oracles for T-255 formal equivalence checking.

Tests cover:
  • half_adder_pre ≡ half_adder_post  → equivalent=True
  • half_adder_pre ≢ half_adder_broken → equivalent=False + 2-bit counterexample
  • BDD engine primitives (in-house path)
  • Topological sort, combinational loop detection
  • evaluate_netlist simulation oracle
  • explain_counterexample formatting
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Public API under test
from kerf_silicon.formal import EquivResult, equiv
from kerf_silicon.formal.bdd import BDDEngine, _InHouseBDDEngine
from kerf_silicon.formal.counterexample import evaluate_netlist, explain_counterexample
from kerf_silicon.formal.equiv import build_output_bdds, check_equiv


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "formal"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def ha_pre() -> dict[str, Any]:
    return _load("half_adder_pre.json")


@pytest.fixture
def ha_post() -> dict[str, Any]:
    return _load("half_adder_post.json")


@pytest.fixture
def ha_broken() -> dict[str, Any]:
    return _load("half_adder_broken.json")


# ===========================================================================
# 1. BDD engine primitives
# ===========================================================================


class TestInHouseBDD:
    """Tests exercising the built-in Shannon-cofactor BDD directly."""

    def _engine(self) -> _InHouseBDDEngine:
        return _InHouseBDDEngine()

    def test_const_zero_is_false(self) -> None:
        eng = self._engine()
        zero = eng.const(0)
        one = eng.const(1)
        assert not eng.equivalent(zero, one)

    def test_const_equivalent(self) -> None:
        eng = self._engine()
        assert eng.equivalent(eng.const(1), eng.const(1))
        assert eng.equivalent(eng.const(0), eng.const(0))

    def test_var_not_equiv_to_complement(self) -> None:
        eng = self._engine()
        a = eng.var("a")
        na = eng.apply_not(a)
        assert not eng.equivalent(a, na)

    def test_and_truth_table(self) -> None:
        """a AND b = 1 iff a=1 and b=1."""
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        ab = eng.apply_and(a, b)
        # Should be SAT (a=1, b=1)
        sat = eng.satisfying_assignment(ab)
        assert sat is not None
        assert sat.get("a", 0) == 1 and sat.get("b", 0) == 1

    def test_xor_idempotent_complement(self) -> None:
        """a XOR a = 0."""
        eng = self._engine()
        a = eng.var("a")
        aa = eng.apply_xor(a, a)
        assert eng.equivalent(aa, eng.const(0))

    def test_xor_complement_is_not(self) -> None:
        """a XOR 1 = NOT a."""
        eng = self._engine()
        a = eng.var("a")
        a_xor_1 = eng.apply_xor(a, eng.const(1))
        not_a = eng.apply_not(a)
        assert eng.equivalent(a_xor_1, not_a)

    def test_or_identity(self) -> None:
        """a OR 0 = a."""
        eng = self._engine()
        a = eng.var("a")
        assert eng.equivalent(eng.apply_or(a, eng.const(0)), a)

    def test_nand_is_not_and(self) -> None:
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        nand_ab = eng.apply_nand(a, b)
        not_and_ab = eng.apply_not(eng.apply_and(a, b))
        assert eng.equivalent(nand_ab, not_and_ab)

    def test_nor_is_not_or(self) -> None:
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        nor_ab = eng.apply_nor(a, b)
        not_or_ab = eng.apply_not(eng.apply_or(a, b))
        assert eng.equivalent(nor_ab, not_or_ab)

    def test_counterexample_returns_none_when_equivalent(self) -> None:
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        expr1 = eng.apply_xor(a, b)
        expr2 = eng.apply_xor(b, a)  # commutative — same function
        assert eng.counterexample(expr1, expr2) is None

    def test_counterexample_found_when_different(self) -> None:
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        xor_ab = eng.apply_xor(a, b)
        or_ab = eng.apply_or(a, b)
        cex = eng.counterexample(xor_ab, or_ab)
        assert cex is not None
        # The counterexample must be a=1, b=1 (only point where OR≠XOR)
        assert cex.get("a") == 1 and cex.get("b") == 1

    def test_satisfying_assignment_false_returns_none(self) -> None:
        eng = self._engine()
        assert eng.satisfying_assignment(eng.const(0)) is None

    def test_de_morgan_and(self) -> None:
        """NOT(a AND b) = (NOT a) OR (NOT b)."""
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        lhs = eng.apply_not(eng.apply_and(a, b))
        rhs = eng.apply_or(eng.apply_not(a), eng.apply_not(b))
        assert eng.equivalent(lhs, rhs)

    def test_de_morgan_or(self) -> None:
        """NOT(a OR b) = (NOT a) AND (NOT b)."""
        eng = self._engine()
        a = eng.var("a")
        b = eng.var("b")
        lhs = eng.apply_not(eng.apply_or(a, b))
        rhs = eng.apply_and(eng.apply_not(a), eng.apply_not(b))
        assert eng.equivalent(lhs, rhs)


class TestBDDEngineFacade:
    """Smoke-test the public BDDEngine facade."""

    def test_facade_delegates_correctly(self) -> None:
        eng = BDDEngine()
        a = eng.var("a")
        b = eng.var("b")
        xor_ab = eng.apply_xor(a, b)
        or_ab = eng.apply_or(a, b)
        assert not eng.equivalent(xor_ab, or_ab)
        cex = eng.counterexample(xor_ab, or_ab)
        assert cex is not None


# ===========================================================================
# 2. Netlist compilation (build_output_bdds)
# ===========================================================================


class TestBuildOutputBDDs:
    def test_half_adder_pre_compiles(self, ha_pre: dict) -> None:
        eng = BDDEngine()
        bdds = build_output_bdds(ha_pre, eng)
        assert set(bdds.keys()) == {"sum", "cout"}

    def test_half_adder_post_compiles(self, ha_post: dict) -> None:
        eng = BDDEngine()
        bdds = build_output_bdds(ha_post, eng)
        assert set(bdds.keys()) == {"sum", "cout"}

    def test_combinational_loop_raises(self) -> None:
        looped = {
            "inputs": ["a"],
            "outputs": ["y"],
            "gates": [
                {"type": "and", "inputs": ["a", "y"], "output": "y"},
            ],
        }
        eng = BDDEngine()
        with pytest.raises(ValueError, match="loop"):
            build_output_bdds(looped, eng)

    def test_missing_input_raises(self) -> None:
        bad = {
            "inputs": ["a"],
            "outputs": ["y"],
            "gates": [
                {"type": "and", "inputs": ["a", "b"], "output": "y"},
            ],
        }
        eng = BDDEngine()
        with pytest.raises(KeyError):
            build_output_bdds(bad, eng)

    def test_unsupported_gate_raises(self) -> None:
        bad = {
            "inputs": ["a"],
            "outputs": ["y"],
            "gates": [
                {"type": "mux", "inputs": ["a", "a"], "output": "y"},
            ],
        }
        eng = BDDEngine()
        with pytest.raises(ValueError, match="Unsupported gate"):
            build_output_bdds(bad, eng)

    def test_multi_driver_raises(self) -> None:
        bad = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [
                {"type": "and", "inputs": ["a", "b"], "output": "y"},
                {"type": "or",  "inputs": ["a", "b"], "output": "y"},
            ],
        }
        eng = BDDEngine()
        with pytest.raises(ValueError, match="Multiple drivers"):
            build_output_bdds(bad, eng)

    def test_buf_gate(self) -> None:
        netlist = {
            "inputs": ["a"],
            "outputs": ["y"],
            "gates": [{"type": "buf", "inputs": ["a"], "output": "y"}],
        }
        eng = BDDEngine()
        bdds = build_output_bdds(netlist, eng)
        a_node = eng.var("a")
        assert eng.equivalent(bdds["y"], a_node)

    def test_xnor_gate(self) -> None:
        """a XNOR b = NOT(a XOR b)."""
        netlist = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [{"type": "xnor", "inputs": ["a", "b"], "output": "y"}],
        }
        ref_netlist = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [
                {"type": "xor", "inputs": ["a", "b"], "output": "xab"},
                {"type": "not", "inputs": ["xab"], "output": "y"},
            ],
        }
        eng = BDDEngine()
        bdds = build_output_bdds(netlist, eng)
        ref_bdds = build_output_bdds(ref_netlist, eng)
        assert eng.equivalent(bdds["y"], ref_bdds["y"])


# ===========================================================================
# 3. check_equiv internal
# ===========================================================================


class TestCheckEquiv:
    def test_primary_input_mismatch_raises(self) -> None:
        a = {"inputs": ["a"], "outputs": ["y"], "gates": [{"type": "buf", "inputs": ["a"], "output": "y"}]}
        b = {"inputs": ["x"], "outputs": ["y"], "gates": [{"type": "buf", "inputs": ["x"], "output": "y"}]}
        with pytest.raises(ValueError, match="Primary-input mismatch"):
            check_equiv(a, b)

    def test_primary_output_mismatch_raises(self) -> None:
        a = {"inputs": ["a"], "outputs": ["y"], "gates": [{"type": "buf", "inputs": ["a"], "output": "y"}]}
        b = {"inputs": ["a"], "outputs": ["z"], "gates": [{"type": "buf", "inputs": ["a"], "output": "z"}]}
        with pytest.raises(ValueError, match="Primary-output mismatch"):
            check_equiv(a, b)


# ===========================================================================
# 4. Public equiv() API — the core DoD tests
# ===========================================================================


class TestEquivPublicAPI:
    """Definition-of-Done tests for T-255."""

    def test_half_adder_pre_post_equivalent(
        self, ha_pre: dict, ha_post: dict
    ) -> None:
        """equiv(half_adder_pre, half_adder_post) → equivalent=True."""
        result = equiv(ha_pre, ha_post)

        assert isinstance(result, EquivResult)
        assert result.equivalent is True
        assert result.per_output["sum"] is True
        assert result.per_output["cout"] is True
        assert result.counterexample is None

    def test_half_adder_pre_broken_not_equivalent(
        self, ha_pre: dict, ha_broken: dict
    ) -> None:
        """equiv(half_adder_pre, half_adder_broken) → equivalent=False + witness."""
        result = equiv(ha_pre, ha_broken)

        assert isinstance(result, EquivResult)
        assert result.equivalent is False

        # At least one output must differ
        assert not all(result.per_output.values())

        # Counter-example must be present and valid
        assert result.counterexample is not None
        cex = result.counterexample
        assert "output" in cex
        assert "assignment" in cex

        assignment = cex["assignment"]
        # Must be a 2-bit assignment covering both primary inputs
        assert set(assignment.keys()) == {"a", "b"}
        assert all(v in (0, 1) for v in assignment.values())

        # Verify the witness actually distinguishes the netlists under
        # gate-level simulation.
        out_pre = evaluate_netlist(ha_pre, assignment)
        out_broken = evaluate_netlist(ha_broken, assignment)
        assert out_pre != out_broken, (
            f"Counterexample {assignment!r} does not produce different outputs: "
            f"pre={out_pre}, broken={out_broken}"
        )

    def test_reflexive_equivalence(self, ha_pre: dict) -> None:
        """A netlist is always equivalent to itself."""
        result = equiv(ha_pre, ha_pre)
        assert result.equivalent is True

    def test_broken_counterexample_is_a_1_b_1(
        self, ha_pre: dict, ha_broken: dict
    ) -> None:
        """The only distinguishing input for the broken fixture is a=1, b=1."""
        result = equiv(ha_pre, ha_broken)
        cex = result.counterexample
        assert cex is not None
        assignment = cex["assignment"]
        # OR and XOR differ exactly when both inputs are 1
        assert assignment.get("a") == 1 and assignment.get("b") == 1

    def test_result_type(self, ha_pre: dict, ha_post: dict) -> None:
        result = equiv(ha_pre, ha_post)
        assert isinstance(result.equivalent, bool)
        assert isinstance(result.per_output, dict)
        assert result.counterexample is None or isinstance(result.counterexample, dict)


# ===========================================================================
# 5. evaluate_netlist simulation
# ===========================================================================


class TestEvaluateNetlist:
    def test_xor_truth_table(self, ha_pre: dict) -> None:
        cases = [
            ({"a": 0, "b": 0}, {"sum": 0, "cout": 0}),
            ({"a": 0, "b": 1}, {"sum": 1, "cout": 0}),
            ({"a": 1, "b": 0}, {"sum": 1, "cout": 0}),
            ({"a": 1, "b": 1}, {"sum": 0, "cout": 1}),
        ]
        for assignment, expected in cases:
            out = evaluate_netlist(ha_pre, assignment)
            assert out == expected, f"assignment={assignment}: got {out}, expected {expected}"

    def test_broken_truth_table(self, ha_broken: dict) -> None:
        """Broken fixture: sum = OR(a,b), so (1,1) → sum=1, not 0."""
        out = evaluate_netlist(ha_broken, {"a": 1, "b": 1})
        assert out["sum"] == 1   # wrong (should be 0 for XOR)
        assert out["cout"] == 1

    def test_nand_based_post_synth(self, ha_post: dict) -> None:
        """Post-synthesis NAND-decomposition must produce the same truth table."""
        cases = [
            ({"a": 0, "b": 0}, {"sum": 0, "cout": 0}),
            ({"a": 0, "b": 1}, {"sum": 1, "cout": 0}),
            ({"a": 1, "b": 0}, {"sum": 1, "cout": 0}),
            ({"a": 1, "b": 1}, {"sum": 0, "cout": 1}),
        ]
        for assignment, expected in cases:
            out = evaluate_netlist(ha_post, assignment)
            assert out == expected, f"assignment={assignment}: got {out}, expected {expected}"

    def test_missing_input_raises(self, ha_pre: dict) -> None:
        with pytest.raises(ValueError, match="not present in the assignment"):
            evaluate_netlist(ha_pre, {"a": 1})  # b missing


# ===========================================================================
# 6. explain_counterexample formatting
# ===========================================================================


class TestExplainCounterexample:
    def test_explanation_contains_assignment(
        self, ha_pre: dict, ha_broken: dict
    ) -> None:
        assignment = {"a": 1, "b": 1}
        text = explain_counterexample(ha_pre, ha_broken, assignment)
        assert "a" in text
        assert "b" in text

    def test_explanation_marks_mismatch(
        self, ha_pre: dict, ha_broken: dict
    ) -> None:
        assignment = {"a": 1, "b": 1}
        text = explain_counterexample(ha_pre, ha_broken, assignment)
        assert "MISMATCH" in text or "sum" in text

    def test_explanation_marks_match(
        self, ha_pre: dict, ha_post: dict
    ) -> None:
        assignment = {"a": 1, "b": 1}
        text = explain_counterexample(ha_pre, ha_post, assignment)
        # Both should agree on (1,1) → sum=0, cout=1
        assert "MISMATCH" not in text


# ===========================================================================
# 7. Additional gate coverage
# ===========================================================================


class TestGateCoverage:
    def test_nor_gate(self) -> None:
        netlist = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [{"type": "nor", "inputs": ["a", "b"], "output": "y"}],
        }
        # NOR truth table
        cases = [
            ({"a": 0, "b": 0}, 1),
            ({"a": 0, "b": 1}, 0),
            ({"a": 1, "b": 0}, 0),
            ({"a": 1, "b": 1}, 0),
        ]
        for assignment, expected_y in cases:
            out = evaluate_netlist(netlist, assignment)
            assert out["y"] == expected_y

    def test_nand_gate(self) -> None:
        netlist = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [{"type": "nand", "inputs": ["a", "b"], "output": "y"}],
        }
        cases = [
            ({"a": 0, "b": 0}, 1),
            ({"a": 0, "b": 1}, 1),
            ({"a": 1, "b": 0}, 1),
            ({"a": 1, "b": 1}, 0),
        ]
        for assignment, expected_y in cases:
            out = evaluate_netlist(netlist, assignment)
            assert out["y"] == expected_y

    def test_not_gate(self) -> None:
        netlist = {
            "inputs": ["a"],
            "outputs": ["y"],
            "gates": [{"type": "not", "inputs": ["a"], "output": "y"}],
        }
        assert evaluate_netlist(netlist, {"a": 0})["y"] == 1
        assert evaluate_netlist(netlist, {"a": 1})["y"] == 0

    def test_chained_gates(self) -> None:
        """a → NOT → y1 → NOT → y2 should give y2 == a."""
        netlist = {
            "inputs": ["a"],
            "outputs": ["y2"],
            "gates": [
                {"type": "not", "inputs": ["a"], "output": "y1"},
                {"type": "not", "inputs": ["y1"], "output": "y2"},
            ],
        }
        eng = BDDEngine()
        bdds = build_output_bdds(netlist, eng)
        a_var = eng.var("a")
        assert eng.equivalent(bdds["y2"], a_var)

    def test_xnor_bdd_equiv(self) -> None:
        netlist_a = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [{"type": "xnor", "inputs": ["a", "b"], "output": "y"}],
        }
        netlist_b = {
            "inputs": ["a", "b"],
            "outputs": ["y"],
            "gates": [
                {"type": "xor", "inputs": ["a", "b"], "output": "xab"},
                {"type": "not", "inputs": ["xab"], "output": "y"},
            ],
        }
        result = equiv(netlist_a, netlist_b)
        assert result.equivalent is True
