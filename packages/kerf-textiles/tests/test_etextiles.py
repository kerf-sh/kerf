"""
Analytic oracles for the e-textiles module.

DoD requirements covered
------------------------
1. Resistive-heating calc matches I²R to 1% tolerance.
2. LED-fabric layout computes correct serial + parallel branch currents
   (Kirchhoff KVL + KCL).
3. Conductive-thread routing produces a valid polyline path on a garment
   panel UV space; arc length is correct.
4. Convenience presets (yarn + LED) are importable and sane.
"""

from __future__ import annotations

import math
import pytest

from kerf_textiles.etextiles import (
    # yarn / heating
    ResistiveYarn,
    HeaterSegment,
    heating_calc,
    # routing
    ThreadRoute,
    thread_route,
    # LED
    LEDNode,
    LEDBranch,
    LEDLayout,
    led_layout,
    # presets
    YARN_SHIELDEX_117,
    YARN_BEKINOX_50,
    LED_FLORA_NEOPIXEL,
    LED_FLORA_RGB,
)


# ---------------------------------------------------------------------------
# Resistive heating — I²R oracle
# ---------------------------------------------------------------------------

class TestHeatingCalc:
    """
    The fundamental oracle: P_computed = I² × R must match I² × (r_per_m × L)
    to within 1%.  We use exact floating-point arithmetic so the match is
    exact (well within 1%).
    """

    def test_basic_i2r(self):
        """
        Oracle: yarn 10 Ω/m, L=0.5 m, I=0.1 A
          R = 10 * 0.5 = 5 Ω
          P = 0.1² * 5 = 0.05 W
        """
        yarn = ResistiveYarn(name="test", resistance_per_metre=10.0)
        result = heating_calc(yarn, length_m=0.5, current_a=0.1)
        assert result["resistance_ohm"] == pytest.approx(5.0, rel=1e-9)
        assert result["power_w"] == pytest.approx(0.05, rel=1e-9)

    def test_power_matches_i2r_within_1pct(self):
        """
        Explicit 1% oracle: for any valid (yarn, L, I) the returned power_w
        must match I² * r_per_m * L to within 1%.
        """
        yarn = ResistiveYarn(name="oracle", resistance_per_metre=25.0)
        L = 1.2   # m
        I = 0.08  # A
        result = heating_calc(yarn, length_m=L, current_a=I)
        expected_power = I ** 2 * yarn.resistance_per_metre * L
        rel_error = abs(result["power_w"] - expected_power) / expected_power
        assert rel_error < 0.01, (
            f"Power error {rel_error:.4%} exceeds 1% tolerance: "
            f"got {result['power_w']}, expected {expected_power}"
        )

    def test_voltage_drop(self):
        """V = I * R."""
        yarn = ResistiveYarn(name="v_test", resistance_per_metre=100.0)
        result = heating_calc(yarn, length_m=0.3, current_a=0.05)
        expected_v = 0.05 * 100.0 * 0.3  # 1.5 V
        assert result["voltage_drop_v"] == pytest.approx(expected_v, rel=1e-9)

    def test_zero_current_zero_power(self):
        """I=0 → P=0."""
        yarn = ResistiveYarn(name="zero", resistance_per_metre=50.0)
        result = heating_calc(yarn, length_m=1.0, current_a=0.0)
        assert result["power_w"] == pytest.approx(0.0, abs=1e-12)
        assert result["voltage_drop_v"] == pytest.approx(0.0, abs=1e-12)

    def test_shieldex_preset(self):
        """
        Oracle for YARN_SHIELDEX_117 (30 Ω/m):
          L=0.5 m, I=0.04 A → R=15 Ω, P=0.024 W, V=0.6 V
        """
        result = heating_calc(YARN_SHIELDEX_117, length_m=0.5, current_a=0.04)
        assert result["resistance_ohm"] == pytest.approx(15.0, rel=1e-9)
        assert result["power_w"] == pytest.approx(0.04 ** 2 * 15.0, rel=1e-9)
        assert result["voltage_drop_v"] == pytest.approx(0.04 * 15.0, rel=1e-9)

    def test_bekinox_preset(self):
        """
        Oracle for YARN_BEKINOX_50 (4.5 Ω/m):
          L=2.0 m, I=0.15 A → R=9 Ω, P=0.2025 W
        """
        result = heating_calc(YARN_BEKINOX_50, length_m=2.0, current_a=0.15)
        assert result["resistance_ohm"] == pytest.approx(9.0, rel=1e-9)
        assert result["power_w"] == pytest.approx(0.15 ** 2 * 9.0, rel=1e-6)

    def test_echoes_input(self):
        """Result must echo back current_a and length_m."""
        yarn = ResistiveYarn(name="echo", resistance_per_metre=5.0)
        result = heating_calc(yarn, length_m=1.7, current_a=0.12)
        assert result["current_a"] == pytest.approx(0.12)
        assert result["length_m"] == pytest.approx(1.7)

    def test_heater_segment_properties(self):
        """HeaterSegment properties must agree with healing_calc."""
        yarn = ResistiveYarn(name="seg", resistance_per_metre=20.0)
        seg = HeaterSegment(yarn=yarn, length_m=0.8, current_a=0.1)
        assert seg.resistance == pytest.approx(16.0, rel=1e-9)
        assert seg.power_w == pytest.approx(0.1 ** 2 * 16.0, rel=1e-9)
        assert seg.voltage_drop == pytest.approx(0.1 * 16.0, rel=1e-9)

    def test_negative_resistance_raises(self):
        with pytest.raises(ValueError):
            ResistiveYarn(name="bad", resistance_per_metre=-1.0)

    def test_negative_length_raises(self):
        yarn = ResistiveYarn(name="ok", resistance_per_metre=10.0)
        with pytest.raises(ValueError):
            HeaterSegment(yarn=yarn, length_m=-0.1, current_a=0.1)


# ---------------------------------------------------------------------------
# Conductive-thread routing
# ---------------------------------------------------------------------------

class TestThreadRoute:
    """
    Verify the UV polyline routing over a garment panel.
    """

    def _make_route(self) -> ThreadRoute:
        """A simple L-shaped route on a 0.5 m × 0.4 m panel."""
        return thread_route(
            panel_name="front-bodice",
            waypoints=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
            panel_width_m=0.5,
            panel_height_m=0.4,
        )

    def test_arc_length_axis_aligned(self):
        """
        Horizontal segment (0,0)→(1,0) on a 0.5 m wide panel:
          length = 1.0 * 0.5 = 0.5 m
        Vertical segment (1,0)→(1,1) on a 0.4 m tall panel:
          length = 1.0 * 0.4 = 0.4 m
        Total = 0.9 m
        """
        route = self._make_route()
        assert route.arc_length_m == pytest.approx(0.9, rel=1e-9)

    def test_segment_lengths(self):
        route = self._make_route()
        segs = route.segment_lengths_m
        assert len(segs) == 2
        assert segs[0] == pytest.approx(0.5, rel=1e-9)
        assert segs[1] == pytest.approx(0.4, rel=1e-9)

    def test_diagonal_route(self):
        """
        Diagonal (0,0)→(1,1) on a 0.3 m × 0.4 m panel:
          length = sqrt(0.3² + 0.4²) = sqrt(0.09 + 0.16) = sqrt(0.25) = 0.5 m
        """
        route = thread_route(
            panel_name="sleeve",
            waypoints=[(0.0, 0.0), (1.0, 1.0)],
            panel_width_m=0.3,
            panel_height_m=0.4,
        )
        assert route.arc_length_m == pytest.approx(0.5, rel=1e-9)

    def test_single_waypoint_zero_length(self):
        """A single waypoint has arc length 0."""
        route = thread_route(
            panel_name="collar",
            waypoints=[(0.5, 0.5)],
            panel_width_m=0.2,
            panel_height_m=0.2,
        )
        assert route.arc_length_m == pytest.approx(0.0, abs=1e-12)

    def test_route_with_yarn_heating(self):
        """Route with yarn gives heating result on demand."""
        yarn = ResistiveYarn(name="trace", resistance_per_metre=30.0)
        route = thread_route(
            panel_name="back",
            waypoints=[(0.0, 0.0), (1.0, 0.0)],
            panel_width_m=0.6,
            panel_height_m=0.5,
            yarn=yarn,
        )
        # arc length = 0.6 m, R = 30 * 0.6 = 18 Ω
        result = route.heating(current_a=0.05)
        assert result is not None
        assert result["resistance_ohm"] == pytest.approx(18.0, rel=1e-9)
        assert result["power_w"] == pytest.approx(0.05 ** 2 * 18.0, rel=1e-9)

    def test_route_no_yarn_heating_none(self):
        """Route without yarn returns None for heating."""
        route = thread_route(
            panel_name="cuff",
            waypoints=[(0.0, 0.0), (0.5, 0.5)],
            panel_width_m=0.2,
            panel_height_m=0.1,
        )
        assert route.heating(current_a=0.1) is None

    def test_out_of_range_uv_raises(self):
        """Waypoints outside [0,1]² must raise ValueError."""
        with pytest.raises(ValueError, match="UV"):
            thread_route(
                panel_name="x",
                waypoints=[(0.0, 0.0), (1.5, 0.5)],  # u=1.5 out of range
                panel_width_m=0.5,
                panel_height_m=0.5,
            )

    def test_panel_name_stored(self):
        route = self._make_route()
        assert route.panel_name == "front-bodice"

    def test_waypoints_preserved(self):
        wps = [(0.0, 0.0), (0.5, 0.5), (1.0, 0.0)]
        route = thread_route("panel", wps, 1.0, 1.0)
        assert route.waypoints == wps

    def test_multipoint_route_matches_sum(self):
        """Multi-segment route: total == sum of segments."""
        wps = [(0.0, 0.0), (0.25, 0.0), (0.5, 0.5), (1.0, 1.0)]
        route = thread_route("x", wps, 1.0, 1.0)
        segs = route.segment_lengths_m
        assert route.arc_length_m == pytest.approx(sum(segs), rel=1e-9)


# ---------------------------------------------------------------------------
# LED-fabric layout — Kirchhoff current oracles
# ---------------------------------------------------------------------------

class TestLEDLayout:
    """
    Kirchhoff KVL + KCL oracles.

    For a series branch with N_s LEDs (Vf each) and R_series, driven at Vsupply:
        I_branch = (Vsupply - N_s * Vf) / R_series     [A]

    For M parallel branches:
        I_total = M * I_branch                          [A]
    """

    def _flora_led(self) -> LEDNode:
        return LEDNode(name="test-led", vf_v=3.5, if_ma=60.0)

    def test_single_series_branch_current(self):
        """
        1 LED (Vf=3.5 V) + R=47 Ω, Vsupply=5.0 V:
          I = (5.0 - 3.5) / 47 = 1.5 / 47 ≈ 0.031915 A
        """
        led = self._flora_led()
        branch = LEDBranch(nodes=[led], r_series_ohm=47.0)
        I = branch.branch_current_a(vsupply=5.0)
        expected = (5.0 - 3.5) / 47.0
        assert I == pytest.approx(expected, rel=1e-6)

    def test_two_series_leds(self):
        """
        2 LEDs in series (Vf=3.5 each) + R=22 Ω, Vsupply=9.0 V:
          I = (9.0 - 2*3.5) / 22 = 2.0/22 ≈ 0.09091 A
        """
        led = self._flora_led()
        branch = LEDBranch(nodes=[led, led], r_series_ohm=22.0)
        I = branch.branch_current_a(vsupply=9.0)
        expected = (9.0 - 2 * 3.5) / 22.0
        assert I == pytest.approx(expected, rel=1e-6)

    def test_parallel_branches_total_current(self):
        """
        4 parallel branches each with I_branch=0.02 A → I_total=0.08 A (KCL).
        """
        led = LEDNode(name="led", vf_v=2.0, if_ma=20.0)
        # Vsupply=5V, R=150Ω → I_branch = (5 - 2) / 150 = 0.02 A
        layout = led_layout(
            vsupply=5.0,
            n_parallel=4,
            n_series=1,
            led=led,
            r_series_ohm=150.0,
        )
        sol = layout.solve()
        expected_branch_i = (5.0 - 2.0) / 150.0
        assert all(
            pytest.approx(i, rel=1e-6) == expected_branch_i
            for i in sol["branch_currents_a"]
        )
        assert sol["total_current_a"] == pytest.approx(4 * expected_branch_i, rel=1e-6)

    def test_kirchhoff_kcl_total_equals_sum(self):
        """
        KCL oracle: total_current_a == sum(branch_currents_a) regardless of topology.
        """
        led = self._flora_led()
        layout = led_layout(
            vsupply=5.0,
            n_parallel=6,
            n_series=1,
            led=led,
            r_series_ohm=47.0,
        )
        sol = layout.solve()
        assert sol["total_current_a"] == pytest.approx(
            sum(sol["branch_currents_a"]), rel=1e-9
        )

    def test_serial_voltage_drop(self):
        """
        KVL oracle: Vsupply == Σ Vf + I * R_series per branch.
        """
        led = LEDNode(name="led", vf_v=3.3, if_ma=20.0)
        r = 68.0
        vsupply = 5.0
        branch = LEDBranch(nodes=[led], r_series_ohm=r)
        I = branch.branch_current_a(vsupply)
        # KVL: Vsupply = Vf + I*R
        assert vsupply == pytest.approx(led.vf_v + I * r, rel=1e-6)

    def test_reverse_biased_branch_zero_current(self):
        """Branch with Vsupply < Σ Vf → I_branch = 0."""
        led = LEDNode(name="led", vf_v=3.5, if_ma=20.0)
        branch = LEDBranch(nodes=[led, led, led], r_series_ohm=10.0)  # 3*3.5=10.5 V
        I = branch.branch_current_a(vsupply=5.0)
        assert I == pytest.approx(0.0, abs=1e-9)

    def test_total_leds_count(self):
        """total_leds = n_parallel * n_series."""
        led = self._flora_led()
        layout = led_layout(vsupply=5.0, n_parallel=3, n_series=2, led=led, r_series_ohm=47.0)
        assert layout.total_leds == 6
        assert layout.n_branches == 3

    def test_total_power(self):
        """total_power_w = Vsupply * I_total."""
        led = LEDNode(name="led", vf_v=2.0, if_ma=20.0)
        layout = led_layout(vsupply=5.0, n_parallel=2, n_series=1, led=led, r_series_ohm=100.0)
        sol = layout.solve()
        expected_power = 5.0 * sol["total_current_a"]
        assert sol["total_power_w"] == pytest.approx(expected_power, rel=1e-9)

    def test_flora_neopixel_preset(self):
        """
        4 Flora NeoPixels (Vf=3.5 V, 60 mA each) in parallel, each with R=0 Ω
        and driven at 5V.  With R_series=0 the driver is ideal; branch_current_a
        returns if_ma / 1000 = 0.06 A per branch.
        Total = 4 * 0.06 = 0.24 A.
        """
        layout = led_layout(
            vsupply=5.0,
            n_parallel=4,
            n_series=1,
            led=LED_FLORA_NEOPIXEL,
            r_series_ohm=0.0,
        )
        sol = layout.solve()
        assert sol["total_current_a"] == pytest.approx(4 * 0.06, rel=1e-6)

    def test_branch_vf_sums(self):
        """branch_vf_sums = [N_s * Vf, ...] for each branch."""
        led = LEDNode(name="led", vf_v=2.5, if_ma=20.0)
        layout = led_layout(vsupply=5.0, n_parallel=3, n_series=2, led=led, r_series_ohm=10.0)
        sol = layout.solve()
        assert all(pytest.approx(v, rel=1e-9) == 5.0 for v in sol["branch_vf_sums"])

    def test_invalid_n_parallel_raises(self):
        with pytest.raises(ValueError):
            led_layout(vsupply=5.0, n_parallel=0, n_series=1, led=self._flora_led())

    def test_invalid_n_series_raises(self):
        with pytest.raises(ValueError):
            led_layout(vsupply=5.0, n_parallel=1, n_series=0, led=self._flora_led())

    def test_led_node_negative_vf_raises(self):
        with pytest.raises(ValueError):
            LEDNode(name="bad", vf_v=-1.0, if_ma=20.0)

    def test_empty_branch_raises(self):
        with pytest.raises(ValueError):
            LEDBranch(nodes=[], r_series_ohm=10.0)


# ---------------------------------------------------------------------------
# Cross-module: routing + heating integration
# ---------------------------------------------------------------------------

class TestRoutingHeatingIntegration:
    """
    End-to-end: route a heater trace on a garment panel, compute its
    resistance and power, verify I²R to 1%.
    """

    def test_serpentine_heater(self):
        """
        Serpentine trace on 0.4 m × 0.3 m panel:
          waypoints: zigzag across 5 horizontal lines
          using YARN_BEKINOX_50 (4.5 Ω/m), I=0.15 A

        Each horizontal segment spans u=0→1 (0.4 m wide).
        4 vertical transitions of Δv=0.25 each (0.3 m tall → each = 0.075 m).
        Total: 5 horizontal × 0.4 m + 4 vertical × 0.075 m
             = 2.0 + 0.3 = 2.3 m
        R = 4.5 * 2.3 = 10.35 Ω
        P = 0.15² * 10.35 = 0.232875 W
        """
        waypoints = [
            (0.0, 0.00), (1.0, 0.00),
            (1.0, 0.25), (0.0, 0.25),
            (0.0, 0.50), (1.0, 0.50),
            (1.0, 0.75), (0.0, 0.75),
            (0.0, 1.00), (1.0, 1.00),
        ]
        route = thread_route(
            panel_name="back-heater",
            waypoints=waypoints,
            panel_width_m=0.4,
            panel_height_m=0.3,
            yarn=YARN_BEKINOX_50,
        )
        expected_length = 5 * 0.4 + 4 * 0.075
        assert route.arc_length_m == pytest.approx(expected_length, rel=1e-9)

        result = route.heating(current_a=0.15)
        assert result is not None
        expected_p = 0.15 ** 2 * YARN_BEKINOX_50.resistance_per_metre * expected_length
        rel_err = abs(result["power_w"] - expected_p) / expected_p
        assert rel_err < 0.01, (
            f"Serpentine power error {rel_err:.4%} > 1%: "
            f"got {result['power_w']:.6f} W, expected {expected_p:.6f} W"
        )

    def test_i2r_rel_error_below_1pct(self):
        """
        Parametric sweep: for 10 different (length, current) combinations,
        ensure power error < 1%.
        """
        yarn = ResistiveYarn(name="sweep", resistance_per_metre=15.0)
        test_cases = [
            (0.1, 0.01),
            (0.5, 0.05),
            (1.0, 0.10),
            (2.0, 0.20),
            (0.3, 0.15),
            (0.8, 0.08),
            (1.5, 0.30),
            (0.2, 0.25),
            (3.0, 0.05),
            (0.7, 0.12),
        ]
        for L, I in test_cases:
            result = heating_calc(yarn, length_m=L, current_a=I)
            expected_p = I ** 2 * yarn.resistance_per_metre * L
            rel_err = abs(result["power_w"] - expected_p) / expected_p if expected_p > 0 else 0.0
            assert rel_err < 0.01, (
                f"L={L}, I={I}: power error {rel_err:.4%} > 1%"
            )
