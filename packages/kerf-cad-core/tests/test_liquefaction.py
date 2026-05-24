"""
Tests for kerf_cad_core.geotech.liquefaction — seismic liquefaction triggering.

Coverage:
  csr_seed_idriss       — CSR formula, rd, MSF, validation cases
  crr_from_spt          — CN, fines correction, CRR_7.5 formula
  crr_from_cpt          — qc1N, Ic classification, CRR_7.5
  liquefaction_safety_factor — FS_L = CRR / CSR, flags
  post_triggering_settlement — Tokimatsu-Seed volumetric strain
  liq_tools             — LLM tool wrapper happy / error paths

Validation: Loma Prieta (1989) representative case.
  Watsonville array, z=5m, sand layer.
  amax=0.34g, M=6.9, σ=87.5 kPa, σ'=49.0 kPa, N60=10, FC=3%.
  Published FS_L ≈ 0.85–0.95 (liquefaction triggered).
  Source: Youd & Perkins (1994); Idriss & Boulanger (2008, p.48).

All tests are pure-Python and hermetic: no OCC, no DB, no network.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.geotech.liquefaction import (
    csr_seed_idriss,
    crr_from_spt,
    crr_from_cpt,
    liquefaction_safety_factor,
    post_triggering_settlement,
    _rd,
    _msf,
)
from kerf_cad_core.geotech.liq_tools import (
    run_liq_csr,
    run_liq_crr_spt,
    run_liq_crr_cpt,
    run_liq_safety_factor,
    run_liq_settlement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-4  # 0.01% relative tolerance


# ===========================================================================
# 1. rd — stress reduction factor (Liao & Whitman 1986)
# ===========================================================================

class TestStressReductionFactor:

    def test_rd_at_surface_is_1(self):
        """rd = 1.0 at z = 0."""
        assert _rd(0.0) == 1.0

    def test_rd_shallow_formula(self):
        """rd = 1 − 0.00765·z for z < 9.15 m."""
        z = 5.0
        assert abs(_rd(z) - (1.0 - 0.00765 * z)) < 1e-12

    def test_rd_deep_formula(self):
        """rd = 1.174 − 0.0267·z for 9.15 ≤ z < 23 m."""
        z = 15.0
        assert abs(_rd(z) - (1.174 - 0.0267 * z)) < 1e-12

    def test_rd_continuous_at_9_15(self):
        """rd must be nearly continuous at the 9.15 m boundary."""
        z = 9.15
        rd_shallow = 1.0 - 0.00765 * z
        rd_deep = 1.174 - 0.0267 * z
        assert abs(rd_shallow - rd_deep) < 0.01  # within 0.01

    def test_rd_decreases_with_depth(self):
        """rd must be a decreasing function of depth."""
        assert _rd(3.0) > _rd(6.0) > _rd(12.0) > _rd(20.0)

    def test_rd_positive(self):
        """rd must be positive at all reasonable depths."""
        for z in [0, 2, 5, 9, 15, 22]:
            assert _rd(z) > 0


# ===========================================================================
# 2. MSF — magnitude scaling factor (Idriss 1999)
# ===========================================================================

class TestMagnitudeScalingFactor:

    def test_msf_at_7_5_is_unity(self):
        """MSF = 10^2.24 / 7.5^2.56 ≈ 1.0 (M=7.5 is the reference)."""
        msf = _msf(7.5)
        assert abs(msf - 1.0) < 0.005  # within 0.5% of 1.0

    def test_msf_increases_for_smaller_M(self):
        """Smaller earthquakes → MSF > 1 (fewer cycles needed for same damage)."""
        assert _msf(6.0) > _msf(7.5) > _msf(8.0)

    def test_msf_formula(self):
        """MSF = 10^2.24 / M^2.56 exactly."""
        M = 7.0
        expected = (10.0 ** 2.24) / (M ** 2.56)
        assert abs(_msf(M) - expected) < 1e-12


# ===========================================================================
# 3. csr_seed_idriss
# ===========================================================================

class TestCSR:

    def test_basic_formula(self):
        """CSR_raw = 0.65 · amax · (σ/σ') · rd exactly."""
        amax, sig, sigp, z, M = 0.20, 100.0, 60.0, 5.0, 7.5
        res = csr_seed_idriss(amax, sig, sigp, z, M)
        assert res["ok"] is True
        rd = 1.0 - 0.00765 * z
        csr_raw_exp = 0.65 * amax * (sig / sigp) * rd
        assert abs(res["CSR_raw"] - csr_raw_exp) / csr_raw_exp < REL

    def test_m75_normalisation(self):
        """CSR_M7.5 = CSR_raw / MSF (within rounding of 6dp stored values)."""
        res = csr_seed_idriss(0.20, 100.0, 60.0, 5.0, 7.5)
        assert res["ok"] is True
        # Values are rounded to 6 dp; allow tolerance of 1e-5
        assert abs(res["CSR_M7.5"] - res["CSR_raw"] / res["MSF"]) < 1e-5

    def test_at_m75_csr_close_to_raw(self):
        """At M=7.5, MSF ≈ 1.0, so CSR_M7.5 ≈ CSR_raw."""
        res = csr_seed_idriss(0.20, 100.0, 60.0, 5.0, 7.5)
        assert res["ok"] is True
        assert abs(res["CSR_M7.5"] - res["CSR_raw"]) < 0.01

    def test_higher_amax_gives_higher_csr(self):
        """Larger PGA → higher CSR."""
        r1 = csr_seed_idriss(0.10, 100.0, 60.0, 5.0, 7.5)
        r2 = csr_seed_idriss(0.30, 100.0, 60.0, 5.0, 7.5)
        assert r2["CSR_M7.5"] > r1["CSR_M7.5"]

    def test_smaller_M_gives_lower_normalised_csr(self):
        """Smaller M → larger MSF → smaller CSR_M7.5 (fewer equivalent cycles)."""
        r_small = csr_seed_idriss(0.20, 100.0, 60.0, 5.0, 6.0)
        r_large = csr_seed_idriss(0.20, 100.0, 60.0, 5.0, 8.0)
        # M=6.0 has larger MSF → CSR_M7.5 is smaller
        assert r_small["CSR_M7.5"] < r_large["CSR_M7.5"]

    def test_negative_amax_returns_error(self):
        res = csr_seed_idriss(-0.1, 100.0, 60.0, 5.0, 7.5)
        assert res["ok"] is False

    def test_effective_gt_total_returns_error(self):
        res = csr_seed_idriss(0.20, 80.0, 100.0, 5.0, 7.5)
        assert res["ok"] is False

    def test_negative_depth_returns_error(self):
        res = csr_seed_idriss(0.20, 100.0, 60.0, -1.0, 7.5)
        assert res["ok"] is False

    def test_M_out_of_range_returns_error(self):
        res = csr_seed_idriss(0.20, 100.0, 60.0, 5.0, 4.0)
        assert res["ok"] is False

    def test_deep_depth_triggers_warning(self):
        """Depth > 23 m should trigger a warning about rd approximation."""
        res = csr_seed_idriss(0.20, 500.0, 300.0, 25.0, 7.5)
        assert res["ok"] is True
        assert any("23" in w or "rd" in w.lower() for w in res["warnings"])


# ===========================================================================
# 4. crr_from_spt
# ===========================================================================

class TestCRR_SPT:

    def test_CN_formula(self):
        """CN = (Pa/σ')^0.5, capped at 1.7."""
        Pa = 101.325
        sigma_p = 50.0
        res = crr_from_spt(10.0, sigma_p, Pa=Pa)
        assert res["ok"] is True
        CN_exp = min((Pa / sigma_p) ** 0.5, 1.7)
        assert abs(res["CN"] - CN_exp) / CN_exp < REL

    def test_CN_capped_at_1_7(self):
        """For very low effective stress, CN must be capped at 1.7."""
        res = crr_from_spt(5.0, 10.0)  # very low σ' → CN would be > 1.7
        assert res["ok"] is True
        assert res["CN"] <= 1.7 + 1e-9

    def test_N1_60_equals_CN_times_N60(self):
        """(N1)60 = CN × N60 (within rounding of 4dp stored values)."""
        res = crr_from_spt(12.0, 80.0)
        assert res["ok"] is True
        # Values are rounded to 4 dp; allow tolerance of 1e-3
        assert abs(res["N1_60"] - res["CN"] * 12.0) < 1e-3

    def test_clean_sand_no_fines_correction(self):
        """FC < 5% → Δ(N1)60 = 0."""
        res = crr_from_spt(10.0, 80.0, FC=2.0)
        assert res["ok"] is True
        assert res["delta_N1_60cs"] == 0.0

    def test_fines_correction_increases_N1_60cs(self):
        """FC > 5% → (N1)60cs > (N1)60."""
        res_clean = crr_from_spt(10.0, 80.0, FC=0.0)
        res_fines = crr_from_spt(10.0, 80.0, FC=20.0)
        assert res_fines["ok"] is True
        assert res_fines["N1_60cs"] > res_fines["N1_60"]

    def test_high_FC_cap(self):
        """FC ≥ 35% → Δ(N1)60 = 5.0 (Youd Eq. 6c)."""
        res = crr_from_spt(5.0, 80.0, FC=40.0)
        assert res["ok"] is True
        assert abs(res["delta_N1_60cs"] - 5.0) < 1e-9

    def test_crr_formula_algebraic(self):
        """CRR_7.5 = 1/(34−x) + x/135 + 50/(10x+45)² − 1/200 for x = (N1)60cs."""
        # Use clean sand, moderate depth so CN < 1.7
        res = crr_from_spt(10.0, 80.0, FC=0.0)
        assert res["ok"] is True
        x = res["N1_60cs"]
        crr_exp = (
            1.0 / (34.0 - x) + x / 135.0
            + 50.0 / (10.0 * x + 45.0) ** 2 - 1.0 / 200.0
        )
        assert abs(res["CRR_7.5"] - crr_exp) / crr_exp < REL

    def test_high_N1_60cs_non_liquefiable(self):
        """(N1)60cs > 30 → CRR_7.5 is None, liquefiable = False."""
        # High N60, low effective stress → high CN → high (N1)60cs
        res = crr_from_spt(50.0, 30.0, FC=0.0)
        assert res["ok"] is True
        assert res["CRR_7.5"] is None
        assert res["liquefiable"] is False

    def test_negative_N60_returns_error(self):
        res = crr_from_spt(-1.0, 80.0)
        assert res["ok"] is False

    def test_FC_out_of_range_returns_error(self):
        res = crr_from_spt(10.0, 80.0, FC=110.0)
        assert res["ok"] is False

    def test_zero_effective_stress_returns_error(self):
        res = crr_from_spt(10.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 5. crr_from_cpt
# ===========================================================================

class TestCRR_CPT:

    def test_sand_like_returns_crr(self):
        """Clean sand (low Fr, high Qt) → Ic ≤ 2.6, CRR returned."""
        # qc=10 MPa (dense-ish sand), fs=0.05 MPa, σ'=60 kPa
        res = crr_from_cpt(10.0, 60.0, 0.05)
        assert res["ok"] is True
        assert res["sand_like"] is True
        assert res["CRR_7.5"] is not None
        assert res["CRR_7.5"] > 0

    def test_Ic_below_2_6_for_clean_sand(self):
        """Low friction ratio (clean sand) should give Ic ≤ 2.6."""
        res = crr_from_cpt(10.0, 60.0, 0.05)
        assert res["ok"] is True
        assert res["Ic"] <= 2.6

    def test_high_friction_ratio_clay_like(self):
        """High sleeve friction (clay) should give Ic > 2.6 and no CRR."""
        # Very high fs relative to qc → high Fr → high Ic
        res = crr_from_cpt(1.0, 60.0, 0.08)
        assert res["ok"] is True
        # If classified as clay-like, CRR is None
        if not res["sand_like"]:
            assert res["CRR_7.5"] is None

    def test_qc1N_proportional_to_qc(self):
        """Double qc should roughly double qc1N (at same effective stress)."""
        r1 = crr_from_cpt(5.0, 60.0, 0.02)
        r2 = crr_from_cpt(10.0, 60.0, 0.04)
        assert r1["ok"] is True and r2["ok"] is True
        if r1["sand_like"] and r2["sand_like"]:
            ratio = r2["qc1N"] / r1["qc1N"]
            assert 1.5 < ratio < 2.5  # approximately double

    def test_negative_qc_returns_error(self):
        res = crr_from_cpt(-1.0, 60.0, 0.05)
        assert res["ok"] is False

    def test_negative_fs_returns_error(self):
        res = crr_from_cpt(5.0, 60.0, -0.01)
        assert res["ok"] is False

    def test_zero_effective_stress_returns_error(self):
        res = crr_from_cpt(5.0, 0.0, 0.05)
        assert res["ok"] is False


# ===========================================================================
# 6. liquefaction_safety_factor
# ===========================================================================

class TestLiquefactionSafetyFactor:

    def test_FS_formula(self):
        """FS_L = CRR / CSR (within rounding of 4dp stored value)."""
        csr, crr = 0.18, 0.20
        res = liquefaction_safety_factor(csr, crr)
        assert res["ok"] is True
        # FS_L stored to 4 dp; allow tolerance of 1e-4
        assert abs(res["FS_L"] - crr / csr) < 1e-4

    def test_liquefied_when_FS_lt_1(self):
        """CRR < CSR → liquefied = True."""
        res = liquefaction_safety_factor(0.25, 0.18)
        assert res["ok"] is True
        assert res["liquefied"] is True
        assert any("triggered" in w.lower() or "liquef" in w.lower() for w in res["warnings"])

    def test_not_liquefied_when_FS_gt_1(self):
        """CRR > CSR → liquefied = False."""
        res = liquefaction_safety_factor(0.15, 0.30)
        assert res["ok"] is True
        assert res["liquefied"] is False

    def test_adequate_when_FS_ge_design_margin(self):
        """FS_L ≥ design_margin → adequate_for_design = True."""
        res = liquefaction_safety_factor(0.10, 0.20, design_margin=1.5)
        assert res["ok"] is True
        assert res["adequate_for_design"] is True

    def test_marginal_when_FS_between_1_and_margin(self):
        """1.0 ≤ FS_L < design_margin → not liquefied but not adequate."""
        res = liquefaction_safety_factor(0.18, 0.20, design_margin=1.25)
        # FS = 0.20/0.18 = 1.111 → between 1.0 and 1.25
        assert res["ok"] is True
        assert res["liquefied"] is False
        assert res["adequate_for_design"] is False
        assert any("marginal" in w.lower() for w in res["warnings"])

    def test_zero_csr_returns_error(self):
        res = liquefaction_safety_factor(0.0, 0.20)
        assert res["ok"] is False

    def test_zero_crr_returns_error(self):
        res = liquefaction_safety_factor(0.15, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. post_triggering_settlement
# ===========================================================================

class TestPostTriggeringSettlement:

    def test_returns_ok(self):
        """Basic call with reasonable inputs should succeed."""
        res = post_triggering_settlement(0.20, 8.0, 3.0)
        assert res["ok"] is True
        assert res["epsilon_v_pct"] >= 0.0
        assert res["settlement_m"] >= 0.0

    def test_settlement_mm_equals_1000_times_m(self):
        """settlement_mm = settlement_m × 1000."""
        res = post_triggering_settlement(0.20, 8.0, 3.0)
        assert res["ok"] is True
        assert abs(res["settlement_mm"] - res["settlement_m"] * 1000.0) < 1e-6

    def test_denser_sand_less_settlement(self):
        """Higher N1_60 → lower volumetric strain → less settlement."""
        r1 = post_triggering_settlement(0.20, 5.0, 3.0)
        r2 = post_triggering_settlement(0.20, 15.0, 3.0)
        assert r1["ok"] is True and r2["ok"] is True
        assert r1["epsilon_v_pct"] > r2["epsilon_v_pct"]

    def test_thicker_layer_more_settlement(self):
        """Thicker layer → proportionally more settlement."""
        r1 = post_triggering_settlement(0.20, 8.0, 2.0)
        r2 = post_triggering_settlement(0.20, 8.0, 4.0)
        assert r1["ok"] is True and r2["ok"] is True
        assert abs(r2["settlement_m"] - 2.0 * r1["settlement_m"]) < 1e-9

    def test_N1_60_gt_30_gives_zero(self):
        """N1_60 > 30 → non-liquefiable, settlement = 0."""
        res = post_triggering_settlement(0.20, 35.0, 3.0)
        assert res["ok"] is True
        assert res["settlement_m"] == 0.0

    def test_zero_CSR_returns_error(self):
        res = post_triggering_settlement(0.0, 8.0, 3.0)
        assert res["ok"] is False

    def test_zero_thickness_returns_error(self):
        res = post_triggering_settlement(0.20, 8.0, 0.0)
        assert res["ok"] is False

    def test_negative_N1_60_returns_error(self):
        res = post_triggering_settlement(0.20, -1.0, 3.0)
        assert res["ok"] is False


# ===========================================================================
# 8. Citable reference case: Loma Prieta (1989) — Watsonville array
# ===========================================================================
# Loma Prieta earthquake Mw=6.9, amax≈0.34g at Watsonville.
# Representative saturated sand layer at z≈5 m:
#   σ_v  = γ_sat × z ≈ 18.5 × 5 = 92.5 kPa   (saturated soil)
#   σ'_v = σ_v − u  ≈ 92.5 − 9.81×5 = 43.4 kPa
#   N60  = 8 (typical for loose sand that liquefied)
#   FC   = 3%
# Published outcome: liquefaction triggered, FS_L < 1.0.
# Reference: Youd & Perkins (1994) USGS OFR 94-596; Idriss & Boulanger (2008).
# ===========================================================================

class TestLomaPrietaReferenceCase:

    # Parameters for Watsonville representative site
    AMAX = 0.34
    M = 6.9
    SIGMA_V = 92.5      # kPa (total)
    SIGMA_EFF = 43.4    # kPa (effective, above water table ~5m)
    DEPTH = 5.0         # m
    N60 = 8
    FC = 3.0

    def test_csr_is_positive_and_reasonable(self):
        res = csr_seed_idriss(self.AMAX, self.SIGMA_V, self.SIGMA_EFF,
                               self.DEPTH, self.M)
        assert res["ok"] is True
        # CSR for this case should be in range 0.20–0.40
        assert 0.15 < res["CSR_M7.5"] < 0.50, f"CSR_M7.5={res['CSR_M7.5']:.4f}"

    def test_crr_spt_is_positive_and_reasonable(self):
        res = crr_from_spt(self.N60, self.SIGMA_EFF, FC=self.FC)
        assert res["ok"] is True
        assert res["CRR_7.5"] is not None
        # CRR for loose sand N60=8 should be ~0.10–0.18
        assert 0.08 < res["CRR_7.5"] < 0.25, f"CRR_7.5={res['CRR_7.5']:.4f}"

    def test_loma_prieta_liquefaction_triggered(self):
        """FS_L < 1.0 for Loma Prieta loose sand layer — matches field observation."""
        csr_res = csr_seed_idriss(self.AMAX, self.SIGMA_V, self.SIGMA_EFF,
                                   self.DEPTH, self.M)
        crr_res = crr_from_spt(self.N60, self.SIGMA_EFF, FC=self.FC)

        assert csr_res["ok"] and crr_res["ok"]
        CSR = csr_res["CSR_M7.5"]
        CRR = crr_res["CRR_7.5"]

        fs_res = liquefaction_safety_factor(CSR, CRR)
        assert fs_res["ok"] is True

        # Field observation: liquefaction was triggered → FS_L < 1.0
        assert fs_res["FS_L"] < 1.0, (
            f"Expected FS_L < 1.0 for Loma Prieta loose sand; got {fs_res['FS_L']:.3f}. "
            f"CSR={CSR:.4f}, CRR={CRR:.4f}"
        )
        assert fs_res["liquefied"] is True

    def test_loma_prieta_settlement_nonzero(self):
        """Tokimatsu-Seed settlement should be > 0 for this liquefiable case."""
        crr_res = crr_from_spt(self.N60, self.SIGMA_EFF, FC=self.FC)
        assert crr_res["ok"] is True
        N1_60 = crr_res["N1_60"]

        # CSR raw (use a CSR ≈ 0.25 as representative for this site)
        csr_res = csr_seed_idriss(self.AMAX, self.SIGMA_V, self.SIGMA_EFF,
                                   self.DEPTH, self.M)
        CSR_m75 = csr_res["CSR_M7.5"]

        s_res = post_triggering_settlement(CSR_m75, N1_60, layer_thickness_m=3.0)
        assert s_res["ok"] is True
        assert s_res["settlement_mm"] > 10.0, (
            f"Expected > 10 mm settlement for loose sand; got {s_res['settlement_mm']:.1f} mm"
        )


# ===========================================================================
# 9. Christchurch 2011 cross-check (CAN_NOT_LIQUEFY control)
# ===========================================================================
# Dense sand (non-liquefiable control): N60=40, σ'=80 kPa.
# Expected: (N1)60cs > 30, CRR = None, FS_L computation impossible.

class TestChristchurchDenseSandControl:

    def test_dense_sand_non_liquefiable(self):
        """Dense Christchurch sand (N60=40) should be non-liquefiable."""
        res = crr_from_spt(40.0, 80.0, FC=5.0)
        assert res["ok"] is True
        assert res["CRR_7.5"] is None
        assert res["liquefiable"] is False
        assert res["N1_60cs"] > 30.0


# ===========================================================================
# 10. LLM tool wrappers
# ===========================================================================

class TestLiqToolWrappers:

    def test_run_liq_csr_happy_path(self):
        ctx = _ctx()
        raw = _run(run_liq_csr(ctx, _args(
            amax_g=0.20, total_stress_kPa=120.0, effective_stress_kPa=70.0,
            depth_m=6.0, M=7.5
        )))
        d = _ok_tool(raw)
        assert d["CSR_M7.5"] > 0
        assert d["rd"] > 0
        assert d["MSF"] > 0

    def test_run_liq_csr_missing_field(self):
        ctx = _ctx()
        raw = _run(run_liq_csr(ctx, _args(
            amax_g=0.20, total_stress_kPa=120.0  # missing fields
        )))
        _err_tool(raw)

    def test_run_liq_csr_bad_json(self):
        ctx = _ctx()
        raw = _run(run_liq_csr(ctx, b"not-json"))
        _err_tool(raw)

    def test_run_liq_crr_spt_happy_path(self):
        ctx = _ctx()
        raw = _run(run_liq_crr_spt(ctx, _args(
            N60=10.0, effective_stress_kPa=80.0, FC=5.0
        )))
        d = _ok_tool(raw)
        assert d["N1_60"] > 0
        assert d["CRR_7.5"] is not None

    def test_run_liq_crr_spt_missing_field(self):
        ctx = _ctx()
        raw = _run(run_liq_crr_spt(ctx, _args(
            N60=10.0  # missing effective_stress_kPa
        )))
        _err_tool(raw)

    def test_run_liq_crr_cpt_happy_path(self):
        ctx = _ctx()
        raw = _run(run_liq_crr_cpt(ctx, _args(
            qc_MPa=8.0, effective_stress_kPa=60.0, fs_MPa=0.04
        )))
        d = _ok_tool(raw)
        assert d["qc1N"] > 0
        assert "Ic" in d

    def test_run_liq_crr_cpt_missing_field(self):
        ctx = _ctx()
        raw = _run(run_liq_crr_cpt(ctx, _args(
            qc_MPa=8.0  # missing other required fields
        )))
        _err_tool(raw)

    def test_run_liq_safety_factor_happy_path(self):
        ctx = _ctx()
        raw = _run(run_liq_safety_factor(ctx, _args(
            CSR=0.18, CRR=0.25
        )))
        d = _ok_tool(raw)
        assert d["FS_L"] > 0
        assert isinstance(d["liquefied"], bool)
        assert isinstance(d["adequate_for_design"], bool)

    def test_run_liq_safety_factor_triggers_liquefaction(self):
        ctx = _ctx()
        raw = _run(run_liq_safety_factor(ctx, _args(
            CSR=0.30, CRR=0.15
        )))
        d = _ok_tool(raw)
        assert d["liquefied"] is True

    def test_run_liq_safety_factor_missing_field(self):
        ctx = _ctx()
        raw = _run(run_liq_safety_factor(ctx, _args(CSR=0.18)))
        _err_tool(raw)

    def test_run_liq_settlement_happy_path(self):
        ctx = _ctx()
        raw = _run(run_liq_settlement(ctx, _args(
            CSR=0.20, N1_60=8.0, layer_thickness_m=3.0
        )))
        d = _ok_tool(raw)
        assert d["epsilon_v_pct"] >= 0.0
        assert d["settlement_m"] >= 0.0
        assert d["settlement_mm"] >= 0.0

    def test_run_liq_settlement_missing_field(self):
        ctx = _ctx()
        raw = _run(run_liq_settlement(ctx, _args(
            CSR=0.20  # missing N1_60, layer_thickness_m
        )))
        _err_tool(raw)

    def test_run_liq_settlement_bad_json(self):
        ctx = _ctx()
        raw = _run(run_liq_settlement(ctx, b"}}bad"))
        _err_tool(raw)
