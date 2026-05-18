"""
test_measured_pbr.py
====================

Tests for the measured PBR material library (T-214).

Run::

    PYTHONPATH=packages/kerf-core/src:packages/kerf-cad-core/src \
        python3 -m pytest packages/kerf-cad-core/tests/test_measured_pbr.py -x
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.materials.measured_pbr import (
    all_categories,
    by_category,
    catalogue,
    lookup,
    to_pbr_dict,
)
from kerf_cad_core.materials.measured_pbr_data import get_all_entries


# ---------------------------------------------------------------------------
# Catalogue size
# ---------------------------------------------------------------------------

class TestCatalogueSize:
    def test_at_least_50_entries(self):
        entries = get_all_entries()
        assert len(entries) >= 50, (
            f"Expected ≥ 50 entries, got {len(entries)}"
        )

    def test_catalogue_keys_match_entries(self):
        entries = get_all_entries()
        cat = catalogue()
        assert len(cat) == len(entries), (
            "catalogue() key count should equal data entry count"
        )


# ---------------------------------------------------------------------------
# Category coverage
# ---------------------------------------------------------------------------

class TestCategories:
    REQUIRED_CATEGORIES = {"jewelry", "automotive", "fabric", "organic", "special"}

    def test_all_required_categories_present(self):
        cats = set(all_categories())
        missing = self.REQUIRED_CATEGORIES - cats
        assert not missing, f"Missing categories: {missing}"

    def test_jewelry_has_multiple_entries(self):
        entries = by_category("jewelry")
        assert len(entries) >= 5

    def test_automotive_has_multiple_entries(self):
        entries = by_category("automotive")
        assert len(entries) >= 5

    def test_fabric_has_multiple_entries(self):
        entries = by_category("fabric")
        assert len(entries) >= 5

    def test_organic_has_multiple_entries(self):
        entries = by_category("organic")
        assert len(entries) >= 5

    def test_special_has_multiple_entries(self):
        entries = by_category("special")
        assert len(entries) >= 5

    def test_by_category_returns_sorted_list(self):
        entries = by_category("jewelry")
        names = [e["name"] for e in entries]
        assert names == sorted(names)

    def test_by_category_case_insensitive(self):
        lower = by_category("jewelry")
        upper = by_category("JEWELRY")
        mixed = by_category("Jewelry")
        assert lower == upper == mixed

    def test_by_category_unknown_returns_empty(self):
        assert by_category("nonexistent_category_xyz") == []


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------

class TestLookup:
    def test_lookup_exact_name(self):
        entry = lookup("gold_24k")
        assert entry["name"] == "gold_24k"

    def test_lookup_case_insensitive_upper(self):
        entry = lookup("GOLD_24K")
        assert entry["name"] == "gold_24k"

    def test_lookup_case_insensitive_mixed(self):
        entry = lookup("Gold_24K")
        assert entry["name"] == "gold_24k"

    def test_lookup_strips_whitespace(self):
        entry = lookup("  gold_24k  ")
        assert entry["name"] == "gold_24k"

    def test_lookup_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            lookup("completely_unknown_material_xyz")

    def test_lookup_returns_independent_copy(self):
        a = lookup("gold_24k")
        b = lookup("gold_24k")
        a["base_color"] = (0.0, 0.0, 0.0)
        assert b["base_color"] != (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Gold 24K — published reflectance
# Mathon et al. 2012: R(589 nm) ≈ (1.000, 0.766, 0.336) linear sRGB.
# -----------------------------------------------------------------------

class TestGold24K:
    _PUBLISHED = (1.000, 0.766, 0.336)
    _TOL = 0.01  # ±1% on each channel

    def test_base_color_near_published(self):
        entry = lookup("gold_24k")
        bc = entry["base_color"]
        for channel, pub, got in zip(("R", "G", "B"), self._PUBLISHED, bc):
            assert abs(got - pub) <= self._TOL, (
                f"gold_24k base_color[{channel}]: got {got:.4f}, "
                f"expected {pub:.4f} ± {self._TOL}"
            )

    def test_metalness_is_1(self):
        entry = lookup("gold_24k")
        assert entry["metalness"] == 1.0

    def test_category_is_jewelry(self):
        entry = lookup("gold_24k")
        assert entry["category"] == "jewelry"


# ---------------------------------------------------------------------------
# Silver metalness
# ---------------------------------------------------------------------------

class TestSilver:
    def test_sterling_metalness_is_1(self):
        entry = lookup("silver_sterling")
        assert entry["metalness"] == 1.0

    def test_fine_silver_metalness_is_1(self):
        entry = lookup("silver_fine")
        assert entry["metalness"] == 1.0


# ---------------------------------------------------------------------------
# Glass transmission
# ---------------------------------------------------------------------------

class TestGlass:
    def test_clear_glass_transmission_above_0_9(self):
        entry = lookup("glass_clear")
        assert entry["transmission"] > 0.9, (
            f"glass_clear transmission={entry['transmission']}, expected > 0.9"
        )

    def test_frosted_glass_transmission_present(self):
        entry = lookup("glass_frosted")
        assert 0.0 < entry["transmission"] < 1.0

    def test_dichroic_glass_has_sheen(self):
        entry = lookup("glass_dichroic")
        assert entry["sheen"] > 0.0


# ---------------------------------------------------------------------------
# Automotive
# ---------------------------------------------------------------------------

class TestAutomotive:
    def test_candy_red_has_clearcoat(self):
        entry = lookup("automotive_candy_red")
        assert entry["clearcoat"] > 0.0

    def test_chrome_high_metalness(self):
        entry = lookup("automotive_chrome")
        assert entry["metalness"] == 1.0

    def test_brushed_aluminum_has_anisotropy(self):
        entry = lookup("automotive_brushed_aluminum")
        assert entry["anisotropy"] > 0.0

    def test_carbon_fiber_has_clearcoat_and_anisotropy(self):
        entry = lookup("automotive_carbon_fiber")
        assert entry["clearcoat"] > 0.0
        assert entry["anisotropy"] > 0.0


# ---------------------------------------------------------------------------
# Fabric sheen
# ---------------------------------------------------------------------------

class TestFabric:
    def test_silk_has_sheen_and_anisotropy(self):
        entry = lookup("fabric_silk")
        assert entry["sheen"] > 0.0
        assert entry["anisotropy"] > 0.0

    def test_velvet_sheen_is_1(self):
        entry = lookup("fabric_velvet")
        assert entry["sheen"] == 1.0

    def test_denim_roughness_above_0_8(self):
        entry = lookup("fabric_denim")
        assert entry["roughness"] > 0.8


# ---------------------------------------------------------------------------
# Organic SSS
# ---------------------------------------------------------------------------

class TestOrganic:
    def test_skin_light_has_subsurface(self):
        entry = lookup("skin_light")
        assert entry["subsurface"] > 0.0

    def test_skin_subsurface_radius_channels_differ(self):
        entry = lookup("skin_light")
        r, g, b = entry["subsurface_radius"]
        # red channel scatters furthest in skin
        assert r > g > b, (
            f"Expected r > g > b for skin SSS radii, got ({r}, {g}, {b})"
        )

    def test_wax_has_subsurface(self):
        entry = lookup("wax")
        assert entry["subsurface"] > 0.0

    def test_jade_ior_above_1_6(self):
        entry = lookup("jade_nephrite")
        assert entry["ior"] > 1.6


# ---------------------------------------------------------------------------
# to_pbr_dict schema completeness
# ---------------------------------------------------------------------------

class TestToPbrDict:
    REQUIRED_KEYS = {
        "name",
        "category",
        "description",
        "base_color",
        "metalness",
        "roughness",
        "ior",
        "transmission",
        "clearcoat",
        "clearcoat_roughness",
        "sheen",
        "sheen_color",
        "anisotropy",
        "anisotropy_rotation",
        "subsurface",
        "subsurface_color",
        "subsurface_radius",
    }

    def test_all_required_keys_present(self):
        d = to_pbr_dict("gold_24k")
        missing = self.REQUIRED_KEYS - d.keys()
        assert not missing, f"to_pbr_dict missing keys: {missing}"

    def test_base_color_is_3_tuple(self):
        d = to_pbr_dict("platinum")
        assert len(d["base_color"]) == 3

    def test_all_entries_produce_valid_pbr_dict(self):
        entries = get_all_entries()
        for entry in entries:
            d = to_pbr_dict(entry["name"])  # type: ignore[arg-type]
            assert d["name"] == entry["name"]
            r, g, b = d["base_color"]
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0
            assert 0.0 <= d["metalness"] <= 1.0
            assert 0.0 <= d["roughness"] <= 1.0
            assert d["ior"] > 0.0
            assert 0.0 <= d["transmission"] <= 1.0
            assert 0.0 <= d["clearcoat"] <= 1.0
            assert 0.0 <= d["sheen"] <= 1.0
            assert 0.0 <= d["subsurface"] <= 1.0

    def test_to_pbr_dict_case_insensitive(self):
        a = to_pbr_dict("gold_24k")
        b = to_pbr_dict("GOLD_24K")
        assert a == b

    def test_to_pbr_dict_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            to_pbr_dict("nonexistent_xyz")


# ---------------------------------------------------------------------------
# Specific published values
# ---------------------------------------------------------------------------

class TestPublishedValues:
    def test_water_ior_near_1_333(self):
        entry = lookup("liquid_water")
        assert abs(entry["ior"] - 1.333) < 0.005

    def test_snow_ior_near_1_31(self):
        entry = lookup("snow")
        assert abs(entry["ior"] - 1.31) < 0.01

    def test_platinum_metalness_is_1(self):
        entry = lookup("platinum")
        assert entry["metalness"] == 1.0

    def test_velvet_category_is_fabric(self):
        entry = lookup("fabric_velvet")
        assert entry["category"] == "fabric"

    def test_skin_dark_category_is_organic(self):
        entry = lookup("skin_dark")
        assert entry["category"] == "organic"

    def test_glass_frosted_roughness_above_0_4(self):
        entry = lookup("glass_frosted")
        assert entry["roughness"] > 0.4

    def test_honey_transmission_is_set(self):
        entry = lookup("liquid_honey")
        assert entry["transmission"] > 0.0

    def test_marble_white_subsurface_set(self):
        entry = lookup("marble_white_carrara")
        assert entry["subsurface"] > 0.0

    def test_carbon_fiber_anisotropy_positive(self):
        entry = lookup("automotive_carbon_fiber")
        assert entry["anisotropy"] > 0.0

    def test_all_entries_have_description(self):
        for entry in get_all_entries():
            assert isinstance(entry.get("description"), str), (
                f"{entry['name']} missing 'description' field"
            )
            assert len(entry["description"]) > 0, (  # type: ignore[arg-type]
                f"{entry['name']} has empty description"
            )
