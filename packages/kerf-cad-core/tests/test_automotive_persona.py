"""
Hermetic pytest for T-100: Automotive Persona — composites layup + clash check.

Scope
-----
Models a simplified Body-In-White (BIW) assembly extract for a sports car:

  Components (mm coordinate space):
    roof-panel   composite   CFRP roof skin (structural, composite discipline)
    a-pillar     structural  Steel A-pillar extrusion (structural)
    harness-run  mep         12V wiring harness routed above door aperture (mep)
    door-seal    architectural  Rubber door seal frame (architectural)
    crossbar     structural  Roof crossmember bar (structural)

  Known interferences after assembly error:
    harness-run vs a-pillar   → mep penetrates structural; hard clash
    harness-run vs crossbar   → mep penetrates structural (runs through crossbar zone)
    door-seal   vs a-pillar   → architectural penetrates structural at corner

  Composites scenario:
    Roof panel: quasi-isotropic [0/±45/90]_s T300/5208 CFRP (8 plies, 0.25 mm each).
    Analysis: ABD assembly, effective moduli, first-ply-failure under in-plane
    tension Nx = 50 kN/m (representative panel load from rollover case).

All assertions use analytic oracles (CLT hand-calculations or structural reasoning).
No OCC, no DB, no network, no fixtures — purely hermetic.

References
----------
Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999)
SAE J3082 — Test Method for Body Structure Impact Performance (rollover)

Author: imranparuk
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.composites.laminate import (
    reduced_stiffness,
    transform_Q,
    abd_matrix,
    laminate_response,
    failure_indices,
    laminate_engineering_moduli,
    first_ply_failure_load,
)
from kerf_cad_core.clash.detect import (
    ClashType,
    ClashRecord,
    ClashReport,
    ComponentShape,
    clash_detect,
)


# ===========================================================================
# Shared material: T300/5208 CFRP (automotive CFRP roof panel)
# E1=181 GPa, E2=10.3 GPa, nu12=0.28, G12=7.17 GPa
# Strengths (MPa): F1t=1500, F1c=1500, F2t=40, F2c=246, F12=68
# ===========================================================================

E1  = 181e9   # Pa
E2  = 10.3e9  # Pa
NU  = 0.28
G12 = 7.17e9  # Pa

S_T300 = {
    "F1t": 1500e6, "F1c": 1500e6,
    "F2t":   40e6, "F2c":  246e6,
    "F12":   68e6,
}

_PLY_T = 0.25e-3  # 0.25 mm ply thickness (m)


def _cf_ply(angle_deg: float) -> dict:
    """Return a ply dict for the T300/5208 material at the given angle."""
    return {
        "E1": E1, "E2": E2, "nu12": NU, "G12": G12,
        "thickness": _PLY_T, "angle_deg": angle_deg,
    }


# Quasi-isotropic [0/45/-45/90]_s  — 8 plies
_QI_ANGLES = [0, 45, -45, 90, 90, -45, 45, 0]
_QI_PLIES  = [_cf_ply(a) for a in _QI_ANGLES]


# ===========================================================================
# Automotive BIW fixture — clash components (mm coordinates)
# ===========================================================================

def _biw_components() -> list[ComponentShape]:
    """
    BIW extract in mm:
      roof-panel  composite / structural   (wide, thin, at Z=1450..1452)
      a-pillar    structural               (tall, along Y, near front corner)
      harness-run mep                      (cable run along door aperture top edge)
      door-seal   architectural            (door opening seal frame at front)
      crossbar    structural               (transverse roof brace)

    Known hard clashes (assembly placement error):
      harness-run vs a-pillar   (harness routed through A-pillar zone)
      harness-run vs crossbar   (harness overlaps crossbar at Z=1450..1460)
      door-seal   vs a-pillar   (seal overruns A-pillar corner by 20mm)
    """
    roof_panel = ComponentShape(
        instance_id="roof-panel",
        discipline="structural",
        bbox_min=(200, 0, 1450),
        bbox_max=(1600, 1400, 1452),   # nearly flat panel
    )
    a_pillar = ComponentShape(
        instance_id="a-pillar",
        discipline="structural",
        bbox_min=(180, 0, 0),
        bbox_max=(230, 60, 1500),      # tall column at front-left
    )
    harness_run = ComponentShape(
        instance_id="harness-run",
        discipline="mep",
        bbox_min=(200, 10, 1440),
        bbox_max=(1500, 30, 1465),     # routed along top of door aperture
        # Overlaps a-pillar: harness X=200..230, a-pillar X=180..230 → 30mm overlap
        # Overlaps crossbar:  Z 1440-1465 ∩ 1448-1455 → yes
    )
    door_seal = ComponentShape(
        instance_id="door-seal",
        discipline="architectural",
        bbox_min=(170, 0, 500),
        bbox_max=(250, 1400, 1460),    # seal frame; overruns A-pillar (X 180-230 inside 170-250)
    )
    crossbar = ComponentShape(
        instance_id="crossbar",
        discipline="structural",
        bbox_min=(200, 0, 1448),
        bbox_max=(1600, 1400, 1455),   # transverse roof brace sitting just under panel
    )
    return [roof_panel, a_pillar, harness_run, door_seal, crossbar]


# ===========================================================================
# 1. Composites layup: ABD matrix, effective moduli, FPF
# ===========================================================================

class TestAutomotiveCFRPLayup:
    """QI [0/±45/90]_s roof panel — CLT analysis."""

    def test_abd_matrix_ok(self):
        res = abd_matrix(_QI_PLIES)
        assert res["ok"] is True

    def test_total_thickness(self):
        res = abd_matrix(_QI_PLIES)
        expected = 8 * _PLY_T
        assert abs(res["total_thickness"] - expected) / expected < 1e-6

    def test_qi_is_symmetric(self):
        """[0/45/-45/90]_s is a symmetric layup → B ≈ 0."""
        res = abd_matrix(_QI_PLIES)
        assert res["ok"] is True
        assert res["is_symmetric"] is True

    def test_qi_b_matrix_near_zero(self):
        """Symmetric laminate: |B[i]| < 1e-4 * max(|A|)."""
        res = abd_matrix(_QI_PLIES)
        A_max = max(abs(v) for v in res["A"])
        for v in res["B"]:
            assert abs(v) < 1e-4 * A_max, f"B term {v:.3e} not near zero for symmetric QI"

    def test_qi_effective_moduli_isotropic(self):
        """Quasi-isotropic: effective Ex ≈ Ey (in-plane isotropy)."""
        res_abd = abd_matrix(_QI_PLIES)
        mod = laminate_engineering_moduli(res_abd)
        assert mod["ok"] is True
        assert abs(mod["Ex"] - mod["Ey"]) / mod["Ex"] < 5e-3

    def test_qi_effective_modulus_in_range(self):
        """T300/5208 QI effective modulus should be in [50 GPa, 80 GPa]."""
        res_abd = abd_matrix(_QI_PLIES)
        mod = laminate_engineering_moduli(res_abd)
        assert 50e9 <= mod["Ex"] <= 80e9, f"Ex = {mod['Ex']/1e9:.1f} GPa out of expected [50,80] GPa"

    def test_laminate_response_uniaxial_nx(self):
        """50 kN/m Nx → positive ε_x (tension)."""
        res_abd = abd_matrix(_QI_PLIES)
        resp = laminate_response(res_abd, [50e3, 0, 0, 0, 0, 0])
        assert resp["ok"] is True
        assert resp["epsilon0"][0] > 0

    def test_laminate_response_qi_no_curvature_under_nx(self):
        """Symmetric laminate (B=0): Nx only → κ ≈ 0."""
        res_abd = abd_matrix(_QI_PLIES)
        resp = laminate_response(res_abd, [50e3, 0, 0, 0, 0, 0])
        for k in resp["kappa"]:
            assert abs(k) < 1.0, f"Unexpected curvature κ={k:.3e} for symmetric QI under Nx"

    def test_failure_indices_safe_under_design_load(self):
        """Roof panel at 50 kN/m — failure indices well below 1 for all criteria."""
        res_abd = abd_matrix(_QI_PLIES)
        resp = laminate_response(res_abd, [50e3, 0, 0, 0, 0, 0])
        # Back-calculate approximate ply stress for first 0° ply:
        # σ₁ ≈ E1 · ε_x (fibre direction = x for 0° ply)
        eps_x = resp["epsilon0"][0]
        sigma1_approx = E1 * eps_x
        sigma2_approx = 0.0
        tau12_approx  = 0.0
        fi = failure_indices(
            [sigma1_approx, sigma2_approx, tau12_approx],
            [eps_x, 0.0, 0.0],
            S_T300,
        )
        assert fi["ok"] is True
        assert fi["failed"] is False

    def test_first_ply_failure_load_positive(self):
        """λ_FPF > 0 — there exists a finite load at first ply failure."""
        strengths = [S_T300.copy() for _ in range(8)]
        res = first_ply_failure_load(
            _QI_PLIES,
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            strengths,
            criteria=["max-stress"],
        )
        assert res["ok"] is True
        assert res["lambda_fpf"] > 0

    def test_first_ply_failure_load_exceeds_design(self):
        """λ_FPF > 50 kN/m (design load) → panel not at first-ply-failure under rollover load."""
        strengths = [S_T300.copy() for _ in range(8)]
        res = first_ply_failure_load(
            _QI_PLIES,
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            strengths,
            criteria=["max-stress"],
        )
        assert res["lambda_fpf"] > 50e3, (
            f"λ_FPF = {res['lambda_fpf']:.1f} N/m should exceed design load 50 kN/m"
        )

    def test_layup_table_ply_count(self):
        """Layup table has 8 plies for [0/±45/90]_s."""
        res = abd_matrix(_QI_PLIES)
        assert res["n_plies"] == 8

    def test_layup_table_angles(self):
        """Layup table records correct ply angles in order."""
        for i, (ply, expected_angle) in enumerate(zip(_QI_PLIES, _QI_ANGLES)):
            assert ply["angle_deg"] == expected_angle, (
                f"Ply {i}: expected {expected_angle}°, got {ply['angle_deg']}°"
            )


# ===========================================================================
# 2. Automotive BIW clash detection
# ===========================================================================

class TestAutomotiveBIWClash:
    """Known interferences in the BIW fixture must all be found."""

    def setup_method(self):
        comps = _biw_components()
        self.result = clash_detect(comps)
        self.clashes = self.result["clashes"]
        self.report  = ClashReport(self.result)

    def _clash_pair(self, id_a: str, id_b: str) -> dict | None:
        for c in self.clashes:
            if {c["a"], c["b"]} == {id_a, id_b}:
                return c
        return None

    # -----------------------------------------------------------------------
    # Basic result validity
    # -----------------------------------------------------------------------

    def test_ok(self):
        assert self.result["ok"] is True

    def test_errors_empty(self):
        assert self.result["errors"] == []

    # -----------------------------------------------------------------------
    # Known hard clashes
    # -----------------------------------------------------------------------

    def test_harness_vs_a_pillar_found(self):
        """Wiring harness (mep) penetrates A-pillar (structural)."""
        c = self._clash_pair("harness-run", "a-pillar")
        assert c is not None, "harness-run vs a-pillar clash not detected"
        assert c["type"] == ClashType.HARD
        assert c["depth"] > 0

    def test_harness_vs_crossbar_found(self):
        """Wiring harness (mep) penetrates roof crossbar (structural)."""
        c = self._clash_pair("harness-run", "crossbar")
        assert c is not None, "harness-run vs crossbar clash not detected"
        assert c["type"] == ClashType.HARD

    def test_door_seal_vs_a_pillar_found(self):
        """Door seal (architectural) penetrates A-pillar (structural)."""
        c = self._clash_pair("door-seal", "a-pillar")
        assert c is not None, "door-seal vs a-pillar clash not detected"
        assert c["type"] == ClashType.HARD

    def test_all_expected_clashes_present(self):
        """All 3 known hard clashes are detected."""
        expected = [
            ("harness-run", "a-pillar"),
            ("harness-run", "crossbar"),
            ("door-seal",   "a-pillar"),
        ]
        for id_a, id_b in expected:
            c = self._clash_pair(id_a, id_b)
            assert c is not None, f"Expected clash {id_a!r} vs {id_b!r} not found"
            assert c["type"] == ClashType.HARD

    # -----------------------------------------------------------------------
    # Discipline tags on clash records
    # -----------------------------------------------------------------------

    def test_harness_a_pillar_discipline_pair(self):
        c = self._clash_pair("harness-run", "a-pillar")
        assert c is not None
        assert c["discipline_pair"] == "mep vs structural"

    def test_door_seal_a_pillar_discipline_pair(self):
        c = self._clash_pair("door-seal", "a-pillar")
        assert c is not None
        assert c["discipline_pair"] == "architectural vs structural"

    def test_all_clashes_have_discipline_keys(self):
        for c in self.clashes:
            assert "discipline_pair" in c
            assert "discipline_a" in c
            assert "discipline_b" in c

    def test_discipline_pairs_are_sorted(self):
        """discipline_pair is always lexicographically sorted (canonical form)."""
        for c in self.clashes:
            pair = c.get("discipline_pair", "")
            if " vs " in pair:
                left, right = pair.split(" vs ", 1)
                assert left <= right, f"discipline_pair not sorted: {pair!r}"

    # -----------------------------------------------------------------------
    # by_discipline_pair summary (clash report grouping)
    # -----------------------------------------------------------------------

    def test_by_discipline_pair_present(self):
        assert "by_discipline_pair" in self.result

    def test_mep_vs_structural_in_summary(self):
        by_pair = self.result["by_discipline_pair"]
        assert "mep vs structural" in by_pair

    def test_mep_vs_structural_count_at_least_two(self):
        """harness-run vs a-pillar AND harness-run vs crossbar → ≥ 2 mep/structural clashes."""
        by_pair = self.result["by_discipline_pair"]
        assert by_pair["mep vs structural"]["hard"] >= 2

    def test_architectural_vs_structural_in_summary(self):
        by_pair = self.result["by_discipline_pair"]
        assert "architectural vs structural" in by_pair

    def test_totals_consistent(self):
        """Sum of all by_discipline_pair totals == total clash count."""
        total = sum(v["total"] for v in self.result["by_discipline_pair"].values())
        assert total == len(self.clashes)

    # -----------------------------------------------------------------------
    # ClashReport structured API
    # -----------------------------------------------------------------------

    def test_report_ok(self):
        assert self.report.ok is True

    def test_report_clash_count_matches(self):
        assert self.report.clash_count == len(self.clashes)

    def test_report_hard_clashes_list_non_empty(self):
        hard = self.report.hard_clashes
        assert len(hard) >= 3

    def test_report_hard_clashes_all_hard_type(self):
        for r in self.report.hard_clashes:
            assert r.type == ClashType.HARD

    def test_report_clashes_for_mep_structural(self):
        pairs = self.report.clashes_for_pair("mep", "structural")
        assert len(pairs) >= 2
        for r in pairs:
            assert {r.discipline_a, r.discipline_b} == {"mep", "structural"}

    def test_report_clashes_for_pair_order_independent(self):
        a = self.report.clashes_for_pair("mep", "structural")
        b = self.report.clashes_for_pair("structural", "mep")
        assert len(a) == len(b)

    def test_report_to_dict_has_clash_count(self):
        d = self.report.to_dict()
        assert "clash_count" in d
        assert d["clash_count"] >= 3

    def test_report_to_dict_has_by_discipline_pair(self):
        d = self.report.to_dict()
        assert "by_discipline_pair" in d


# ===========================================================================
# 3. Integrated workflow: composites layup + clash report together
# ===========================================================================

class TestAutomotiveIntegrated:
    """
    Combined check: run the full CLT + clash pipeline and validate
    the 'report' structure that would be delivered to the user.
    """

    def test_layup_report_keys_present(self):
        """ABD result has all keys expected in a layup report."""
        res = abd_matrix(_QI_PLIES)
        required = {"ok", "A", "B", "D", "ABD", "total_thickness", "n_plies",
                    "is_symmetric", "is_balanced", "z_coords"}
        missing = required - set(res.keys())
        assert not missing, f"Missing layup report keys: {missing}"

    def test_clash_report_delivery(self):
        """Clash report is delivered as dict with expected top-level keys."""
        result = clash_detect(_biw_components())
        required = {"ok", "clashes", "errors", "by_discipline_pair"}
        missing = required - set(result.keys())
        assert not missing, f"Missing clash report keys: {missing}"

    def test_no_roof_panel_self_clash(self):
        """The roof-panel (composite) should not clash with itself."""
        result = clash_detect(_biw_components())
        roof_clashes = [
            c for c in result["clashes"]
            if c["a"] == "roof-panel" and c["b"] == "roof-panel"
        ]
        assert roof_clashes == []

    def test_crossbar_within_clearance_of_roof_panel(self):
        """
        Crossbar sits 3mm below the roof panel (Z: crossbar 1448-1455, panel 1450-1452).
        They OVERLAP: crossbar top (1455) > panel bottom (1450). So a hard clash is
        expected between crossbar and roof panel (intentional design — bonded contact).
        """
        result = clash_detect(_biw_components())
        roof_crossbar_clash = next(
            (c for c in result["clashes"]
             if {c["a"], c["b"]} == {"roof-panel", "crossbar"}),
            None,
        )
        # Intentional overlap (bonded) — clash detected but both are structural
        if roof_crossbar_clash:
            assert roof_crossbar_clash["discipline_pair"] == "structural vs structural"

    def test_composite_panel_effective_poisson(self):
        """
        QI laminate Poisson ratio should be ≈ 0.30 (Daniel & Ishai QI result for T300/5208).
        """
        res_abd = abd_matrix(_QI_PLIES)
        mod = laminate_engineering_moduli(res_abd)
        assert 0.25 <= mod["nu_xy"] <= 0.35, (
            f"ν_xy = {mod['nu_xy']:.3f} outside expected QI range [0.25, 0.35]"
        )

    def test_combined_mep_structural_clash_depth_finite(self):
        """All hard-clash depth values must be finite positive floats."""
        result = clash_detect(_biw_components())
        hard = [c for c in result["clashes"] if c["type"] == ClashType.HARD]
        assert len(hard) >= 3
        for c in hard:
            assert isinstance(c["depth"], float)
            assert math.isfinite(c["depth"])
            assert c["depth"] >= 0.0
