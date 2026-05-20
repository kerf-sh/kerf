"""
T-25: Mech — gears / gearbox composite feature tests.

Spec: 25 gear pair specs; module / addendum / dedendum vs AGMA;
      mesh clash check.
Scope: gears.py + gearbox/ + wormbevel/ mesh.

Tests cover:
  - 25 explicit gear-pair parameter combinations (varying module, z1, z2, alpha, x)
  - AGMA standard addendum ha = 1.0·m, dedendum hf = 1.25·m (ISO 21771 Table 2)
  - Mesh clash / contact-ratio checks
  - Boundary inputs (min/max teeth, pressure-angle edges)
  - Malformed / invalid inputs
  - Idempotency (same inputs → same outputs)
  - Cross-check: gear_spur addendum/dedendum agrees with gear_pair_check diameters

Pure-Python: no OCC, no DB, no ProjectCtx side-effects.
Reference: ISO 21771:2007; AGMA 2101-D04.
Author: imranparuk.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.gears import (
    _HA_COEFF,
    _HF_COEFF,
    _spur_geometry,
    run_gear_spur,
    run_gear_pair_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        class _Stub:
            pass
        return _Stub()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _spur(**kwargs):
    ctx = _fake_ctx()
    defaults = {"module": 2.0, "teeth": 20, "pressure_angle_deg": 20.0}
    defaults.update(kwargs)
    raw = _run(run_gear_spur(ctx, json.dumps(defaults).encode()))
    return json.loads(raw)


def _pair(**kwargs):
    ctx = _fake_ctx()
    defaults = {
        "module": 2.0,
        "teeth_1": 20,
        "teeth_2": 40,
        "pressure_angle_deg": 20.0,
    }
    defaults.update(kwargs)
    raw = _run(run_gear_pair_check(ctx, json.dumps(defaults).encode()))
    return json.loads(raw)


# ---------------------------------------------------------------------------
# AGMA standard parameters (ISO 21771 Table 2)
# ---------------------------------------------------------------------------
# ha* = 1.0  (addendum coefficient)
# hf* = 1.25 (dedendum coefficient)
_HA_STD = 1.0
_HF_STD = 1.25


# ===========================================================================
# 1. 25 gear-pair specifications — module / addendum / dedendum vs AGMA
# ===========================================================================

# Each entry: (module, z1, z2, alpha_deg, x1, x2)
# Selected to cover a range of sizes, ratios, and profile-shift scenarios.
GEAR_PAIR_SPECS = [
    # ISO std module series × variety of ratios
    (1.0,  17, 17,  20.0,  0.0,  0.0),   # 1 — m1, equal teeth, boundary z
    (1.0,  20, 40,  20.0,  0.0,  0.0),   # 2 — m1, 2:1 ratio
    (1.25, 18, 36,  20.0,  0.0,  0.0),   # 3 — m1.25
    (1.5,  20, 60,  20.0,  0.0,  0.0),   # 4 — m1.5, 3:1 ratio
    (2.0,  14, 28,  20.0,  0.3,  0.0),   # 5 — m2, low-z pinion, profile shift
    (2.0,  17, 34,  20.0,  0.0,  0.0),   # 6 — m2, 2:1, z=17 boundary (undercut edge)
    (2.0,  20, 40,  20.0,  0.0,  0.0),   # 7 — m2, standard pair
    (2.0,  25, 25,  20.0,  0.0,  0.0),   # 8 — m2, unit ratio
    (2.5,  20, 80,  20.0,  0.0,  0.0),   # 9 — m2.5, 4:1 ratio
    (3.0,  18, 72,  20.0,  0.0,  0.0),   # 10 — m3, 4:1 ratio
    (3.0,  24, 48,  20.0,  0.0,  0.0),   # 11 — m3, 2:1 ratio
    (4.0,  20, 40,  20.0,  0.0,  0.0),   # 12 — m4
    (4.0,  14, 56,  20.0,  0.4,  0.0),   # 13 — m4, 4:1, profile-shift pinion
    (5.0,  17, 51,  20.0,  0.0,  0.0),   # 14 — m5, 3:1
    (5.0,  20, 100, 20.0,  0.0,  0.0),   # 15 — m5, 5:1 ratio
    (6.0,  20, 60,  20.0,  0.0,  0.0),   # 16 — m6, 3:1
    (8.0,  18, 72,  20.0,  0.0,  0.0),   # 17 — m8, 4:1
    (10.0, 20, 40,  20.0,  0.0,  0.0),   # 18 — m10
    # Non-standard pressure angles
    (2.0,  20, 40,  14.5,  0.0,  0.0),   # 19 — α=14.5° (legacy AGMA)
    (2.0,  20, 40,  25.0,  0.0,  0.0),   # 20 — α=25° (high-angle)
    # Profile-shifted pairs
    (2.0,  12, 36,  20.0,  0.5,  0.0),   # 21 — x1>0 to avoid undercut at z=12
    (2.0,  12, 36,  20.0,  0.5, -0.1),   # 22 — x1+x2 != 0 (operating shift)
    (2.0,  20, 40,  20.0,  0.2,  0.2),   # 23 — positive shift both gears
    (3.0,  20, 40,  20.0, -0.1, -0.1),   # 24 — negative shift both gears (tighter centre)
    (2.0,  30, 90,  20.0,  0.0,  0.0),   # 25 — m2, 3:1, large gear
]

assert len(GEAR_PAIR_SPECS) == 25, "Spec requires exactly 25 pair combinations"


class TestGearPairSpecs:
    """Parametric sweep: verify all 25 pair specs return ok=True and sane geometry."""

    @pytest.mark.parametrize("spec", GEAR_PAIR_SPECS)
    def test_pair_ok(self, spec):
        m, z1, z2, alpha, x1, x2 = spec
        r = _pair(module=m, teeth_1=z1, teeth_2=z2,
                  pressure_angle_deg=alpha,
                  profile_shift_1=x1, profile_shift_2=x2)
        assert r.get("ok") is True, f"spec {spec}: {r}"

    @pytest.mark.parametrize("spec", GEAR_PAIR_SPECS)
    def test_pair_gear_ratio(self, spec):
        """Gear ratio = z2 / z1 for every pair (ISO 21771 §3.12)."""
        m, z1, z2, alpha, x1, x2 = spec
        r = _pair(module=m, teeth_1=z1, teeth_2=z2,
                  pressure_angle_deg=alpha,
                  profile_shift_1=x1, profile_shift_2=x2)
        assert r.get("ok") is True
        assert r["gear_ratio"] == pytest.approx(z2 / z1, rel=1e-9)

    @pytest.mark.parametrize("spec", GEAR_PAIR_SPECS)
    def test_pair_centre_distance_positive(self, spec):
        """Centre distance must be > 0."""
        m, z1, z2, alpha, x1, x2 = spec
        r = _pair(module=m, teeth_1=z1, teeth_2=z2,
                  pressure_angle_deg=alpha,
                  profile_shift_1=x1, profile_shift_2=x2)
        assert r.get("ok") is True
        assert r["centre_distance"] > 0.0

    @pytest.mark.parametrize("spec", GEAR_PAIR_SPECS)
    def test_pair_contact_ratio_positive(self, spec):
        """Contact ratio must be > 0 for all valid pairs."""
        m, z1, z2, alpha, x1, x2 = spec
        r = _pair(module=m, teeth_1=z1, teeth_2=z2,
                  pressure_angle_deg=alpha,
                  profile_shift_1=x1, profile_shift_2=x2)
        assert r.get("ok") is True
        assert r["contact_ratio"] > 0.0


# ===========================================================================
# 2. AGMA addendum / dedendum standard values (ISO 21771 Table 2)
# ===========================================================================

class TestAGMAAddendumDedendum:
    """Verify addendum ha = 1.0·m and dedendum hf = 1.25·m (AGMA/ISO standard)."""

    @pytest.mark.parametrize("m", [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0])
    def test_addendum_standard_module(self, m):
        """ha = ha* · m = 1.0 · m  (ISO 21771 §4.1, ha* = 1)."""
        r = _spur(module=m, teeth=20)
        assert r.get("ok") is True
        assert r["addendum"] == pytest.approx(_HA_STD * m, rel=1e-9), (
            f"m={m}: expected ha={_HA_STD * m}, got {r['addendum']}"
        )

    @pytest.mark.parametrize("m", [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0])
    def test_dedendum_standard_module(self, m):
        """hf = hf* · m = 1.25 · m  (ISO 21771 §4.1, hf* = 1.25)."""
        r = _spur(module=m, teeth=20)
        assert r.get("ok") is True
        assert r["dedendum"] == pytest.approx(_HF_STD * m, rel=1e-9), (
            f"m={m}: expected hf={_HF_STD * m}, got {r['dedendum']}"
        )

    @pytest.mark.parametrize("m", [1.0, 2.0, 3.0, 4.0, 5.0])
    def test_whole_depth_standard(self, m):
        """Whole depth h = ha + hf = (1.0 + 1.25)·m = 2.25·m."""
        r = _spur(module=m, teeth=20)
        assert r.get("ok") is True
        assert r["whole_depth"] == pytest.approx(2.25 * m, rel=1e-9)

    @pytest.mark.parametrize("m", [1.0, 2.0, 3.0])
    def test_tip_diameter_from_addendum(self, m):
        """da = d + 2·ha = m·z + 2·m = m·(z+2) for x=0."""
        z = 20
        r = _spur(module=m, teeth=z, profile_shift=0.0)
        assert r.get("ok") is True
        expected_da = m * (z + 2 * _HA_STD)
        assert r["tip_diameter"] == pytest.approx(expected_da, rel=1e-9)

    @pytest.mark.parametrize("m", [1.0, 2.0, 3.0])
    def test_root_diameter_from_dedendum(self, m):
        """df = d - 2·hf = m·z - 2·1.25·m = m·(z - 2.5) for x=0."""
        z = 20
        r = _spur(module=m, teeth=z, profile_shift=0.0)
        assert r.get("ok") is True
        expected_df = m * z - 2.0 * _HF_STD * m
        assert r["root_diameter"] == pytest.approx(expected_df, rel=1e-9)

    def test_addendum_increases_with_positive_profile_shift(self):
        """Profile shift x > 0 increases tip diameter (addendum grows)."""
        r0 = _spur(module=2.0, teeth=20, profile_shift=0.0)
        rp = _spur(module=2.0, teeth=20, profile_shift=0.5)
        assert r0.get("ok") is True
        assert rp.get("ok") is True
        assert rp["tip_diameter"] > r0["tip_diameter"]

    def test_dedendum_decreases_with_positive_profile_shift(self):
        """Profile shift x > 0 reduces dedendum (root moves inward)."""
        r0 = _spur(module=2.0, teeth=20, profile_shift=0.0)
        rp = _spur(module=2.0, teeth=20, profile_shift=0.5)
        assert r0.get("ok") is True
        assert rp.get("ok") is True
        assert rp["dedendum"] < r0["dedendum"]

    def test_addendum_coefficient_constant(self):
        """Imported _HA_COEFF == 1.0 (AGMA/ISO standard)."""
        assert _HA_COEFF == pytest.approx(1.0, abs=1e-12)

    def test_dedendum_coefficient_constant(self):
        """Imported _HF_COEFF == 1.25 (AGMA/ISO standard)."""
        assert _HF_COEFF == pytest.approx(1.25, abs=1e-12)

    @pytest.mark.parametrize("m,z", [(1.0, 20), (2.0, 30), (3.0, 40), (5.0, 17)])
    def test_addendum_lt_dedendum(self, m, z):
        """Standard gears always have ha < hf (more dedendum clearance)."""
        r = _spur(module=m, teeth=z)
        assert r.get("ok") is True
        assert r["addendum"] < r["dedendum"]

    def test_pair_addendum_agrees_with_spur(self):
        """gear_pair_check tip_diameter for gear 1 == gear_spur tip_diameter."""
        m, z1, z2 = 2.0, 20, 40
        spur = _spur(module=m, teeth=z1, profile_shift=0.0)
        pair = _pair(module=m, teeth_1=z1, teeth_2=z2,
                     profile_shift_1=0.0, profile_shift_2=0.0)
        assert spur.get("ok") is True
        assert pair.get("ok") is True
        assert spur["tip_diameter"] == pytest.approx(
            pair["gear_1"]["tip_diameter"], rel=1e-6
        )

    def test_pair_root_diameter_agrees_with_spur(self):
        """gear_pair_check root_diameter for gear 2 == gear_spur root_diameter."""
        m, z1, z2 = 2.0, 20, 40
        spur = _spur(module=m, teeth=z2, profile_shift=0.0)
        pair = _pair(module=m, teeth_1=z1, teeth_2=z2,
                     profile_shift_1=0.0, profile_shift_2=0.0)
        assert spur.get("ok") is True
        assert pair.get("ok") is True
        assert spur["root_diameter"] == pytest.approx(
            pair["gear_2"]["root_diameter"], rel=1e-6
        )


# ===========================================================================
# 3. Mesh clash / contact-ratio checks
# ===========================================================================

class TestMeshClashCheck:
    """Verify contact ratio logic and interference warnings."""

    def test_standard_pair_contact_ratio_above_one(self):
        """Standard m=2 pair z=20/40 at α=20° must have εα > 1.0."""
        r = _pair(module=2.0, teeth_1=20, teeth_2=40, pressure_angle_deg=20.0)
        assert r.get("ok") is True
        assert r["contact_ratio"] > 1.0

    def test_large_teeth_contact_ratio_above_1_5(self):
        """z=50/50 at α=20° should give εα ≥ 1.5 (healthy overlap)."""
        r = _pair(module=2.0, teeth_1=50, teeth_2=50, pressure_angle_deg=20.0)
        assert r.get("ok") is True
        assert r["contact_ratio"] >= 1.5

    def test_contact_ratio_increases_with_tooth_count(self):
        """More teeth → longer addendum reach → higher εα."""
        r_small = _pair(module=2.0, teeth_1=20, teeth_2=20)
        r_large = _pair(module=2.0, teeth_1=60, teeth_2=60)
        assert r_small.get("ok") is True
        assert r_large.get("ok") is True
        assert r_large["contact_ratio"] > r_small["contact_ratio"]

    def test_contact_ratio_at_14_5_degrees(self):
        """Legacy α=14.5° pair should still give εα > 1.0 for z=20/40."""
        r = _pair(module=2.0, teeth_1=20, teeth_2=40, pressure_angle_deg=14.5)
        assert r.get("ok") is True
        assert r["contact_ratio"] > 1.0

    def test_low_teeth_pinion_undercut_warning(self):
        """z1=10 at α=20° with no shift triggers undercut/profile-shift warning."""
        r = _pair(module=2.0, teeth_1=10, teeth_2=40,
                  profile_shift_1=0.0, profile_shift_2=0.0)
        assert r.get("ok") is True
        w = " ".join(r.get("warnings", []))
        assert "undercut" in w.lower() or "profile shift" in w.lower()

    def test_profile_shift_clears_undercut_warning(self):
        """Applying sufficient x1 > 0 removes the root-circle undercut warning.

        For z1=10 at α=20°:  x_min = z1*(cos α − 1)/2 + 1.25 ≈ 0.949.
        Using x1=1.1 (> x_min) ensures r_f1 ≥ r_b1.
        z2=42 is used because z2=40 is borderline (r_f < r_b); z≥42 is safe.
        """
        r = _pair(module=2.0, teeth_1=10, teeth_2=42,
                  profile_shift_1=1.1, profile_shift_2=0.0)
        assert r.get("ok") is True
        w = " ".join(r.get("warnings", []))
        # Root-circle undercut (r_f < r_b) should not appear with sufficient shift
        assert "undercut risk" not in w.lower()

    def test_no_undercut_warning_for_safe_teeth_count(self):
        """z1=42 at α=20° has no root-circle undercut (r_f ≥ r_b)."""
        r = _pair(module=2.0, teeth_1=42, teeth_2=42)
        assert r.get("ok") is True
        w = " ".join(r.get("warnings", []))
        assert "undercut risk" not in w.lower()

    def test_standard_centre_distance_formula(self):
        """For x1=x2=0: a_w = m·(z1+z2)/2  (ISO 21771 §10.1)."""
        m, z1, z2 = 3.0, 18, 36
        r = _pair(module=m, teeth_1=z1, teeth_2=z2,
                  profile_shift_1=0.0, profile_shift_2=0.0)
        assert r.get("ok") is True
        expected = m * (z1 + z2) / 2
        assert r["centre_distance"] == pytest.approx(expected, rel=1e-6)

    def test_positive_shift_increases_centre_distance(self):
        """x1 + x2 > 0 → operating centre distance > standard centre distance."""
        r = _pair(module=2.0, teeth_1=20, teeth_2=40,
                  profile_shift_1=0.4, profile_shift_2=0.0)
        assert r.get("ok") is True
        assert r["centre_distance"] > r["standard_centre_distance"]

    def test_negative_shift_reduces_centre_distance(self):
        """x1 + x2 < 0 → operating centre distance < standard centre distance."""
        r = _pair(module=2.0, teeth_1=20, teeth_2=40,
                  profile_shift_1=-0.2, profile_shift_2=-0.2)
        assert r.get("ok") is True
        assert r["centre_distance"] < r["standard_centre_distance"]

    def test_no_shift_operating_angle_equals_reference_angle(self):
        """x1=x2=0 → α_w == α  (operating pressure angle = reference)."""
        alpha = 20.0
        r = _pair(module=2.0, teeth_1=20, teeth_2=40,
                  pressure_angle_deg=alpha,
                  profile_shift_1=0.0, profile_shift_2=0.0)
        assert r.get("ok") is True
        assert r["operating_pressure_angle_deg"] == pytest.approx(alpha, abs=1e-4)

    def test_positive_shift_increases_operating_angle(self):
        """x1 + x2 > 0 → α_w > α  (ISO 21771 §10.1)."""
        alpha = 20.0
        r = _pair(module=2.0, teeth_1=20, teeth_2=40,
                  pressure_angle_deg=alpha,
                  profile_shift_1=0.4, profile_shift_2=0.0)
        assert r.get("ok") is True
        assert r["operating_pressure_angle_deg"] > alpha

    def test_gear_ratio_in_pair_result(self):
        """gear_ratio field present and equals z2/z1."""
        r = _pair(module=2.0, teeth_1=15, teeth_2=45)
        assert r.get("ok") is True
        assert r["gear_ratio"] == pytest.approx(3.0, rel=1e-9)

    def test_gear_data_sub_dicts_present(self):
        """Result must contain gear_1 and gear_2 geometry sub-dicts."""
        r = _pair(module=2.0, teeth_1=20, teeth_2=40)
        assert r.get("ok") is True
        for sub in ("gear_1", "gear_2"):
            assert sub in r, f"missing {sub}"
            for key in ("pitch_diameter", "base_diameter",
                        "tip_diameter", "root_diameter"):
                assert key in r[sub], f"missing {sub}.{key}"


# ===========================================================================
# 4. Boundary inputs
# ===========================================================================

class TestGearPairBoundaries:

    def test_minimum_valid_teeth(self):
        """z=3 is the minimum valid tooth count."""
        r = _pair(module=2.0, teeth_1=3, teeth_2=3)
        assert r.get("ok") is True

    def test_exactly_at_pressure_angle_lower_bound_is_invalid(self):
        """α=10.0° exactly is excluded → ok=False."""
        r = _pair(pressure_angle_deg=10.0)
        assert r.get("ok") is False

    def test_exactly_at_pressure_angle_upper_bound_is_invalid(self):
        """α=30.0° exactly is excluded → ok=False."""
        r = _pair(pressure_angle_deg=30.0)
        assert r.get("ok") is False

    def test_pressure_angle_just_above_lower_bound(self):
        """α=10.01° is within the open interval — must succeed."""
        r = _pair(pressure_angle_deg=10.01)
        assert r.get("ok") is True

    def test_pressure_angle_just_below_upper_bound(self):
        """α=29.99° is within the open interval — must succeed."""
        r = _pair(pressure_angle_deg=29.99)
        assert r.get("ok") is True

    def test_very_large_teeth_count(self):
        """z=200 is allowed — no overflow or crash."""
        r = _pair(module=1.0, teeth_1=100, teeth_2=200)
        assert r.get("ok") is True

    def test_unit_gear_ratio(self):
        """z1 == z2 → gear_ratio == 1.0."""
        r = _pair(module=2.0, teeth_1=30, teeth_2=30)
        assert r.get("ok") is True
        assert r["gear_ratio"] == pytest.approx(1.0, rel=1e-9)

    def test_large_gear_ratio(self):
        """High step-down ratio z2/z1 = 8 should succeed."""
        r = _pair(module=2.0, teeth_1=10, teeth_2=80)
        assert r.get("ok") is True
        assert r["gear_ratio"] == pytest.approx(8.0, rel=1e-9)


# ===========================================================================
# 5. Malformed / invalid inputs
# ===========================================================================

class TestGearPairMalformed:

    def test_module_zero_invalid(self):
        r = _pair(module=0)
        assert r.get("ok") is False

    def test_module_negative_invalid(self):
        r = _pair(module=-2.0)
        assert r.get("ok") is False

    def test_teeth_1_below_minimum(self):
        r = _pair(teeth_1=2)
        assert r.get("ok") is False
        assert any("teeth_1" in e or "z" in e for e in r.get("errors", []))

    def test_teeth_2_below_minimum(self):
        r = _pair(teeth_2=2)
        assert r.get("ok") is False

    def test_alpha_too_low(self):
        r = _pair(pressure_angle_deg=5.0)
        assert r.get("ok") is False

    def test_alpha_too_high(self):
        r = _pair(pressure_angle_deg=45.0)
        assert r.get("ok") is False

    def test_multiple_errors_collected(self):
        """Both module=0 and teeth_1=1 should appear as multiple errors."""
        r = _pair(module=0, teeth_1=1)
        assert r.get("ok") is False
        assert len(r.get("errors", [])) >= 2

    def test_invalid_json_returns_error_payload(self):
        ctx = _fake_ctx()
        raw = _run(run_gear_pair_check(ctx, b"not-valid-json"))
        result = json.loads(raw)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_empty_json_object(self):
        """Empty {} → module=0 → invalid."""
        ctx = _fake_ctx()
        raw = _run(run_gear_pair_check(ctx, b"{}"))
        result = json.loads(raw)
        assert result.get("ok") is False

    def test_spur_invalid_json_returns_error_payload(self):
        ctx = _fake_ctx()
        raw = _run(run_gear_spur(ctx, b"{bad:json"))
        result = json.loads(raw)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"


# ===========================================================================
# 6. Idempotency
# ===========================================================================

class TestGearPairIdempotency:
    """Same inputs must always produce bit-identical outputs."""

    @pytest.mark.parametrize("spec", [
        (2.0, 20, 40, 20.0, 0.0, 0.0),
        (3.0, 18, 54, 20.0, 0.0, 0.0),
        (1.0, 17, 34, 20.0, 0.3, 0.0),
    ])
    def test_pair_check_idempotent(self, spec):
        m, z1, z2, alpha, x1, x2 = spec
        kwargs = dict(module=m, teeth_1=z1, teeth_2=z2,
                      pressure_angle_deg=alpha,
                      profile_shift_1=x1, profile_shift_2=x2)
        r1 = _pair(**kwargs)
        r2 = _pair(**kwargs)
        assert r1 == r2

    @pytest.mark.parametrize("m,z", [(2.0, 20), (3.0, 30), (1.0, 17)])
    def test_spur_geometry_idempotent(self, m, z):
        r1 = _spur_geometry(m, z, 20.0)
        r2 = _spur_geometry(m, z, 20.0)
        assert r1 == r2

    def test_spur_runner_idempotent(self):
        kwargs = dict(module=2.0, teeth=25, pressure_angle_deg=20.0)
        ctx = _fake_ctx()
        r1 = json.loads(_run(run_gear_spur(ctx, json.dumps(kwargs).encode())))
        r2 = json.loads(_run(run_gear_spur(ctx, json.dumps(kwargs).encode())))
        assert r1 == r2
