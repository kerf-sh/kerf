"""
Hermetic tests for the EMC pre-compliance wizard (emc_wizard.py).

Coverage (≥25 tests):
  - Clearly-failing DM loop → negative margin, flagged
  - Loop-area-reduction recommendation present and predicts improved margin
  - Choke recommendation reduces CM emission in re-run
  - Shield recommendation SE ≥ required deficit
  - FCC vs CISPR class changes the verdict
  - Pass case → compliant=True, margin positive, no critical fixes
  - Results numerically consistent with calling emc.estimate functions directly
  - Invalid inputs → ok=False, never raise
  - LLM tool wrapper (stub registry) — round-trips correctly

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
import warnings

# ── Stub kerf_chat.tools.registry before any imports ─────────────────────────
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps(
    {"ok": False, "error": msg, "code": code}
)
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.emc_wizard import emc_precompliance
from kerf_electronics.emc.estimate import (
    emission_margin_db,
    radiated_emission_differential,
    radiated_emission_common_mode,
    shielding_effectiveness,
)

# ── Load tool module via importlib (stub active) ──────────────────────────────
_wizard_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.emc_wizard",
    os.path.join(_SRC, "kerf_electronics", "emc_wizard.py"),
)
_wizard_mod = importlib.util.module_from_spec(_wizard_spec)
_wizard_spec.loader.exec_module(_wizard_mod)
_emc_wizard_tool = _wizard_mod.emc_precompliance_wizard


async def _call_tool(**kwargs) -> dict:
    raw = await _emc_wizard_tool(None, json.dumps(kwargs).encode())
    return json.loads(raw)


# ── Minimal valid design (DM loop only, clearly failing) ─────────────────────
# 100 MHz, 10 cm × 10 cm loop (100 cm² = 1e-4 m²), 100 mA → very high emission

_FAIL_DESIGN = {
    "clock_hz": 100e6,
    "loop_area_m2": 1e-4,   # 10 cm × 10 cm
    "loop_current_a": 0.1,  # 100 mA — clearly failing
    "standard": "cispr",
    "class_": "B",
    "distance_m": 10.0,
}

# Minimal passing design: tiny loop, tiny current
_PASS_DESIGN = {
    "clock_hz": 100e6,
    "loop_area_m2": 1e-9,   # 1 mm² — very small
    "loop_current_a": 1e-6, # 1 µA — very small
    "standard": "cispr",
    "class_": "B",
    "distance_m": 10.0,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Basic structure / pass-fail
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicStructure:
    def test_ok_keys_present(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert res["ok"] is True
        for k in ("compliant", "worst_freq_hz", "worst_margin_db",
                  "findings", "recommendations", "checklist", "summary"):
            assert k in res, f"missing key {k!r}"

    def test_failing_loop_compliant_false(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert res["ok"] is True
        assert res["compliant"] is False

    def test_failing_loop_negative_worst_margin(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert res["worst_margin_db"] < 0

    def test_passing_design_compliant_true(self):
        res = emc_precompliance(_PASS_DESIGN)
        assert res["ok"] is True
        assert res["compliant"] is True

    def test_passing_design_positive_margin(self):
        res = emc_precompliance(_PASS_DESIGN)
        assert res["worst_margin_db"] > 0

    def test_passing_design_no_dm_fix_needed(self):
        """Pass case: no DM loop fix recommendation."""
        res = emc_precompliance(_PASS_DESIGN)
        dm_recs = [r for r in res["recommendations"] if r["channel"] == "DM_loop"]
        assert len(dm_recs) == 0, "No DM_loop fix should be recommended when passing"

    def test_summary_contains_compliant_when_passing(self):
        res = emc_precompliance(_PASS_DESIGN)
        assert "compliant" in res["summary"].lower()

    def test_summary_contains_fail_when_failing(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert "fail" in res["summary"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DM loop findings
# ═══════════════════════════════════════════════════════════════════════════════

class TestDMFindings:
    def test_findings_list_non_empty(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert len(res["findings"]) > 0

    def test_findings_have_required_keys(self):
        res = emc_precompliance(_FAIL_DESIGN)
        for f in res["findings"]:
            for k in ("channel", "harmonic", "freq_hz", "emission_dbuvm",
                      "limit_dbuvm", "margin_db", "passes"):
                assert k in f, f"finding missing {k!r}"

    def test_dm_findings_present_for_harmonics(self):
        res = emc_precompliance(_FAIL_DESIGN)
        dm = [f for f in res["findings"] if f["channel"] == "DM_loop"]
        # At 100 MHz with n_harmonics=10, harmonics 1–10 in the 30MHz–1GHz range
        assert len(dm) >= 1

    def test_findings_consistent_with_emc_estimate(self):
        """Wizard DM emission must equal calling radiated_emission_differential directly."""
        design = _FAIL_DESIGN.copy()
        res = emc_precompliance(design)
        # Get harmonic 1 (100 MHz) DM finding
        dm_h1 = next(
            (f for f in res["findings"] if f["channel"] == "DM_loop" and f["harmonic"] == 1),
            None,
        )
        assert dm_h1 is not None
        direct = radiated_emission_differential(
            freq_hz=100e6,
            loop_area_m2=1e-4,
            current_a=0.1,
            distance_m=10.0,
        )
        assert abs(dm_h1["emission_dbuvm"] - direct["e_field_dbuvm"]) < 0.01

    def test_margin_consistent_with_emission_margin_db(self):
        """Wizard margin must equal emission_margin_db called with same inputs."""
        design = _FAIL_DESIGN.copy()
        res = emc_precompliance(design)
        dm_h1 = next(
            (f for f in res["findings"] if f["channel"] == "DM_loop" and f["harmonic"] == 1),
            None,
        )
        assert dm_h1 is not None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            direct_margin = emission_margin_db(
                e_field_dbuvm=dm_h1["emission_dbuvm"],
                freq_hz=100e6,
                standard="cispr",
                class_="B",
                distance_m=10.0,
            )
        assert abs(dm_h1["margin_db"] - direct_margin["margin_db"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DM loop-area reduction recommendation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDMLoopRecommendation:
    def test_shorten_loop_recommendation_present(self):
        res = emc_precompliance(_FAIL_DESIGN)
        actions = [r["action"] for r in res["recommendations"]]
        assert "shorten_loop" in actions

    def test_loop_reduction_target_is_half_area(self):
        res = emc_precompliance(_FAIL_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "shorten_loop")
        expected = _FAIL_DESIGN["loop_area_m2"] * 0.5
        assert abs(rec["target_loop_area_m2"] - expected) / expected < 1e-9

    def test_loop_reduction_predicted_margin_improves(self):
        """After halving loop area, predicted margin must be > before margin."""
        res = emc_precompliance(_FAIL_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "shorten_loop")
        assert rec["predicted_margin_db"] > rec["before_margin_db"]

    def test_loop_reduction_improvement_positive(self):
        res = emc_precompliance(_FAIL_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "shorten_loop")
        assert rec["improvement_db"] > 0

    def test_loop_reduction_improvement_approx_6db(self):
        """Halving loop area reduces emission by 6.02 dB (factor of 2 in E-field)."""
        res = emc_precompliance(_FAIL_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "shorten_loop")
        # improvement_db = margin_after - margin_before
        # = (limit - emission/2_in_linear)  - (limit - emission)
        # = emission - emission/2 in dB = ~6.02 dB
        assert abs(rec["improvement_db"] - 6.02) < 0.05

    def test_predicted_margin_consistent_with_direct_rerun(self):
        """Wizard predicted margin must match directly re-running emc estimate."""
        res = emc_precompliance(_FAIL_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "shorten_loop")
        # Re-run directly
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dm_after = radiated_emission_differential(
                freq_hz=rec["freq_hz"],
                loop_area_m2=rec["target_loop_area_m2"],
                current_a=_FAIL_DESIGN["loop_current_a"],
                distance_m=_FAIL_DESIGN["distance_m"],
            )
            margin_after = emission_margin_db(
                e_field_dbuvm=dm_after["e_field_dbuvm"],
                freq_hz=rec["freq_hz"],
                standard="cispr",
                class_="B",
                distance_m=_FAIL_DESIGN["distance_m"],
            )
        assert abs(rec["predicted_margin_db"] - margin_after["margin_db"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CM cable + choke recommendation
# ═══════════════════════════════════════════════════════════════════════════════

class TestCMCable:
    _DESIGN_WITH_CABLE = {
        "clock_hz": 100e6,
        "loop_area_m2": 1e-9,     # tiny DM loop so DM passes
        "loop_current_a": 1e-6,
        "cable_length_m": 1.0,    # 1 m cable
        "cm_current_a": 1e-4,     # 100 µA — should fail
        "standard": "cispr",
        "class_": "B",
        "distance_m": 10.0,
    }

    def test_cm_findings_present(self):
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        cm = [f for f in res["findings"] if f["channel"] == "CM_cable"]
        assert len(cm) > 0

    def test_cm_emission_consistent_with_direct(self):
        """Wizard CM emission must equal radiated_emission_common_mode directly."""
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        cm_h1 = next(
            (f for f in res["findings"] if f["channel"] == "CM_cable" and f["harmonic"] == 1),
            None,
        )
        assert cm_h1 is not None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            direct = radiated_emission_common_mode(
                freq_hz=100e6,
                cable_length_m=1.0,
                current_a=1e-4,
                distance_m=10.0,
            )
        assert abs(cm_h1["emission_dbuvm"] - direct["e_field_dbuvm"]) < 0.01

    def test_choke_recommendation_present_when_cm_fails(self):
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        actions = [r["action"] for r in res["recommendations"]]
        assert "add_common_mode_choke" in actions

    def test_choke_predicted_margin_better_than_before(self):
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        rec = next(r for r in res["recommendations"] if r["action"] == "add_common_mode_choke")
        assert rec["predicted_margin_db"] > rec["before_margin_db"]

    def test_choke_improvement_equals_attenuation(self):
        """Adding a 20 dB choke must improve margin by ~20 dB."""
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        rec = next(r for r in res["recommendations"] if r["action"] == "add_common_mode_choke")
        assert abs(rec["improvement_db"] - 20.0) < 0.05

    def test_choke_predicted_consistent_with_direct_rerun(self):
        """Wizard choke prediction must match re-running CM function with 10× reduced current."""
        res = emc_precompliance(self._DESIGN_WITH_CABLE)
        rec = next(r for r in res["recommendations"] if r["action"] == "add_common_mode_choke")
        choke_factor = 10.0 ** (-20.0 / 20.0)  # 20 dB attenuation
        reduced_current = 1e-4 * choke_factor
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cm_after = radiated_emission_common_mode(
                freq_hz=rec["freq_hz"],
                cable_length_m=1.0,
                current_a=reduced_current,
                distance_m=10.0,
            )
            margin_after = emission_margin_db(
                e_field_dbuvm=cm_after["e_field_dbuvm"],
                freq_hz=rec["freq_hz"],
                standard="cispr",
                class_="B",
                distance_m=10.0,
            )
        assert abs(rec["predicted_margin_db"] - margin_after["margin_db"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Shielding recommendation
# ═══════════════════════════════════════════════════════════════════════════════

class TestShielding:
    _SHIELD_DESIGN = {
        "clock_hz": 100e6,
        "loop_area_m2": 1e-4,
        "loop_current_a": 0.1,   # failing
        "shield_thickness_m": 1e-4,  # thin shield — 0.1 mm
        "shield_conductivity_rel": 1.0,
        "shield_permeability_rel": 1.0,
        "shield_aperture_length_m": 0.05,
        "standard": "cispr",
        "class_": "B",
        "distance_m": 10.0,
    }

    def test_shield_recommendation_present(self):
        res = emc_precompliance(self._SHIELD_DESIGN)
        actions = [r["action"] for r in res["recommendations"]]
        assert "add_shield" in actions

    def test_shield_required_se_ge_current_se_plus_deficit(self):
        """required_se ≥ current_se_effective + |margin_deficit| + 3 dB guard."""
        res = emc_precompliance(self._SHIELD_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "add_shield")
        # required_se should cover the deficit plus 3 dB guard
        assert rec["required_se_db"] >= rec["current_se_effective_db"] + abs(res["worst_margin_db"]) + 2.9

    def test_shield_se_consistent_with_direct(self):
        """current_se_effective must match shielding_effectiveness directly."""
        res = emc_precompliance(self._SHIELD_DESIGN)
        rec = next(r for r in res["recommendations"] if r["action"] == "add_shield")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            direct_se = shielding_effectiveness(
                freq_hz=rec["freq_hz"],
                thickness_m=1e-4,
                conductivity_relative=1.0,
                permeability_relative=1.0,
                aperture_length_m=0.05,
            )
        assert abs(rec["current_se_effective_db"] - direct_se["se_effective_db"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FCC vs CISPR changes verdict
# ═══════════════════════════════════════════════════════════════════════════════

class TestStandardSwitch:
    # Design tuned so that CISPR B (30 dBμV/m at 100 MHz @ 10m) fails
    # but FCC A (39.5 dBμV/m @ 10m) might pass.
    _BORDERLINE = {
        "clock_hz": 100e6,
        "loop_area_m2": 3e-6,
        "loop_current_a": 0.01,
        "distance_m": 10.0,
    }

    def test_cispr_b_stricter_than_fcc_a(self):
        cispr_b = emc_precompliance({**self._BORDERLINE, "standard": "cispr", "class_": "B"})
        fcc_a = emc_precompliance({**self._BORDERLINE, "standard": "fcc", "class_": "A"})
        assert cispr_b["ok"] and fcc_a["ok"]
        # FCC A limit is higher (more relaxed) than CISPR B → FCC A has better margin
        assert fcc_a["worst_margin_db"] > cispr_b["worst_margin_db"]

    def test_class_a_more_relaxed_than_class_b_cispr(self):
        cispr_b = emc_precompliance({**self._BORDERLINE, "standard": "cispr", "class_": "B"})
        cispr_a = emc_precompliance({**self._BORDERLINE, "standard": "cispr", "class_": "A"})
        assert cispr_a["worst_margin_db"] > cispr_b["worst_margin_db"]

    def test_fcc_margin_differs_from_cispr(self):
        fcc_res = emc_precompliance({**self._BORDERLINE, "standard": "fcc", "class_": "B"})
        cispr_res = emc_precompliance({**self._BORDERLINE, "standard": "cispr", "class_": "B"})
        # The margins should differ (FCC uses different limit)
        assert fcc_res["worst_margin_db"] != cispr_res["worst_margin_db"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Invalid inputs → ok=False, never raise
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidInputs:
    def test_not_a_dict(self):
        res = emc_precompliance("not a dict")
        assert res["ok"] is False
        assert "reason" in res

    def test_missing_clock_hz(self):
        res = emc_precompliance({"loop_area_m2": 1e-4, "loop_current_a": 0.001})
        assert res["ok"] is False

    def test_zero_clock_hz(self):
        res = emc_precompliance({"clock_hz": 0, "loop_area_m2": 1e-4, "loop_current_a": 0.001})
        assert res["ok"] is False

    def test_negative_loop_area(self):
        res = emc_precompliance({"clock_hz": 100e6, "loop_area_m2": -1e-4, "loop_current_a": 0.001})
        assert res["ok"] is False

    def test_invalid_standard(self):
        res = emc_precompliance({
            "clock_hz": 100e6, "loop_area_m2": 1e-4, "loop_current_a": 0.001,
            "standard": "iec_61000",
        })
        assert res["ok"] is False

    def test_invalid_class(self):
        res = emc_precompliance({
            "clock_hz": 100e6, "loop_area_m2": 1e-4, "loop_current_a": 0.001,
            "class_": "C",
        })
        assert res["ok"] is False

    def test_zero_distance(self):
        res = emc_precompliance({
            "clock_hz": 100e6, "loop_area_m2": 1e-4, "loop_current_a": 0.001,
            "distance_m": 0,
        })
        assert res["ok"] is False

    def test_negative_cm_current(self):
        res = emc_precompliance({
            "clock_hz": 100e6, "loop_area_m2": 1e-4, "loop_current_a": 0.001,
            "cable_length_m": 1.0,
            "cm_current_a": -1e-6,
        })
        assert res["ok"] is False

    def test_never_raises(self):
        """All invalid inputs must return ok=False, never raise."""
        bad_inputs = [
            None,
            42,
            {},
            {"clock_hz": -1, "loop_area_m2": 1e-4, "loop_current_a": 0.001},
            {"clock_hz": 100e6, "loop_area_m2": 0, "loop_current_a": 0.001},
        ]
        for inp in bad_inputs:
            try:
                res = emc_precompliance(inp)
                assert res.get("ok") is False, f"Expected ok=False for input {inp!r}"
            except Exception as exc:
                pytest.fail(f"emc_precompliance raised {exc!r} for input {inp!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Checklist
# ═══════════════════════════════════════════════════════════════════════════════

class TestChecklist:
    def test_checklist_contains_harmonics(self):
        res = emc_precompliance(_FAIL_DESIGN)
        assert "harmonics_evaluated" in res["checklist"]
        assert len(res["checklist"]["harmonics_evaluated"]) > 0

    def test_checklist_harmonics_are_multiples_of_clock(self):
        res = emc_precompliance(_FAIL_DESIGN)
        clock = _FAIL_DESIGN["clock_hz"]
        for h in res["checklist"]["harmonics_evaluated"]:
            n = round(h / clock)
            assert abs(h - n * clock) < 1.0, f"{h} is not a harmonic of {clock}"

    def test_checklist_cable_resonances_present_when_cable_given(self):
        design = {**_PASS_DESIGN, "cable_length_m": 1.5, "cm_current_a": 1e-8}
        res = emc_precompliance(design)
        assert res["checklist"]["cable_resonances_hz"] is not None
        assert len(res["checklist"]["cable_resonances_hz"]) > 0

    def test_checklist_cable_resonances_none_without_cable(self):
        res = emc_precompliance(_PASS_DESIGN)
        assert res["checklist"]["cable_resonances_hz"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 9. LLM tool wrapper
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolWrapper:
    @pytest.mark.asyncio
    async def test_tool_ok_failing_design(self):
        res = await _call_tool(**_FAIL_DESIGN)
        assert res["ok"] is True
        assert res["compliant"] is False

    @pytest.mark.asyncio
    async def test_tool_ok_passing_design(self):
        res = await _call_tool(**_PASS_DESIGN)
        assert res["ok"] is True
        assert res["compliant"] is True

    @pytest.mark.asyncio
    async def test_tool_invalid_json(self):
        raw = await _emc_wizard_tool(None, b"not valid json{{")
        data = json.loads(raw)
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_tool_missing_required_field(self):
        res = await _call_tool(loop_area_m2=1e-4, loop_current_a=0.001)
        assert res.get("ok") is False or "error" in res

    @pytest.mark.asyncio
    async def test_tool_roundtrip_worst_margin(self):
        """Tool worst_margin_db must match direct wizard call."""
        direct = emc_precompliance(_FAIL_DESIGN)
        tool_res = await _call_tool(**_FAIL_DESIGN)
        assert abs(tool_res["worst_margin_db"] - direct["worst_margin_db"]) < 0.01
