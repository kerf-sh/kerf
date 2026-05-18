"""Tests for IEEE 1164 9-state std_logic type, truth tables, and resolution."""
import pytest

from kerf_silicon.vhdl.std_logic import (
    STATES,
    and2,
    not1,
    or2,
    resolve,
    to_01,
    xor2,
)


class TestStdLogicStates:
    def test_all_nine_states_defined(self):
        assert len(STATES) == 9
        for s in ("U", "X", "0", "1", "Z", "W", "L", "H", "-"):
            assert s in STATES

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            resolve(["Q"])


class TestResolution:
    """IEEE 1164 bus resolution table tests."""

    def test_single_driver_returned_unchanged(self):
        for s in STATES:
            assert resolve([s]) == s

    def test_no_drivers_returns_z(self):
        assert resolve([]) == "Z"

    def test_one_and_z_resolves_to_one(self):
        # (1, Z) → 1
        assert resolve(["1", "Z"]) == "1"
        assert resolve(["Z", "1"]) == "1"

    def test_zero_and_one_resolves_to_x(self):
        # (0, 1) → X (bus contention)
        assert resolve(["0", "1"]) == "X"
        assert resolve(["1", "0"]) == "X"

    def test_z_and_z_resolves_to_z(self):
        # (Z, Z) → Z (both tristated)
        assert resolve(["Z", "Z"]) == "Z"

    def test_zero_and_z_resolves_to_zero(self):
        assert resolve(["0", "Z"]) == "0"
        assert resolve(["Z", "0"]) == "0"

    def test_multiple_drivers_fold_correctly(self):
        # Three drivers: Z, Z, 1 → 1
        assert resolve(["Z", "Z", "1"]) == "1"

    def test_u_dominates(self):
        # U with anything except U stays U
        for s in STATES:
            assert resolve(["U", s]) == "U"
            assert resolve([s, "U"]) == "U"

    def test_x_dominates_weak(self):
        # X with W → X
        assert resolve(["X", "W"]) == "X"

    def test_symmetric_resolution(self):
        """Resolution table must be symmetric."""
        for a in STATES:
            for b in STATES:
                assert resolve([a, b]) == resolve([b, a]), (
                    f"Resolution not symmetric for ({a}, {b})"
                )


class TestAndGate:
    """IEEE 1164 AND truth table."""

    def test_zero_dominates(self):
        for s in STATES:
            assert and2("0", s) == "0"
            assert and2(s, "0") == "0"

    def test_one_identity(self):
        # 1 AND x = x for forcing states
        assert and2("1", "1") == "1"
        assert and2("1", "0") == "0"

    def test_u_and_one(self):
        assert and2("U", "1") == "U"

    def test_x_and_one(self):
        assert and2("X", "1") == "X"

    def test_z_and_one(self):
        assert and2("Z", "1") == "X"

    def test_l_treated_as_zero(self):
        # L (weak 0) AND anything should give 0
        for s in STATES:
            assert and2("L", s) == "0"
            assert and2(s, "L") == "0"

    def test_h_treated_as_one_for_forcing(self):
        assert and2("H", "1") == "1"
        assert and2("H", "0") == "0"
        assert and2("1", "H") == "1"

    def test_symmetric(self):
        for a in STATES:
            for b in STATES:
                assert and2(a, b) == and2(b, a), f"AND not symmetric for ({a}, {b})"


class TestOrGate:
    def test_one_dominates(self):
        for s in STATES:
            assert or2("1", s) == "1"
            assert or2(s, "1") == "1"

    def test_zero_identity(self):
        assert or2("0", "0") == "0"
        assert or2("0", "1") == "1"

    def test_l_is_weak_zero(self):
        assert or2("L", "L") == "0"

    def test_h_is_weak_one(self):
        assert or2("H", "H") == "1"

    def test_symmetric(self):
        for a in STATES:
            for b in STATES:
                assert or2(a, b) == or2(b, a), f"OR not symmetric for ({a}, {b})"


class TestXorGate:
    def test_same_inputs(self):
        assert xor2("0", "0") == "0"
        assert xor2("1", "1") == "0"

    def test_different_inputs(self):
        assert xor2("0", "1") == "1"
        assert xor2("1", "0") == "1"

    def test_x_propagates(self):
        assert xor2("X", "0") == "X"
        assert xor2("0", "X") == "X"

    def test_u_propagates(self):
        assert xor2("U", "0") == "U"

    def test_symmetric(self):
        for a in STATES:
            for b in STATES:
                assert xor2(a, b) == xor2(b, a), f"XOR not symmetric for ({a}, {b})"


class TestNotGate:
    def test_zero_to_one(self):
        assert not1("0") == "1"

    def test_one_to_zero(self):
        assert not1("1") == "0"

    def test_l_to_one(self):
        assert not1("L") == "1"

    def test_h_to_zero(self):
        assert not1("H") == "0"

    def test_x_stays_x(self):
        assert not1("X") == "X"

    def test_u_stays_u(self):
        assert not1("U") == "U"

    def test_z_to_x(self):
        assert not1("Z") == "X"

    def test_involution(self):
        # double negation: not(not(0)) == 0, not(not(1)) == 1
        assert not1(not1("0")) == "0"
        assert not1(not1("1")) == "1"


class TestTo01:
    def test_zero(self):
        assert to_01("0") == "0"

    def test_one(self):
        assert to_01("1") == "1"

    def test_l_is_zero(self):
        assert to_01("L") == "0"

    def test_h_is_one(self):
        assert to_01("H") == "1"

    def test_x_maps_to_xmap(self):
        assert to_01("X") == "X"
        assert to_01("X", xmap="0") == "0"

    def test_z_maps_to_xmap(self):
        assert to_01("Z") == "X"
