"""
test_materials_catalogue.py
===========================

Hermetic tests for kerf_bim.materials_catalogue with citable reference values.

All numeric tolerances are chosen conservatively (1 % relative) unless the
source gives an exact formula, in which case exact equivalence is checked.

Sources cited inline match the authoritative references embedded in the
module docstring and catalogue entries.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import os


# ---------------------------------------------------------------------------
# Lightweight module load (no kerf_core / FastAPI required)
# ---------------------------------------------------------------------------

def _load_catalogue():
    """Import materials_catalogue directly from the source tree."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_path = os.path.join(
        base, "src", "kerf_bim", "materials_catalogue.py"
    )
    spec = importlib.util.spec_from_file_location(
        "kerf_bim.materials_catalogue", src_path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kerf_bim.materials_catalogue"] = mod
    spec.loader.exec_module(mod)
    return mod


_mc = _load_catalogue()

BIMMaterial      = _mc.BIMMaterial
PBRAppearance    = _mc.PBRAppearance
StructuralProps  = _mc.StructuralProps
ThermalProps     = _mc.ThermalProps
FireProps        = _mc.FireProps
find_material    = _mc.find_material
list_by_category = _mc.list_by_category
CATALOGUE        = _mc.CATALOGUE
MPa              = _mc.MPa
GPa              = _mc.GPa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(val: float, ref: float, tol: float = 0.01) -> bool:
    """True if |val - ref| / ref ≤ tol."""
    return abs(val - ref) / ref <= tol


def _get(name: str) -> BIMMaterial:
    result = find_material(name)
    assert result["ok"], f"Material '{name}' not in catalogue: {result['reason']}"
    return result["material"]


# ---------------------------------------------------------------------------
# 1. Catalogue completeness
# ---------------------------------------------------------------------------

class TestCatalogueCompleteness:
    def test_minimum_40_materials(self):
        """Catalogue must contain at least 40 entries (task requirement)."""
        assert len(CATALOGUE) >= 40, f"Only {len(CATALOGUE)} materials found"

    def test_all_required_categories_present(self):
        cats = {m.category for m in CATALOGUE.values()}
        required = {"concrete", "metal", "wood", "masonry", "glass",
                    "insulation", "stone", "membrane", "board", "plaster"}
        missing = required - cats
        assert not missing, f"Missing categories: {missing}"

    def test_no_duplicate_names(self):
        names = [m.name for m in CATALOGUE.values()]
        assert len(names) == len(set(names)), "Duplicate material names found"

    def test_every_entry_has_source(self):
        for mat in CATALOGUE.values():
            assert mat.source.strip(), f"{mat.name} has no source citation"


# ---------------------------------------------------------------------------
# 2. Concrete — IS 456:2000
# ---------------------------------------------------------------------------

class TestConcreteIS456:
    """
    Reference: IS 456:2000 Table 2 (f_ck); IS 456 Cl.6.2.3.1 (E_c = 5000√f_ck MPa).
    """

    def test_m30_characteristic_strength(self):
        """IS 456 Table 2: f_ck = 30 MPa for M30."""
        mat = _get("concrete_m30")
        assert mat.structural is not None
        fck_MPa = mat.structural.yield_strength / MPa
        assert abs(fck_MPa - 30.0) < 0.01, f"f_ck = {fck_MPa} MPa, expected 30 MPa"

    def test_m30_elastic_modulus_is456_formula(self):
        """IS 456 Cl.6.2.3.1: E_c = 5000√f_ck MPa.  For M30: E_c ≈ 27386 MPa."""
        mat = _get("concrete_m30")
        Ec_MPa = mat.structural.elastic_modulus / MPa
        expected = 5000.0 * math.sqrt(30.0)   # ≈ 27386 MPa
        assert abs(Ec_MPa - expected) < 0.5, (
            f"E_c = {Ec_MPa:.1f} MPa, expected {expected:.1f} MPa"
        )

    def test_m20_characteristic_strength(self):
        """IS 456 Table 2: f_ck = 20 MPa for M20."""
        mat = _get("concrete_m20")
        fck_MPa = mat.structural.yield_strength / MPa
        assert abs(fck_MPa - 20.0) < 0.01

    def test_m40_elastic_modulus(self):
        """IS 456: E_c(M40) = 5000√40 ≈ 31623 MPa."""
        mat = _get("concrete_m40")
        Ec_MPa = mat.structural.elastic_modulus / MPa
        expected = 5000.0 * math.sqrt(40.0)
        assert abs(Ec_MPa - expected) < 0.5

    def test_m50_elastic_modulus(self):
        """IS 456: E_c(M50) = 5000√50 ≈ 35355 MPa."""
        mat = _get("concrete_m50")
        Ec_MPa = mat.structural.elastic_modulus / MPa
        expected = 5000.0 * math.sqrt(50.0)
        assert abs(Ec_MPa - expected) < 0.5

    def test_concrete_poisson_ratio(self):
        """IS 456 / ACI 318: ν = 0.20 for normal concrete."""
        mat = _get("concrete_m30")
        assert abs(mat.structural.poisson_ratio - 0.20) < 0.001

    def test_concrete_density(self):
        """IS 456 Table 1: normal-weight concrete 2400 kg/m³ (M20/M30)."""
        for grade in ("concrete_m20", "concrete_m30"):
            mat = _get(grade)
            assert abs(mat.density - 2400.0) < 1.0, (
                f"{grade} density {mat.density} ≠ 2400 kg/m³"
            )

    def test_concrete_non_metallic(self):
        """Concrete must not be metallic."""
        mat = _get("concrete_m30")
        assert mat.render_appearance.metallic == 0.0

    def test_concrete_rough_surface(self):
        """Concrete roughness must be high (> 0.7)."""
        mat = _get("concrete_m30")
        assert mat.render_appearance.roughness > 0.7

    def test_concrete_fire_class_A1(self):
        """EN 13501-1: concrete is non-combustible — class A1."""
        mat = _get("concrete_m30")
        assert mat.fire is not None
        assert mat.fire.rating_class == "A1"


# ---------------------------------------------------------------------------
# 3. Steel — AISC 360-22 / EN 1993-1-1
# ---------------------------------------------------------------------------

class TestSteelAISC:
    """
    References:
      AISC 360-22 / ASTM A36: F_y = 36 ksi = 248.2 MPa; E = 200 GPa.
      ASTM A572-50: F_y = 50 ksi = 344.7 MPa.
      EN 1993-1-1 Table 3.1: S275 f_y = 275 MPa; S355 f_y = 355 MPa.
      NIST SP 1018: density 7850 kg/m³.
    """

    def test_a36_yield_strength(self):
        """AISC / ASTM A36: F_y = 36 ksi = 248 MPa (within 1 %)."""
        mat = _get("steel_a36")
        fy_MPa = mat.structural.yield_strength / MPa
        assert _rel(fy_MPa, 248.0), f"F_y = {fy_MPa:.1f} MPa, expected 248 MPa"

    def test_a36_elastic_modulus(self):
        """AISC: E = 29000 ksi = 200 GPa."""
        mat = _get("steel_a36")
        E_GPa = mat.structural.elastic_modulus / GPa
        assert _rel(E_GPa, 200.0), f"E = {E_GPa:.1f} GPa, expected 200 GPa"

    def test_a36_density(self):
        """NIST SP 1018: ρ = 7850 kg/m³."""
        mat = _get("steel_a36")
        assert abs(mat.density - 7850.0) < 1.0

    def test_a572_50_yield_strength(self):
        """ASTM A572-50: F_y = 50 ksi ≈ 345 MPa."""
        mat = _get("steel_a572_50")
        fy_MPa = mat.structural.yield_strength / MPa
        assert _rel(fy_MPa, 345.0), f"F_y = {fy_MPa:.1f} MPa, expected 345 MPa"

    def test_s275_yield_strength(self):
        """EN 1993-1-1 Table 3.1: S275 f_y = 275 MPa."""
        mat = _get("steel_s275")
        fy_MPa = mat.structural.yield_strength / MPa
        assert abs(fy_MPa - 275.0) < 1.0

    def test_s355_yield_strength(self):
        """EN 1993-1-1 Table 3.1: S355 f_y = 355 MPa."""
        mat = _get("steel_s355")
        fy_MPa = mat.structural.yield_strength / MPa
        assert abs(fy_MPa - 355.0) < 1.0

    def test_steel_fully_metallic(self):
        """Structural steel must have metallic = 1.0 in render appearance."""
        for name in ("steel_a36", "steel_a572_50", "steel_s275", "steel_s355"):
            mat = _get(name)
            assert mat.render_appearance.metallic == 1.0, (
                f"{name}: metallic ≠ 1.0"
            )

    def test_steel_shear_modulus_isotropic(self):
        """G = E / (2(1+ν)) for isotropic steel.  Tolerance 1 %."""
        mat = _get("steel_a36")
        E = mat.structural.elastic_modulus
        nu = mat.structural.poisson_ratio
        G_expected = E / (2.0 * (1.0 + nu))
        G_actual = mat.structural.shear_modulus
        assert _rel(G_actual, G_expected), (
            f"G = {G_actual:.3e} Pa, expected {G_expected:.3e} Pa"
        )


# ---------------------------------------------------------------------------
# 4. Aluminium — Aluminum Design Manual 2020
# ---------------------------------------------------------------------------

class TestAluminumADM:
    """
    Reference: Aluminum Design Manual 2020 (ADM 2020) Tables A.3.4, B.4.1.
      6061-T6: F_y = 40 ksi = 276 MPa; F_tu = 45 ksi = 310 MPa.
      5052-H32: F_y = 28 ksi = 193 MPa; F_tu = 33 ksi = 228 MPa.
    """

    def test_6061_t6_yield(self):
        """ADM 2020 Table A.3.4: 6061-T6 F_y = 40 ksi = 276 MPa."""
        mat = _get("aluminum_6061_t6")
        fy_MPa = mat.structural.yield_strength / MPa
        assert _rel(fy_MPa, 276.0), f"F_y = {fy_MPa:.1f} MPa, expected 276 MPa"

    def test_6061_t6_tensile(self):
        """ADM 2020: 6061-T6 F_tu = 45 ksi = 310 MPa."""
        mat = _get("aluminum_6061_t6")
        fu_MPa = mat.structural.tensile_strength / MPa
        assert _rel(fu_MPa, 310.0), f"F_tu = {fu_MPa:.1f} MPa, expected 310 MPa"

    def test_5052_h32_yield(self):
        """ADM 2020: 5052-H32 F_y = 28 ksi = 193 MPa."""
        mat = _get("aluminum_5052_h32")
        fy_MPa = mat.structural.yield_strength / MPa
        assert _rel(fy_MPa, 193.0), f"F_y = {fy_MPa:.1f} MPa, expected 193 MPa"

    def test_aluminum_metallic(self):
        """Aluminium is a metal — metallic = 1.0."""
        for name in ("aluminum_6061_t6", "aluminum_5052_h32"):
            mat = _get(name)
            assert mat.render_appearance.metallic == 1.0


# ---------------------------------------------------------------------------
# 5. Timber — NDS 2018
# ---------------------------------------------------------------------------

class TestTimberNDS:
    """
    References: NDS 2018 Supplement Table 4A; NDS 2018 reference design values.
      Doug-fir: density 530 kg/m³; E = 11.0 GPa.
    """

    def test_doug_fir_density(self):
        """NDS 2018: Doug-fir density ≈ 530 kg/m³."""
        mat = _get("timber_doug_fir")
        assert abs(mat.density - 530.0) < 5.0

    def test_doug_fir_elastic_modulus(self):
        """NDS 2018: Doug-fir E = 11.0 GPa (reference modulus)."""
        mat = _get("timber_doug_fir")
        E_GPa = mat.structural.elastic_modulus / GPa
        assert _rel(E_GPa, 11.0), f"E = {E_GPa:.2f} GPa, expected 11.0 GPa"

    def test_timber_non_metallic(self):
        """Wood must not appear metallic."""
        for name in ("timber_spf", "timber_doug_fir", "timber_oak"):
            mat = _get(name)
            assert mat.render_appearance.metallic == 0.0


# ---------------------------------------------------------------------------
# 6. Glass — ASTM C1036-21
# ---------------------------------------------------------------------------

class TestGlassASTM:
    """
    References: ASTM C1036-21; ASTM C158-02 (modulus of rupture).
    """

    def test_float_glass_density(self):
        """ASTM C1036: sodalime float glass density 2500 kg/m³."""
        mat = _get("glass_annealed_float")
        assert abs(mat.density - 2500.0) < 1.0

    def test_float_glass_ior(self):
        """Standard sodalime glass IOR = 1.52 (ASTM C1036 / literature)."""
        mat = _get("glass_annealed_float")
        assert abs(mat.render_appearance.ior - 1.52) < 0.005

    def test_tempered_glass_higher_yield_than_annealed(self):
        """Tempered glass is ~4× stronger in bending than annealed glass."""
        annealed = _get("glass_annealed_float")
        tempered = _get("glass_tempered")
        ratio = (tempered.structural.yield_strength /
                 annealed.structural.yield_strength)
        assert ratio >= 3.0, f"Tempered/annealed strength ratio = {ratio:.2f}, expected ≥ 3"

    def test_glass_opacity_less_than_one(self):
        """Float glass must be partially transparent (opacity < 1.0)."""
        mat = _get("glass_annealed_float")
        assert mat.render_appearance.opacity < 1.0


# ---------------------------------------------------------------------------
# 7. Masonry — ASTM C62 / ASTM C90 / ACI 530
# ---------------------------------------------------------------------------

class TestMasonry:
    def test_clay_brick_category(self):
        """ASTM C62-17: clay brick is masonry."""
        mat = _get("brick_clay")
        assert mat.category == "masonry"

    def test_cmu_density(self):
        """ASTM C90-22: CMU normal-weight density ~1900 kg/m³."""
        mat = _get("masonry_cmu_concrete")
        assert 1800.0 <= mat.density <= 2000.0


# ---------------------------------------------------------------------------
# 8. Query API
# ---------------------------------------------------------------------------

class TestQueryAPI:
    def test_find_material_found(self):
        """find_material('concrete_m30') returns ok=True with the entry."""
        result = find_material("concrete_m30")
        assert result["ok"] is True
        mat = result["material"]
        assert isinstance(mat, BIMMaterial)
        assert mat.name == "concrete_m30"

    def test_find_material_case_insensitive(self):
        """Lookup is case-insensitive."""
        result = find_material("CONCRETE_M30")
        assert result["ok"] is True

    def test_find_material_missing_graceful(self):
        """Missing material returns ok=False with a reason string."""
        result = find_material("nonexistent_material_xyz")
        assert result["ok"] is False
        assert "reason" in result
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_list_by_category_metals(self):
        """list_by_category('metal') returns all metal entries (≥ 4)."""
        metals = list_by_category("metal")
        assert len(metals) >= 4
        for m in metals:
            assert m.category == "metal"

    def test_list_by_category_concrete(self):
        """list_by_category('concrete') returns all 4 concrete grades."""
        concretes = list_by_category("concrete")
        names = {m.name for m in concretes}
        expected = {"concrete_m20", "concrete_m30", "concrete_m40", "concrete_m50"}
        assert expected.issubset(names)

    def test_list_by_category_sorted_by_name(self):
        """Results are sorted alphabetically by name."""
        metals = list_by_category("metal")
        names = [m.name for m in metals]
        assert names == sorted(names)

    def test_list_by_category_unknown_returns_empty(self):
        """Unknown category yields empty list, not an error."""
        result = list_by_category("unknown_category_xyz")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_material_returns_correct_type(self):
        """All find_material hits return BIMMaterial instances."""
        for name in ("steel_a36", "timber_spf", "glass_annealed_float"):
            result = find_material(name)
            assert isinstance(result["material"], BIMMaterial)


# ---------------------------------------------------------------------------
# 9. Render appearance sanity checks
# ---------------------------------------------------------------------------

class TestRenderAppearance:
    def test_base_color_in_range(self):
        """All base_color components must be in [0, 1]."""
        for mat in CATALOGUE.values():
            r, g, b = mat.render_appearance.base_color
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0

    def test_metallic_in_range(self):
        for mat in CATALOGUE.values():
            assert 0.0 <= mat.render_appearance.metallic <= 1.0

    def test_roughness_in_range(self):
        for mat in CATALOGUE.values():
            assert 0.0 <= mat.render_appearance.roughness <= 1.0

    def test_opacity_in_range(self):
        for mat in CATALOGUE.values():
            assert 0.0 < mat.render_appearance.opacity <= 1.0

    def test_ior_physically_plausible(self):
        """IOR must be in [1.0, 3.0] for all construction materials."""
        for mat in CATALOGUE.values():
            assert 1.0 <= mat.render_appearance.ior <= 3.0, (
                f"{mat.name}: IOR = {mat.render_appearance.ior}"
            )

    def test_concrete_rough_not_metallic(self):
        """Concrete: metallic=0, roughness>0.7."""
        mat = _get("concrete_m30")
        assert mat.render_appearance.metallic == 0.0
        assert mat.render_appearance.roughness > 0.7

    def test_steel_metallic_1(self):
        """Steel metallic=1."""
        mat = _get("steel_a36")
        assert mat.render_appearance.metallic == 1.0
