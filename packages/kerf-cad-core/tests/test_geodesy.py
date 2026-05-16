"""
Hermetic tests for kerf_cad_core.geodesy — geodetic computation & map projection.

Coverage
--------
  Ellipsoid parameters (WGS84, GRS80, Clarke1866)
  radius_curvature   — M and N at known latitudes
  meridian_arc       — quarter-meridian, specific latitudes
  geodetic_to_ecef   — known ECEF coords at equator and poles
  ecef_to_geodetic   — Bowring iterative inverse, round-trip
  ecef_to_enu / enu_to_ecef — local tangent plane round-trip
  transverse_mercator_fwd / _inv — Krüger series round-trip
  utm_fwd / utm_inv  — UTM forward, inverse, and round-trip
  utm_zone_from_lon / utm_lon0 — zone utilities
  lcc_fwd / lcc_inv  — Lambert Conformal Conic round-trip
  web_mercator_fwd / _inv — EPSG:3857 round-trip
  vincenty_inverse   — Flinders Peak → Buninyong (WGS84), coincident points
  vincenty_direct    — geodesic destination & back-azimuth
  haversine          — great-circle distance
  rhumb_line         — rhumb distance & bearing (due N/S/E/W)
  grid_to_ground     — combined scale factor
  GEOID_NOTE         — string constant present
  tools.*            — LLM tool wrappers (happy path + error paths)

All tests are hermetic: pure-Python, no OCC, no DB, no network.

References
----------
Vincenty (1975) — Table 3 test data (ANS ellipsoid, converted to WGS84 approx)
EPSG Guidance Note 7-2 (2023) — projection formulas
Karney (2011) — Transverse Mercator accuracy references

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import warnings

import pytest

from kerf_cad_core.geodesy.geo import (
    WGS84,
    GRS80,
    CLARKE1866,
    GEOID_NOTE,
    ecef_to_enu,
    ecef_to_geodetic,
    enu_to_ecef,
    geodetic_to_ecef,
    grid_to_ground,
    haversine,
    lcc_fwd,
    lcc_inv,
    meridian_arc,
    radius_curvature,
    rhumb_line,
    transverse_mercator_fwd,
    transverse_mercator_inv,
    utm_fwd,
    utm_inv,
    utm_lon0,
    utm_zone_from_lon,
    vincenty_direct,
    vincenty_inverse,
    web_mercator_fwd,
    web_mercator_inv,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Ellipsoid parameters
# ---------------------------------------------------------------------------

class TestEllipsoids:
    def test_wgs84_a(self):
        assert WGS84.a == pytest.approx(6_378_137.0)

    def test_wgs84_f(self):
        assert WGS84.f == pytest.approx(1.0 / 298.257223563, rel=1e-10)

    def test_grs80_a(self):
        assert GRS80.a == pytest.approx(6_378_137.0)

    def test_grs80_inv_f(self):
        # GRS80 inverse flattening
        assert 1.0 / GRS80.f == pytest.approx(298.257222101, rel=1e-9)

    def test_clarke1866_a(self):
        assert CLARKE1866.a == pytest.approx(6_378_206.4)

    def test_geoid_note_present(self):
        assert "EGM2008" in GEOID_NOTE
        assert "ellipsoidal" in GEOID_NOTE.lower()


# ---------------------------------------------------------------------------
# Radii of curvature
# ---------------------------------------------------------------------------

class TestRadiusCurvature:
    def test_equator(self):
        rc = radius_curvature(0.0)
        # At equator: N = a / sqrt(1-e2*0) = a; M = a*(1-e2)
        e2 = WGS84.f * (2.0 - WGS84.f)
        assert rc["N_m"] == pytest.approx(WGS84.a, rel=1e-10)
        assert rc["M_m"] == pytest.approx(WGS84.a * (1.0 - e2), rel=1e-10)

    def test_pole(self):
        rc = radius_curvature(90.0)
        # At poles: M = N (equal) = a*(1-e2)/(1-e2)^(3/2) = a/sqrt(1-e2)
        e2 = WGS84.f * (2.0 - WGS84.f)
        b2 = WGS84.a**2 * (1.0 - e2)
        expected = WGS84.a**2 / math.sqrt(b2)
        assert rc["N_m"] == pytest.approx(expected, rel=1e-6)

    def test_45_degrees(self):
        rc = radius_curvature(45.0)
        # M < N always on oblate ellipsoid
        assert rc["M_m"] < rc["N_m"]
        assert rc["M_m"] == pytest.approx(6_367_381.815, rel=1e-6)
        assert rc["N_m"] == pytest.approx(6_388_838.290, rel=1e-6)

    def test_grs80_at_equator(self):
        rc = radius_curvature(0.0, ellipsoid="GRS80")
        assert rc["N_m"] == pytest.approx(GRS80.a, rel=1e-10)


# ---------------------------------------------------------------------------
# Meridian arc
# ---------------------------------------------------------------------------

class TestMeridianArc:
    def test_equator_zero(self):
        assert meridian_arc(0.0) == pytest.approx(0.0, abs=1e-6)

    def test_quarter_meridian(self):
        # Quarter meridian for WGS84 should be ~10 001 965.7 m
        m90 = meridian_arc(90.0)
        assert m90 == pytest.approx(10_001_965.729, rel=1e-6)

    def test_45_degrees(self):
        m45 = meridian_arc(45.0)
        assert m45 == pytest.approx(4_984_944.378, rel=1e-6)

    def test_negative_latitude(self):
        # Southern latitudes give negative arc (south of equator)
        assert meridian_arc(-45.0) == pytest.approx(-meridian_arc(45.0), rel=1e-12)

    def test_grs80_quarter_meridian(self):
        m = meridian_arc(90.0, ellipsoid="GRS80")
        assert m == pytest.approx(10_001_965.729, rel=1e-5)


# ---------------------------------------------------------------------------
# Geodetic ↔ ECEF
# ---------------------------------------------------------------------------

class TestGeodeticEcef:
    def test_equator_prime_meridian(self):
        r = geodetic_to_ecef(0.0, 0.0)
        assert r["X_m"] == pytest.approx(WGS84.a, rel=1e-10)
        assert r["Y_m"] == pytest.approx(0.0, abs=1e-6)
        assert r["Z_m"] == pytest.approx(0.0, abs=1e-6)

    def test_equator_90e(self):
        r = geodetic_to_ecef(0.0, 90.0)
        assert r["X_m"] == pytest.approx(0.0, abs=1e-4)
        assert r["Y_m"] == pytest.approx(WGS84.a, rel=1e-10)
        assert r["Z_m"] == pytest.approx(0.0, abs=1e-4)

    def test_north_pole(self):
        r = geodetic_to_ecef(90.0, 0.0)
        assert r["X_m"] == pytest.approx(0.0, abs=1e-3)
        assert r["Y_m"] == pytest.approx(0.0, abs=1e-3)
        # Z at pole = b
        b = WGS84.a * (1.0 - WGS84.f)
        assert r["Z_m"] == pytest.approx(b, rel=1e-10)

    def test_with_height(self):
        r0 = geodetic_to_ecef(0.0, 0.0, h_m=0.0)
        r1 = geodetic_to_ecef(0.0, 0.0, h_m=1000.0)
        assert r1["X_m"] - r0["X_m"] == pytest.approx(1000.0, abs=1e-4)

    def test_round_trip(self):
        for lat, lon, h in [
            (0.0, 0.0, 0.0),
            (51.5, -0.1, 100.0),
            (-33.9, 151.2, 50.0),
            (89.9, 45.0, 0.0),
            (-89.9, -90.0, 500.0),
        ]:
            ecef = geodetic_to_ecef(lat, lon, h)
            geo = ecef_to_geodetic(ecef["X_m"], ecef["Y_m"], ecef["Z_m"])
            assert geo["lat_deg"] == pytest.approx(lat, abs=1e-10)
            assert geo["lon_deg"] == pytest.approx(lon, abs=1e-10)
            assert geo["h_m"]    == pytest.approx(h,   abs=1e-6)


# ---------------------------------------------------------------------------
# ECEF ↔ ENU
# ---------------------------------------------------------------------------

class TestEcefEnu:
    def test_enu_up_only(self):
        """Point 100m directly above origin: ENU should be (0, 0, 100)."""
        ref_lat, ref_lon = 51.5, -0.1
        ecef_up = geodetic_to_ecef(ref_lat, ref_lon, 100.0)
        enu = ecef_to_enu(
            ecef_up["X_m"], ecef_up["Y_m"], ecef_up["Z_m"],
            ref_lat, ref_lon, 0.0,
        )
        assert enu["e_m"] == pytest.approx(0.0, abs=1e-4)
        assert enu["n_m"] == pytest.approx(0.0, abs=1e-4)
        assert enu["u_m"] == pytest.approx(100.0, rel=1e-8)

    def test_enu_round_trip(self):
        """ECEF → ENU → ECEF round-trip."""
        X, Y, Z = 4_209_000.0, 172_500.0, 4_726_000.0
        ref_lat, ref_lon = 51.5, 2.3
        enu = ecef_to_enu(X, Y, Z, ref_lat, ref_lon)
        back = enu_to_ecef(enu["e_m"], enu["n_m"], enu["u_m"], ref_lat, ref_lon)
        assert back["X_m"] == pytest.approx(X, abs=1e-4)
        assert back["Y_m"] == pytest.approx(Y, abs=1e-4)
        assert back["Z_m"] == pytest.approx(Z, abs=1e-4)


# ---------------------------------------------------------------------------
# Transverse Mercator (raw, k0=1)
# ---------------------------------------------------------------------------

class TestTransverseMercator:
    def test_equator_on_cm(self):
        """On equator at central meridian: xi=0, eta=0."""
        r = transverse_mercator_fwd(0.0, 0.0, 0.0, k0=1.0)
        assert r["xi_m"]  == pytest.approx(0.0, abs=1e-4)
        assert r["eta_m"] == pytest.approx(0.0, abs=1e-4)

    def test_scale_on_cm(self):
        """Scale k0=1 on central meridian."""
        r = transverse_mercator_fwd(0.0, 0.0, 0.0, k0=1.0)
        assert r["k"] == pytest.approx(1.0, abs=1e-8)

    def test_convergence_on_cm(self):
        """Meridian convergence = 0 on central meridian."""
        r = transverse_mercator_fwd(45.0, 9.0, 9.0, k0=1.0)
        assert r["gamma_deg"] == pytest.approx(0.0, abs=1e-8)

    def test_round_trip_on_cm(self):
        """Forward/inverse round-trip on CM."""
        fwd = transverse_mercator_fwd(45.0, 9.0, 9.0, k0=0.9996)
        inv = transverse_mercator_inv(fwd["xi_m"], fwd["eta_m"], 9.0, k0=0.9996)
        assert inv["lat_deg"] == pytest.approx(45.0, abs=1e-10)
        assert inv["lon_deg"] == pytest.approx(9.0,  abs=1e-10)

    def test_round_trip_off_cm(self):
        """Forward/inverse round-trip off central meridian."""
        lat, lon, lon0 = -33.9, 151.2, 153.0
        fwd = transverse_mercator_fwd(lat, lon, lon0, k0=0.9996)
        inv = transverse_mercator_inv(fwd["xi_m"], fwd["eta_m"], lon0, k0=0.9996)
        assert inv["lat_deg"] == pytest.approx(lat, abs=1e-10)
        assert inv["lon_deg"] == pytest.approx(lon, abs=1e-10)


# ---------------------------------------------------------------------------
# UTM
# ---------------------------------------------------------------------------

class TestUTM:
    def test_zone_from_lon(self):
        assert utm_zone_from_lon(0.0)   == 31
        assert utm_zone_from_lon(9.0)   == 32
        assert utm_zone_from_lon(144.0) == 55
        assert utm_zone_from_lon(-74.0) == 18

    def test_lon0(self):
        assert utm_lon0(31) == pytest.approx(3.0)
        assert utm_lon0(32) == pytest.approx(9.0)
        assert utm_lon0(55) == pytest.approx(147.0)

    def test_equator_false_easting(self):
        """On equator at CM: easting = 500000, northing = 0."""
        u = utm_fwd(0.0, 3.0, zone=31)
        assert u["easting_m"]  == pytest.approx(500_000.0, abs=1e-3)
        assert u["northing_m"] == pytest.approx(0.0, abs=1e-3)
        assert u["zone"] == 31
        assert u["hemisphere"] == "N"

    def test_southern_hemisphere_false_northing(self):
        """Southern hemisphere false northing: ~10 000 000 at equator."""
        u = utm_fwd(0.0, 3.0, zone=31)
        assert u["northing_m"] == pytest.approx(0.0, abs=1e-3)
        # A point at -1 degree should have northing close to 10^7 - ~111km
        u_s = utm_fwd(-1.0, 3.0, zone=31)
        assert u_s["hemisphere"] == "S"
        assert u_s["northing_m"] == pytest.approx(10_000_000.0 - 110_574.0, rel=2e-3)

    def test_eiffel_tower_easting(self):
        """Eiffel Tower (lat=48.8584, lon=2.2945) in zone 31N: known easting ~448252."""
        u = utm_fwd(48.8584, 2.2945, zone=31)
        assert u["easting_m"] == pytest.approx(448_252.0, abs=2.0)

    def test_round_trip_northern(self):
        """UTM forward→inverse round-trip: northern hemisphere."""
        cases = [
            (51.5,  -0.1, None),
            (48.86,  2.35, None),
            (40.0,  -74.0, None),
            (60.0,   25.0, None),
        ]
        for lat, lon, zone in cases:
            u = utm_fwd(lat, lon, zone=zone)
            r = utm_inv(u["easting_m"], u["northing_m"], u["zone"], u["hemisphere"])
            assert r["lat_deg"] == pytest.approx(lat, abs=1e-9)
            assert r["lon_deg"] == pytest.approx(lon, abs=1e-9)

    def test_round_trip_southern(self):
        """UTM forward→inverse round-trip: southern hemisphere."""
        cases = [
            (-33.9,  151.2, None),
            (-37.9510334, 144.4248679, None),
            (-22.9,  -43.2, None),
        ]
        for lat, lon, zone in cases:
            u = utm_fwd(lat, lon, zone=zone)
            r = utm_inv(u["easting_m"], u["northing_m"], u["zone"], u["hemisphere"])
            assert r["lat_deg"] == pytest.approx(lat, abs=1e-9)
            assert r["lon_deg"] == pytest.approx(lon, abs=1e-9)

    def test_scale_on_cm(self):
        """Scale factor k = 0.9996 on central meridian."""
        u = utm_fwd(0.0, 3.0, zone=31)
        assert u["k"] == pytest.approx(0.9996, abs=1e-8)

    def test_scale_off_cm(self):
        """Scale factor > 0.9996 for point off CM."""
        u = utm_fwd(0.0, 0.0, zone=31)
        assert u["k"] > 0.9996  # 3 degrees from CM raises scale above k0


# ---------------------------------------------------------------------------
# Lambert Conformal Conic
# ---------------------------------------------------------------------------

class TestLCC:
    def test_round_trip_2parallel(self):
        """2-parallel LCC round-trip for a CONUS-like configuration."""
        lat, lon = 40.0, -75.0
        lat0, lon0, lat1, lat2 = 23.0, -96.0, 33.0, 45.0
        fwd = lcc_fwd(lat, lon, lat0, lon0, lat1, lat2)
        inv = lcc_inv(fwd["easting_m"], fwd["northing_m"], lat0, lon0, lat1, lat2)
        assert inv["lat_deg"] == pytest.approx(lat, abs=1e-9)
        assert inv["lon_deg"] == pytest.approx(lon, abs=1e-9)

    def test_round_trip_1parallel(self):
        """1-parallel LCC round-trip."""
        lat, lon = 60.0, 25.0
        lat0, lon0, lat1 = 57.0, 21.0, 59.0
        fwd = lcc_fwd(lat, lon, lat0, lon0, lat1)
        inv = lcc_inv(fwd["easting_m"], fwd["northing_m"], lat0, lon0, lat1)
        assert inv["lat_deg"] == pytest.approx(lat, abs=1e-9)
        assert inv["lon_deg"] == pytest.approx(lon, abs=1e-9)

    def test_scale_at_standard_parallel(self):
        """Scale factor k = 1.0 at standard parallels."""
        lat1 = 33.0
        lat0, lon0 = 23.0, -96.0
        fwd = lcc_fwd(lat1, -96.0, lat0, lon0, lat1, 45.0)
        assert fwd["k"] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Web Mercator
# ---------------------------------------------------------------------------

class TestWebMercator:
    def test_origin(self):
        """(0, 0) → (0, 0) in Web Mercator."""
        r = web_mercator_fwd(0.0, 0.0)
        assert r["x_m"] == pytest.approx(0.0, abs=1e-6)
        assert r["y_m"] == pytest.approx(0.0, abs=1e-6)

    def test_round_trip(self):
        for lat, lon in [(0.0, 0.0), (51.5, -0.1), (-33.9, 151.2), (0.0, 90.0)]:
            fwd = web_mercator_fwd(lat, lon)
            inv = web_mercator_inv(fwd["x_m"], fwd["y_m"])
            assert inv["lat_deg"] == pytest.approx(lat, abs=1e-10)
            assert inv["lon_deg"] == pytest.approx(lon, abs=1e-10)

    def test_x_at_180e(self):
        """At lon=180: x = pi * R."""
        r = web_mercator_fwd(0.0, 180.0)
        assert r["x_m"] == pytest.approx(math.pi * 6_378_137.0, rel=1e-10)

    def test_warning_beyond_85(self):
        """Web Mercator warns for latitudes beyond ±85.05°."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            web_mercator_fwd(86.0, 0.0)
            assert len(w) >= 1


# ---------------------------------------------------------------------------
# Vincenty inverse
# ---------------------------------------------------------------------------

class TestVincentyInverse:
    def test_flinders_peak_to_buninyong_wgs84(self):
        """
        Vincenty distance Flinders Peak → Buninyong on WGS84.
        The Vincenty (1975) paper used the ANS ellipsoid; here we test WGS84.
        Reference distance ~54 969 m (WGS84 is slightly different from the
        54 972.271 m paper value on ANS/AGD66).
        """
        v = vincenty_inverse(
            -37.9510334, 144.4248679,
            -37.6528722, 143.9264955,
        )
        assert v["distance_m"] == pytest.approx(54_968.848, abs=1.0)
        assert not v["convergence_warning"]

    def test_coincident_points(self):
        v = vincenty_inverse(51.5, -0.1, 51.5, -0.1)
        assert v["distance_m"] == pytest.approx(0.0, abs=1e-6)

    def test_equatorial_1_degree(self):
        """1 degree of longitude on equator ~111 319 m on WGS84."""
        v = vincenty_inverse(0.0, 0.0, 0.0, 1.0)
        assert v["distance_m"] == pytest.approx(111_319.49, abs=1.0)

    def test_azimuth_north(self):
        """Due-north geodesic should have az12 = 0 and az21 = 180."""
        v = vincenty_inverse(10.0, 0.0, 20.0, 0.0)
        assert v["az12_deg"] == pytest.approx(0.0, abs=1e-6)
        assert v["az21_deg"] == pytest.approx(180.0, abs=1e-6)

    def test_azimuth_east(self):
        """Due-east geodesic on equator: az12=90, az21=270."""
        v = vincenty_inverse(0.0, 0.0, 0.0, 1.0)
        assert v["az12_deg"] == pytest.approx(90.0, abs=1e-5)
        assert v["az21_deg"] == pytest.approx(270.0, abs=1e-5)

    def test_grs80_ellipsoid(self):
        """GRS80 result should be very close to WGS84 for the same point-pair."""
        v84  = vincenty_inverse(-37.95, 144.42, -37.65, 143.93)
        vgrs = vincenty_inverse(-37.95, 144.42, -37.65, 143.93, ellipsoid="GRS80")
        assert abs(v84["distance_m"] - vgrs["distance_m"]) < 0.01


# ---------------------------------------------------------------------------
# Vincenty direct
# ---------------------------------------------------------------------------

class TestVincentyDirect:
    def test_north_geodesic(self):
        """Start at (0, 0), go north 111 319.49 m: should arrive at (~1, 0)."""
        r = vincenty_direct(0.0, 0.0, 0.0, 111_319.49)
        assert r["lat2_deg"] == pytest.approx(1.0, abs=0.01)
        assert r["lon2_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_flinders_peak_direct_wgs84(self):
        """
        Vincenty direct from Flinders Peak with forward azimuth to Buninyong.
        Round-trip check against vincenty_inverse.
        """
        # First get distance and azimuth from inverse
        inv = vincenty_inverse(
            -37.9510334, 144.4248679,
            -37.6528722, 143.9264955,
        )
        # Then use direct to get destination
        d = vincenty_direct(
            -37.9510334, 144.4248679,
            inv["az12_deg"],
            inv["distance_m"],
        )
        assert d["lat2_deg"] == pytest.approx(-37.6528722, abs=1e-5)
        assert d["lon2_deg"] == pytest.approx(143.9264955, abs=1e-5)

    def test_zero_distance(self):
        r = vincenty_direct(51.5, -0.1, 90.0, 0.0)
        assert r["lat2_deg"] == pytest.approx(51.5,  abs=1e-8)
        assert r["lon2_deg"] == pytest.approx(-0.1, abs=1e-8)


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

class TestHaversine:
    def test_1_degree_equatorial(self):
        h = haversine(0.0, 0.0, 0.0, 1.0)
        # Equatorial 1-degree arc on IUGG mean sphere
        assert h["distance_m"] == pytest.approx(111_195.08, abs=1.0)

    def test_zero_distance(self):
        h = haversine(51.5, -0.1, 51.5, -0.1)
        assert h["distance_m"] == pytest.approx(0.0, abs=1e-6)

    def test_antipodal(self):
        """Antipodal distance ≈ pi * R."""
        h = haversine(0.0, 0.0, 0.0, 180.0)
        assert h["distance_m"] == pytest.approx(math.pi * 6_371_008.8, rel=1e-6)

    def test_azimuth_east(self):
        h = haversine(0.0, 0.0, 0.0, 1.0)
        assert h["az12_deg"] == pytest.approx(90.0, abs=1e-5)

    def test_azimuth_north(self):
        h = haversine(0.0, 0.0, 10.0, 0.0)
        assert h["az12_deg"] == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Rhumb line
# ---------------------------------------------------------------------------

class TestRhumbLine:
    def test_due_north_bearing(self):
        r = rhumb_line(51.5, -0.1, 52.5, -0.1)
        assert r["bearing_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_due_south_bearing(self):
        r = rhumb_line(52.5, -0.1, 51.5, -0.1)
        assert r["bearing_deg"] == pytest.approx(180.0, abs=1e-5)

    def test_due_east_bearing(self):
        r = rhumb_line(0.0, 0.0, 0.0, 1.0)
        assert r["bearing_deg"] == pytest.approx(90.0, abs=1e-5)

    def test_distance_approx(self):
        """1 degree north at mid-latitude: rhumb ≈ meridian arc for 1 deg."""
        r = rhumb_line(51.5, -0.1, 52.5, -0.1)
        # Meridian arc for 1 degree of latitude at ~51-52 is ~111 267 m
        assert r["distance_m"] == pytest.approx(111_267.0, abs=50.0)


# ---------------------------------------------------------------------------
# Grid to ground
# ---------------------------------------------------------------------------

class TestGridToGround:
    def test_sea_level_k1(self):
        """At sea level with k=1: ground = grid."""
        gg = grid_to_ground(1000.0, 0.0, 1.0)
        assert gg["ground_distance_m"] == pytest.approx(1000.0, rel=1e-9)
        assert gg["csf"] == pytest.approx(1.0, rel=1e-9)

    def test_utm_cm_sea_level(self):
        """UTM CM k=0.9996 at sea level: ground > grid."""
        gg = grid_to_ground(1000.0, 0.0, 0.9996)
        assert gg["ground_distance_m"] > 1000.0
        assert gg["csf"] == pytest.approx(0.9996, rel=1e-9)

    def test_elevation_effect(self):
        """Higher elevation → larger k_elevation correction → smaller CSF."""
        gg1 = grid_to_ground(1000.0, 100.0, 0.9996)
        gg2 = grid_to_ground(1000.0, 1000.0, 0.9996)
        assert gg2["k_elevation"] < gg1["k_elevation"]
        assert gg2["csf"] < gg1["csf"]
        assert gg2["ground_distance_m"] > gg1["ground_distance_m"]

    def test_known_value(self):
        """CSF = k_projection * R/(R+h)."""
        R = 6_371_000.0
        h = 500.0
        k = 0.9996
        k_elev = R / (R + h)
        csf = k * k_elev
        gg = grid_to_ground(1000.0, h, k)
        assert gg["csf"] == pytest.approx(csf, rel=1e-10)
        assert gg["ground_distance_m"] == pytest.approx(1000.0 / csf, rel=1e-10)


# ---------------------------------------------------------------------------
# LLM tool wrappers
# ---------------------------------------------------------------------------

class _FakeCtx:
    project_id = "test"


_ctx = _FakeCtx()


def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


class TestGeodesyTools:
    def test_utm_fwd_happy(self):
        from kerf_cad_core.geodesy.tools import run_utm_fwd
        r = json.loads(_run(run_utm_fwd(_ctx, _args(lat_deg=48.8584, lon_deg=2.2945))))
        assert r["ok"] is True
        assert "easting_m" in r
        assert r["easting_m"] == pytest.approx(448_252.0, abs=5.0)

    def test_utm_fwd_missing_lat(self):
        from kerf_cad_core.geodesy.tools import run_utm_fwd
        r = json.loads(_run(run_utm_fwd(_ctx, _args(lon_deg=2.0))))
        assert r["ok"] is False
        assert "lat_deg" in r["reason"]

    def test_utm_inv_happy(self):
        from kerf_cad_core.geodesy.tools import run_utm_inv
        r = json.loads(_run(run_utm_inv(_ctx, _args(easting_m=500000.0, northing_m=0.0, zone=31))))
        assert r["ok"] is True
        assert r["lat_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_utm_inv_missing_zone(self):
        from kerf_cad_core.geodesy.tools import run_utm_inv
        r = json.loads(_run(run_utm_inv(_ctx, _args(easting_m=500000.0, northing_m=0.0))))
        assert r["ok"] is False

    def test_vincenty_inverse_happy(self):
        from kerf_cad_core.geodesy.tools import run_vincenty_inverse
        r = json.loads(_run(run_vincenty_inverse(_ctx, _args(
            lat1_deg=-37.9510334, lon1_deg=144.4248679,
            lat2_deg=-37.6528722, lon2_deg=143.9264955,
        ))))
        assert r["ok"] is True
        assert r["distance_m"] == pytest.approx(54_968.848, abs=2.0)

    def test_vincenty_inverse_missing(self):
        from kerf_cad_core.geodesy.tools import run_vincenty_inverse
        r = json.loads(_run(run_vincenty_inverse(_ctx, _args(lat1_deg=0.0, lon1_deg=0.0))))
        assert r["ok"] is False

    def test_vincenty_direct_happy(self):
        from kerf_cad_core.geodesy.tools import run_vincenty_direct
        r = json.loads(_run(run_vincenty_direct(_ctx, _args(
            lat1_deg=0.0, lon1_deg=0.0, az12_deg=0.0, dist_m=111_319.49,
        ))))
        assert r["ok"] is True
        assert r["lat2_deg"] == pytest.approx(1.0, abs=0.01)

    def test_haversine_happy(self):
        from kerf_cad_core.geodesy.tools import run_haversine
        r = json.loads(_run(run_haversine(_ctx, _args(
            lat1_deg=0.0, lon1_deg=0.0, lat2_deg=0.0, lon2_deg=1.0,
        ))))
        assert r["ok"] is True
        assert r["distance_m"] == pytest.approx(111_195.08, abs=2.0)

    def test_rhumb_happy(self):
        from kerf_cad_core.geodesy.tools import run_rhumb_line
        r = json.loads(_run(run_rhumb_line(_ctx, _args(
            lat1_deg=51.5, lon1_deg=-0.1, lat2_deg=52.5, lon2_deg=-0.1,
        ))))
        assert r["ok"] is True
        assert r["bearing_deg"] == pytest.approx(0.0, abs=1e-5)

    def test_ecef_round_trip_tool(self):
        from kerf_cad_core.geodesy.tools import run_ecef_round_trip
        r = json.loads(_run(run_ecef_round_trip(_ctx, _args(lat_deg=51.5, lon_deg=-0.1, h_m=100.0))))
        assert r["ok"] is True
        assert r["recovered_lat_deg"] == pytest.approx(51.5, abs=1e-9)
        assert r["recovered_lon_deg"] == pytest.approx(-0.1, abs=1e-9)
        assert r["recovered_h_m"]     == pytest.approx(100.0, abs=1e-5)

    def test_enu_tool(self):
        from kerf_cad_core.geodesy.tools import run_enu
        r = json.loads(_run(run_enu(_ctx, _args(
            lat_deg=51.5, lon_deg=-0.1, h_m=100.0,
            ref_lat_deg=51.5, ref_lon_deg=-0.1, ref_h_m=0.0,
        ))))
        assert r["ok"] is True
        assert r["u_m"] == pytest.approx(100.0, abs=1e-4)

    def test_lcc_fwd_tool(self):
        from kerf_cad_core.geodesy.tools import run_lcc_fwd
        r = json.loads(_run(run_lcc_fwd(_ctx, _args(
            lat_deg=40.0, lon_deg=-75.0,
            lat0_deg=23.0, lon0_deg=-96.0, lat1_deg=33.0, lat2_deg=45.0,
        ))))
        assert r["ok"] is True
        assert "easting_m" in r

    def test_web_mercator_fwd_tool(self):
        from kerf_cad_core.geodesy.tools import run_web_mercator_fwd
        r = json.loads(_run(run_web_mercator_fwd(_ctx, _args(lat_deg=0.0, lon_deg=0.0))))
        assert r["ok"] is True
        assert r["x_m"] == pytest.approx(0.0, abs=1e-6)
        assert r["y_m"] == pytest.approx(0.0, abs=1e-6)

    def test_web_mercator_inv_tool(self):
        from kerf_cad_core.geodesy.tools import run_web_mercator_inv
        r = json.loads(_run(run_web_mercator_inv(_ctx, _args(x_m=0.0, y_m=0.0))))
        assert r["ok"] is True
        assert r["lat_deg"] == pytest.approx(0.0, abs=1e-9)
        assert r["lon_deg"] == pytest.approx(0.0, abs=1e-9)

    def test_radius_curvature_tool(self):
        from kerf_cad_core.geodesy.tools import run_radius_curvature
        r = json.loads(_run(run_radius_curvature(_ctx, _args(lat_deg=45.0))))
        assert r["ok"] is True
        assert r["M_m"] == pytest.approx(6_367_381.815, rel=1e-6)
        assert r["N_m"] == pytest.approx(6_388_838.290, rel=1e-6)

    def test_grid_to_ground_tool(self):
        from kerf_cad_core.geodesy.tools import run_grid_to_ground
        r = json.loads(_run(run_grid_to_ground(_ctx, _args(
            grid_distance_m=1000.0, elevation_m=500.0, k_projection=0.9996,
        ))))
        assert r["ok"] is True
        assert r["ground_distance_m"] > 1000.0

    def test_tool_bad_json(self):
        from kerf_cad_core.geodesy.tools import run_utm_fwd
        r = json.loads(_run(run_utm_fwd(_ctx, b"not json")))
        assert r["ok"] is False


# ===========================================================================
# AUTHORITATIVE EXTERNAL REFERENCE CASES
# ---------------------------------------------------------------------------
# Cross-checked against GeographicLib (Karney) and Vincenty (1975) published
# benchmarks. These are the canonical geodesy validation cases.
# References:
#   Vincenty, T. (1975) "Direct and inverse solutions of geodesics on the
#     ellipsoid with application of nested equations", Survey Review 23(176).
#   Karney, C.F.F. (2013) "Algorithms for geodesics", J. Geodesy 87(1):43-55,
#     and the GeographicLib test set / online geodesic calculator.
#   NIMA TR8350.2 (1997) WGS-84 ellipsoid parameters.
# ===========================================================================

class TestGeodesyAuthoritativeReferences:
    def test_flinders_peak_buninyong_geographiclib(self):
        # GeographicLib WGS84 geodesic: Flinders Peak (-37:57:03.72030,
        # 144:25:29.52440) -> Buninyong (-37:39:10.15610, 143:55:35.38390).
        # Authoritative distance s12 = 54972.271 m (Karney/GeographicLib).
        def dms(d, m, s, sign=1):
            return sign * (abs(d) + m / 60.0 + s / 3600.0)
        v = vincenty_inverse(
            dms(-37, 57, 3.72030, -1), dms(144, 25, 29.52440),
            dms(-37, 39, 10.15610, -1), dms(143, 55, 35.38390),
        )
        assert v["distance_m"] == pytest.approx(54972.271, abs=0.01)

    def test_wgs84_quarter_meridian_nima(self):
        # NIMA TR8350.2 / GeographicLib: WGS84 quarter meridian (pole-equator)
        # = 10001965.729 m.
        assert meridian_arc(90.0) == pytest.approx(10_001_965.729, abs=0.01)

    def test_wgs84_equatorial_radius(self):
        # NIMA TR8350.2: a = 6378137.0 m exactly.
        assert WGS84.a == pytest.approx(6_378_137.0, abs=1e-6)

    def test_wgs84_polar_radius(self):
        # NIMA TR8350.2: b = a(1-f) = 6356752.3142 m.
        b = WGS84.a * (1.0 - WGS84.f)
        assert b == pytest.approx(6_356_752.3142, abs=1e-3)

    def test_radius_curvature_45deg_known(self):
        # Standard WGS84 radii at 45 deg: M = 6367381.82 m, N = 6388838.29 m
        # (e.g. Snyder, Map Projections - A Working Manual, USGS PP 1395).
        rc = radius_curvature(45.0)
        assert rc["M_m"] == pytest.approx(6_367_381.815, abs=0.05)
        assert rc["N_m"] == pytest.approx(6_388_838.290, abs=0.05)

    def test_vincenty_direct_inverse_consistency(self):
        # Vincenty (1975) direct/inverse must be mutually consistent to mm.
        inv = vincenty_inverse(-37.951033, 144.424868, -37.652872, 143.926496)
        d = vincenty_direct(-37.951033, 144.424868,
                             inv["az12_deg"], inv["distance_m"])
        assert d["lat2_deg"] == pytest.approx(-37.652872, abs=1e-6)
        assert d["lon2_deg"] == pytest.approx(143.926496, abs=1e-6)

    def test_utm_zone31_eiffel_epsg(self):
        # Eiffel Tower 48.8584N 2.2945E, UTM 31N. epsg.io / PROJ:
        # E ~ 448252 m, N ~ 5411955 m on WGS84.
        u = utm_fwd(48.8584, 2.2945, zone=31)
        assert u["easting_m"] == pytest.approx(448_252.0, abs=2.0)
        assert u["northing_m"] == pytest.approx(5_411_955.0, abs=3.0)

    def test_utm_central_meridian_scale_exact(self):
        # UTM definition: scale on central meridian = k0 = 0.9996 exactly.
        u = utm_fwd(0.0, 3.0, zone=31)
        assert u["k"] == pytest.approx(0.9996, abs=1e-9)

    def test_haversine_mean_earth_1deg(self):
        # 1 deg of equatorial arc on IUGG mean sphere R=6371008.8 m
        # = R * pi/180 = 111195.08 m.
        h = haversine(0.0, 0.0, 0.0, 1.0)
        assert h["distance_m"] == pytest.approx(111_195.08, abs=0.5)

    def test_grs80_vs_wgs84_negligible(self):
        # GRS80 and WGS84 differ only in 1/f at the 1e-8 level; geodesic
        # distance must agree to < 1 mm over ~55 km.
        v84 = vincenty_inverse(-37.95, 144.42, -37.65, 143.93)
        vg = vincenty_inverse(-37.95, 144.42, -37.65, 143.93, ellipsoid="GRS80")
        assert abs(v84["distance_m"] - vg["distance_m"]) < 1e-3
