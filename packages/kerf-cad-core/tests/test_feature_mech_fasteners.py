"""
T-23 — Mech: fasteners library
===============================
Spec: 25 fastener specs; dimensions match standard; hole-pattern integration.

Scope: fasteners/ ISO/DIN/ASME bolt + nut + washer generation.

Standards referenced
--------------------
ISO 4014:2011   Hexagon head bolts — Product grades A and B
ISO 4762:2004   Hexagon socket head cap screws — coarse thread
ISO 4032:2012   Hexagon nuts, style 1 — Product grades A and B
ISO 7089:2000   Plain washers — Normal series — Product grade A
ISO 273:1979    Fasteners; clearance holes for bolts and screws
ASME B18.2.1-2012  Square and Hex Bolts and Screws (inch)

Key dimension relationships verified
-------------------------------------
ISO 4014 hex bolt:
    e (circumscribed circle) = s_af / cos(30°)   ← exact geometry
    d_washer_face = 1.5 × d_nom                   ← VDI 2230 / Shigley default

ISO 4762 socket cap:
    dk_head ≥ 1.5 × d_nom  (head never smaller than ~1.5d)
    k_head == d_nom         (ISO 4762: head height = nominal diameter for M3–M24)
    s_hex_key < dk_head     (key fits inside head)

ISO 4032 hex nut:
    s_af bolt == s_af nut   (matching wrench size per standard pairing)
    m_height > 0.5 × d_nom (nut has sufficient thread engagement height)

ISO 7089 washer:
    d1_inner > d_nom        (clearance bore)
    d2_outer > d1_inner     (outer > bore)
    d2_outer >= 2 × d_nom   (washer distributes load)

Hole-pattern:
    bolt_circle_positions returns correct count and on-radius
    bolt_circle_pcd round-trips with positions via geometry
    clearance_hole > d_nom for all fits

All tests are pure-Python and hermetic: no OCC, no DB, no network.

Author: imranparuk
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.fasteners.catalog import (
    HEX_BOLTS,
    SOCKET_CAPS,
    HEX_NUTS,
    WASHERS,
    ASME_BOLTS,
    lookup_hex_bolt,
    lookup_socket_cap,
    lookup_hex_nut,
    lookup_washer,
    lookup_asme_bolt,
    clearance_hole_diameter,
    bolt_circle_positions,
    bolt_circle_pcd,
)


# ---------------------------------------------------------------------------
# Reference data — 25 fastener specs
# Independent values from the standards (not read back from the catalog).
#
# Group A: 5 ISO 4014 hex bolts
# Group B: 5 ISO 4762 socket cap screws
# Group C: 5 ISO 4032 hex nuts
# Group D: 5 ISO 7089 washers
# Group E: 5 ASME B18.2.1 hex bolts
# ---------------------------------------------------------------------------

# (designation, d_nom_mm, pitch_mm, s_af_mm, k_head_mm)
_ISO_BOLT_REF: list[tuple[str, float, float, float, float]] = [
    ("M6",   6.0,  1.00, 10.0,  4.0),
    ("M8",   8.0,  1.25, 13.0,  5.3),
    ("M10", 10.0,  1.50, 17.0,  6.4),
    ("M16", 16.0,  2.00, 24.0, 10.0),
    ("M24", 24.0,  3.00, 36.0, 15.0),
]

# (designation, d_nom_mm, pitch_mm, dk_head_mm, k_head_mm, s_hex_key_mm)
_SOCKET_CAP_REF: list[tuple[str, float, float, float, float, float]] = [
    ("M5",   5.0,  0.80,  8.5,  5.0,  4.0),
    ("M6",   6.0,  1.00, 10.0,  6.0,  5.0),
    ("M8",   8.0,  1.25, 13.0,  8.0,  6.0),
    ("M12", 12.0,  1.75, 18.0, 12.0, 10.0),
    ("M16", 16.0,  2.00, 24.0, 16.0, 14.0),
]

# (designation, d_nom_mm, pitch_mm, s_af_mm, m_height_mm)
_HEX_NUT_REF: list[tuple[str, float, float, float, float]] = [
    ("M6",   6.0,  1.00, 10.0,  5.2),
    ("M8",   8.0,  1.25, 13.0,  6.8),
    ("M10", 10.0,  1.50, 17.0,  8.4),
    ("M16", 16.0,  2.00, 24.0, 14.8),
    ("M24", 24.0,  3.00, 36.0, 21.5),
]

# (designation, d_nom_mm, d1_inner_mm, d2_outer_mm, h_thick_mm)
_WASHER_REF: list[tuple[str, float, float, float, float]] = [
    ("M6",   6.0,  6.4, 12.0,  1.6),
    ("M8",   8.0,  8.4, 16.0,  1.6),
    ("M10", 10.0, 10.5, 20.0,  2.0),
    ("M16", 16.0, 17.0, 30.0,  3.0),
    ("M24", 24.0, 25.0, 44.0,  4.0),
]

# (designation, d_nom_in, W_af_in, H_head_in)
_ASME_BOLT_REF: list[tuple[str, float, float, float]] = [
    ("1/4-20 UNC",  0.2500, 0.4375, 0.1563),
    ("3/8-16 UNC",  0.3750, 0.5625, 0.2344),
    ("1/2-13 UNC",  0.5000, 0.7500, 0.3125),
    ("3/4-10 UNC",  0.7500, 1.1250, 0.4688),
    ("1-8 UNC",     1.0000, 1.5000, 0.6250),
]

# Total specs: 5+5+5+5+5 = 25
assert (
    len(_ISO_BOLT_REF)
    + len(_SOCKET_CAP_REF)
    + len(_HEX_NUT_REF)
    + len(_WASHER_REF)
    + len(_ASME_BOLT_REF)
) == 25, "Reference fixtures must total 25 specs"


# ---------------------------------------------------------------------------
# Tolerance constant for nominal dimension checks
# ---------------------------------------------------------------------------

_ABS_TOL = 1e-9   # exact match for stored nominals
_MM_TOL  = 0.01   # 10 µm tolerance for derived quantities


# ===========================================================================
# A. ISO 4014 Hex Bolt — 5 specs
# ===========================================================================

class TestISO4014HexBolt:

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_designation_in_catalog(self, desig, d, p, s, k):
        """Designation must be present in HEX_BOLTS catalog."""
        assert desig in HEX_BOLTS, f"{desig} not found in HEX_BOLTS"

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_nominal_diameter(self, desig, d, p, s, k):
        """d_nom_mm must match ISO 4014 nominal exactly."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        assert spec["d_nom_mm"] == pytest.approx(d, abs=_ABS_TOL), (
            f"{desig}: d_nom_mm expected {d}, got {spec['d_nom_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_across_flats(self, desig, d, p, s, k):
        """s_af_mm must match ISO 4014 Table 2 nominal."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        assert spec["s_af_mm"] == pytest.approx(s, abs=_ABS_TOL), (
            f"{desig}: s_af_mm expected {s}, got {spec['s_af_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_head_height(self, desig, d, p, s, k):
        """k_head_mm must match ISO 4014 Table 2 nominal."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        assert spec["k_head_mm"] == pytest.approx(k, abs=_ABS_TOL), (
            f"{desig}: k_head_mm expected {k}, got {spec['k_head_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_circumscribed_circle_geometry(self, desig, d, p, s, k):
        """e = s / cos(30°) must hold for every bolt in catalog."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        e_expected = s / math.cos(math.radians(30.0))
        assert spec["e_circ_mm"] == pytest.approx(e_expected, abs=_MM_TOL), (
            f"{desig}: e_circ_mm expected {e_expected:.4f}, got {spec['e_circ_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_washer_face_diameter(self, desig, d, p, s, k):
        """d_washer_face = 1.5 × d_nom (VDI 2230 default)."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        assert spec["d_washer_face_mm"] == pytest.approx(1.5 * d, abs=_MM_TOL), (
            f"{desig}: d_washer_face_mm expected {1.5*d}, got {spec['d_washer_face_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,k", _ISO_BOLT_REF)
    def test_pitch(self, desig, d, p, s, k):
        """pitch_mm must match ISO 261 coarse-series nominal."""
        spec = lookup_hex_bolt(desig)
        assert spec is not None
        assert spec["pitch_mm"] == pytest.approx(p, abs=_ABS_TOL)

    def test_full_range_catalog_size(self):
        """HEX_BOLTS catalog must contain at least 15 M-sizes (M3–M64)."""
        assert len(HEX_BOLTS) >= 15

    def test_e_gt_s_for_all_bolts(self):
        """Circumscribed circle must always be larger than across-flats."""
        for desig, spec in HEX_BOLTS.items():
            assert spec["e_circ_mm"] > spec["s_af_mm"], (
                f"{desig}: e_circ_mm ({spec['e_circ_mm']}) ≤ s_af_mm ({spec['s_af_mm']})"
            )

    def test_head_height_increases_monotonically(self):
        """Larger bolts must have taller heads (coarse series)."""
        sizes = [
            ("M6", "M8"), ("M8", "M10"), ("M10", "M12"),
            ("M12", "M16"), ("M16", "M20"),
        ]
        for sm, lg in sizes:
            k_sm = HEX_BOLTS[sm]["k_head_mm"]
            k_lg = HEX_BOLTS[lg]["k_head_mm"]
            assert k_lg > k_sm, f"{lg} head height not > {sm}"

    def test_s_af_increases_monotonically(self):
        """Across-flats dimension must increase with bolt size."""
        sizes = sorted(HEX_BOLTS.keys(), key=lambda x: HEX_BOLTS[x]["d_nom_mm"])
        for i in range(len(sizes) - 1):
            sm, lg = sizes[i], sizes[i + 1]
            assert HEX_BOLTS[sm]["s_af_mm"] <= HEX_BOLTS[lg]["s_af_mm"], (
                f"s_af: {sm} ({HEX_BOLTS[sm]['s_af_mm']}) > {lg} ({HEX_BOLTS[lg]['s_af_mm']})"
            )

    def test_lookup_unknown_returns_none(self):
        assert lookup_hex_bolt("M999") is None

    def test_standard_field(self):
        """standard field must be 'ISO 4014' for all hex bolts."""
        for desig, spec in HEX_BOLTS.items():
            assert spec["standard"] == "ISO 4014", f"{desig}: standard={spec['standard']!r}"


# ===========================================================================
# B. ISO 4762 Socket Cap Screw — 5 specs
# ===========================================================================

class TestISO4762SocketCap:

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_designation_in_catalog(self, desig, d, p, dk, k, s):
        assert desig in SOCKET_CAPS, f"{desig} not found in SOCKET_CAPS"

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_head_diameter(self, desig, d, p, dk, k, s):
        """dk_head_mm must match ISO 4762 Table 1 nominal."""
        spec = lookup_socket_cap(desig)
        assert spec is not None
        assert spec["dk_head_mm"] == pytest.approx(dk, abs=_ABS_TOL), (
            f"{desig}: dk_head_mm expected {dk}, got {spec['dk_head_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_head_height(self, desig, d, p, dk, k, s):
        """k_head_mm must match ISO 4762 Table 1 nominal (= d_nom for M3–M24)."""
        spec = lookup_socket_cap(desig)
        assert spec is not None
        assert spec["k_head_mm"] == pytest.approx(k, abs=_ABS_TOL), (
            f"{desig}: k_head_mm expected {k}, got {spec['k_head_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_hex_key_size(self, desig, d, p, dk, k, s):
        """s_hex_key_mm must match ISO 4762 Table 1 nominal."""
        spec = lookup_socket_cap(desig)
        assert spec is not None
        assert spec["s_hex_key_mm"] == pytest.approx(s, abs=_ABS_TOL), (
            f"{desig}: s_hex_key_mm expected {s}, got {spec['s_hex_key_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_key_fits_inside_head(self, desig, d, p, dk, k, s):
        """Hex key must fit inside the head: s_hex_key < dk_head."""
        spec = lookup_socket_cap(desig)
        assert spec is not None
        assert spec["s_hex_key_mm"] < spec["dk_head_mm"], (
            f"{desig}: key ({spec['s_hex_key_mm']}) >= head diam ({spec['dk_head_mm']})"
        )

    @pytest.mark.parametrize("desig,d,p,dk,k,s", _SOCKET_CAP_REF)
    def test_head_height_equals_nominal_diameter(self, desig, d, p, dk, k, s):
        """ISO 4762 specifies k == d_nom for M3–M24 (head height = nominal dia)."""
        spec = lookup_socket_cap(desig)
        assert spec is not None
        assert spec["k_head_mm"] == pytest.approx(spec["d_nom_mm"], abs=_ABS_TOL), (
            f"{desig}: k_head_mm ({spec['k_head_mm']}) != d_nom_mm ({spec['d_nom_mm']})"
        )

    def test_standard_field(self):
        for desig, spec in SOCKET_CAPS.items():
            assert spec["standard"] == "ISO 4762"

    def test_lookup_unknown_returns_none(self):
        assert lookup_socket_cap("M999") is None


# ===========================================================================
# C. ISO 4032 Hex Nut — 5 specs
# ===========================================================================

class TestISO4032HexNut:

    @pytest.mark.parametrize("desig,d,p,s,m", _HEX_NUT_REF)
    def test_designation_in_catalog(self, desig, d, p, s, m):
        assert desig in HEX_NUTS, f"{desig} not found in HEX_NUTS"

    @pytest.mark.parametrize("desig,d,p,s,m", _HEX_NUT_REF)
    def test_across_flats(self, desig, d, p, s, m):
        """s_af_mm must match ISO 4032 Table 1 nominal."""
        spec = lookup_hex_nut(desig)
        assert spec is not None
        assert spec["s_af_mm"] == pytest.approx(s, abs=_ABS_TOL), (
            f"{desig}: s_af_mm expected {s}, got {spec['s_af_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,m", _HEX_NUT_REF)
    def test_nut_height(self, desig, d, p, s, m):
        """m_height_mm must match ISO 4032 Table 1 nominal."""
        spec = lookup_hex_nut(desig)
        assert spec is not None
        assert spec["m_height_mm"] == pytest.approx(m, abs=_ABS_TOL), (
            f"{desig}: m_height_mm expected {m}, got {spec['m_height_mm']}"
        )

    @pytest.mark.parametrize("desig,d,p,s,m", _HEX_NUT_REF)
    def test_nut_circumscribed_circle(self, desig, d, p, s, m):
        """e = s / cos(30°) for nuts too."""
        spec = lookup_hex_nut(desig)
        assert spec is not None
        e_expected = s / math.cos(math.radians(30.0))
        assert spec["e_circ_mm"] == pytest.approx(e_expected, abs=_MM_TOL)

    @pytest.mark.parametrize("desig,d,p,s,m", _HEX_NUT_REF)
    def test_nut_height_minimum(self, desig, d, p, s, m):
        """Nut height must be > 0.5 × d_nom (minimum thread engagement)."""
        spec = lookup_hex_nut(desig)
        assert spec is not None
        assert spec["m_height_mm"] > 0.5 * spec["d_nom_mm"], (
            f"{desig}: nut height {spec['m_height_mm']} <= 0.5 × {spec['d_nom_mm']}"
        )

    def test_bolt_nut_matching_wrench_size(self):
        """Paired bolt and nut (same M-designation) must share the same wrench size."""
        common = set(HEX_BOLTS) & set(HEX_NUTS)
        assert len(common) >= 10, "Should have at least 10 matching sizes"
        for desig in common:
            bolt_s = HEX_BOLTS[desig]["s_af_mm"]
            nut_s = HEX_NUTS[desig]["s_af_mm"]
            assert bolt_s == nut_s, (
                f"{desig}: bolt s_af={bolt_s} != nut s_af={nut_s}"
            )

    def test_full_range_catalog_size(self):
        assert len(HEX_NUTS) >= 15

    def test_nut_height_increases_monotonically(self):
        """Larger nuts are taller."""
        pairs = [("M6", "M8"), ("M8", "M10"), ("M10", "M12"), ("M12", "M16")]
        for sm, lg in pairs:
            m_sm = HEX_NUTS[sm]["m_height_mm"]
            m_lg = HEX_NUTS[lg]["m_height_mm"]
            assert m_lg > m_sm, f"{lg} nut height not > {sm}"

    def test_standard_field(self):
        for desig, spec in HEX_NUTS.items():
            assert spec["standard"] == "ISO 4032"

    def test_lookup_unknown_returns_none(self):
        assert lookup_hex_nut("M999") is None


# ===========================================================================
# D. ISO 7089 Washer — 5 specs
# ===========================================================================

class TestISO7089Washer:

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_designation_in_catalog(self, desig, d, d1, d2, h):
        assert desig in WASHERS, f"{desig} not found in WASHERS"

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_inner_diameter(self, desig, d, d1, d2, h):
        """d1_inner_mm must match ISO 7089 Table 1 nominal."""
        spec = lookup_washer(desig)
        assert spec is not None
        assert spec["d1_inner_mm"] == pytest.approx(d1, abs=_ABS_TOL), (
            f"{desig}: d1_inner_mm expected {d1}, got {spec['d1_inner_mm']}"
        )

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_outer_diameter(self, desig, d, d1, d2, h):
        """d2_outer_mm must match ISO 7089 Table 1 nominal."""
        spec = lookup_washer(desig)
        assert spec is not None
        assert spec["d2_outer_mm"] == pytest.approx(d2, abs=_ABS_TOL), (
            f"{desig}: d2_outer_mm expected {d2}, got {spec['d2_outer_mm']}"
        )

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_thickness(self, desig, d, d1, d2, h):
        """h_thick_mm must match ISO 7089 Table 1 nominal."""
        spec = lookup_washer(desig)
        assert spec is not None
        assert spec["h_thick_mm"] == pytest.approx(h, abs=_ABS_TOL), (
            f"{desig}: h_thick_mm expected {h}, got {spec['h_thick_mm']}"
        )

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_bore_larger_than_nominal(self, desig, d, d1, d2, h):
        """Bore must be larger than nominal thread diameter (clearance fit)."""
        spec = lookup_washer(desig)
        assert spec is not None
        assert spec["d1_inner_mm"] > spec["d_nom_mm"], (
            f"{desig}: bore {spec['d1_inner_mm']} <= d_nom {spec['d_nom_mm']}"
        )

    @pytest.mark.parametrize("desig,d,d1,d2,h", _WASHER_REF)
    def test_outer_greater_than_bore(self, desig, d, d1, d2, h):
        """Outer diameter must be greater than bore."""
        spec = lookup_washer(desig)
        assert spec is not None
        assert spec["d2_outer_mm"] > spec["d1_inner_mm"]

    def test_outer_at_least_1_5_nominal_for_all(self):
        """ISO 7089 normal-series: outer diameter ≥ 1.5 × d_nom for load distribution.
        The ISO 7089 table has d2 ≥ 1.5×d for all sizes (actual ratio is ~1.5–2.0×)."""
        for desig, spec in WASHERS.items():
            assert spec["d2_outer_mm"] >= 1.5 * spec["d_nom_mm"], (
                f"{desig}: outer {spec['d2_outer_mm']} < 1.5 × d_nom {spec['d_nom_mm']}"
            )

    def test_outer_increases_monotonically(self):
        """Larger nominal diameter means larger washer outer diameter."""
        pairs = [("M6", "M8"), ("M8", "M10"), ("M10", "M12"), ("M12", "M16")]
        for sm, lg in pairs:
            d2_sm = WASHERS[sm]["d2_outer_mm"]
            d2_lg = WASHERS[lg]["d2_outer_mm"]
            assert d2_lg > d2_sm, f"washer outer: {lg} not > {sm}"

    def test_standard_field(self):
        for desig, spec in WASHERS.items():
            assert spec["standard"] == "ISO 7089"

    def test_lookup_unknown_returns_none(self):
        assert lookup_washer("M999") is None


# ===========================================================================
# E. ASME B18.2.1 Hex Bolt — 5 specs
# ===========================================================================

class TestASMEB1821HexBolt:

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_designation_in_catalog(self, desig, d_in, W_in, H_in):
        assert desig in ASME_BOLTS, f"{desig} not found in ASME_BOLTS"

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_nominal_diameter_inches(self, desig, d_in, W_in, H_in):
        """d_nom_in must match ASME B18.2.1 Table 2 exactly."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        assert spec["d_nom_in"] == pytest.approx(d_in, abs=_ABS_TOL), (
            f"{desig}: d_nom_in expected {d_in}, got {spec['d_nom_in']}"
        )

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_width_across_flats_inches(self, desig, d_in, W_in, H_in):
        """W_af_in must match ASME B18.2.1 Table 2."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        assert spec["W_af_in"] == pytest.approx(W_in, abs=_ABS_TOL), (
            f"{desig}: W_af_in expected {W_in}, got {spec['W_af_in']}"
        )

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_head_height_inches(self, desig, d_in, W_in, H_in):
        """H_head_in must match ASME B18.2.1 Table 2."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        assert spec["H_head_in"] == pytest.approx(H_in, abs=_ABS_TOL), (
            f"{desig}: H_head_in expected {H_in}, got {spec['H_head_in']}"
        )

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_mm_conversion_diameter(self, desig, d_in, W_in, H_in):
        """d_nom_mm = d_nom_in × 25.4 (exact conversion)."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        assert spec["d_nom_mm"] == pytest.approx(d_in * 25.4, abs=_MM_TOL)

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_mm_conversion_width_across_flats(self, desig, d_in, W_in, H_in):
        """W_af_mm = W_af_in × 25.4."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        assert spec["W_af_mm"] == pytest.approx(W_in * 25.4, abs=_MM_TOL)

    @pytest.mark.parametrize("desig,d_in,W_in,H_in", _ASME_BOLT_REF)
    def test_circumscribed_circle_geometry(self, desig, d_in, W_in, H_in):
        """e_circ_mm = W_af_mm / cos(30°)."""
        spec = lookup_asme_bolt(desig)
        assert spec is not None
        e_expected = spec["W_af_mm"] / math.cos(math.radians(30.0))
        assert spec["e_circ_mm"] == pytest.approx(e_expected, abs=_MM_TOL)

    def test_standard_field(self):
        for desig, spec in ASME_BOLTS.items():
            assert spec["standard"] == "ASME B18.2.1"

    def test_lookup_unknown_returns_none(self):
        assert lookup_asme_bolt("3-8 UNC") is None


# ===========================================================================
# F. Hole-pattern integration
# ===========================================================================

class TestClearanceHole:

    def test_fine_clearance_greater_than_nominal(self):
        """Fine clearance hole must still be > d_nom (can't be tighter than shaft)."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            d_nom = HEX_BOLTS[desig]["d_nom_mm"]
            d_hole = clearance_hole_diameter(desig, fit="fine")
            assert d_hole > d_nom, f"{desig} fine: clearance {d_hole} <= d_nom {d_nom}"

    def test_normal_clearance_greater_than_fine(self):
        """Normal clearance must be ≥ fine clearance."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            d_fine = clearance_hole_diameter(desig, fit="fine")
            d_normal = clearance_hole_diameter(desig, fit="normal")
            assert d_normal >= d_fine, f"{desig}: normal {d_normal} < fine {d_fine}"

    def test_coarse_clearance_greatest(self):
        """Coarse clearance must be ≥ normal."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            d_normal = clearance_hole_diameter(desig, fit="normal")
            d_coarse = clearance_hole_diameter(desig, fit="coarse")
            assert d_coarse >= d_normal, f"{desig}: coarse {d_coarse} < normal {d_normal}"

    def test_washer_bore_matches_clearance_fine(self):
        """ISO 7089 bore is a 'fine' or 'normal' clearance; bore must be in range."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            d_fine = clearance_hole_diameter(desig, fit="fine")
            d_coarse = clearance_hole_diameter(desig, fit="coarse")
            d1 = WASHERS[desig]["d1_inner_mm"]
            assert d_fine <= d1 <= d_coarse + 1.0, (
                f"{desig}: washer bore {d1} outside clearance range [{d_fine}, {d_coarse+1.0}]"
            )

    def test_unknown_designation_returns_none(self):
        assert clearance_hole_diameter("M999") is None

    def test_default_fit_is_normal(self):
        """Calling without fit= arg should give same result as fit='normal'."""
        for desig in ("M6", "M16"):
            d_default = clearance_hole_diameter(desig)
            d_normal = clearance_hole_diameter(desig, fit="normal")
            assert d_default == d_normal


class TestBoltCirclePositions:

    def test_returns_correct_count(self):
        """bolt_circle_positions must return exactly n_bolts positions."""
        for n in (1, 2, 4, 6, 8, 12):
            positions = bolt_circle_positions(n, pcd_mm=100.0)
            assert len(positions) == n

    def test_positions_on_radius(self):
        """All positions must lie exactly on the pitch-circle radius."""
        pcd = 120.0
        r = pcd / 2.0
        for n in (3, 4, 6, 8):
            for x, y in bolt_circle_positions(n, pcd_mm=pcd):
                dist = math.hypot(x, y)
                assert abs(dist - r) < 1e-4, (
                    f"n={n}: point ({x:.3f},{y:.3f}) at r={dist:.4f}, expected {r}"
                )

    def test_equal_angular_spacing(self):
        """Adjacent bolt angles must be exactly 360/n degrees."""
        for n in (3, 4, 5, 6, 8):
            positions = bolt_circle_positions(n, pcd_mm=80.0)
            expected_angle = 360.0 / n
            for i in range(n):
                x0, y0 = positions[i]
                x1, y1 = positions[(i + 1) % n]
                a0 = math.degrees(math.atan2(y0, x0))
                a1 = math.degrees(math.atan2(y1, x1))
                diff = (a1 - a0) % 360.0
                assert abs(diff - expected_angle) < 1e-3, (
                    f"n={n}: angular step {diff:.4f}° != {expected_angle}°"
                )

    def test_start_angle_offset(self):
        """start_angle_deg must rotate the first bolt to that angle."""
        positions_0 = bolt_circle_positions(4, 100.0, start_angle_deg=0.0)
        positions_45 = bolt_circle_positions(4, 100.0, start_angle_deg=45.0)
        x0, y0 = positions_0[0]
        x45, y45 = positions_45[0]
        angle_0 = math.degrees(math.atan2(y0, x0))
        angle_45 = math.degrees(math.atan2(y45, x45))
        assert abs(angle_0 - 0.0) < 1e-9
        assert abs(angle_45 - 45.0) < 1e-9

    def test_single_bolt_at_origin_offset(self):
        """n_bolts=1 single bolt at (r, 0) for start_angle=0."""
        pcd = 80.0
        r = pcd / 2.0
        positions = bolt_circle_positions(1, pcd_mm=pcd)
        assert len(positions) == 1
        x, y = positions[0]
        assert abs(x - r) < 1e-6
        assert abs(y) < 1e-6

    def test_zero_n_bolts_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_positions(0, 100.0)

    def test_negative_pcd_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_positions(4, -100.0)

    def test_zero_pcd_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_positions(4, 0.0)


class TestBoltCirclePCD:

    def test_pcd_from_spacing_geometry(self):
        """PCD = spacing / sin(π/n) must match inverse geometry."""
        for n in (3, 4, 6, 8):
            pcd = 100.0
            positions = bolt_circle_positions(n, pcd_mm=pcd)
            x0, y0 = positions[0]
            x1, y1 = positions[1]
            spacing = math.hypot(x1 - x0, y1 - y0)
            pcd_calc = bolt_circle_pcd(n, spacing_mm=spacing)
            assert abs(pcd_calc - pcd) < 1e-3, (
                f"n={n}: PCD round-trip {pcd_calc:.4f} != {pcd}"
            )

    def test_known_4_bolt_pcd(self):
        """4-bolt square pattern: spacing=s, PCD = s / sin(45°) = s × √2."""
        spacing = 50.0
        pcd = bolt_circle_pcd(4, spacing_mm=spacing)
        expected = spacing * math.sqrt(2.0)
        assert abs(pcd - expected) / expected < 1e-6

    def test_known_6_bolt_pcd(self):
        """6-bolt hexagonal pattern: spacing=s, PCD = s (sin(π/6)=0.5, PCD=2s)."""
        spacing = 40.0
        pcd = bolt_circle_pcd(6, spacing_mm=spacing)
        # sin(π/6) = 0.5  →  PCD = spacing / 0.5 = 2 × spacing
        expected = 2.0 * spacing
        assert abs(pcd - expected) / expected < 1e-9

    def test_n_bolts_lt_2_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_pcd(1, 50.0)

    def test_negative_spacing_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_pcd(4, -50.0)

    def test_zero_spacing_raises(self):
        with pytest.raises(ValueError):
            bolt_circle_pcd(4, 0.0)


# ===========================================================================
# G. Cross-standard consistency checks
# ===========================================================================

class TestCrossStandardConsistency:

    def test_bolt_nut_washer_bore_vs_bolt_s_af(self):
        """Washer bore must be less than the bolt head's across-flats.
        The washer must fit under the bolt head bearing face."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            bolt = HEX_BOLTS[desig]
            washer = WASHERS[desig]
            assert washer["d1_inner_mm"] < bolt["s_af_mm"], (
                f"{desig}: washer bore {washer['d1_inner_mm']} >= bolt s_af {bolt['s_af_mm']}"
            )

    def test_washer_outer_covers_bolt_head_face(self):
        """Washer outer diameter must be at least as large as bolt washer-face."""
        for desig in ("M6", "M8", "M10", "M16", "M24"):
            bolt = HEX_BOLTS[desig]
            washer = WASHERS[desig]
            assert washer["d2_outer_mm"] >= bolt["d_washer_face_mm"], (
                f"{desig}: washer outer {washer['d2_outer_mm']} < "
                f"bolt washer-face {bolt['d_washer_face_mm']}"
            )

    def test_iso_bolt_nut_same_pitch(self):
        """Bolt and nut must have matching pitch (same coarse thread)."""
        for desig in ("M6", "M8", "M10", "M12", "M16", "M20", "M24"):
            bolt_p = HEX_BOLTS[desig]["pitch_mm"]
            nut_p = HEX_NUTS[desig]["pitch_mm"]
            assert bolt_p == pytest.approx(nut_p, abs=_ABS_TOL), (
                f"{desig}: bolt pitch {bolt_p} != nut pitch {nut_p}"
            )

    def test_bolt_head_height_exceeds_pitch(self):
        """Head height must be greater than one thread pitch (structural minimum)."""
        for desig, spec in HEX_BOLTS.items():
            assert spec["k_head_mm"] > spec["pitch_mm"], (
                f"{desig}: k_head {spec['k_head_mm']} <= pitch {spec['pitch_mm']}"
            )

    def test_nut_height_exceeds_pitch(self):
        """Nut height must be greater than one thread pitch."""
        for desig, spec in HEX_NUTS.items():
            assert spec["m_height_mm"] > spec["pitch_mm"], (
                f"{desig}: m_height {spec['m_height_mm']} <= pitch {spec['pitch_mm']}"
            )
