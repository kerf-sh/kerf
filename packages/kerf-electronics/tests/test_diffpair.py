"""
Tests for diffpair.py — differential-pair routing, controlled-impedance
calculations, and matched-length groups.

Loading strategy mirrors test_length_tuning.py: load the module directly via
importlib to avoid pulling in the full kerf_chat stack.
"""
import importlib.util
import json
import math
import sys
# ── Prefer the real kerf_chat (installed in this monorepo). Pinning it into
#    sys.modules BEFORE the stub setdefaults means those become no-ops and the
#    stub never shadows the real, populated Registry that other suites import.
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

import types
import pytest


# ── Stub kerf_chat.tools.registry ────────────────────────────────────────────

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})  # real Registry is a list subclass; keep leaked stub import-compatible
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

# Also register the parent package stub so the dotted import resolves.
_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")

sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
_KERF_CHAT_SAVED = {
    _n: sys.modules.get(_n)
    for _n in ("kerf_chat", "kerf_chat.tools", "kerf_chat.tools.registry")
}
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub
_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.tools.diffpair",
    "packages/kerf-electronics/src/kerf_electronics/tools/diffpair.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Internal helpers
_microstrip_z0 = _mod._microstrip_z0
_stripline_z0 = _mod._stripline_z0
_diff_impedance = _mod._diff_impedance
_offset_polyline = _mod._offset_polyline
_trace_length = _mod._trace_length
_net_length = _mod._net_length

# LLM tool functions
add_diff_pair = _mod.add_diff_pair
route_diff_pair = _mod.route_diff_pair
calc_impedance = _mod.calc_impedance
add_length_group = _mod.add_length_group
check_length_match = _mod.check_length_match


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_board(**extra):
    return {"type": "pcb_board", "width": 100, "height": 100, **extra}


def make_trace(points, net_id="SIG", trace_id=None):
    return {
        "type": "pcb_trace",
        "pcb_trace_id": trace_id or f"t_{net_id}",
        "net_id": net_id,
        "points": points,
    }


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Internal unit tests — geometry and impedance math
# ═══════════════════════════════════════════════════════════════════════════════

class TestOffsetPolyline:
    def test_single_segment_perpendicular(self):
        pts = [{"x": 0, "y": 0}, {"x": 10, "y": 0}]
        offset = _offset_polyline(pts, 1.0)
        # Perpendicular to x-axis should be +y
        assert abs(offset[0]["y"] - 1.0) < 1e-9
        assert abs(offset[1]["y"] - 1.0) < 1e-9
        assert abs(offset[0]["x"] - 0.0) < 1e-9
        assert abs(offset[1]["x"] - 10.0) < 1e-9

    def test_negative_offset_opposite_side(self):
        pts = [{"x": 0, "y": 0}, {"x": 10, "y": 0}]
        neg = _offset_polyline(pts, -1.0)
        assert abs(neg[0]["y"] - (-1.0)) < 1e-9

    def test_vertical_segment(self):
        pts = [{"x": 0, "y": 0}, {"x": 0, "y": 10}]
        offset = _offset_polyline(pts, 1.0)
        # Perpendicular to +y should be -x (CCW)
        assert abs(offset[0]["x"] - (-1.0)) < 1e-9

    def test_three_point_polyline_endpoints(self):
        pts = [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 10, "y": 0}]
        offset = _offset_polyline(pts, 2.0)
        assert len(offset) == 3
        for pt in offset:
            assert abs(pt["y"] - 2.0) < 1e-9


class TestTraceLength:
    def test_single_segment(self):
        t = make_trace([{"x": 0, "y": 0}, {"x": 6, "y": 0}])
        assert abs(_trace_length(t) - 6.0) < 1e-9

    def test_345_triangle(self):
        t = make_trace([{"x": 0, "y": 0}, {"x": 3, "y": 0}, {"x": 3, "y": 4}])
        assert abs(_trace_length(t) - 7.0) < 1e-9

    def test_empty_returns_zero(self):
        assert _trace_length(make_trace([])) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Impedance calculator unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMicrostripZ0:
    """
    Reference: IPC-2141A / Hammerstad (1975) typical 50 Ω microstrip on FR4.
    Verified stackup: W=0.32 mm, H=0.2 mm, T=0.035 mm (1 oz), er=4.5 → ~51.7 Ω.
    At W/H > 1 the Hammerstad effective-permittivity formula is used.
    """

    def test_50_ohm_fr4_microstrip_within_5_percent(self):
        # W=0.32 mm, H=0.2 mm, T=0.035 mm (1 oz), er=4.5 (FR4 mid-band)
        # Hammerstad (1975) / IPC-2141A → ~51.7 Ω
        z0 = _microstrip_z0(W=0.32, H=0.2, T=0.035, er=4.5)
        assert 45 < z0 < 55, f"Expected ~50 Ω, got {z0:.2f} Ω"

    def test_wider_trace_lower_impedance(self):
        z_narrow = _microstrip_z0(W=0.2, H=0.2, T=0.035, er=4.5)
        z_wide = _microstrip_z0(W=1.0, H=0.2, T=0.035, er=4.5)
        assert z_narrow > z_wide

    def test_higher_er_lower_impedance(self):
        z_fr4 = _microstrip_z0(W=0.5, H=0.2, T=0.035, er=4.5)
        z_high = _microstrip_z0(W=0.5, H=0.2, T=0.035, er=9.0)
        assert z_fr4 > z_high

    def test_taller_dielectric_higher_impedance(self):
        z_thin = _microstrip_z0(W=0.5, H=0.1, T=0.035, er=4.5)
        z_thick = _microstrip_z0(W=0.5, H=0.4, T=0.035, er=4.5)
        assert z_thick > z_thin


class TestStriplineZ0:
    """
    Reference: IPC-2141A symmetric buried stripline.
    Verified stackup: W=0.1 mm, B=0.36 mm, T=0.035 mm, er=4.5 → ~50.4 Ω.
    """

    def test_50_ohm_fr4_stripline_within_10_percent(self):
        # W=0.1 mm, B=0.36 mm, T=0.035 mm, er=4.5 → ~50.4 Ω
        z0 = _stripline_z0(W=0.1, B=0.36, T=0.035, er=4.5)
        assert 40 < z0 < 65, f"Expected ~50 Ω, got {z0:.2f} Ω"

    def test_wider_trace_lower_impedance_stripline(self):
        z_narrow = _stripline_z0(W=0.1, B=0.36, T=0.035, er=4.5)
        z_wide = _stripline_z0(W=0.4, B=0.36, T=0.035, er=4.5)
        assert z_narrow > z_wide


class TestDiffImpedance:
    """
    Wadell (1991) §3.7: for microstrip with large spacing, Zdiff → 2*Z0.
    """

    def test_large_spacing_approaches_2_z0(self):
        z0 = 50.0
        zdiff = _diff_impedance(z0, S=10.0, H_or_B=0.2, structure="microstrip")
        # At S/H = 50 the coupling exp term ≈ 0; Zdiff ≈ 2*Z0
        assert abs(zdiff - 2 * z0) < 1.0

    def test_tight_spacing_lower_than_2_z0(self):
        z0 = 50.0
        zdiff_tight = _diff_impedance(z0, S=0.1, H_or_B=0.2, structure="microstrip")
        zdiff_far = _diff_impedance(z0, S=2.0, H_or_B=0.2, structure="microstrip")
        assert zdiff_tight < zdiff_far

    def test_100_ohm_diff_fr4_microstrip(self):
        """
        100 Ω diff pair on FR4: W=0.32mm, H=0.2mm, S=0.5mm → ~103 Ω.
        Reference: Wadell (1991) §3.7 coupling factor applied to IPC-2141A Z0.
        Z0 ≈ 51.7 Ω single-ended → Zdiff ≈ 103.3 Ω (coupling negligible at S/H=2.5).
        """
        z0 = _microstrip_z0(W=0.32, H=0.2, T=0.035, er=4.5)
        zdiff = _diff_impedance(z0, S=0.5, H_or_B=0.2, structure="microstrip")
        assert 85 < zdiff < 115, f"Expected ~100 Ω diff, got {zdiff:.2f} Ω"


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: add_diff_pair
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddDiffPair:
    @pytest.mark.asyncio
    async def test_add_creates_pair(self):
        circuit = [make_board()]
        r = await call(
            add_diff_pair,
            circuit_json=circuit,
            name="USB_DP",
            net_p_id="USB_P",
            net_n_id="USB_N",
            spacing_mm=0.2,
        )
        assert "error" not in r
        board = next(e for e in r["circuit_json"] if e.get("type") == "pcb_board")
        assert len(board["differential_pairs"]) == 1
        pair = board["differential_pairs"][0]
        assert pair["name"] == "USB_DP"
        assert pair["net_p_id"] == "USB_P"
        assert pair["net_n_id"] == "USB_N"
        assert pair["spacing_mm"] == 0.2

    @pytest.mark.asyncio
    async def test_add_upserts_existing_pair(self):
        circuit = [make_board()]
        r1 = await call(
            add_diff_pair,
            circuit_json=circuit,
            name="USB_DP",
            net_p_id="USB_P",
            net_n_id="USB_N",
            spacing_mm=0.2,
        )
        r2 = await call(
            add_diff_pair,
            circuit_json=r1["circuit_json"],
            name="USB_DP",
            net_p_id="USB_P",
            net_n_id="USB_N",
            spacing_mm=0.3,
        )
        board = next(e for e in r2["circuit_json"] if e.get("type") == "pcb_board")
        assert len(board["differential_pairs"]) == 1
        assert board["differential_pairs"][0]["spacing_mm"] == 0.3

    @pytest.mark.asyncio
    async def test_add_records_optional_impedance(self):
        circuit = [make_board()]
        r = await call(
            add_diff_pair,
            circuit_json=circuit,
            name="HDMI",
            net_p_id="HDMI_P",
            net_n_id="HDMI_N",
            spacing_mm=0.15,
            target_impedance_ohms=100,
        )
        pair = r["pair"]
        assert pair.get("target_impedance_ohms") == 100

    @pytest.mark.asyncio
    async def test_add_missing_name_returns_error(self):
        circuit = [make_board()]
        r = await call(
            add_diff_pair,
            circuit_json=circuit,
            name="",
            net_p_id="A",
            net_n_id="B",
            spacing_mm=0.2,
        )
        assert "error" in r

    @pytest.mark.asyncio
    async def test_add_negative_spacing_returns_error(self):
        circuit = [make_board()]
        r = await call(
            add_diff_pair,
            circuit_json=circuit,
            name="PAIR",
            net_p_id="P",
            net_n_id="N",
            spacing_mm=-0.2,
        )
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: route_diff_pair
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteDiffPair:
    def _base_circuit(self):
        board = make_board()
        board["differential_pairs"] = [{
            "name": "USB_DP",
            "net_p_id": "USB_P",
            "net_n_id": "USB_N",
            "spacing_mm": 0.2,
            "width_mm": 0.15,
            "skew_max_mm": 0.05,
        }]
        return [board]

    @pytest.mark.asyncio
    async def test_route_adds_two_traces(self):
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}, {"x": 20, "y": 0}],
        )
        assert "error" not in r
        traces = [e for e in r["circuit_json"] if e.get("type") == "pcb_trace"]
        assert len(traces) == 2

    @pytest.mark.asyncio
    async def test_traces_on_correct_nets(self):
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}, {"x": 20, "y": 0}],
        )
        traces = [e for e in r["circuit_json"] if e.get("type") == "pcb_trace"]
        net_ids = {t["net_id"] for t in traces}
        assert net_ids == {"USB_P", "USB_N"}

    @pytest.mark.asyncio
    async def test_traces_are_coupled_at_target_spacing(self):
        """The P and N traces for a horizontal centreline should be offset by
        spacing_mm = 0.2, so the midpoint y-coordinates differ by 0.2."""
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}, {"x": 20, "y": 0}],
        )
        traces = {t["net_id"]: t for t in r["circuit_json"] if isinstance(t, dict) and t.get("type") == "pcb_trace"}
        y_p = traces["USB_P"]["points"][0]["y"]
        y_n = traces["USB_N"]["points"][0]["y"]
        assert abs(abs(y_p - y_n) - 0.2) < 1e-6, (
            f"Expected spacing 0.2, got {abs(y_p - y_n):.6f}"
        )

    @pytest.mark.asyncio
    async def test_route_records_diff_pair_routes(self):
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}, {"x": 10, "y": 0}],
        )
        board = next(e for e in r["circuit_json"] if e.get("type") == "pcb_board")
        assert len(board.get("diff_pair_routes", [])) == 1

    @pytest.mark.asyncio
    async def test_route_skew_near_zero_for_straight_line(self):
        """Straight horizontal centreline → offset polylines have equal length."""
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}, {"x": 30, "y": 0}],
        )
        assert r["skew_mm"] < 1e-6

    @pytest.mark.asyncio
    async def test_route_pair_not_found_returns_error(self):
        circuit = [make_board()]
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="GHOST",
            centreline=[{"x": 0, "y": 0}, {"x": 10, "y": 0}],
        )
        assert "error" in r

    @pytest.mark.asyncio
    async def test_route_too_few_centreline_points_returns_error(self):
        circuit = self._base_circuit()
        r = await call(
            route_diff_pair,
            circuit_json=circuit,
            pair_name="USB_DP",
            centreline=[{"x": 0, "y": 0}],
        )
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: calc_impedance
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalcImpedance:
    @pytest.mark.asyncio
    async def test_microstrip_50_ohm_fr4(self):
        """
        IPC-2141A / Hammerstad reference: 50 Ω microstrip on FR4.
        Verified stackup: W=0.32 mm, H=0.2 mm, T=0.035 mm (1 oz), er=4.5 → ~51.7 Ω.
        """
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.32,
            dielectric_height_mm=0.2,
            copper_thickness_mm=0.035,
            er=4.5,
        )
        assert "error" not in r
        assert 45 < r["z0_ohms"] < 55, f"Expected ~50 Ω, got {r['z0_ohms']}"

    @pytest.mark.asyncio
    async def test_stripline_50_ohm_fr4(self):
        """
        IPC-2141A reference: 50 Ω symmetric buried stripline on FR4.
        Verified stackup: W=0.1 mm, B=0.36 mm, T=0.035 mm, er=4.5 → ~50.4 Ω.
        """
        r = await call(
            calc_impedance,
            structure="stripline",
            trace_width_mm=0.1,
            dielectric_height_mm=0.36,
            copper_thickness_mm=0.035,
            er=4.5,
        )
        assert "error" not in r
        assert 40 < r["z0_ohms"] < 65, f"Expected ~50 Ω, got {r['z0_ohms']}"

    @pytest.mark.asyncio
    async def test_diff_impedance_included_when_spacing_given(self):
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.32,
            dielectric_height_mm=0.2,
            copper_thickness_mm=0.035,
            er=4.5,
            spacing_mm=0.5,
        )
        assert "error" not in r
        assert "zdiff_ohms" in r

    @pytest.mark.asyncio
    async def test_100_ohm_diff_pair_microstrip(self):
        """
        Wadell (1991) §3.7 / IPC-2141A combined: 100 Ω diff pair on FR4.
        Verified: W=0.32 mm, H=0.2 mm, S=0.5 mm, T=0.035 mm, er=4.5 → ~103.3 Ω.
        Z0 ≈ 51.7 Ω; at S/H=2.5 coupling is negligible; Zdiff ≈ 2×Z0.
        """
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.32,
            dielectric_height_mm=0.2,
            copper_thickness_mm=0.035,
            er=4.5,
            spacing_mm=0.5,
        )
        assert "error" not in r
        assert 85 < r["zdiff_ohms"] < 115, f"Expected ~100 Ω diff, got {r['zdiff_ohms']}"

    @pytest.mark.asyncio
    async def test_formulas_field_present(self):
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.5,
            dielectric_height_mm=0.2,
            er=4.5,
        )
        assert "IPC-2141A" in r["formulas"]
        assert "Wadell" in r["formulas"]

    @pytest.mark.asyncio
    async def test_invalid_structure_returns_error(self):
        r = await call(
            calc_impedance,
            structure="coaxial",
            trace_width_mm=0.5,
            dielectric_height_mm=0.2,
            er=4.5,
        )
        assert "error" in r

    @pytest.mark.asyncio
    async def test_missing_er_returns_error(self):
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.5,
            dielectric_height_mm=0.2,
            er=-1,
        )
        assert "error" in r

    @pytest.mark.asyncio
    async def test_no_zdiff_when_no_spacing(self):
        r = await call(
            calc_impedance,
            structure="microstrip",
            trace_width_mm=0.5,
            dielectric_height_mm=0.2,
            er=4.5,
        )
        assert "error" not in r
        assert "zdiff_ohms" not in r


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: add_length_group
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddLengthGroup:
    @pytest.mark.asyncio
    async def test_add_creates_group(self):
        circuit = [make_board()]
        r = await call(
            add_length_group,
            circuit_json=circuit,
            name="DDR_DQ_BYTE0",
            net_ids=["DQ0", "DQ1", "DQ2", "DQ3"],
            target_length_mm=72.0,
        )
        assert "error" not in r
        board = next(e for e in r["circuit_json"] if e.get("type") == "pcb_board")
        assert len(board["length_groups"]) == 1
        g = board["length_groups"][0]
        assert g["name"] == "DDR_DQ_BYTE0"
        assert g["target_length_mm"] == 72.0
        assert g["net_ids"] == ["DQ0", "DQ1", "DQ2", "DQ3"]

    @pytest.mark.asyncio
    async def test_add_upserts(self):
        circuit = [make_board()]
        r1 = await call(
            add_length_group,
            circuit_json=circuit,
            name="GRP",
            net_ids=["A", "B"],
            target_length_mm=50.0,
        )
        r2 = await call(
            add_length_group,
            circuit_json=r1["circuit_json"],
            name="GRP",
            net_ids=["A", "B", "C"],
            target_length_mm=55.0,
        )
        board = next(e for e in r2["circuit_json"] if e.get("type") == "pcb_board")
        assert len(board["length_groups"]) == 1
        assert board["length_groups"][0]["target_length_mm"] == 55.0

    @pytest.mark.asyncio
    async def test_single_net_returns_error(self):
        circuit = [make_board()]
        r = await call(
            add_length_group,
            circuit_json=circuit,
            name="GRP",
            net_ids=["ONLY_ONE"],
            target_length_mm=50.0,
        )
        assert "error" in r

    @pytest.mark.asyncio
    async def test_zero_target_returns_error(self):
        circuit = [make_board()]
        r = await call(
            add_length_group,
            circuit_json=circuit,
            name="GRP",
            net_ids=["A", "B"],
            target_length_mm=0,
        )
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: check_length_match
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckLengthMatch:
    def _circuit_with_traces(self):
        """Board with a length group; DQ0=60mm, DQ1=70mm, DQ2=72mm, target=72mm."""
        board = make_board()
        board["length_groups"] = [{
            "name": "BYTE0",
            "net_ids": ["DQ0", "DQ1", "DQ2"],
            "target_length_mm": 72.0,
            "skew_max_mm": 0.5,
            "serpentine_amplitude_mm": 0.5,
        }]
        traces = [
            make_trace([{"x": 0, "y": 0}, {"x": 60, "y": 0}], net_id="DQ0"),
            make_trace([{"x": 0, "y": 1}, {"x": 70, "y": 1}], net_id="DQ1"),
            make_trace([{"x": 0, "y": 2}, {"x": 72, "y": 2}], net_id="DQ2"),
        ]
        return [board] + traces

    @pytest.mark.asyncio
    async def test_reports_correct_deltas(self):
        circuit = self._circuit_with_traces()
        r = await call(check_length_match, circuit_json=circuit, group_name="BYTE0")
        assert "error" not in r
        nets = {n["net_id"]: n for n in r["nets"]}
        assert abs(nets["DQ0"]["delta_mm"] - 12.0) < 0.01
        assert abs(nets["DQ1"]["delta_mm"] - 2.0) < 0.01
        assert abs(nets["DQ2"]["delta_mm"] - 0.0) < 0.01

    @pytest.mark.asyncio
    async def test_flags_nets_that_need_tuning(self):
        circuit = self._circuit_with_traces()
        r = await call(check_length_match, circuit_json=circuit, group_name="BYTE0")
        nets = {n["net_id"]: n for n in r["nets"]}
        # DQ0 is 12mm short — clearly needs tuning
        assert nets["DQ0"]["needs_tuning"] is True
        # DQ2 is on target — no tuning needed
        assert nets["DQ2"]["needs_tuning"] is False

    @pytest.mark.asyncio
    async def test_all_pass_when_within_tolerance(self):
        board = make_board()
        board["length_groups"] = [{
            "name": "TIGHT",
            "net_ids": ["A", "B"],
            "target_length_mm": 10.0,
            "skew_max_mm": 1.0,
        }]
        traces = [
            make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}], net_id="A"),
            make_trace([{"x": 0, "y": 1}, {"x": 10.3, "y": 1}], net_id="B"),
        ]
        r = await call(check_length_match, circuit_json=[board] + traces, group_name="TIGHT")
        assert r["all_pass"] is True

    @pytest.mark.asyncio
    async def test_recommends_serpentine_delta(self):
        circuit = self._circuit_with_traces()
        r = await call(check_length_match, circuit_json=circuit, group_name="BYTE0")
        nets = {n["net_id"]: n for n in r["nets"]}
        # DQ0 needs 12mm of serpentine
        assert abs(nets["DQ0"]["recommended_serpentine_delta_mm"] - 12.0) < 0.01
        # DQ2 needs none
        assert nets["DQ2"]["recommended_serpentine_delta_mm"] == 0.0

    @pytest.mark.asyncio
    async def test_group_not_found_returns_error(self):
        circuit = [make_board()]
        r = await call(check_length_match, circuit_json=circuit, group_name="GHOST")
        assert "error" in r

    @pytest.mark.asyncio
    async def test_zero_length_net_treated_as_unrouted(self):
        """A net with no traces has length 0; delta = target."""
        board = make_board()
        board["length_groups"] = [{
            "name": "G",
            "net_ids": ["UNROUTED", "ROUTED"],
            "target_length_mm": 20.0,
            "skew_max_mm": 0.1,
        }]
        traces = [
            make_trace([{"x": 0, "y": 0}, {"x": 20, "y": 0}], net_id="ROUTED"),
        ]
        r = await call(check_length_match, circuit_json=[board] + traces, group_name="G")
        nets = {n["net_id"]: n for n in r["nets"]}
        assert nets["UNROUTED"]["current_length_mm"] == 0.0
        assert abs(nets["UNROUTED"]["delta_mm"] - 20.0) < 0.01
        assert nets["UNROUTED"]["needs_tuning"] is True


# ── Restore sys.modules so the kerf_chat stub does not leak into other test
#    modules (real kerf_chat.tools.registry is a populated list other suites
#    iterate; a leaked stub breaks ~100 downstream tests). ───────────────────
def teardown_module(module):  # noqa: D401  (pytest module teardown)
    import sys as _sys
    for _name, _orig in _KERF_CHAT_SAVED.items():
        if _orig is None:
            _sys.modules.pop(_name, None)
        else:
            _sys.modules[_name] = _orig
