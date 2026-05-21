"""
GK-129 — Helical thread profile oracle tests
=============================================

Pure-Python, hermetic.  No OCCT, no network, no DB.

Standards
---------
ISO 68-1 / ISO 261  — ISO metric 60° V-thread
ASME B1.5-1997      — ACME 29° trapezoidal thread
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom import iso_metric_thread, acme_thread


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOL = 1e-4   # dimensional tolerance (mm)


def _check_profile_shape(profile):
    """Assert profile is a non-empty list of (float, float) pairs."""
    assert isinstance(profile, list)
    assert len(profile) >= 2
    for pt in profile:
        assert len(pt) == 2, f"expected (x, y) pair, got {pt!r}"
        x, y = pt
        assert isinstance(x, float)
        assert isinstance(y, float)


# ---------------------------------------------------------------------------
# iso_metric_thread — M6×1 oracle (the canonical spec-test)
# ---------------------------------------------------------------------------

class TestIsoMetricM6x1:
    """M6×1 is the canonical fixture from the spec: pitch 1.0, depth ≈ 0.6134·p."""

    @pytest.fixture(autouse=True)
    def result(self):
        self.t = iso_metric_thread(nominal_d=6.0, pitch=1.0)

    def test_pitch(self):
        assert self.t["pitch"] == pytest.approx(1.0, abs=_TOL)

    def test_depth_iso_constant(self):
        """ISO thread depth = 0.6134 × pitch ± tol (spec oracle)."""
        expected = 0.6134 * 1.0
        assert self.t["depth"] == pytest.approx(expected, abs=_TOL)

    def test_crest_d_equals_nominal(self):
        assert self.t["crest_d"] == pytest.approx(6.0, abs=_TOL)

    def test_root_d_crest_minus_twice_depth(self):
        """root_d = crest_d − 2 × depth."""
        expected = 6.0 - 2.0 * self.t["depth"]
        assert self.t["root_d"] == pytest.approx(expected, abs=_TOL)

    def test_root_d_positive(self):
        assert self.t["root_d"] > 0.0

    def test_crest_to_root_height(self):
        """Radial height from root to crest = depth (half of dia diff)."""
        radial_height = (self.t["crest_d"] - self.t["root_d"]) / 2.0
        assert radial_height == pytest.approx(self.t["depth"], abs=_TOL)

    def test_profile_shape(self):
        _check_profile_shape(self.t["profile"])

    def test_profile_x_crest_equals_crest_r(self):
        """First and last profile points must sit at crest radius."""
        crest_r = self.t["crest_d"] / 2.0
        xs = [pt[0] for pt in self.t["profile"]]
        assert max(xs) == pytest.approx(crest_r, abs=_TOL)

    def test_profile_x_root_equals_root_r(self):
        """Minimum x in profile must equal root radius."""
        root_r = self.t["root_d"] / 2.0
        xs = [pt[0] for pt in self.t["profile"]]
        assert min(xs) == pytest.approx(root_r, abs=_TOL)

    def test_profile_y_spans_one_pitch(self):
        """Profile y coordinates span exactly [0, pitch]."""
        ys = [pt[1] for pt in self.t["profile"]]
        assert min(ys) == pytest.approx(0.0, abs=_TOL)
        assert max(ys) == pytest.approx(1.0, abs=_TOL)

    def test_return_keys(self):
        assert set(self.t.keys()) == {"profile", "pitch", "depth", "crest_d", "root_d"}


# ---------------------------------------------------------------------------
# iso_metric_thread — parametric sweep over common metric sizes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nominal_d,pitch", [
    (1.6, 0.35),   # M1.6 coarse
    (3.0, 0.50),   # M3 coarse
    (6.0, 1.00),   # M6 coarse
    (10.0, 1.50),  # M10 coarse
    (16.0, 2.00),  # M16 coarse
    (24.0, 3.00),  # M24 coarse
    (6.0, 0.75),   # M6 fine
    (10.0, 1.00),  # M10 fine
    (12.0, 1.50),  # M12 fine
])
def test_iso_depth_formula_parametric(nominal_d, pitch):
    """depth = 0.6134 × pitch for all standard metric threads."""
    t = iso_metric_thread(nominal_d, pitch)
    assert t["depth"] == pytest.approx(0.6134 * pitch, abs=_TOL), (
        f"M{nominal_d}×{pitch}: depth={t['depth']}, expected {0.6134 * pitch}"
    )


@pytest.mark.parametrize("nominal_d,pitch", [
    (6.0, 1.00),
    (10.0, 1.50),
    (16.0, 2.00),
])
def test_iso_root_d_parametric(nominal_d, pitch):
    """root_d = nominal_d − 2 × 0.6134 × pitch (ISO 68-1)."""
    t = iso_metric_thread(nominal_d, pitch)
    expected_root = nominal_d - 2.0 * 0.6134 * pitch
    assert t["root_d"] == pytest.approx(expected_root, abs=_TOL)


@pytest.mark.parametrize("nominal_d,pitch", [
    (6.0, 1.00),
    (10.0, 1.50),
])
def test_iso_profile_y_spans_pitch(nominal_d, pitch):
    """Profile y spans exactly [0, pitch] for any standard size."""
    t = iso_metric_thread(nominal_d, pitch)
    ys = [pt[1] for pt in t["profile"]]
    assert min(ys) == pytest.approx(0.0, abs=_TOL)
    assert max(ys) == pytest.approx(pitch, abs=_TOL)


# ---------------------------------------------------------------------------
# iso_metric_thread — error handling
# ---------------------------------------------------------------------------

def test_iso_zero_nominal_d_raises():
    with pytest.raises(ValueError, match="nominal_d"):
        iso_metric_thread(0.0, 1.0)


def test_iso_negative_nominal_d_raises():
    with pytest.raises(ValueError, match="nominal_d"):
        iso_metric_thread(-6.0, 1.0)


def test_iso_zero_pitch_raises():
    with pytest.raises(ValueError, match="pitch"):
        iso_metric_thread(6.0, 0.0)


def test_iso_negative_pitch_raises():
    with pytest.raises(ValueError, match="pitch"):
        iso_metric_thread(6.0, -1.0)


# ---------------------------------------------------------------------------
# acme_thread — basic oracle
# ---------------------------------------------------------------------------

class TestAcmeBasic:
    """ACME 29°: depth = 0.5 × pitch, 14.5° flanks."""

    @pytest.fixture(autouse=True)
    def result(self):
        # 1-inch ACME (25.4 mm nominal), 5 TPI → pitch = 5.08 mm
        self.t = acme_thread(nominal_d=25.4, pitch=5.08)

    def test_pitch(self):
        assert self.t["pitch"] == pytest.approx(5.08, abs=_TOL)

    def test_depth_half_pitch(self):
        """ACME depth = 0.5 × pitch (ASME B1.5)."""
        assert self.t["depth"] == pytest.approx(0.5 * 5.08, abs=_TOL)

    def test_crest_d(self):
        assert self.t["crest_d"] == pytest.approx(25.4, abs=_TOL)

    def test_root_d(self):
        expected = 25.4 - 2.0 * (0.5 * 5.08)
        assert self.t["root_d"] == pytest.approx(expected, abs=_TOL)

    def test_root_d_positive(self):
        assert self.t["root_d"] > 0.0

    def test_profile_shape(self):
        _check_profile_shape(self.t["profile"])

    def test_profile_y_spans_pitch(self):
        ys = [pt[1] for pt in self.t["profile"]]
        assert min(ys) == pytest.approx(0.0, abs=_TOL)
        assert max(ys) == pytest.approx(5.08, abs=_TOL)

    def test_return_keys(self):
        assert set(self.t.keys()) == {"profile", "pitch", "depth", "crest_d", "root_d"}


@pytest.mark.parametrize("nominal_d,pitch", [
    (12.7, 2.54),   # 0.5″ × 10 TPI
    (25.4, 5.08),   # 1″ × 5 TPI
    (50.8, 8.47),   # 2″ × 3 TPI
])
def test_acme_depth_half_pitch_parametric(nominal_d, pitch):
    t = acme_thread(nominal_d, pitch)
    assert t["depth"] == pytest.approx(0.5 * pitch, abs=_TOL)


# ---------------------------------------------------------------------------
# acme_thread — error handling
# ---------------------------------------------------------------------------

def test_acme_zero_nominal_d_raises():
    with pytest.raises(ValueError, match="nominal_d"):
        acme_thread(0.0, 2.0)


def test_acme_negative_pitch_raises():
    with pytest.raises(ValueError, match="pitch"):
        acme_thread(25.4, -1.0)


# ---------------------------------------------------------------------------
# Idempotency: calling twice gives same result
# ---------------------------------------------------------------------------

def test_iso_idempotent():
    r1 = iso_metric_thread(6.0, 1.0)
    r2 = iso_metric_thread(6.0, 1.0)
    assert r1 == r2


def test_acme_idempotent():
    r1 = acme_thread(25.4, 5.08)
    r2 = acme_thread(25.4, 5.08)
    assert r1 == r2


# ---------------------------------------------------------------------------
# Public API reachable from geom.__init__
# ---------------------------------------------------------------------------

def test_public_import():
    """iso_metric_thread and acme_thread must be importable from geom."""
    from kerf_cad_core.geom import iso_metric_thread as f1, acme_thread as f2
    assert callable(f1)
    assert callable(f2)
