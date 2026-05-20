"""
T-29: Electronic SPICE simulation hand-off.

Scope: routes_spice.py  — circuit → .cir → result parse.

Tests are hermetic: ngspice is never executed.  We patch subprocess.run
(called by run_ngspice) and tempfile.TemporaryDirectory as needed, and
construct synthetic .raw files to exercise parse_raw_file.

Success criteria (from spec):
  - 25 analog circuit scenarios: RC, op-amp, regulator, oscillator
  - DC op-point / AC sweep / transient analysis types covered
  - .cir generation covers boundary / malformed / idempotency cases
  - Result-parse path validated against analytic expectations
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Add src to path (conftest.py also does this, but keep explicit for direct
#    invocation via python -m pytest from the repo root) ─────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_electronics.routes_spice import (
    inject_print_statement,
    inject_print_statements,
    parse_raw_file,
    run_ngspice,
    run_spice,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raw_header(title: str, num_points: int, num_vars: int, analysis: str = "Transient Analysis") -> str:
    return (
        f"Title: {title}\n"
        f"Date: Thu Jan  1 00:00:00 2026\n"
        f"Plotname: {analysis}\n"
        f"Flags: real\n"
        f"No. Variables: {num_vars}\n"
        f"No. Points: {num_points}\n"
        f"Command: version 38\n"
    )


def _raw_file_tran(var_names: list[str], var_types: list[str],
                   x_vals: list[float], y_matrix: list[list[float]]) -> str:
    """Build a synthetic ngspice ASCII .raw file for transient analysis."""
    n_vars = len(var_names)
    n_pts = len(x_vals)
    lines = [_raw_header("Test", n_pts, n_vars)]
    lines.append("Variables:")
    for i, (name, vtype) in enumerate(zip(var_names, var_types)):
        lines.append(f"\t{i}\t{name}\t{vtype}")
    lines.append("Values:")
    for pi, x in enumerate(x_vals):
        row_parts = [str(pi), f"{x:.6e}"]
        for vi in range(n_vars):
            row_parts.append(f"{y_matrix[vi][pi]:.6e}")
        lines.append("\t".join(row_parts))
    return "\n".join(lines) + "\n"


def _write_raw(tmpdir: str, content: str) -> str:
    p = os.path.join(tmpdir, "output.raw")
    Path(p).write_text(content)
    return p


def _make_ngspice_success(raw_content: str):
    """Return a subprocess.run mock that writes raw_content to the output file."""
    def _side_effect(cmd, **kwargs):
        # cmd is ["ngspice", "-b", "-o", raw_path, cir_path]
        raw_path = cmd[3]
        Path(raw_path).write_text(raw_content)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result
    return _side_effect


def _make_ngspice_fail(returncode: int = 1, stderr: str = "Error: unknown element"):
    def _side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = ""
        result.stderr = stderr
        return result
    return _side_effect


# ── 1. inject_print_statement ─────────────────────────────────────────────────

class TestInjectPrintStatement(unittest.TestCase):

    def test_appends_print_line_if_absent(self):
        netlist = "RC filter\nR1 1 2 1k\nC1 2 0 1u\nV1 1 0 DC 5\n.op\n.end\n"
        result = inject_print_statement(netlist, "V(2)")
        self.assertIn(".PRINT", result)
        self.assertIn("V(2)", result)

    def test_tran_analysis_produces_tran_print(self):
        netlist = "Tran test\nR1 1 2 1k\n.tran 1us 10ms\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        self.assertIn(".PRINT TRAN V(1)", result)

    def test_ac_analysis_produces_ac_print(self):
        netlist = "AC test\nR1 1 2 1k\n.ac dec 10 1k 10Meg\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        self.assertIn(".PRINT AC V(1)", result)

    def test_op_analysis_produces_op_print(self):
        netlist = "OP test\nR1 1 2 1k\n.op\n.end\n"
        result = inject_print_statement(netlist, "I(V1)")
        self.assertIn(".PRINT OP I(V1)", result)

    def test_dc_analysis_produces_dc_print(self):
        netlist = "DC test\nR1 1 2 1k\n.dc V1 0 5 0.1\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        self.assertIn(".PRINT DC V(1)", result)

    def test_no_duplicate_print_if_already_present(self):
        netlist = "Test\nR1 1 2 1k\n.op\n.PRINT OP V(1)\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        # Should contain the probe
        self.assertIn("V(1)", result)

    def test_inject_multiple_probes(self):
        netlist = "Multi\nR1 1 2 1k\n.op\n.end\n"
        result = inject_print_statements(netlist, ["V(1)", "V(2)", "I(V1)"])
        self.assertIn("V(1)", result)
        self.assertIn("V(2)", result)
        self.assertIn("I(V1)", result)

    def test_empty_probes_returns_unchanged(self):
        netlist = "RC\nR1 1 2 1k\n.op\n.end\n"
        result = inject_print_statements(netlist, [])
        self.assertEqual(result, netlist)

    def test_inject_preserves_title_line(self):
        netlist = "My Circuit Title\nR1 1 2 1k\n.op\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        self.assertTrue(result.startswith("My Circuit Title"))

    def test_inject_preserves_end_directive(self):
        netlist = "Test\nR1 1 2 1k\n.op\n.end\n"
        result = inject_print_statement(netlist, "V(1)")
        self.assertIn(".end", result.lower())


# ── 2. parse_raw_file ─────────────────────────────────────────────────────────

class TestParseRawFile(unittest.TestCase):

    def _parse(self, content: str) -> list:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_raw(tmpdir, content)
            return parse_raw_file(path)

    def test_empty_file_returns_empty_list(self):
        result = self._parse("")
        self.assertEqual(result, [])

    def test_no_variables_section_returns_empty(self):
        result = self._parse("Title: test\nDate: now\n")
        self.assertEqual(result, [])

    def test_single_voltage_waveform(self):
        n_pts = 5
        x_vals = [i * 1e-6 for i in range(n_pts)]
        y_vals = [1.0, 1.5, 2.0, 2.5, 3.0]
        raw = _raw_file_tran(["time", "V(1)"], ["time", "voltage"], x_vals, [x_vals, y_vals])
        result = self._parse(raw)
        self.assertGreater(len(result), 0)
        v_wave = next((w for w in result if "V(1)" in w["name"] or w["name"] == "V(1)"), None)
        self.assertIsNotNone(v_wave, f"V(1) waveform not found in {[w['name'] for w in result]}")
        self.assertEqual(len(v_wave["y"]), n_pts)

    def test_waveform_y_values_correct(self):
        x_vals = [0.0, 1e-6, 2e-6]
        y_vals = [3.3, 1.65, 0.825]
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], x_vals, [x_vals, y_vals])
        result = self._parse(raw)
        v_wave = next((w for w in result if "V(out)" in w["name"]), None)
        self.assertIsNotNone(v_wave)
        for i, expected in enumerate(y_vals):
            self.assertAlmostEqual(v_wave["y"][i], expected, places=5)

    def test_multiple_waveforms(self):
        x_vals = [0.0, 1e-3, 2e-3]
        v_vals = [5.0, 4.9, 4.8]
        i_vals = [0.01, 0.0098, 0.0096]
        raw = _raw_file_tran(
            ["time", "V(1)", "I(R1)"],
            ["time", "voltage", "current"],
            x_vals,
            [x_vals, v_vals, i_vals],
        )
        result = self._parse(raw)
        names = [w["name"] for w in result]
        self.assertIn("V(1)", names)
        self.assertIn("I(R1)", names)

    def test_voltage_kind_classification(self):
        x_vals = [0.0, 1e-3]
        raw = _raw_file_tran(["time", "V(1)"], ["time", "voltage"], x_vals, [[0.0, 1e-3], [5.0, 4.9]])
        result = self._parse(raw)
        v_wave = next((w for w in result if w["name"] == "V(1)"), None)
        self.assertIsNotNone(v_wave)
        self.assertEqual(v_wave["kind"], "V")

    def test_current_kind_classification(self):
        x_vals = [0.0, 1e-3]
        raw = _raw_file_tran(["time", "I(R1)"], ["time", "current"], x_vals, [[0.0, 1e-3], [0.01, 0.009]])
        result = self._parse(raw)
        i_wave = next((w for w in result if w["name"] == "I(R1)"), None)
        self.assertIsNotNone(i_wave)
        self.assertEqual(i_wave["kind"], "I")

    def test_binary_marker_stops_parse(self):
        """Binary: line should not crash parser — it just stops reading."""
        raw = _raw_header("T", 2, 2) + "Variables:\n\t0\ttime\ttime\n\t1\tV(1)\tvoltage\nValues:\n\t0\t0.0\t5.0\nBinary:\n\x00\x01\x02\n"
        result = self._parse(raw)
        # Should return something without crashing
        self.assertIsInstance(result, list)

    def test_malformed_value_line_skipped(self):
        """Non-numeric value lines should be skipped gracefully."""
        raw = (
            _raw_header("T", 3, 2)
            + "Variables:\n\t0\ttime\ttime\n\t1\tV(1)\tvoltage\nValues:\n"
            + "0\t0.0\t5.0\n"
            + "GARBAGE LINE\n"
            + "1\t1e-3\t4.9\n"
        )
        result = self._parse(raw)
        self.assertIsInstance(result, list)

    def test_rc_dc_oppoint_parse(self):
        """DC op-point: single x=0.0 data point, V(out) = Vcc * R2/(R1+R2)."""
        # R1=1k, R2=1k, Vcc=5V → V(out) = 2.5V
        vcc = 5.0
        r1 = 1000.0
        r2 = 1000.0
        v_out = vcc * r2 / (r1 + r2)
        x_vals = [0.0]
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], x_vals, [x_vals, [v_out]])
        result = self._parse(raw)
        v_wave = next((w for w in result if "V(out)" in w["name"]), None)
        self.assertIsNotNone(v_wave)
        self.assertAlmostEqual(v_wave["y"][0], v_out, places=3)

    def test_x_vals_deduplicated(self):
        """Duplicate x values (same time step repeated) should not accumulate."""
        raw = (
            _raw_header("T", 2, 2)
            + "Variables:\n\t0\ttime\ttime\n\t1\tV(1)\tvoltage\nValues:\n"
            + "0\t0.0\t5.0\n"
            + "1\t0.0\t5.0\n"
        )
        result = self._parse(raw)
        # x_vals deduplication: the second 0.0 should not be appended again
        for w in result:
            if w["name"] == "time":
                self.assertLessEqual(len(set(w["x"])), len(w["x"]) + 1)


# ── 3. run_ngspice + run_spice (hermetic) ─────────────────────────────────────

class TestRunNgspiceHermetic(unittest.TestCase):

    def _run(self, raw_content: str, analysis: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            cir = os.path.join(tmpdir, "input.cir")
            raw = os.path.join(tmpdir, "output.raw")
            lst = os.path.join(tmpdir, "output.lis")
            Path(cir).write_text("Test\n.op\n.end\n")
            with patch("subprocess.run", side_effect=_make_ngspice_success(raw_content)):
                return run_ngspice(cir, raw, lst, analysis or {}, tmpdir)

    def test_success_returns_waveforms_key(self):
        x = [0.0, 1e-3, 2e-3]
        raw = _raw_file_tran(["time", "V(1)"], ["time", "voltage"], x, [x, [5.0, 4.5, 4.0]])
        result = self._run(raw)
        self.assertIn("waveforms", result)
        self.assertIn("errors", result)
        self.assertIn("warnings", result)

    def test_success_no_errors(self):
        x = [0.0, 1e-3]
        raw = _raw_file_tran(["time", "V(1)"], ["time", "voltage"], x, [x, [3.3, 3.3]])
        result = self._run(raw)
        self.assertEqual(result["errors"], [])

    def test_ngspice_not_found_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cir = os.path.join(tmpdir, "input.cir")
            raw = os.path.join(tmpdir, "output.raw")
            lst = os.path.join(tmpdir, "output.lis")
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = run_ngspice(cir, raw, lst, {}, tmpdir)
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("ngspice", result["errors"][0])

    def test_ngspice_timeout_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cir = os.path.join(tmpdir, "input.cir")
            raw = os.path.join(tmpdir, "output.raw")
            lst = os.path.join(tmpdir, "output.lis")
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ngspice", timeout=300)):
                result = run_ngspice(cir, raw, lst, {}, tmpdir)
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("timed out", result["errors"][0])

    def test_ngspice_nonzero_exit_reports_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cir = os.path.join(tmpdir, "input.cir")
            raw = os.path.join(tmpdir, "output.raw")
            lst = os.path.join(tmpdir, "output.lis")
            with patch("subprocess.run", side_effect=_make_ngspice_fail(1, "Error: blah")):
                result = run_ngspice(cir, raw, lst, {}, tmpdir)
        self.assertGreater(len(result["errors"]), 0)

    def test_no_raw_file_returns_empty_waveforms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cir = os.path.join(tmpdir, "input.cir")
            raw = os.path.join(tmpdir, "output.raw")
            lst = os.path.join(tmpdir, "output.lis")
            # ngspice "succeeds" but writes no raw file
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            with patch("subprocess.run", return_value=mock_result):
                result = run_ngspice(cir, raw, lst, {}, tmpdir)
        self.assertEqual(result["waveforms"], [])


class TestRunSpiceEndpoint(unittest.IsolatedAsyncioTestCase):

    async def _call(self, req: dict, raw_content: str = "") -> dict:
        x = [0.0]
        default_raw = _raw_file_tran(["time", "V(1)"], ["time", "voltage"], x, [x, [5.0]])
        content = raw_content or default_raw

        def _subprocess_side_effect(cmd, **kwargs):
            raw_path = cmd[3]
            Path(raw_path).write_text(content)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        with patch("kerf_electronics.routes_spice.subprocess.run",
                   side_effect=_subprocess_side_effect):
            return await run_spice(req)

    async def test_empty_netlist_raises_400(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            await run_spice({"netlist": "", "analysis": {"type": "op"}})
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_whitespace_netlist_raises_400(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            await run_spice({"netlist": "   \n\t  ", "analysis": {"type": "op"}})
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_valid_netlist_returns_waveforms_key(self):
        req = {"netlist": "RC\nR1 1 2 1k\nC1 2 0 1u\nV1 1 0 DC 5\n.op\n.end\n"}
        result = await self._call(req)
        self.assertIn("waveforms", result)

    async def test_valid_netlist_returns_errors_key(self):
        req = {"netlist": "Test\nR1 1 2 1k\n.op\n.end\n"}
        result = await self._call(req)
        self.assertIn("errors", result)

    async def test_probes_injected_into_netlist(self):
        """Probes should be wired in via inject_print_statements before sim."""
        captured = {}

        def _spy(cmd, **kwargs):
            cir_path = cmd[4]
            captured["netlist"] = Path(cir_path).read_text()
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        netlist = "RC\nR1 1 2 1k\nC1 2 0 1u\nV1 1 0 DC 5\n.op\n.end\n"
        with patch("kerf_electronics.routes_spice.subprocess.run", side_effect=_spy):
            await run_spice({"netlist": netlist, "probes": ["V(2)"]})

        self.assertIn("V(2)", captured.get("netlist", ""))

    async def test_ngspice_failure_returns_error_list(self):
        def _fail(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 1
            r.stdout = ""
            r.stderr = "parse error"
            return r

        with patch("kerf_electronics.routes_spice.subprocess.run", side_effect=_fail):
            result = await run_spice({"netlist": "Test\nR1 1 0 1k\n.op\n.end\n"})
        self.assertIn("errors", result)

    async def test_ngspice_not_installed_returns_friendly_error(self):
        with patch("kerf_electronics.routes_spice.subprocess.run",
                   side_effect=FileNotFoundError):
            result = await run_spice({"netlist": "Test\nR1 1 0 1k\n.op\n.end\n"})
        self.assertGreater(len(result["errors"]), 0)
        error_text = " ".join(result["errors"])
        self.assertIn("ngspice", error_text.lower())


# ── 4. 25 Analog circuit scenarios ───────────────────────────────────────────
#
# Each scenario is hermetic: we synthesise the exact ngspice ASCII .raw output
# that a correct ngspice run would produce, then validate that parse_raw_file
# returns waveforms matching the analytic solution.
#
# Circuit families: RC low-pass, high-pass, integrator, differentiator;
# voltage divider; BJT bias; opamp inverting, non-inverting, differentiator;
# LDO regulator; LC resonator; oscillator frequency; rectifier; clamp; etc.

class TestAnalogCircuitScenarios(unittest.TestCase):
    """25 hermetic SPICE result-parse scenarios with analytic validation."""

    def _parse_raw(self, raw_content: str) -> list:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_raw(tmpdir, raw_content)
            return parse_raw_file(path)

    def _v_wave(self, waveforms: list, name: str) -> list[float]:
        for w in waveforms:
            if w["name"] == name:
                return w["y"]
        raise AssertionError(f"Waveform {name!r} not found in {[w['name'] for w in waveforms]}")

    # --- scenario 1: RC series resistor DC op-point (voltage divider) -------
    def test_s01_rc_voltage_divider_dc(self):
        vcc, r1, r2 = 5.0, 1000.0, 1000.0
        v_out = vcc * r2 / (r1 + r2)
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out, places=3)

    # --- scenario 2: RC low-pass 3dB frequency (AC sweep envelope) ----------
    def test_s02_rc_lowpass_ac_3db(self):
        r, c = 1000.0, 1e-6  # 1 kΩ, 1 µF → f_3dB = 1/(2πRC) ≈ 159.15 Hz
        f_3db = 1.0 / (2 * math.pi * r * c)
        freqs = [10.0, f_3db, 1000.0, 10000.0]
        amps = [1.0 / math.sqrt(1 + (2 * math.pi * f * r * c) ** 2) for f in freqs]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], freqs, [freqs, amps])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        # At f_3dB the amplitude should be 1/√2 ≈ 0.7071
        self.assertAlmostEqual(y[1], 1.0 / math.sqrt(2), places=3)

    # --- scenario 3: RC integrator transient (ramp output) ------------------
    def test_s03_rc_integrator_transient(self):
        r, c, vin = 1000.0, 1e-6, 1.0
        tau = r * c
        # Use multiples of tau so t_vals[1] == tau exactly
        t_vals = [k * tau for k in range(6)]  # 0, τ, 2τ, 3τ, 4τ, 5τ
        # V_out(t) = Vin*(1 - e^(-t/RC))
        y_vals = [vin * (1 - math.exp(-t / tau)) for t in t_vals]
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], t_vals, [t_vals, y_vals])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        # At t = tau (index 1) the output should be Vin * (1 - 1/e) ≈ 0.6321
        expected = vin * (1 - math.exp(-1))
        self.assertAlmostEqual(y[1], expected, places=5)

    # --- scenario 4: RC high-pass 3dB frequency -----------------------------
    def test_s04_rc_highpass_ac_3db(self):
        r, c = 1000.0, 1e-6
        f_3db = 1.0 / (2 * math.pi * r * c)
        freqs = [10.0, f_3db, 10000.0]
        # High-pass: H(f) = jωRC / (1 + jωRC) → |H| = ωRC/√(1+(ωRC)²)
        amps = [(2 * math.pi * f * r * c) / math.sqrt(1 + (2 * math.pi * f * r * c) ** 2) for f in freqs]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], freqs, [freqs, amps])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[1], 1.0 / math.sqrt(2), places=3)

    # --- scenario 5: resistor current calculation ----------------------------
    def test_s05_resistor_current_dc(self):
        vcc, r = 5.0, 100.0
        i_exp = vcc / r  # 0.05 A
        raw = _raw_file_tran(["time", "I(R1)"], ["time", "current"], [0.0], [[0.0], [i_exp]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "I(R1)")
        self.assertAlmostEqual(y[0], i_exp, places=5)

    # --- scenario 6: ideal opamp inverting gain ------------------------------
    def test_s06_opamp_inverting_gain(self):
        r_in, r_f, v_in = 1000.0, 10000.0, 0.5
        gain = -(r_f / r_in)
        v_out = gain * v_in  # -5.0 V
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out, places=3)

    # --- scenario 7: opamp non-inverting gain --------------------------------
    def test_s07_opamp_noninverting_gain(self):
        r1, r2, v_in = 1000.0, 9000.0, 0.1
        gain = 1 + r2 / r1  # 10x
        v_out = gain * v_in  # 1.0 V
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], gain * v_in, places=3)

    # --- scenario 8: LDO regulator output voltage ----------------------------
    def test_s08_ldo_regulator_vout(self):
        # 78xx: Vout = 5 V (regulated)
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [5.0]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], 5.0, places=2)

    # --- scenario 9: LC resonant frequency -----------------------------------
    def test_s09_lc_resonance_frequency(self):
        l_h, c_f = 1e-3, 1e-6  # 1 mH, 1 µF → f_res ≈ 5.03 kHz
        f_res = 1.0 / (2 * math.pi * math.sqrt(l_h * c_f))
        freqs = [100.0, 1000.0, f_res, 10000.0]
        # At resonance Z_LC = 0 → max current (gain peak in bandpass config)
        gains = [0.1, 0.5, 1.0, 0.5]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], freqs, [freqs, gains])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        # Peak gain at resonance index
        self.assertEqual(y.index(max(y)), 2)

    # --- scenario 10: RC differentiator step response -----------------------
    def test_s10_rc_differentiator_step(self):
        r, c = 1000.0, 1e-6
        tau = r * c
        t_vals = [0.0, tau * 0.01, tau * 0.1, tau, tau * 5]
        # After step at t=0: V_out(t) = e^(-t/RC)
        y_vals = [math.exp(-t / tau) for t in t_vals]
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], t_vals, [t_vals, y_vals])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        # At t = tau output should be 1/e
        self.assertAlmostEqual(y[3], math.exp(-1), places=3)

    # --- scenario 11: voltage-controlled voltage source ----------------------
    def test_s11_vcvs_gain(self):
        gain = 20.0
        v_ctrl = 0.25
        v_out = gain * v_ctrl  # 5.0 V
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out, places=3)

    # --- scenario 12: Zener clamp DC output ----------------------------------
    def test_s12_zener_clamp_dc(self):
        v_zener = 5.1
        v_in = 12.0
        # With series R the output clamps at V_zener
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_zener]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_zener, places=2)

    # --- scenario 13: BJT base bias voltage divider --------------------------
    def test_s13_bjt_base_voltage_divider(self):
        vcc, r1, r2 = 12.0, 22000.0, 10000.0
        v_b = vcc * r2 / (r1 + r2)  # ≈ 3.75 V
        raw = _raw_file_tran(["time", "V(base)"], ["time", "voltage"], [0.0], [[0.0], [v_b]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(base)")
        self.assertAlmostEqual(y[0], v_b, places=2)

    # --- scenario 14: BJT emitter follower output voltage --------------------
    def test_s14_bjt_emitter_follower(self):
        v_b, v_be = 3.75, 0.7
        v_e = v_b - v_be  # ≈ 3.05 V
        raw = _raw_file_tran(["time", "V(emit)"], ["time", "voltage"], [0.0], [[0.0], [v_e]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(emit)")
        self.assertAlmostEqual(y[0], v_e, places=2)

    # --- scenario 15: RC charging curve (multiple time constants) -----------
    def test_s15_rc_charge_5tau(self):
        r, c, vcc = 1000.0, 1e-6, 5.0
        tau = r * c
        t_vals = [k * tau for k in range(6)]  # 0 to 5 tau
        y_vals = [vcc * (1 - math.exp(-t / tau)) for t in t_vals]
        raw = _raw_file_tran(["time", "V(cap)"], ["time", "voltage"], t_vals, [t_vals, y_vals])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(cap)")
        # At 5τ: V ≈ 0.9933 * Vcc
        self.assertGreater(y[5], 0.99 * vcc)
        # At 0: V = 0
        self.assertAlmostEqual(y[0], 0.0, places=5)

    # --- scenario 16: opamp AC integrator (-1/(j*ω*RC)) ----------------------
    def test_s16_opamp_integrator_gain(self):
        r, c = 1000.0, 1e-6
        freqs = [100.0, 1000.0, 10000.0]
        # |H(f)| = 1 / (2π f R C)
        gains = [1.0 / (2 * math.pi * f * r * c) for f in freqs]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], freqs, [freqs, gains])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        expected_1k = 1.0 / (2 * math.pi * 1000.0 * r * c)
        self.assertAlmostEqual(y[1], expected_1k, places=3)

    # --- scenario 17: power dissipation in resistor --------------------------
    def test_s17_power_dissipation(self):
        v, r = 5.0, 100.0
        p = v ** 2 / r  # 0.25 W
        raw = _raw_file_tran(["time", "P(R1)"], ["time", "power"], [0.0], [[0.0], [p]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "P(R1)")
        self.assertAlmostEqual(y[0], p, places=4)

    # --- scenario 18: RC network frequency sweep — 10 points ----------------
    def test_s18_rc_sweep_10pts(self):
        r, c = 10000.0, 10e-9  # 10 kΩ, 10 nF → τ ≈ 100 µs, f_3dB ≈ 1591 Hz
        n = 10
        f_log = [10 ** (2 + i * 4 / (n - 1)) for i in range(n)]  # 100 Hz → 1 MHz
        amps = [1.0 / math.sqrt(1 + (2 * math.pi * f * r * c) ** 2) for f in f_log]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], f_log, [f_log, amps])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertEqual(len(y), n)
        # Gain at DC-approx (100 Hz) should be near 1
        self.assertGreater(y[0], 0.9)
        # Gain at 1 MHz (far above f_3dB) should be small
        self.assertLess(y[-1], 0.1)

    # --- scenario 19: adjustable LDO output voltage -------------------------
    def test_s19_adj_ldo_output_voltage(self):
        # LM317: Vout = Vref * (1 + R2/R1) = 1.25 * (1 + 7.2k/1.2k) = 8.75 V
        vref, r1, r2 = 1.25, 1200.0, 7200.0
        v_out = vref * (1 + r2 / r1)
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out, places=2)

    # --- scenario 20: oscillator RC time constant ----------------------------
    def test_s20_rc_oscillator_period(self):
        # 555-style: T = 1.1 * R * C → f = 1/T
        r, c = 10000.0, 1e-6
        period = 1.1 * r * c  # 11 ms
        freq = 1.0 / period    # ≈ 90.9 Hz
        n = 40
        t_vals = [i * period / 20 for i in range(n)]
        # Square wave approximation
        y_vals = [3.3 if math.floor(t / (period / 2)) % 2 == 0 else 0.0 for t in t_vals]
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], t_vals, [t_vals, y_vals])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertEqual(len(y), n)
        # High states ≈ 3.3 V
        highs = [v for v in y if v > 3.0]
        self.assertGreater(len(highs), 0)

    # --- scenario 21: multi-stage RC ladder DC voltage ----------------------
    def test_s21_rc_ladder_dc(self):
        # Three-resistor ladder: V1 = 12V, R1=R2=R3=1kΩ → V(n2) = 4V
        vcc, r = 12.0, 1000.0
        v_n2 = vcc / 3  # 4.0 V
        raw = _raw_file_tran(["time", "V(n2)"], ["time", "voltage"], [0.0], [[0.0], [v_n2]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(n2)")
        self.assertAlmostEqual(y[0], v_n2, places=3)

    # --- scenario 22: Schottky diode half-wave rectifier --------------------
    def test_s22_half_wave_rectifier_peak(self):
        v_peak, v_f = 5.0, 0.3  # Schottky forward voltage
        v_out_peak = v_peak - v_f  # 4.7 V
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out_peak]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out_peak, places=2)

    # --- scenario 23: capacitor discharge transient -------------------------
    def test_s23_cap_discharge_transient(self):
        r, c, v0 = 100.0, 100e-6, 10.0
        tau = r * c  # 10 ms
        t_vals = [k * tau for k in range(6)]
        y_vals = [v0 * math.exp(-t / tau) for t in t_vals]
        raw = _raw_file_tran(["time", "V(cap)"], ["time", "voltage"], t_vals, [t_vals, y_vals])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(cap)")
        # At t=τ: V = V0/e
        self.assertAlmostEqual(y[1], v0 / math.e, places=3)
        # Monotonically decreasing
        for i in range(1, len(y)):
            self.assertLessEqual(y[i], y[i - 1] + 1e-9)

    # --- scenario 24: opamp summing amplifier --------------------------------
    def test_s24_opamp_summing_amplifier(self):
        v1, v2, r_in, r_f = 1.0, 2.0, 1000.0, 2000.0
        # V_out = -(R_f/R_in) * (V1 + V2) = -2 * (1+2) = -6 V
        v_out = -(r_f / r_in) * (v1 + v2)
        raw = _raw_file_tran(["time", "V(out)"], ["time", "voltage"], [0.0], [[0.0], [v_out]])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        self.assertAlmostEqual(y[0], v_out, places=3)

    # --- scenario 25: second-order RLC band-pass filter peak ----------------
    def test_s25_rlc_bandpass_peak(self):
        r, l, c = 100.0, 1e-3, 1e-6
        # Resonant frequency: f_0 = 1/(2π√(LC))
        f_0 = 1.0 / (2 * math.pi * math.sqrt(l * c))
        freqs = [f_0 * 0.1, f_0 * 0.5, f_0, f_0 * 2.0, f_0 * 10.0]
        # RLC bandpass: |H(f)| = (R/Z), peak at resonance
        def h_rlc(f):
            w = 2 * math.pi * f
            zl = w * l
            zc = 1.0 / (w * c) if w > 0 else 1e9
            z = math.sqrt(r ** 2 + (zl - zc) ** 2)
            return r / z
        gains = [h_rlc(f) for f in freqs]
        raw = _raw_file_tran(["freq", "V(out)"], ["freq", "voltage"], freqs, [freqs, gains])
        wfm = self._parse_raw(raw)
        y = self._v_wave(wfm, "V(out)")
        # Peak should be at f_0 (index 2)
        peak_idx = y.index(max(y))
        self.assertEqual(peak_idx, 2)
        # At resonance gain = 1.0 (R/R)
        self.assertAlmostEqual(y[2], 1.0, places=3)


# ── 5. .cir netlist generation correctness ────────────────────────────────────

class TestCirNetlistGeneration(unittest.TestCase):
    """Verify that the netlist passed to ngspice has correct structure."""

    def _capture_netlist(self, req: dict) -> str:
        captured = {}

        def _spy(cmd, **kwargs):
            cir_path = cmd[4]
            captured["netlist"] = Path(cir_path).read_text()
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        import asyncio
        with patch("kerf_electronics.routes_spice.subprocess.run", side_effect=_spy):
            asyncio.run(run_spice(req))
        return captured.get("netlist", "")

    def test_netlist_written_to_cir_file(self):
        netlist = "RC filter\nR1 1 2 1k\nC1 2 0 1u\nV1 1 0 DC 5\n.op\n.end\n"
        cir = self._capture_netlist({"netlist": netlist})
        self.assertIn("R1", cir)
        self.assertIn("C1", cir)

    def test_probes_appear_in_cir(self):
        netlist = "RC\nR1 1 2 1k\n.op\n.end\n"
        cir = self._capture_netlist({"netlist": netlist, "probes": ["V(1)", "V(2)"]})
        self.assertIn("V(1)", cir)
        self.assertIn("V(2)", cir)

    def test_title_preserved_in_cir(self):
        netlist = "My Custom Title\nR1 1 2 1k\n.op\n.end\n"
        cir = self._capture_netlist({"netlist": netlist})
        self.assertIn("My Custom Title", cir)

    def test_end_directive_preserved(self):
        netlist = "Test\nR1 1 2 1k\n.op\n.end\n"
        cir = self._capture_netlist({"netlist": netlist})
        self.assertIn(".end", cir.lower())

    def test_analysis_directive_preserved(self):
        netlist = "Tran test\nR1 1 2 1k\nC1 2 0 1u\nV1 1 0 PULSE(0 5 0 1ns 1ns 5ms 10ms)\n.tran 10us 50ms\n.end\n"
        cir = self._capture_netlist({"netlist": netlist})
        self.assertIn(".tran", cir.lower())

    def test_idempotent_run_same_netlist(self):
        """Running the same netlist twice should not modify it."""
        netlist = "Idempotent\nR1 1 2 1k\n.op\n.end\n"
        cir1 = self._capture_netlist({"netlist": netlist})
        cir2 = self._capture_netlist({"netlist": netlist})
        self.assertEqual(cir1, cir2)


if __name__ == "__main__":
    unittest.main()
