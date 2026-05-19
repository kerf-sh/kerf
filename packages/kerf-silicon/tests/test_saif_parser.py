"""test_saif_parser.py — pytest suite for kerf_silicon.power.saif_parser.

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \
        python3 -m pytest packages/kerf-silicon/tests/test_saif_parser.py -x

SAIF format quick reference
----------------------------
The SAIF file is a nested parenthesised S-expression::

    (SAIF 2.0)
    (TIMESCALE 1 ns)
    (DURATION 1000)
    (INSTANCE top
        (NET
            (clk
                (T0 500)
                (T1 500)
                (TC 100)
                (TX 0)
            )
            (data
                (T0 700)
                (T1 300)
                (TC 40)
            )
        )
    )

Activity factor:
    alpha = TC / (2 × DURATION)

For clk above:  alpha = 100 / (2 × 1000) = 0.05
For data above: alpha = 40  / (2 × 1000) = 0.02
"""
from __future__ import annotations

import pytest

from kerf_silicon.power.saif_parser import (
    NetActivity,
    SaifData,
    parse_saif,
)


# ---------------------------------------------------------------------------
# Minimal SAIF fixtures
# ---------------------------------------------------------------------------

MINIMAL_SAIF = """
(SAIF 2.0)
(TIMESCALE 1 ns)
(DURATION 1000)
(INSTANCE top
    (NET
        (clk
            (T0 500)
            (T1 500)
            (TC 100)
            (TX 0)
        )
        (data
            (T0 700)
            (T1 300)
            (TC 40)
        )
    )
)
"""

INVERTER_CHAIN_SAIF = """
(SAIF 2.0)
(TIMESCALE 1 ns)
(DURATION 2000)
(INSTANCE inverter_chain
    (NET
        (in
            (T0 1000)
            (T1 1000)
            (TC 200)
            (TX 0)
        )
        (n1
            (T0 1000)
            (T1 1000)
            (TC 200)
            (TX 0)
        )
        (n2
            (T0 1000)
            (T1 1000)
            (TC 200)
            (TX 0)
        )
        (n3
            (T0 1000)
            (T1 1000)
            (TC 200)
            (TX 0)
        )
        (out
            (T0 1000)
            (T1 1000)
            (TC 200)
            (TX 0)
        )
    )
)
"""

MULTI_INSTANCE_SAIF = """
(SAIF 2.0)
(TIMESCALE 1 ns)
(DURATION 500)
(INSTANCE top
    (INSTANCE sub_a
        (NET
            (sig_a
                (T0 250)
                (T1 250)
                (TC 50)
            )
        )
    )
    (INSTANCE sub_b
        (NET
            (sig_b
                (T0 400)
                (T1 100)
                (TC 10)
            )
        )
    )
)
"""


# ---------------------------------------------------------------------------
# Parsing returns correct top-level data
# ---------------------------------------------------------------------------

class TestSaifTopLevel:
    @pytest.fixture
    def data(self):
        return parse_saif(MINIMAL_SAIF)

    def test_returns_saif_data(self, data):
        assert isinstance(data, SaifData)

    def test_duration_parsed(self, data):
        assert data.duration == 1000

    def test_timescale_parsed(self, data):
        assert "1" in data.timescale
        assert "ns" in data.timescale

    def test_nets_is_dict(self, data):
        assert isinstance(data.nets, dict)

    def test_two_nets_found(self, data):
        assert len(data.nets) == 2

    def test_clk_net_present(self, data):
        assert "clk" in data.nets

    def test_data_net_present(self, data):
        assert "data" in data.nets


# ---------------------------------------------------------------------------
# Per-net activity fields
# ---------------------------------------------------------------------------

class TestNetActivityFields:
    @pytest.fixture
    def data(self):
        return parse_saif(MINIMAL_SAIF)

    def test_clk_T0(self, data):
        assert data.nets["clk"].T0 == 500

    def test_clk_T1(self, data):
        assert data.nets["clk"].T1 == 500

    def test_clk_TC(self, data):
        assert data.nets["clk"].TC == 100

    def test_clk_TX(self, data):
        assert data.nets["clk"].TX == 0

    def test_data_T0(self, data):
        assert data.nets["data"].T0 == 700

    def test_data_T1(self, data):
        assert data.nets["data"].T1 == 300

    def test_data_TC(self, data):
        assert data.nets["data"].TC == 40

    def test_net_activity_type(self, data):
        assert isinstance(data.nets["clk"], NetActivity)


# ---------------------------------------------------------------------------
# Activity factor alpha = TC / (2 × DURATION)
# ---------------------------------------------------------------------------

class TestActivityFactor:
    @pytest.fixture
    def data(self):
        return parse_saif(MINIMAL_SAIF)

    def test_clk_alpha_value(self, data):
        """clk: TC=100, DURATION=1000 → alpha = 100/(2×1000) = 0.05."""
        assert data.nets["clk"].alpha == pytest.approx(0.05)

    def test_data_alpha_value(self, data):
        """data: TC=40, DURATION=1000 → alpha = 40/(2×1000) = 0.02."""
        assert data.nets["data"].alpha == pytest.approx(0.02)

    def test_alpha_is_float_or_none(self, data):
        for net in data.nets.values():
            assert net.alpha is None or isinstance(net.alpha, float)

    def test_50pct_toggle_alpha(self):
        """TC = DURATION → alpha = 0.5 (switches every clock edge)."""
        saif = """
        (SAIF 2.0)
        (DURATION 200)
        (INSTANCE top
            (NET
                (sig (T0 100) (T1 100) (TC 200))
            )
        )
        """
        data = parse_saif(saif)
        assert data.nets["sig"].alpha == pytest.approx(0.5)

    def test_alpha_none_when_duration_zero(self):
        """When DURATION is 0 or absent, alpha should be None."""
        saif = """
        (SAIF 2.0)
        (INSTANCE top
            (NET
                (sig (T0 100) (T1 100) (TC 50))
            )
        )
        """
        data = parse_saif(saif)
        assert data.duration == 0
        assert data.nets["sig"].alpha is None


# ---------------------------------------------------------------------------
# Inverter chain fixture
# ---------------------------------------------------------------------------

class TestInverterChain:
    @pytest.fixture
    def data(self):
        return parse_saif(INVERTER_CHAIN_SAIF)

    def test_five_nets_found(self, data):
        assert len(data.nets) == 5

    def test_all_nets_present(self, data):
        expected = {"in", "n1", "n2", "n3", "out"}
        assert set(data.nets.keys()) == expected

    def test_all_nets_alpha_equal(self, data):
        """All nets have TC=200, DURATION=2000 → alpha = 200/4000 = 0.05."""
        for name, net in data.nets.items():
            assert net.alpha == pytest.approx(0.05), (
                f"net {name!r}: alpha = {net.alpha}, expected 0.05"
            )

    def test_duration(self, data):
        assert data.duration == 2000


# ---------------------------------------------------------------------------
# Multi-level instance hierarchy
# ---------------------------------------------------------------------------

class TestMultiInstance:
    @pytest.fixture
    def data(self):
        return parse_saif(MULTI_INSTANCE_SAIF)

    def test_sig_a_found(self, data):
        assert "sig_a" in data.nets

    def test_sig_b_found(self, data):
        assert "sig_b" in data.nets

    def test_sig_a_TC(self, data):
        assert data.nets["sig_a"].TC == 50

    def test_sig_b_TC(self, data):
        assert data.nets["sig_b"].TC == 10

    def test_sig_a_alpha(self, data):
        """sig_a: TC=50, DURATION=500 → alpha = 50/1000 = 0.05."""
        assert data.nets["sig_a"].alpha == pytest.approx(0.05)

    def test_sig_b_alpha(self, data):
        """sig_b: TC=10, DURATION=500 → alpha = 10/1000 = 0.01."""
        assert data.nets["sig_b"].alpha == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_duration_defaults_zero(self):
        saif = "(SAIF 2.0)"
        data = parse_saif(saif)
        assert data.duration == 0

    def test_no_nets_gives_empty_dict(self):
        saif = "(SAIF 2.0) (DURATION 1000)"
        data = parse_saif(saif)
        assert data.nets == {}

    def test_net_name_preserved(self):
        saif = """
        (SAIF 2.0) (DURATION 100)
        (INSTANCE top
            (NET (my_special_net (TC 10) (T0 50) (T1 50)))
        )
        """
        data = parse_saif(saif)
        assert "my_special_net" in data.nets

    def test_missing_tc_defaults_zero(self):
        """Nets with no TC field should have TC=0."""
        saif = """
        (SAIF 2.0) (DURATION 100)
        (INSTANCE top
            (NET (sig (T0 50) (T1 50)))
        )
        """
        data = parse_saif(saif)
        assert data.nets["sig"].TC == 0

    def test_net_activity_name_set(self):
        saif = """
        (SAIF 2.0) (DURATION 200)
        (INSTANCE top
            (NET (my_net (TC 10) (T0 90) (T1 110)))
        )
        """
        data = parse_saif(saif)
        assert data.nets["my_net"].name == "my_net"
