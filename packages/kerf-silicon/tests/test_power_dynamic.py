"""test_power_dynamic.py — pytest suite for kerf_silicon.power.dynamic.

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \
        python3 -m pytest packages/kerf-silicon/tests/test_power_dynamic.py -x

Analytic oracle
---------------
1 pF net at 100 MHz, 1 V supply, α = 0.5:

    P = 0.5 × α × C × V² × f
      = 0.5 × 0.5 × 1e-12 × 1.0² × 100e6
      = 0.25 × 1e-12 × 1e8
      = 0.25 × 1e-4
      = 2.5e-5 W  (25 µW)
"""
from __future__ import annotations

import math
import pytest

from kerf_silicon.power.dynamic import (
    dynamic_power,
    dynamic_power_report,
    DynamicPowerReport,
    NetPowerEntry,
)


# ---------------------------------------------------------------------------
# Core formula — analytic oracle
# ---------------------------------------------------------------------------

class TestDynamicPowerFormula:
    def test_oracle_1pF_100MHz_1V_alpha05(self):
        """Primary oracle: 1 pF, 100 MHz, 1 V, α=0.5 → 25 µW."""
        P = dynamic_power(
            capacitance_F=1e-12,
            voltage_V=1.0,
            freq_Hz=100e6,
            alpha=0.5,
        )
        expected = 25e-6  # 25 µW
        assert abs(P - expected) < 1e-12, (
            f"P = {P:.3e} W, expected {expected:.3e} W (25 µW)"
        )

    def test_oracle_exact_formula(self):
        """Verify result equals exactly 0.5 * alpha * C * V^2 * f."""
        C, V, f, alpha = 1e-12, 1.0, 100e6, 0.5
        expected = 0.5 * alpha * C * (V ** 2) * f
        assert dynamic_power(C, V, f, alpha) == pytest.approx(expected)

    def test_zero_capacitance_gives_zero_power(self):
        P = dynamic_power(capacitance_F=0.0, voltage_V=1.8, freq_Hz=1e9, alpha=0.5)
        assert P == 0.0

    def test_zero_alpha_gives_zero_power(self):
        P = dynamic_power(capacitance_F=1e-12, voltage_V=1.8, freq_Hz=1e9, alpha=0.0)
        assert P == 0.0

    def test_alpha_one_doubles_power_vs_alpha_half(self):
        """α=1.0 gives exactly twice the power of α=0.5."""
        P05 = dynamic_power(1e-12, 1.8, 100e6, alpha=0.5)
        P10 = dynamic_power(1e-12, 1.8, 100e6, alpha=1.0)
        assert P10 == pytest.approx(2 * P05)

    def test_power_scales_with_capacitance(self):
        """Doubling capacitance doubles power."""
        P1 = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        P2 = dynamic_power(2e-12, 1.0, 100e6, 0.5)
        assert P2 == pytest.approx(2 * P1)

    def test_power_scales_quadratically_with_voltage(self):
        """Doubling voltage quadruples power."""
        P1 = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        P2 = dynamic_power(1e-12, 2.0, 100e6, 0.5)
        assert P2 == pytest.approx(4 * P1)

    def test_power_scales_linearly_with_frequency(self):
        """Doubling frequency doubles power."""
        P1 = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        P2 = dynamic_power(1e-12, 1.0, 200e6, 0.5)
        assert P2 == pytest.approx(2 * P1)

    def test_default_alpha_is_0p5(self):
        """When alpha is omitted, the default must be 0.5."""
        P_default = dynamic_power(1e-12, 1.0, 100e6)
        P_explicit = dynamic_power(1e-12, 1.0, 100e6, alpha=0.5)
        assert P_default == P_explicit

    def test_1p8V_typical_operating(self):
        """Representative: 100 fF, 1.8 V, 500 MHz, α=0.3."""
        C, V, f, alpha = 100e-15, 1.8, 500e6, 0.3
        expected = 0.5 * alpha * C * V ** 2 * f
        assert dynamic_power(C, V, f, alpha) == pytest.approx(expected, rel=1e-9)

    def test_result_is_float(self):
        P = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        assert isinstance(P, float)

    def test_25uW_magnitude_order(self):
        """25 µW = 2.5e-5 W — verify it is in the micro-watt range."""
        P = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        assert 1e-6 < P < 1e-3, f"Expected µW range, got {P:.3e} W"


# ---------------------------------------------------------------------------
# Report API
# ---------------------------------------------------------------------------

class TestDynamicPowerReport:
    def test_single_net_report(self):
        caps = {"net_clk": 1e-12}
        report = dynamic_power_report(
            net_capacitances=caps,
            voltage_V=1.0,
            freq_Hz=100e6,
            activity_factors={"net_clk": 0.5},
        )
        assert isinstance(report, DynamicPowerReport)
        assert len(report.nets) == 1
        assert report.nets[0].net_name == "net_clk"
        assert report.nets[0].power_W == pytest.approx(25e-6)

    def test_total_power_sums_nets(self):
        caps = {"A": 1e-12, "B": 2e-12}
        report = dynamic_power_report(
            caps, voltage_V=1.0, freq_Hz=100e6,
            activity_factors={"A": 0.5, "B": 0.5},
        )
        P_A = dynamic_power(1e-12, 1.0, 100e6, 0.5)
        P_B = dynamic_power(2e-12, 1.0, 100e6, 0.5)
        assert report.total_W == pytest.approx(P_A + P_B)

    def test_missing_activity_uses_default_alpha(self):
        caps = {"net_x": 1e-12}
        report = dynamic_power_report(
            caps, voltage_V=1.0, freq_Hz=100e6,
            activity_factors={},
            default_alpha=0.3,
        )
        expected = dynamic_power(1e-12, 1.0, 100e6, alpha=0.3)
        assert report.nets[0].power_W == pytest.approx(expected)

    def test_empty_nets(self):
        report = dynamic_power_report({}, voltage_V=1.8, freq_Hz=1e9)
        assert report.total_W == 0.0
        assert report.nets == []

    def test_report_stores_voltage_and_freq(self):
        report = dynamic_power_report({}, voltage_V=1.8, freq_Hz=500e6)
        assert report.voltage_V == pytest.approx(1.8)
        assert report.freq_Hz == pytest.approx(500e6)

    def test_net_entry_stores_capacitance_and_alpha(self):
        caps = {"my_net": 5e-12}
        report = dynamic_power_report(
            caps, voltage_V=1.0, freq_Hz=100e6,
            activity_factors={"my_net": 0.4},
        )
        entry = report.nets[0]
        assert entry.capacitance_F == pytest.approx(5e-12)
        assert entry.alpha == pytest.approx(0.4)
