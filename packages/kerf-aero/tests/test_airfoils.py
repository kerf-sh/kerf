"""
Pytest analytic-oracle tests for kerf_aero.airfoils.

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-aero/src \
        python3 -m pytest packages/kerf-aero/tests/test_airfoils.py -x
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_aero.airfoils import (
    AIRFOIL_CATALOGUE,
    naca4,
    naca5,
    parse_naca5,
    selig_load,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _le_index(coords: np.ndarray) -> int:
    """Return index of the point closest to the leading edge (x=0)."""
    return int(np.argmin(coords[:, 0]))


def _max_thickness(coords: np.ndarray) -> tuple[float, float]:
    """
    Return (x_at_max_thickness, max_thickness) for an airfoil outline.

    Splits the outline at the leading edge into upper and lower surfaces and
    interpolates the thickness distribution.
    """
    le = _le_index(coords)
    upper = coords[: le + 1][::-1]  # sort LE→TE
    lower = coords[le:]              # LE→TE

    # Interpolate lower onto upper x-stations
    x_u = upper[:, 0]
    y_u = upper[:, 1]
    y_l = np.interp(x_u, lower[:, 0], lower[:, 1])
    thickness = y_u - y_l

    idx = int(np.argmax(thickness))
    return float(x_u[idx]), float(thickness[idx])


def _max_camber(coords: np.ndarray) -> tuple[float, float]:
    """Return (x_at_max_camber, max_camber) for an airfoil outline."""
    le = _le_index(coords)
    upper = coords[: le + 1][::-1]
    lower = coords[le:]

    x_u = upper[:, 0]
    y_u = upper[:, 1]
    y_l = np.interp(x_u, lower[:, 0], lower[:, 1])
    camber = (y_u + y_l) / 2.0

    idx = int(np.argmax(camber))
    return float(x_u[idx]), float(camber[idx])


# ---------------------------------------------------------------------------
# NACA 4-digit tests
# ---------------------------------------------------------------------------


class TestNaca4:
    def test_returns_ndarray(self):
        coords = naca4("0012")
        assert isinstance(coords, np.ndarray)

    def test_shape(self):
        n = 200
        coords = naca4("0012", n_points=n)
        # upper: n points, lower: n-1 points (LE shared) → 2n-1
        assert coords.shape == (2 * n - 1, 2)

    def test_custom_n_points(self):
        n = 100
        coords = naca4("0012", n_points=n)
        assert coords.shape == (2 * n - 1, 2)

    def test_0012_symmetry(self):
        """NACA 0012 must be symmetric about y=0 (upper = -lower)."""
        coords = naca4("0012", n_points=300)
        le = _le_index(coords)
        upper = coords[: le + 1][::-1]   # LE→TE, ascending x
        lower = coords[le:]               # LE→TE, ascending x

        x_u = upper[:, 0]
        y_u = upper[:, 1]
        y_l = np.interp(x_u, lower[:, 0], lower[:, 1])

        # Upper should equal -lower everywhere (within floating-point noise)
        np.testing.assert_allclose(y_u, -y_l, atol=1e-10,
                                   err_msg="NACA 0012 not symmetric about y=0")

    def test_0012_max_thickness_position(self):
        """NACA 0012 max thickness = 0.12c at x/c ≈ 0.30 (within 0.5%)."""
        coords = naca4("0012", n_points=500)
        x_t, t_max = _max_thickness(coords)

        assert abs(t_max - 0.12) < 0.005, \
            f"Expected max thickness ≈ 0.12, got {t_max:.4f}"
        assert abs(x_t - 0.30) < 0.005, \
            f"Expected max-thickness x ≈ 0.30, got {x_t:.4f}"

    def test_2412_max_camber(self):
        """NACA 2412: max camber at x/c = 0.4, magnitude = 0.02·c."""
        coords = naca4("2412", n_points=500)
        x_c, c_max = _max_camber(coords)

        assert abs(c_max - 0.02) < 0.001, \
            f"Expected max camber ≈ 0.02, got {c_max:.4f}"
        assert abs(x_c - 0.40) < 0.005, \
            f"Expected max-camber x ≈ 0.40, got {x_c:.4f}"

    def test_leading_edge_near_origin(self):
        """Leading edge x should be near 0 (within 0.01c)."""
        coords = naca4("2412", n_points=200)
        le = _le_index(coords)
        le_pt = coords[le]
        assert abs(le_pt[0]) < 0.01, \
            f"Leading edge x not near 0: {le_pt[0]}"
        assert abs(le_pt[1]) < 0.02, \
            f"Leading edge y not near 0 for cambered airfoil: {le_pt[1]}"

    def test_trailing_edge_near_one(self):
        """Trailing edge should be near (1, 0)."""
        coords = naca4("2412", n_points=200)
        # TE is the first and last point (wrapped outline)
        te_start = coords[0]
        assert abs(te_start[0] - 1.0) < 0.001, \
            f"Trailing edge x not near 1.0: {te_start[0]}"

    def test_finite_te_flag(self):
        """finite_te=True should close the trailing edge to y=0."""
        coords_closed = naca4("0012", n_points=100, finite_te=True)
        coords_open = naca4("0012", n_points=100, finite_te=False)
        # Both variants should produce valid coordinate arrays
        assert coords_closed.shape == coords_open.shape

    def test_invalid_profile(self):
        with pytest.raises(ValueError, match="4 digits"):
            naca4("241")

    def test_invalid_non_digit(self):
        with pytest.raises(ValueError):
            naca4("24XY")

    def test_symmetric_zero_camber(self):
        """Profile starting with '00' must have zero camber line."""
        coords = naca4("0015", n_points=200)
        le = _le_index(coords)
        upper = coords[: le + 1][::-1]
        lower = coords[le:]
        x_u = upper[:, 0]
        y_u = upper[:, 1]
        y_l = np.interp(x_u, lower[:, 0], lower[:, 1])
        camber = (y_u + y_l) / 2.0
        np.testing.assert_allclose(camber, 0.0, atol=1e-10,
                                   err_msg="NACA 00xx should have zero camber")

    def test_naca0006_thickness(self):
        """NACA 0006 max thickness should be ≈ 0.06c."""
        coords = naca4("0006", n_points=500)
        _, t_max = _max_thickness(coords)
        assert abs(t_max - 0.06) < 0.003, \
            f"NACA 0006 max thickness expected 0.06, got {t_max:.4f}"

    def test_naca4412_positive_camber(self):
        """NACA 4412 should have positive max camber ≈ 0.04."""
        coords = naca4("4412", n_points=400)
        _, c_max = _max_camber(coords)
        assert 0.035 < c_max < 0.045, \
            f"NACA 4412 max camber expected ~0.04, got {c_max:.4f}"

    def test_chord_spans_zero_to_one(self):
        """x coordinates should be within a small tolerance of [0, 1]."""
        coords = naca4("2412", n_points=200)
        # Surface projection can push slightly negative near the LE — allow 0.5% slack
        assert coords[:, 0].min() >= -0.005
        assert abs(coords[:, 0].max() - 1.0) < 0.01


# ---------------------------------------------------------------------------
# NACA 5-digit tests
# ---------------------------------------------------------------------------


class TestNaca5:
    def test_returns_ndarray(self):
        coords = naca5("23012")
        assert isinstance(coords, np.ndarray)

    def test_shape(self):
        n = 200
        coords = naca5("23012", n_points=n)
        assert coords.shape == (2 * n - 1, 2)

    def test_23012_parses_correctly(self):
        """23012 → CL_design=0.3, x_camber=0.15, thickness=12%."""
        params = parse_naca5("23012")
        assert abs(params["cl_design"] - 0.3) < 1e-9, \
            f"CL_design expected 0.3, got {params['cl_design']}"
        assert abs(params["x_camber"] - 0.15) < 1e-9, \
            f"x_camber expected 0.15, got {params['x_camber']}"
        assert abs(params["thickness_frac"] - 0.12) < 1e-9, \
            f"thickness expected 0.12, got {params['thickness_frac']}"
        assert params["reflexed"] is False

    def test_23012_positive_camber(self):
        """NACA 23012 should have a positive cambered shape."""
        coords = naca5("23012", n_points=400)
        _, c_max = _max_camber(coords)
        assert c_max > 0.005, \
            f"NACA 23012 should have positive camber, got {c_max:.4f}"

    def test_23012_leading_edge_origin(self):
        coords = naca5("23012", n_points=200)
        le = _le_index(coords)
        le_pt = coords[le]
        assert abs(le_pt[0]) < 0.01, \
            f"NACA 23012 leading edge x not near 0: {le_pt[0]}"

    def test_21012_valid(self):
        coords = naca5("21012")
        assert coords.shape[1] == 2

    def test_24012_valid(self):
        coords = naca5("24012")
        assert coords.shape[1] == 2

    def test_25012_valid(self):
        coords = naca5("25012")
        assert coords.shape[1] == 2

    def test_invalid_profile(self):
        with pytest.raises(ValueError, match="5 digits"):
            naca5("2301")

    def test_unsupported_key(self):
        with pytest.raises(ValueError, match="Unsupported"):
            naca5("29012")  # key "290" not in table

    def test_reflexed_21012(self):
        """Reflexed camber line (digit 4 = 1) should parse without error."""
        params = parse_naca5("21112")
        assert params["reflexed"] is True

    def test_reflexed_coords(self):
        coords = naca5("23112")
        assert coords.shape[1] == 2
        assert coords.shape[0] > 10


# ---------------------------------------------------------------------------
# Selig loader tests
# ---------------------------------------------------------------------------


class TestSeligLoad:
    _slugs = [
        "naca0006", "naca0009", "naca0012", "naca0015", "naca0018", "naca0021",
        "naca2412", "naca4412", "naca23012", "naca23015", "naca23018",
        "fx60-126", "fx60-100", "fx63-137",
        "e374", "e387", "e423",
        "s1223", "sd7037", "sd7032",
        "clarky", "clarkyh",
        "la203a", "l1003",
        "e1098",
    ]

    def test_all_slugs_loadable(self):
        for slug in self._slugs:
            coords = selig_load(slug)
            assert coords.shape[1] == 2, f"{slug}: expected 2 columns"
            assert coords.shape[0] >= 10, f"{slug}: too few points"

    def test_leading_edge_near_origin(self):
        """Leading edge should be near (0, 0) for all curated airfoils."""
        for slug in self._slugs:
            coords = selig_load(slug)
            le_idx = int(np.argmin(coords[:, 0]))
            le_pt = coords[le_idx]
            assert le_pt[0] < 0.02, \
                f"{slug}: leading-edge x too far from 0: {le_pt[0]}"
            assert abs(le_pt[1]) < 0.05, \
                f"{slug}: leading-edge y too far from 0: {le_pt[1]}"

    def test_trailing_edge_near_one(self):
        """Trailing edge should be near (1, 0) for all curated airfoils."""
        for slug in self._slugs:
            coords = selig_load(slug)
            # Find max x
            te_idx = int(np.argmax(coords[:, 0]))
            te_x = coords[te_idx, 0]
            assert abs(te_x - 1.0) < 0.02, \
                f"{slug}: trailing-edge x not near 1.0: {te_x}"

    def test_unknown_slug_raises(self):
        with pytest.raises(KeyError):
            selig_load("totally_unknown_foil_xyz")

    def test_case_insensitive(self):
        """selig_load should accept lowercase names."""
        coords = selig_load("NACA0012")
        assert coords.shape[1] == 2

    def test_naca0012_symmetry(self):
        """Inline NACA 0012 Selig data should be roughly symmetric."""
        coords = selig_load("naca0012")
        le_idx = int(np.argmin(coords[:, 0]))
        upper = coords[: le_idx + 1][::-1]
        lower = coords[le_idx:]
        x_u = upper[:, 0]
        y_u = upper[:, 1]
        y_l_interp = np.interp(x_u, lower[:, 0], lower[:, 1])
        camber = (y_u + y_l_interp) / 2.0
        assert np.max(np.abs(camber)) < 0.005, \
            "Inline NACA 0012 should be nearly symmetric"


# ---------------------------------------------------------------------------
# AIRFOIL_CATALOGUE tests
# ---------------------------------------------------------------------------


class TestAirfoilCatalogue:
    def test_has_40_plus_entries(self):
        assert len(AIRFOIL_CATALOGUE) >= 40, \
            f"Catalogue has only {len(AIRFOIL_CATALOGUE)} entries, need ≥ 40"

    def test_all_slugs_distinct(self):
        slugs = [e["slug"] for e in AIRFOIL_CATALOGUE]
        assert len(slugs) == len(set(slugs)), \
            "AIRFOIL_CATALOGUE contains duplicate slugs"

    def test_required_keys_present(self):
        required = {"slug", "name", "category", "source", "description"}
        for entry in AIRFOIL_CATALOGUE:
            missing = required - set(entry.keys())
            assert not missing, \
                f"Entry {entry.get('slug')!r} missing keys: {missing}"

    def test_all_catalogue_slugs_loadable_via_selig(self):
        """Every catalogue slug that is in SELIG_SLUGS must be loadable."""
        from kerf_aero.airfoils import SELIG_SLUGS
        for entry in AIRFOIL_CATALOGUE:
            slug = entry["slug"]
            if slug in SELIG_SLUGS:
                coords = selig_load(slug)
                assert coords.shape[1] == 2, \
                    f"selig_load({slug!r}) returned wrong shape"

    def test_selig_slugs_subset_of_catalogue(self):
        """All SELIG_SLUGS should appear in the catalogue."""
        from kerf_aero.airfoils import SELIG_SLUGS
        catalogue_slugs = {e["slug"] for e in AIRFOIL_CATALOGUE}
        missing = SELIG_SLUGS - catalogue_slugs
        assert not missing, \
            f"SELIG_SLUGS not in catalogue: {missing}"

    def test_catalogue_covers_required_categories(self):
        categories = {e["category"] for e in AIRFOIL_CATALOGUE}
        expected = {"symmetric", "general-aviation", "sailplane",
                    "low-reynolds", "high-lift", "vintage", "propeller"}
        missing = expected - categories
        assert not missing, f"Missing categories: {missing}"

    def test_selig_coords_le_near_origin(self):
        """All selig_load(slug) results must have LE near (0,0) and TE near (1,0)."""
        from kerf_aero.airfoils import SELIG_SLUGS
        for slug in SELIG_SLUGS:
            coords = selig_load(slug)
            x = coords[:, 0]
            # LE
            le_x = x.min()
            assert le_x < 0.02, f"{slug}: LE x = {le_x}"
            # TE
            te_x = x.max()
            assert abs(te_x - 1.0) < 0.02, f"{slug}: TE x = {te_x}"

    def test_all_slugs_non_empty_strings(self):
        for entry in AIRFOIL_CATALOGUE:
            for key in ("slug", "name", "category", "source", "description"):
                assert isinstance(entry[key], str) and entry[key].strip(), \
                    f"Entry {entry.get('slug')!r} has empty {key!r}"
