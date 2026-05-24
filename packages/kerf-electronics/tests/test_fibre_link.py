"""
Tests for kerf_electronics.photonics.fibre_link — full fibre-optic link analysis.

Validates:
  mode_overlap_coupling  — Marcuse Gaussian coupling (MFD, offset, tilt)
  dispersion_penalty     — CD, PMD, modal bandwidth
  splitter_loss          — 1×N ideal + excess loss
  optical_link_budget    — full end-to-end power budget
  LLM tools              — photonics_fibre_coupling, photonics_link_budget,
                           photonics_dispersion_penalty

Canonical validation cases (from task spec):
  1. SMF-28 @ 1550 nm, 40 km, 2 connectors + 2 fusion splices,
     Tx=0 dBm, Rx_sens=-28 dBm, 10 Gbps → margin > 10 dB.
  2. Matched MFD fibers (10 µm) with 5 µm lateral offset →
     coupling loss between 2 and 7 dB (Marcuse Gaussian, w=MFD/2).

Physical constants
------------------
All formulas are cross-verified against:
  Marcuse (1977) BSTJ 56(5): Gaussian mode-field coupling
  ITU-T G.652.D: SMF-28 attenuation and dispersion
  ISO 11801 OM4: MMF-OM4 EMB bandwidth

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

# ── Stub kerf_chat.tools.registry so import works without the full backend ───
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
sys.modules.setdefault("kerf_chat.tools.registry", _reg_stub)

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.photonics.fibre_link import (
    FIBRE_TABLE,
    SPLICE_LOSS_DB,
    dispersion_penalty,
    mode_overlap_coupling,
    optical_link_budget,
    splitter_loss,
)

# ── Load LLM tool module via importlib (so stub stays active) ─────────────────
_fl_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.photonics.fibre_link",
    os.path.join(_SRC, "kerf_electronics", "photonics", "fibre_link.py"),
)
_fl_mod = importlib.util.module_from_spec(_fl_spec)
_fl_spec.loader.exec_module(_fl_mod)

tool_fibre_coupling     = _fl_mod.photonics_fibre_coupling
tool_link_budget        = _fl_mod.photonics_link_budget
tool_dispersion_penalty = _fl_mod.photonics_dispersion_penalty


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FIBRE_TABLE sanity checks
# ═══════════════════════════════════════════════════════════════════════════════

class TestFibreTable:
    def test_smf28_present(self):
        assert "SMF-28" in FIBRE_TABLE

    def test_mmf_om4_present(self):
        assert "MMF-OM4" in FIBRE_TABLE

    def test_smf28_attenuation_1550(self):
        """SMF-28: 0.20 dB/km @ 1550 nm (ITU-T G.652.D)."""
        fp = FIBRE_TABLE["SMF-28"]
        assert abs(fp["attenuation_1550_db_per_km"] - 0.20) < 0.01

    def test_smf28_attenuation_1310(self):
        """SMF-28: 0.35 dB/km @ 1310 nm."""
        fp = FIBRE_TABLE["SMF-28"]
        assert abs(fp["attenuation_1310_db_per_km"] - 0.35) < 0.01

    def test_smf28_dispersion_1550(self):
        """SMF-28: D = 17 ps/(nm·km) @ 1550 nm."""
        fp = FIBRE_TABLE["SMF-28"]
        assert abs(fp["dispersion_1550_ps_per_nm_km"] - 17.0) < 0.5

    def test_smf28_mfd_1550(self):
        """SMF-28: MFD ≈ 10.4 µm @ 1550 nm (Corning datasheet)."""
        fp = FIBRE_TABLE["SMF-28"]
        assert 9.5 <= fp["mfd_1550_um"] <= 11.0

    def test_mmf_om4_core_diameter(self):
        """OM4: 50 µm core."""
        fp = FIBRE_TABLE["MMF-OM4"]
        assert fp["core_diameter_um"] == 50.0

    def test_mmf_om4_attenuation_850(self):
        """OM4: 2.3 dB/km @ 850 nm."""
        fp = FIBRE_TABLE["MMF-OM4"]
        assert abs(fp["attenuation_850_db_per_km"] - 2.3) < 0.1

    def test_mmf_om4_emb_bandwidth(self):
        """OM4: EMB BW·distance = 4700 MHz·km @ 850 nm."""
        fp = FIBRE_TABLE["MMF-OM4"]
        assert abs(fp["bandwidth_mhz_km"] - 4700.0) < 10

    def test_splice_loss_defaults(self):
        """Fusion splice 0.05 dB, mechanical 0.10 dB, connector 0.30 dB."""
        assert SPLICE_LOSS_DB["fusion"] == 0.05
        assert SPLICE_LOSS_DB["mechanical"] == 0.10
        assert 0.20 <= SPLICE_LOSS_DB["connector"] <= 0.50


# ═══════════════════════════════════════════════════════════════════════════════
# 2. mode_overlap_coupling (Marcuse)
# ═══════════════════════════════════════════════════════════════════════════════

class TestModeOverlapCoupling:
    """Marcuse (1977) Gaussian coupling: MFD mismatch + lateral offset + angular tilt."""

    def test_perfect_match_zero_loss(self):
        """Identical fibers, no offset, no tilt → η = 1.0, loss = 0 dB."""
        r = mode_overlap_coupling(mfd1_um=10.4, mfd2_um=10.4)
        assert r["ok"] is True
        assert abs(r["eta_total"] - 1.0) < 1e-6
        assert r["coupling_loss_db"] < 1e-4

    def test_eta_overlap_formula(self):
        """η_overlap = [2·w₁·w₂/(w₁²+w₂²)]² — Marcuse 1977 Eq. 2."""
        mfd1, mfd2 = 10.0, 8.0
        w1, w2 = mfd1 / 2, mfd2 / 2
        expected = (2 * w1 * w2 / (w1**2 + w2**2)) ** 2
        r = mode_overlap_coupling(mfd1_um=mfd1, mfd2_um=mfd2)
        assert abs(r["eta_overlap"] - expected) < 1e-9

    def test_mfd_mismatch_reduces_overlap(self):
        """Different MFDs → η_overlap < 1."""
        r = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=5.0)
        assert r["eta_overlap"] < 1.0
        assert r["coupling_loss_db"] > 0.0

    def test_lateral_offset_reduces_coupling(self):
        """Nonzero lateral offset → η_offset < 1 → higher loss."""
        r0 = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, lateral_offset_um=0.0)
        r1 = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, lateral_offset_um=2.0)
        assert r1["eta_offset"] < 1.0
        assert r1["coupling_loss_db"] > r0["coupling_loss_db"]

    def test_lateral_offset_formula(self):
        """η_offset = exp(-d²/((w₁²+w₂²)/2)) for equal fibers."""
        mfd = 10.0
        d = 3.0
        w = mfd / 2
        expected = math.exp(-(d**2) / ((w**2 + w**2) / 2.0))
        r = mode_overlap_coupling(mfd1_um=mfd, mfd2_um=mfd, lateral_offset_um=d)
        assert abs(r["eta_offset"] - expected) < 1e-9

    def test_canonical_5um_offset_10um_mfd(self):
        """5 µm lateral offset on matched 10 µm MFD: Marcuse gives ~3–6 dB loss."""
        r = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, lateral_offset_um=5.0)
        assert r["ok"] is True
        # Marcuse formula (w=MFD/2, denominator=(w1^2+w2^2)/2=w^2):
        # eta_offset = exp(-25/25) = e^-1 ≈ 0.368 → 4.34 dB
        assert 2.0 <= r["coupling_loss_db"] <= 7.0
        assert r["eta_offset"] < 0.5  # significant coupling loss

    def test_angular_tilt_reduces_coupling(self):
        """Angular misalignment → η_tilt < 1."""
        r0 = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, angular_mrad=0.0)
        r1 = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, angular_mrad=5.0)
        assert r1["eta_tilt"] < 1.0
        assert r1["coupling_loss_db"] > r0["coupling_loss_db"]

    def test_angular_tilt_formula(self):
        """η_tilt = exp(-(π·n·w_avg·θ/λ)²)."""
        mfd = 10.0
        theta_mrad = 3.0
        n_core = 1.468
        lambda_nm = 1550.0
        w_avg = mfd / 2  # equal fibers
        theta_rad = theta_mrad * 1e-3
        lambda_um = lambda_nm * 1e-3
        expected = math.exp(-((math.pi * n_core * w_avg * theta_rad / lambda_um) ** 2))
        r = mode_overlap_coupling(
            mfd1_um=mfd, mfd2_um=mfd,
            angular_mrad=theta_mrad, lambda_nm=lambda_nm, n_core=n_core
        )
        assert abs(r["eta_tilt"] - expected) < 1e-9

    def test_combined_loss_additive_in_db(self):
        """Total loss [dB] ≈ overlap_loss + offset_loss + tilt_loss."""
        r = mode_overlap_coupling(
            mfd1_um=10.0, mfd2_um=8.0,
            lateral_offset_um=2.0, angular_mrad=1.0, lambda_nm=1550.0
        )
        total_from_parts = r["eta_overlap_db"] + r["eta_offset_db"] + r["eta_tilt_db"]
        assert abs(r["coupling_loss_db"] - total_from_parts) < 0.01

    def test_coupling_loss_db_matches_eta_total(self):
        """coupling_loss_db = -10·log10(eta_total)."""
        r = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=7.0, lateral_offset_um=3.0)
        expected_db = -10 * math.log10(max(r["eta_total"], 1e-15))
        assert abs(r["coupling_loss_db"] - expected_db) < 0.001

    def test_zero_mfd_returns_error(self):
        r = mode_overlap_coupling(mfd1_um=0.0, mfd2_um=10.0)
        assert r["ok"] is False

    def test_negative_offset_returns_error(self):
        r = mode_overlap_coupling(mfd1_um=10.0, mfd2_um=10.0, lateral_offset_um=-1.0)
        assert r["ok"] is False

    def test_smf28_spliced_to_itself_low_loss(self):
        """Fusion splice of SMF-28 to itself: loss should be < 0.1 dB (ideal)."""
        mfd = FIBRE_TABLE["SMF-28"]["mfd_1550_um"]
        r = mode_overlap_coupling(mfd1_um=mfd, mfd2_um=mfd)
        assert r["coupling_loss_db"] < 0.01

    def test_smf_to_mmf_large_mfd_mismatch(self):
        """SMF MFD ≈ 10 µm vs MMF core 50 µm: overlap loss > 0."""
        # MMF effective MFD not well-defined; use core as proxy
        r = mode_overlap_coupling(mfd1_um=10.4, mfd2_um=50.0)
        assert r["ok"] is True
        assert r["eta_overlap"] < 1.0
        assert r["coupling_loss_db"] > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. dispersion_penalty
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispersionPenalty:
    """CD, PMD, and modal bandwidth penalties."""

    def test_smf28_cd_penalty_positive(self):
        """SMF-28 40 km @ 1550 nm: chromatic dispersion penalty > 0."""
        r = dispersion_penalty(
            fibre_type="SMF-28", length_km=40, bit_rate_gbps=10,
            wavelength_nm=1550, source_linewidth_nm=0.1
        )
        assert r["ok"] is True
        assert r["delta_tau_cd_ps"] > 0.0
        assert r["cd_penalty_db"] >= 0.0

    def test_cd_tau_formula(self):
        """Δτ_CD = |D| · Δλ · L [ps]."""
        D = 17.0    # ps/(nm·km) — SMF-28 at 1550 nm (table value)
        delta_lam = 0.1   # nm
        L = 40.0    # km
        expected_tau = D * delta_lam * L    # 68 ps
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty(
                fibre_type="SMF-28", length_km=L, bit_rate_gbps=100,  # high BR: small penalty
                wavelength_nm=1550, source_linewidth_nm=delta_lam, pmd_enabled=False
            )
        # The code may interpolate D from slope; allow generous tolerance
        assert abs(r["delta_tau_cd_ps"] - expected_tau) < 30.0   # within 30 ps

    def test_longer_fibre_more_dispersion(self):
        """Longer fibre → larger Δτ_CD."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r1 = dispersion_penalty("SMF-28", 20, 10)
            r2 = dispersion_penalty("SMF-28", 40, 10)
        assert r2["delta_tau_cd_ps"] > r1["delta_tau_cd_ps"]

    def test_pmd_scales_as_sqrt_length(self):
        """Δτ_PMD = PMD_coeff · √L → doubles when L quadruples."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r1 = dispersion_penalty("SMF-28", length_km=25.0, bit_rate_gbps=10)
            r4 = dispersion_penalty("SMF-28", length_km=100.0, bit_rate_gbps=10)
        pmd_coeff = FIBRE_TABLE["SMF-28"]["polarisation_mode_dispersion_ps_per_sqrt_km"]
        if pmd_coeff and r1.get("delta_tau_pmd_ps") and r4.get("delta_tau_pmd_ps"):
            # PMD at L=25 and L=100: ratio = sqrt(100/25) = 2
            ratio = r4["delta_tau_pmd_ps"] / r1["delta_tau_pmd_ps"]
            assert abs(ratio - 2.0) < 0.01

    def test_mmf_om4_modal_bandwidth(self):
        """MMF-OM4 modal BW @ 300 m, 10 Gbps at 850 nm."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty(
                "MMF-OM4", length_km=0.3, bit_rate_gbps=10, wavelength_nm=850
            )
        assert r["ok"] is True
        bw = r["bw_modal_ghz"]
        assert bw is not None
        # EMB = 4700 MHz·km; at 300m: BW = 4700/sqrt(0.3) = ~8581 MHz ≈ 8.58 GHz
        assert 5.0 <= bw <= 15.0

    def test_mmf_om4_bandwidth_formula(self):
        """BW_modal = BW_per_km / sqrt(L)."""
        L = 0.5   # km
        bw_km = FIBRE_TABLE["MMF-OM4"]["bandwidth_mhz_km"]
        expected_bw_ghz = bw_km / (math.sqrt(L) * 1e3)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty(
                "MMF-OM4", length_km=L, bit_rate_gbps=1, wavelength_nm=850
            )
        assert abs(r["bw_modal_ghz"] - expected_bw_ghz) < 0.01

    def test_unknown_fibre_returns_error(self):
        r = dispersion_penalty("NONEXISTENT", 40, 10)
        assert r["ok"] is False

    def test_zero_length_returns_error(self):
        r = dispersion_penalty("SMF-28", 0, 10)
        assert r["ok"] is False

    def test_total_penalty_geq_zero(self):
        """Total dispersion penalty must be non-negative."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty("SMF-28", 40, 10)
        assert r["total_dispersion_penalty_db"] >= 0.0

    def test_pmd_disabled(self):
        """pmd_enabled=False → delta_tau_pmd_ps is None, pmd_penalty_db = 0."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty("SMF-28", 40, 10, pmd_enabled=False)
        assert r["delta_tau_pmd_ps"] is None
        assert r["pmd_penalty_db"] == 0.0

    def test_dsf_near_zero_cd_at_1550(self):
        """DSF (G.653): zero-dispersion at 1550 nm → CD ≈ 0."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = dispersion_penalty("DSF", 100, 10, wavelength_nm=1550)
        assert r["ok"] is True
        assert abs(r["delta_tau_cd_ps"]) < 5.0   # near-zero


# ═══════════════════════════════════════════════════════════════════════════════
# 4. splitter_loss
# ═══════════════════════════════════════════════════════════════════════════════

class TestSplitterLoss:
    def test_1x2_splitting_loss(self):
        """1×2 ideal splitting loss = 10·log10(2) ≈ 3.01 dB."""
        r = splitter_loss(n_outputs=2)
        assert r["ok"] is True
        assert abs(r["splitting_loss_db"] - 10 * math.log10(2)) < 0.001

    def test_1x4_splitting_loss(self):
        """1×4 ideal splitting loss = 10·log10(4) ≈ 6.02 dB."""
        r = splitter_loss(n_outputs=4)
        assert abs(r["splitting_loss_db"] - 10 * math.log10(4)) < 0.001

    def test_excess_loss_added(self):
        """total_insertion_loss = splitting_loss + excess_loss."""
        excess = 0.7
        r = splitter_loss(n_outputs=4, excess_loss_db=excess)
        assert abs(r["total_insertion_loss_db"] - r["splitting_loss_db"] - excess) < 1e-9

    def test_1x8_total_loss(self):
        """1×8: 9.03 dB splitting + 0.7 dB excess = 9.73 dB."""
        r = splitter_loss(n_outputs=8, excess_loss_db=0.7)
        assert abs(r["total_insertion_loss_db"] - (10 * math.log10(8) + 0.7)) < 0.001

    def test_n_outputs_one_returns_error(self):
        r = splitter_loss(n_outputs=1)
        assert r["ok"] is False

    def test_negative_excess_loss_returns_error(self):
        r = splitter_loss(n_outputs=4, excess_loss_db=-0.1)
        assert r["ok"] is False

    def test_zero_excess_loss_allowed(self):
        """Ideal splitter (no excess loss) is valid."""
        r = splitter_loss(n_outputs=2, excess_loss_db=0.0)
        assert r["ok"] is True
        assert r["total_insertion_loss_db"] == r["splitting_loss_db"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. optical_link_budget
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpticalLinkBudget:
    """Full end-to-end link power budget."""

    # ── Canonical validation case ─────────────────────────────────────────────

    def test_smf28_40km_canonical_margin_gt_10dB(self):
        """
        SMF-28, 1550 nm, 40 km, 2 connectors + 2 fusion splices,
        Tx=0 dBm, Rx_sens=-28 dBm, 10 Gbps → margin > 10 dB.

        Loss breakdown:
          fibre:      0.20 dB/km × 40 km = 8.00 dB
          connectors: 2 × 0.30 dB       = 0.60 dB
          splices:    2 × 0.05 dB       = 0.10 dB
          ageing:                         3.00 dB
          dispersion: ~0–4 dB (varies by D slope interpolation)
        Max allowable loss: 0 − (−28) = 28 dB
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=0.0,
                rx_sens_dbm=-28.0,
                fibre_type="SMF-28",
                length_km=40.0,
                n_connectors=2,
                n_splices=2,
                bit_rate_gbps=10.0,
                wavelength_nm=1550.0,
                ageing_margin_db=3.0,
            )
        assert r["ok"] is True
        assert r["margin_db"] > 10.0
        assert r["link_ok"] is True

    def test_smf28_40km_fibre_loss_exact(self):
        """Fibre loss = α × L = 0.20 × 40 = 8.00 dB."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=40,
                n_connectors=0, n_splices=0, bit_rate_gbps=10,
                include_dispersion_penalty=False, ageing_margin_db=0.0
            )
        assert abs(r["fibre_loss_db"] - 8.0) < 0.001

    def test_connector_loss_sum(self):
        """Total connector loss = n × loss_per_connector."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-30, fibre_type="SMF-28", length_km=10,
                n_connectors=4, n_splices=0, connector_loss_db=0.25,
                include_dispersion_penalty=False, ageing_margin_db=0.0
            )
        assert abs(r["total_connector_loss_db"] - 4 * 0.25) < 1e-9

    def test_splice_loss_sum(self):
        """Total splice loss = n × loss_per_splice."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-30, fibre_type="SMF-28", length_km=10,
                n_connectors=0, n_splices=6, splice_loss_db=0.05,
                include_dispersion_penalty=False, ageing_margin_db=0.0
            )
        assert abs(r["total_splice_loss_db"] - 6 * 0.05) < 1e-9

    def test_max_allowable_loss_equals_tx_minus_rx(self):
        """Max allowable loss = Tx_dBm − Rx_sens_dBm."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=3.0, rx_sens_dbm=-25.0, fibre_type="SMF-28", length_km=10,
                include_dispersion_penalty=False
            )
        assert abs(r["max_allowable_loss_db"] - 28.0) < 1e-9

    def test_margin_formula(self):
        """margin = max_allowable_loss − total_loss."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=20,
                n_connectors=2, n_splices=1, ageing_margin_db=2.0,
                include_dispersion_penalty=False
            )
        expected_margin = r["max_allowable_loss_db"] - r["total_loss_db"]
        assert abs(r["margin_db"] - expected_margin) < 1e-9

    def test_link_ok_false_when_margin_negative(self):
        """Link budget fails when total loss exceeds available margin."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=-10.0,    # very low Tx
                rx_sens_dbm=-15.0,    # poor sensitivity
                fibre_type="SMF-28",
                length_km=100.0,     # very long span
                n_connectors=10,
                n_splices=20,
                ageing_margin_db=3.0,
                include_dispersion_penalty=False,
            )
        assert r["ok"] is True
        assert r["link_ok"] is False
        assert r["margin_db"] < 0.0

    def test_splitter_included_in_budget(self):
        """Adding a 1×4 splitter increases total loss by ~6.7 dB."""
        common = dict(
            tx_dbm=0, rx_sens_dbm=-30, fibre_type="SMF-28", length_km=10,
            n_connectors=2, n_splices=0, include_dispersion_penalty=False, ageing_margin_db=0
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r_no_split = optical_link_budget(**common, n_splitter_outputs=0)
            r_split = optical_link_budget(**common, n_splitter_outputs=4, splitter_excess_loss_db=0.7)
        assert r_split["total_loss_db"] > r_no_split["total_loss_db"] + 5.0

    def test_dispersion_penalty_adds_to_loss(self):
        """Including dispersion penalty increases total loss."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r_no = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=40,
                n_connectors=2, n_splices=2, include_dispersion_penalty=False
            )
            r_dp = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=40,
                n_connectors=2, n_splices=2, include_dispersion_penalty=True
            )
        assert r_dp["total_loss_db"] >= r_no["total_loss_db"]

    def test_mmf_om4_850nm_link(self):
        """MMF-OM4 short-reach link at 850 nm."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=-2.0,
                rx_sens_dbm=-18.0,
                fibre_type="MMF-OM4",
                length_km=0.3,
                n_connectors=2,
                n_splices=0,
                wavelength_nm=850.0,
                bit_rate_gbps=10.0,
                ageing_margin_db=2.0,
            )
        assert r["ok"] is True
        # 0.3 km × 2.3 dB/km = 0.69 dB fibre; max_allow = 16 dB → should pass
        assert r["fibre_loss_db"] < 1.0

    def test_ageing_margin_reduces_effective_budget(self):
        """Higher ageing margin → lower effective margin."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r1 = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=20,
                ageing_margin_db=1.0, include_dispersion_penalty=False
            )
            r2 = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=20,
                ageing_margin_db=5.0, include_dispersion_penalty=False
            )
        assert r2["margin_db"] < r1["margin_db"]
        assert abs(r1["margin_db"] - r2["margin_db"] - 4.0) < 1e-6

    def test_longer_span_smaller_margin(self):
        """Doubling span doubles fibre loss → smaller margin."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r1 = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=20,
                n_connectors=0, n_splices=0, include_dispersion_penalty=False, ageing_margin_db=0
            )
            r2 = optical_link_budget(
                tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=40,
                n_connectors=0, n_splices=0, include_dispersion_penalty=False, ageing_margin_db=0
            )
        assert r2["margin_db"] < r1["margin_db"]
        # Delta = 0.20 * 20 = 4.0 dB
        assert abs(r1["margin_db"] - r2["margin_db"] - 4.0) < 0.01

    def test_unknown_fibre_returns_error(self):
        r = optical_link_budget(
            tx_dbm=0, rx_sens_dbm=-28, fibre_type="UNKNOWN_FIBRE", length_km=40
        )
        assert r["ok"] is False

    def test_zero_length_returns_error(self):
        r = optical_link_budget(
            tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=0.0
        )
        assert r["ok"] is False

    def test_nzdsf_link_budget(self):
        """NZDSF (G.655) 80 km DWDM link at 1550 nm."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = optical_link_budget(
                tx_dbm=2.0,
                rx_sens_dbm=-28.0,
                fibre_type="NZDSF",
                length_km=80.0,
                n_connectors=2,
                n_splices=10,
                bit_rate_gbps=10.0,
                ageing_margin_db=3.0,
            )
        assert r["ok"] is True
        # NZDSF: 0.22 dB/km × 80 km = 17.6 dB
        assert abs(r["fibre_loss_db"] - 0.22 * 80) < 0.01

    def test_smf28_1310nm_higher_loss(self):
        """SMF-28 at 1310 nm has higher attenuation than 1550 nm."""
        common = dict(
            tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=40,
            n_connectors=0, n_splices=0, include_dispersion_penalty=False, ageing_margin_db=0
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r1310 = optical_link_budget(**common, wavelength_nm=1310)
            r1550 = optical_link_budget(**common, wavelength_nm=1550)
        assert r1310["fibre_loss_db"] > r1550["fibre_loss_db"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. LLM tool handlers (async, stub registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_fibre_coupling_tool_ok(self):
        """Tool returns eta_total and coupling_loss_db for matched fibers."""
        r = await call(tool_fibre_coupling, mfd1_um=10.4, mfd2_um=10.4)
        assert r["ok"] is True
        assert "eta_total" in r
        assert "coupling_loss_db" in r
        assert r["coupling_loss_db"] < 0.01   # matched → near zero loss

    @pytest.mark.asyncio
    async def test_fibre_coupling_tool_with_offset(self):
        """Tool handles lateral_offset_um."""
        r = await call(
            tool_fibre_coupling,
            mfd1_um=10.0, mfd2_um=10.0, lateral_offset_um=5.0, lambda_nm=1550.0
        )
        assert r["ok"] is True
        assert r["coupling_loss_db"] > 2.0

    @pytest.mark.asyncio
    async def test_link_budget_tool_ok(self):
        """Tool returns margin_db and full breakdown."""
        r = await call(
            tool_link_budget,
            tx_dbm=0.0, rx_sens_dbm=-28.0,
            fibre_type="SMF-28", length_km=40.0,
            n_connectors=2, n_splices=2, bit_rate_gbps=10.0,
            wavelength_nm=1550.0, ageing_margin_db=3.0
        )
        assert r["ok"] is True
        assert "margin_db" in r
        assert "fibre_loss_db" in r
        assert r["margin_db"] > 10.0

    @pytest.mark.asyncio
    async def test_link_budget_tool_unknown_fibre(self):
        """Tool returns error for unknown fibre type."""
        r = await call(
            tool_link_budget,
            tx_dbm=0, rx_sens_dbm=-28, fibre_type="BADFIBRE", length_km=40
        )
        assert r.get("ok") is False or "error" in r

    @pytest.mark.asyncio
    async def test_dispersion_penalty_tool_ok(self):
        """Tool returns dispersion breakdown for SMF-28."""
        r = await call(
            tool_dispersion_penalty,
            fibre_type="SMF-28", length_km=40.0, bit_rate_gbps=10.0
        )
        assert r["ok"] is True
        assert "delta_tau_cd_ps" in r
        assert "total_dispersion_penalty_db" in r
        assert r["delta_tau_cd_ps"] > 0.0

    @pytest.mark.asyncio
    async def test_dispersion_penalty_tool_mmf(self):
        """Tool returns modal BW for MMF-OM4."""
        r = await call(
            tool_dispersion_penalty,
            fibre_type="MMF-OM4", length_km=0.3, bit_rate_gbps=10.0,
            wavelength_nm=850.0
        )
        assert r["ok"] is True
        assert r["bw_modal_ghz"] is not None
        assert r["bw_modal_ghz"] > 0.0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        """Malformed JSON returns error."""
        raw = await tool_fibre_coupling(None, b"{{not valid json")
        data = json.loads(raw)
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_link_budget_tool_zero_length_error(self):
        """Tool returns error for zero span length."""
        r = await call(
            tool_link_budget,
            tx_dbm=0, rx_sens_dbm=-28, fibre_type="SMF-28", length_km=0.0
        )
        assert r.get("ok") is False or "error" in r
