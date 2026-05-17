"""
materials_catalogue.py
======================

BIM material catalogue with citable reference values.

Sources
-------
- IS 456:2000       Indian Standard: Plain and Reinforced Concrete — Code of Practice
- AISC 360-22       Specification for Structural Steel Buildings
- ASTM A36          Standard Specification for Carbon Structural Steel
- ASTM A572-50      Standard Specification for High-Strength Low-Alloy
                    Columbium-Vanadium Structural Steel, Grade 50
- EN 1993-1-1:2005  Eurocode 3: Design of Steel Structures, Table 3.1
- ADM 2020          Aluminum Design Manual 2020 (Tables A.3.4, B.4.1)
- NDS 2018          National Design Specification for Wood Construction (Supplement
                    Table 4A)
- ASTM C1036-21     Standard Specification for Flat Glass
- ASTM C158-02      Standard Test Methods for Strength of Glass by Flexure
- ASTM C62-17       Standard Specification for Building Brick
- ASTM C90-22       Standard Specification for Loadbearing Concrete Masonry Units
- ACI 530-13        Building Code Requirements and Specification for Masonry
                    Structures
- EN 13501-1:2018   Fire classification of construction products and building
                    elements
- NIST SP 1018      Fire Dynamics Simulator (density reference data)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Unit helpers (SI base: Pa, kg)
# ---------------------------------------------------------------------------

MPa: float = 1.0e6   # 1 MPa in Pa
GPa: float = 1.0e9   # 1 GPa in Pa


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PBRAppearance:
    """Physically-based render appearance parameters."""
    base_color: Tuple[float, float, float]
    metallic: float
    roughness: float
    ior: float
    normal_map: Optional[str] = None
    opacity: float = 1.0
    emissive: Optional[Tuple[float, float, float]] = None


@dataclass
class StructuralProps:
    """Linear-elastic structural properties (SI: Pa)."""
    elastic_modulus: float    # E  [Pa]
    poisson_ratio: float      # ν  [–]
    yield_strength: float     # f_y or f_ck  [Pa]
    tensile_strength: float   # f_u  [Pa]
    shear_modulus: float      # G   [Pa]


@dataclass
class ThermalProps:
    """Thermal properties (SI)."""
    thermal_conductivity: float  # λ  [W/(m·K)]
    specific_heat: float         # c_p [J/(kg·K)]
    thermal_expansion: float     # α  [1/K]
    emissivity: float            # ε  [–]


@dataclass
class FireProps:
    """Fire-resistance classification."""
    rating_class: str    # e.g. "A1", "B", "E"
    fire_resistance_hours: float  # [h]


@dataclass
class BIMMaterial:
    """A single BIM material entry."""
    name: str
    category: str
    render_appearance: PBRAppearance
    structural: Optional[StructuralProps]
    thermal: Optional[ThermalProps]
    fire: Optional[FireProps]
    density: float           # ρ  [kg/m³]
    source: str              # authoritative citation


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _G(E: float, nu: float) -> float:
    """Isotropic shear modulus: G = E / (2(1 + ν))."""
    return E / (2.0 * (1.0 + nu))


def _concrete(grade_mpa: float) -> StructuralProps:
    """
    IS 456:2000 Cl.6.2.3.1: E_c = 5000 √f_ck MPa.
    ν = 0.20 (IS 456 / ACI 318-19).
    """
    fck = grade_mpa * MPa
    Ec = 5000.0 * math.sqrt(grade_mpa) * MPa
    nu = 0.20
    return StructuralProps(
        elastic_modulus=Ec,
        poisson_ratio=nu,
        yield_strength=fck,
        tensile_strength=fck * 0.1,      # ~0.1 f_ck tensile (nominal)
        shear_modulus=_G(Ec, nu),
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def _build_catalogue() -> dict[str, BIMMaterial]:
    cat: dict[str, BIMMaterial] = {}

    def add(mat: BIMMaterial) -> None:
        cat[mat.name] = mat

    # -----------------------------------------------------------------------
    # CONCRETE — IS 456:2000
    # -----------------------------------------------------------------------

    _concrete_fire = FireProps(rating_class="A1", fire_resistance_hours=4.0)
    _concrete_thermal = ThermalProps(
        thermal_conductivity=1.7,
        specific_heat=880.0,
        thermal_expansion=10e-6,
        emissivity=0.92,
    )

    for grade in (20, 30, 40, 50):
        add(BIMMaterial(
            name=f"concrete_m{grade}",
            category="concrete",
            render_appearance=PBRAppearance(
                base_color=(0.72, 0.72, 0.70),
                metallic=0.0,
                roughness=0.85,
                ior=1.50,
                opacity=1.0,
            ),
            structural=_concrete(float(grade)),
            thermal=_concrete_thermal,
            fire=_concrete_fire,
            density=2400.0,
            source="IS 456:2000 Table 2 (f_ck); IS 456 Cl.6.2.3.1 (E_c = 5000√f_ck MPa); EN 13501-1:2018 (Class A1)",
        ))

    # -----------------------------------------------------------------------
    # METAL — structural steels
    # -----------------------------------------------------------------------

    _steel_thermal = ThermalProps(
        thermal_conductivity=50.0,
        specific_heat=490.0,
        thermal_expansion=12e-6,
        emissivity=0.28,
    )
    _steel_fire = FireProps(rating_class="A1", fire_resistance_hours=0.5)
    _steel_pbr = PBRAppearance(
        base_color=(0.72, 0.72, 0.72),
        metallic=1.0,
        roughness=0.40,
        ior=2.50,
        opacity=1.0,
    )

    # ASTM A36 — F_y = 250 MPa, E = 200 GPa, ν = 0.30, ρ = 7850 kg/m³
    _nu_steel = 0.30
    _E_steel = 200.0 * GPa
    add(BIMMaterial(
        name="steel_a36",
        category="metal",
        render_appearance=_steel_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_steel,
            poisson_ratio=_nu_steel,
            yield_strength=248.0 * MPa,   # 36 ksi = 248.2 MPa
            tensile_strength=400.0 * MPa,  # 58 ksi = 400 MPa
            shear_modulus=_G(_E_steel, _nu_steel),
        ),
        thermal=_steel_thermal,
        fire=_steel_fire,
        density=7850.0,
        source="AISC 360-22; ASTM A36: F_y=36 ksi=248 MPa, E=200 GPa; NIST SP 1018 (ρ=7850 kg/m³)",
    ))

    # ASTM A572-50 — F_y = 345 MPa
    add(BIMMaterial(
        name="steel_a572_50",
        category="metal",
        render_appearance=_steel_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_steel,
            poisson_ratio=_nu_steel,
            yield_strength=345.0 * MPa,   # 50 ksi = 344.7 MPa
            tensile_strength=450.0 * MPa,  # 65 ksi = 448 MPa
            shear_modulus=_G(_E_steel, _nu_steel),
        ),
        thermal=_steel_thermal,
        fire=_steel_fire,
        density=7850.0,
        source="ASTM A572-50: F_y=50 ksi=345 MPa; AISC 360-22; NIST SP 1018",
    ))

    # EN 1993-1-1 S275 — f_y = 275 MPa
    add(BIMMaterial(
        name="steel_s275",
        category="metal",
        render_appearance=_steel_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_steel,
            poisson_ratio=_nu_steel,
            yield_strength=275.0 * MPa,
            tensile_strength=430.0 * MPa,
            shear_modulus=_G(_E_steel, _nu_steel),
        ),
        thermal=_steel_thermal,
        fire=_steel_fire,
        density=7850.0,
        source="EN 1993-1-1:2005 Table 3.1: S275 f_y=275 MPa; NIST SP 1018",
    ))

    # EN 1993-1-1 S355 — f_y = 355 MPa
    add(BIMMaterial(
        name="steel_s355",
        category="metal",
        render_appearance=_steel_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_steel,
            poisson_ratio=_nu_steel,
            yield_strength=355.0 * MPa,
            tensile_strength=510.0 * MPa,
            shear_modulus=_G(_E_steel, _nu_steel),
        ),
        thermal=_steel_thermal,
        fire=_steel_fire,
        density=7850.0,
        source="EN 1993-1-1:2005 Table 3.1: S355 f_y=355 MPa; NIST SP 1018",
    ))

    # -----------------------------------------------------------------------
    # METAL — aluminium alloys (ADM 2020)
    # -----------------------------------------------------------------------

    _alu_thermal = ThermalProps(
        thermal_conductivity=167.0,
        specific_heat=896.0,
        thermal_expansion=23.6e-6,
        emissivity=0.09,
    )
    _alu_fire = FireProps(rating_class="A1", fire_resistance_hours=0.5)
    _alu_pbr = PBRAppearance(
        base_color=(0.82, 0.83, 0.85),
        metallic=1.0,
        roughness=0.30,
        ior=2.00,
        opacity=1.0,
    )
    _E_alu = 68.9 * GPa   # ADM 2020
    _nu_alu = 0.33

    # 6061-T6 — F_y = 276 MPa, F_tu = 310 MPa (ADM 2020 Table A.3.4)
    add(BIMMaterial(
        name="aluminum_6061_t6",
        category="metal",
        render_appearance=_alu_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_alu,
            poisson_ratio=_nu_alu,
            yield_strength=276.0 * MPa,   # 40 ksi = 275.8 MPa
            tensile_strength=310.0 * MPa,  # 45 ksi = 310.3 MPa
            shear_modulus=_G(_E_alu, _nu_alu),
        ),
        thermal=_alu_thermal,
        fire=_alu_fire,
        density=2700.0,
        source="ADM 2020 Table A.3.4: 6061-T6 F_y=40 ksi=276 MPa, F_tu=45 ksi=310 MPa",
    ))

    # 5052-H32 — F_y = 193 MPa, F_tu = 228 MPa (ADM 2020 Table B.4.1)
    add(BIMMaterial(
        name="aluminum_5052_h32",
        category="metal",
        render_appearance=_alu_pbr,
        structural=StructuralProps(
            elastic_modulus=_E_alu,
            poisson_ratio=_nu_alu,
            yield_strength=193.0 * MPa,   # 28 ksi = 193.1 MPa
            tensile_strength=228.0 * MPa,  # 33 ksi = 227.5 MPa
            shear_modulus=_G(_E_alu, _nu_alu),
        ),
        thermal=_alu_thermal,
        fire=_alu_fire,
        density=2680.0,
        source="ADM 2020 Table B.4.1: 5052-H32 F_y=28 ksi=193 MPa, F_tu=33 ksi=228 MPa",
    ))

    # -----------------------------------------------------------------------
    # WOOD / TIMBER — NDS 2018
    # -----------------------------------------------------------------------

    _wood_fire = FireProps(rating_class="D", fire_resistance_hours=0.5)
    _wood_pbr_light = PBRAppearance(
        base_color=(0.76, 0.60, 0.42),
        metallic=0.0,
        roughness=0.75,
        ior=1.50,
        opacity=1.0,
    )
    _wood_pbr_dark = PBRAppearance(
        base_color=(0.55, 0.35, 0.18),
        metallic=0.0,
        roughness=0.80,
        ior=1.50,
        opacity=1.0,
    )

    # SPF (Spruce-Pine-Fir) — NDS 2018 Supplement Table 4A
    add(BIMMaterial(
        name="timber_spf",
        category="wood",
        render_appearance=_wood_pbr_light,
        structural=StructuralProps(
            elastic_modulus=9.0 * GPa,    # NDS 2018: E=1,300,000 psi ≈ 9 GPa
            poisson_ratio=0.37,
            yield_strength=9.7 * MPa,     # F_b = 1400 psi ≈ 9.7 MPa
            tensile_strength=5.5 * MPa,
            shear_modulus=0.56 * GPa,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.12,
            specific_heat=1700.0,
            thermal_expansion=5.0e-6,
            emissivity=0.90,
        ),
        fire=_wood_fire,
        density=420.0,
        source="NDS 2018 Supplement Table 4A: SPF E=1,300,000 psi; density ~420 kg/m³",
    ))

    # Douglas Fir-Larch — NDS 2018 Supplement Table 4A; E=11.0 GPa, ρ=530 kg/m³
    add(BIMMaterial(
        name="timber_doug_fir",
        category="wood",
        render_appearance=_wood_pbr_light,
        structural=StructuralProps(
            elastic_modulus=11.0 * GPa,   # NDS 2018: E=1,600,000 psi = 11.03 GPa
            poisson_ratio=0.37,
            yield_strength=12.4 * MPa,    # F_b = 1800 psi ≈ 12.4 MPa
            tensile_strength=7.6 * MPa,
            shear_modulus=0.69 * GPa,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.14,
            specific_heat=1700.0,
            thermal_expansion=5.0e-6,
            emissivity=0.90,
        ),
        fire=_wood_fire,
        density=530.0,
        source="NDS 2018 Supplement Table 4A: Douglas Fir-Larch E=1,600,000 psi; density 530 kg/m³",
    ))

    # Red Oak — NDS 2018 Supplement Table 4A
    add(BIMMaterial(
        name="timber_oak",
        category="wood",
        render_appearance=_wood_pbr_dark,
        structural=StructuralProps(
            elastic_modulus=12.5 * GPa,   # E=1,800,000 psi ≈ 12.4 GPa
            poisson_ratio=0.37,
            yield_strength=14.8 * MPa,    # F_b = 2150 psi ≈ 14.8 MPa
            tensile_strength=9.0 * MPa,
            shear_modulus=0.78 * GPa,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.18,
            specific_heat=1700.0,
            thermal_expansion=5.0e-6,
            emissivity=0.90,
        ),
        fire=_wood_fire,
        density=700.0,
        source="NDS 2018 Supplement Table 4A: Red Oak E=1,800,000 psi; density ~700 kg/m³",
    ))

    # -----------------------------------------------------------------------
    # MASONRY — ASTM C62 / ASTM C90 / ACI 530
    # -----------------------------------------------------------------------

    add(BIMMaterial(
        name="brick_clay",
        category="masonry",
        render_appearance=PBRAppearance(
            base_color=(0.72, 0.36, 0.25),
            metallic=0.0,
            roughness=0.88,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=15.0 * GPa,
            poisson_ratio=0.20,
            yield_strength=20.0 * MPa,   # f'm per ACI 530 (common brick)
            tensile_strength=2.0 * MPa,
            shear_modulus=_G(15.0 * GPa, 0.20),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.72,
            specific_heat=840.0,
            thermal_expansion=5.5e-6,
            emissivity=0.93,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=4.0),
        density=1900.0,
        source="ASTM C62-17: clay building brick; ACI 530-13: f'm typical; EN 13501-1:2018 A1",
    ))

    add(BIMMaterial(
        name="masonry_cmu_concrete",
        category="masonry",
        render_appearance=PBRAppearance(
            base_color=(0.65, 0.65, 0.62),
            metallic=0.0,
            roughness=0.90,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=17.0 * GPa,
            poisson_ratio=0.20,
            yield_strength=13.8 * MPa,   # f'm = 2000 psi typical per ACI 530
            tensile_strength=1.4 * MPa,
            shear_modulus=_G(17.0 * GPa, 0.20),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.88,
            specific_heat=880.0,
            thermal_expansion=10.0e-6,
            emissivity=0.92,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=4.0),
        density=1920.0,
        source="ASTM C90-22: normal-weight CMU density ~1920 kg/m³; ACI 530-13; EN 13501-1:2018 A1",
    ))

    # -----------------------------------------------------------------------
    # GLASS — ASTM C1036-21 / ASTM C158-02
    # -----------------------------------------------------------------------

    add(BIMMaterial(
        name="glass_annealed_float",
        category="glass",
        render_appearance=PBRAppearance(
            base_color=(0.82, 0.90, 0.90),
            metallic=0.0,
            roughness=0.05,
            ior=1.52,     # ASTM C1036-21 / sodalime literature
            opacity=0.08,
        ),
        structural=StructuralProps(
            elastic_modulus=70.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=45.0 * MPa,   # ASTM C158-02: modulus of rupture ~45 MPa
            tensile_strength=45.0 * MPa,
            shear_modulus=_G(70.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=1.0,
            specific_heat=840.0,
            thermal_expansion=9.0e-6,
            emissivity=0.84,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=0.0),
        density=2500.0,
        source="ASTM C1036-21: sodalime float glass, density 2500 kg/m³, IOR 1.52; ASTM C158-02",
    ))

    add(BIMMaterial(
        name="glass_tempered",
        category="glass",
        render_appearance=PBRAppearance(
            base_color=(0.82, 0.90, 0.90),
            metallic=0.0,
            roughness=0.04,
            ior=1.52,
            opacity=0.08,
        ),
        structural=StructuralProps(
            elastic_modulus=70.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=180.0 * MPa,  # ~4× annealed (ASTM C1036-21 heat-treated)
            tensile_strength=180.0 * MPa,
            shear_modulus=_G(70.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=1.0,
            specific_heat=840.0,
            thermal_expansion=9.0e-6,
            emissivity=0.84,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=0.0),
        density=2500.0,
        source="ASTM C1036-21 Type I Class 1 (heat-treated tempered): ~4× MOR of annealed glass",
    ))

    # -----------------------------------------------------------------------
    # INSULATION
    # -----------------------------------------------------------------------

    _ins_fire_a1 = FireProps(rating_class="A1", fire_resistance_hours=0.0)
    _ins_fire_e = FireProps(rating_class="E", fire_resistance_hours=0.0)

    add(BIMMaterial(
        name="insulation_rockwool",
        category="insulation",
        render_appearance=PBRAppearance(
            base_color=(0.82, 0.74, 0.58),
            metallic=0.0,
            roughness=0.95,
            ior=1.20,
            opacity=1.0,
        ),
        structural=None,
        thermal=ThermalProps(
            thermal_conductivity=0.036,
            specific_heat=840.0,
            thermal_expansion=12e-6,
            emissivity=0.94,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=0.0),
        density=40.0,
        source="EN ISO 10456:2007; ASTM C547: rockwool mineral wool λ≈0.036 W/(m·K); EN 13501-1 A1",
    ))

    add(BIMMaterial(
        name="insulation_eps",
        category="insulation",
        render_appearance=PBRAppearance(
            base_color=(0.96, 0.96, 0.96),
            metallic=0.0,
            roughness=0.90,
            ior=1.10,
            opacity=1.0,
        ),
        structural=None,
        thermal=ThermalProps(
            thermal_conductivity=0.038,
            specific_heat=1300.0,
            thermal_expansion=70e-6,
            emissivity=0.90,
        ),
        fire=_ins_fire_e,
        density=20.0,
        source="EN 13163:2012 EPS: λ≈0.038 W/(m·K), density 15–30 kg/m³; EN 13501-1 E",
    ))

    add(BIMMaterial(
        name="insulation_xps",
        category="insulation",
        render_appearance=PBRAppearance(
            base_color=(0.30, 0.65, 0.85),
            metallic=0.0,
            roughness=0.80,
            ior=1.10,
            opacity=1.0,
        ),
        structural=None,
        thermal=ThermalProps(
            thermal_conductivity=0.030,
            specific_heat=1500.0,
            thermal_expansion=70e-6,
            emissivity=0.90,
        ),
        fire=_ins_fire_e,
        density=30.0,
        source="EN 13164:2012 XPS: λ≈0.030 W/(m·K), density 25–45 kg/m³; EN 13501-1 E",
    ))

    add(BIMMaterial(
        name="insulation_fiberglass_batt",
        category="insulation",
        render_appearance=PBRAppearance(
            base_color=(0.95, 0.85, 0.40),
            metallic=0.0,
            roughness=0.95,
            ior=1.20,
            opacity=1.0,
        ),
        structural=None,
        thermal=ThermalProps(
            thermal_conductivity=0.040,
            specific_heat=840.0,
            thermal_expansion=10e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=0.0),
        density=12.0,
        source="ASTM C665: glass-fibre batt insulation λ≈0.040 W/(m·K); ASHRAE 2021 HOF Chapter 26",
    ))

    # -----------------------------------------------------------------------
    # STONE
    # -----------------------------------------------------------------------

    _stone_fire = FireProps(rating_class="A1", fire_resistance_hours=4.0)

    add(BIMMaterial(
        name="stone_granite",
        category="stone",
        render_appearance=PBRAppearance(
            base_color=(0.55, 0.50, 0.50),
            metallic=0.0,
            roughness=0.60,
            ior=1.55,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=70.0 * GPa,
            poisson_ratio=0.26,
            yield_strength=170.0 * MPa,   # UCS 130–220 MPa typical
            tensile_strength=14.0 * MPa,
            shear_modulus=_G(70.0 * GPa, 0.26),
        ),
        thermal=ThermalProps(
            thermal_conductivity=3.0,
            specific_heat=790.0,
            thermal_expansion=8.0e-6,
            emissivity=0.90,
        ),
        fire=_stone_fire,
        density=2700.0,
        source="ASTM C615-18: granite; Goodman 1989 Rock Mechanics (E, ν, UCS); EN 13501-1 A1",
    ))

    add(BIMMaterial(
        name="stone_marble",
        category="stone",
        render_appearance=PBRAppearance(
            base_color=(0.93, 0.93, 0.90),
            metallic=0.0,
            roughness=0.25,
            ior=1.55,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=55.0 * GPa,
            poisson_ratio=0.27,
            yield_strength=90.0 * MPa,    # UCS ~90 MPa typical
            tensile_strength=7.0 * MPa,
            shear_modulus=_G(55.0 * GPa, 0.27),
        ),
        thermal=ThermalProps(
            thermal_conductivity=2.5,
            specific_heat=880.0,
            thermal_expansion=6.0e-6,
            emissivity=0.90,
        ),
        fire=_stone_fire,
        density=2720.0,
        source="ASTM C503-19: marble; Goodman 1989 Rock Mechanics; EN 13501-1 A1",
    ))

    add(BIMMaterial(
        name="stone_limestone",
        category="stone",
        render_appearance=PBRAppearance(
            base_color=(0.85, 0.83, 0.75),
            metallic=0.0,
            roughness=0.70,
            ior=1.55,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=40.0 * GPa,
            poisson_ratio=0.25,
            yield_strength=55.0 * MPa,
            tensile_strength=5.0 * MPa,
            shear_modulus=_G(40.0 * GPa, 0.25),
        ),
        thermal=ThermalProps(
            thermal_conductivity=1.5,
            specific_heat=840.0,
            thermal_expansion=8.0e-6,
            emissivity=0.92,
        ),
        fire=_stone_fire,
        density=2400.0,
        source="ASTM C568-19: limestone; Winkler 1994 Stone in Architecture; EN 13501-1 A1",
    ))

    # -----------------------------------------------------------------------
    # MEMBRANE — roofing
    # -----------------------------------------------------------------------

    add(BIMMaterial(
        name="membrane_epdm",
        category="membrane",
        render_appearance=PBRAppearance(
            base_color=(0.10, 0.10, 0.10),
            metallic=0.0,
            roughness=0.85,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=0.002 * GPa,  # ~2 MPa rubber-like
            poisson_ratio=0.49,
            yield_strength=9.0 * MPa,
            tensile_strength=9.0 * MPa,
            shear_modulus=0.67e6,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.25,
            specific_heat=1000.0,
            thermal_expansion=160e-6,
            emissivity=0.93,
        ),
        fire=FireProps(rating_class="E", fire_resistance_hours=0.0),
        density=1150.0,
        source="ASTM D4637-15: EPDM roofing membrane, tensile ≥9 MPa; density ~1150 kg/m³",
    ))

    add(BIMMaterial(
        name="membrane_pvc",
        category="membrane",
        render_appearance=PBRAppearance(
            base_color=(0.85, 0.85, 0.82),
            metallic=0.0,
            roughness=0.75,
            ior=1.54,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=0.003 * GPa,  # ~3 MPa flexible PVC
            poisson_ratio=0.40,
            yield_strength=12.0 * MPa,
            tensile_strength=15.0 * MPa,
            shear_modulus=1.07e6,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.19,
            specific_heat=900.0,
            thermal_expansion=80e-6,
            emissivity=0.91,
        ),
        fire=FireProps(rating_class="B", fire_resistance_hours=0.0),
        density=1400.0,
        source="ASTM D4434-16: PVC roofing sheet, tensile ≥12 MPa; density ~1400 kg/m³",
    ))

    # -----------------------------------------------------------------------
    # BOARD — gypsum / cement
    # -----------------------------------------------------------------------

    add(BIMMaterial(
        name="board_drywall_gypsum",
        category="board",
        render_appearance=PBRAppearance(
            base_color=(0.96, 0.96, 0.95),
            metallic=0.0,
            roughness=0.85,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=2.5 * GPa,
            poisson_ratio=0.25,
            yield_strength=5.5 * MPa,
            tensile_strength=5.5 * MPa,
            shear_modulus=_G(2.5 * GPa, 0.25),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.25,
            specific_heat=1090.0,
            thermal_expansion=17e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="A2", fire_resistance_hours=1.0),
        density=800.0,
        source="ASTM C1396-21: gypsum board; ASTM C473-19 (flexural); EN 13501-1 A2",
    ))

    add(BIMMaterial(
        name="board_cement_fibre",
        category="board",
        render_appearance=PBRAppearance(
            base_color=(0.72, 0.72, 0.70),
            metallic=0.0,
            roughness=0.88,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=9.0 * GPa,
            poisson_ratio=0.20,
            yield_strength=18.0 * MPa,
            tensile_strength=18.0 * MPa,
            shear_modulus=_G(9.0 * GPa, 0.20),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.35,
            specific_heat=1050.0,
            thermal_expansion=10e-6,
            emissivity=0.91,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=2.0),
        density=1200.0,
        source="ISO 8336:2009: fibre-cement flat sheets; EN 13501-1 A1",
    ))

    # -----------------------------------------------------------------------
    # PLASTER — lime / cement
    # -----------------------------------------------------------------------

    add(BIMMaterial(
        name="plaster_lime",
        category="plaster",
        render_appearance=PBRAppearance(
            base_color=(0.96, 0.94, 0.88),
            metallic=0.0,
            roughness=0.80,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=5.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=2.0 * MPa,
            tensile_strength=1.0 * MPa,
            shear_modulus=_G(5.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.72,
            specific_heat=840.0,
            thermal_expansion=12e-6,
            emissivity=0.92,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=1.0),
        density=1600.0,
        source="BS EN 998-1:2016: rendering and plastering mortar (lime); EN 13501-1 A1",
    ))

    add(BIMMaterial(
        name="plaster_cement",
        category="plaster",
        render_appearance=PBRAppearance(
            base_color=(0.82, 0.82, 0.80),
            metallic=0.0,
            roughness=0.82,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=18.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=10.0 * MPa,
            tensile_strength=3.0 * MPa,
            shear_modulus=_G(18.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=1.0,
            specific_heat=880.0,
            thermal_expansion=12e-6,
            emissivity=0.92,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=1.5),
        density=1800.0,
        source="BS EN 998-1:2016: cement render mortar (GP); IS 1661:1972; EN 13501-1 A1",
    ))

    # -----------------------------------------------------------------------
    # Additional materials to reach ≥ 40 entries
    # -----------------------------------------------------------------------

    # METAL — stainless steel 304 (ASTM A240 / EN 1.4301)
    add(BIMMaterial(
        name="steel_stainless_304",
        category="metal",
        render_appearance=PBRAppearance(
            base_color=(0.80, 0.82, 0.83),
            metallic=1.0,
            roughness=0.25,
            ior=2.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=193.0 * GPa,
            poisson_ratio=0.29,
            yield_strength=215.0 * MPa,   # ASTM A240: min 30 ksi = 207 MPa (use 215 typical)
            tensile_strength=505.0 * MPa,  # ASTM A240: min 75 ksi = 517 MPa
            shear_modulus=_G(193.0 * GPa, 0.29),
        ),
        thermal=ThermalProps(
            thermal_conductivity=16.3,
            specific_heat=500.0,
            thermal_expansion=17.2e-6,
            emissivity=0.17,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=0.5),
        density=8000.0,
        source="ASTM A240-22: 304 stainless steel; EN 10088-2:2014 (1.4301); NIST JPCRD 14",
    ))

    # WOOD — southern yellow pine
    add(BIMMaterial(
        name="timber_southern_pine",
        category="wood",
        render_appearance=PBRAppearance(
            base_color=(0.80, 0.63, 0.38),
            metallic=0.0,
            roughness=0.78,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=12.4 * GPa,   # NDS 2018 Table 4B: Southern Pine No. 2, E=1,800,000 psi
            poisson_ratio=0.37,
            yield_strength=11.7 * MPa,    # F_b = 1700 psi
            tensile_strength=6.9 * MPa,
            shear_modulus=0.77 * GPa,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.14,
            specific_heat=1700.0,
            thermal_expansion=5.0e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="D", fire_resistance_hours=0.5),
        density=590.0,
        source="NDS 2018 Supplement Table 4B: Southern Pine No.2; density ~590 kg/m³",
    ))

    # MASONRY — sandstone
    add(BIMMaterial(
        name="stone_sandstone",
        category="stone",
        render_appearance=PBRAppearance(
            base_color=(0.88, 0.75, 0.55),
            metallic=0.0,
            roughness=0.80,
            ior=1.54,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=20.0 * GPa,
            poisson_ratio=0.25,
            yield_strength=40.0 * MPa,
            tensile_strength=4.0 * MPa,
            shear_modulus=_G(20.0 * GPa, 0.25),
        ),
        thermal=ThermalProps(
            thermal_conductivity=2.0,
            specific_heat=920.0,
            thermal_expansion=11.0e-6,
            emissivity=0.92,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=4.0),
        density=2200.0,
        source="ASTM C616-18: sandstone; Winkler 1994 Stone in Architecture; EN 13501-1 A1",
    ))

    # GLASS — laminated safety glass
    add(BIMMaterial(
        name="glass_laminated_pvb",
        category="glass",
        render_appearance=PBRAppearance(
            base_color=(0.82, 0.90, 0.88),
            metallic=0.0,
            roughness=0.04,
            ior=1.52,
            opacity=0.10,
        ),
        structural=StructuralProps(
            elastic_modulus=70.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=45.0 * MPa,
            tensile_strength=45.0 * MPa,
            shear_modulus=_G(70.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=1.0,
            specific_heat=840.0,
            thermal_expansion=9.0e-6,
            emissivity=0.84,
        ),
        fire=FireProps(rating_class="A2", fire_resistance_hours=0.0),
        density=2500.0,
        source="ASTM C1172-19: laminated architectural flat glass (PVB interlayer); EN 14449:2005",
    ))

    # INSULATION — polyisocyanurate (PIR) board
    add(BIMMaterial(
        name="insulation_pir",
        category="insulation",
        render_appearance=PBRAppearance(
            base_color=(0.92, 0.75, 0.30),
            metallic=0.0,
            roughness=0.85,
            ior=1.10,
            opacity=1.0,
        ),
        structural=None,
        thermal=ThermalProps(
            thermal_conductivity=0.022,
            specific_heat=1000.0,
            thermal_expansion=60e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="B", fire_resistance_hours=0.0),
        density=32.0,
        source="EN 13165:2012 PIR: λ≈0.022 W/(m·K), density 28–45 kg/m³; EN 13501-1 B",
    ))

    # MEMBRANE — TPO (thermoplastic polyolefin roofing)
    add(BIMMaterial(
        name="membrane_tpo",
        category="membrane",
        render_appearance=PBRAppearance(
            base_color=(0.94, 0.94, 0.92),
            metallic=0.0,
            roughness=0.70,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=0.005 * GPa,
            poisson_ratio=0.40,
            yield_strength=14.0 * MPa,
            tensile_strength=17.0 * MPa,
            shear_modulus=1.79e6,
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.22,
            specific_heat=1300.0,
            thermal_expansion=100e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="B", fire_resistance_hours=0.0),
        density=900.0,
        source="ASTM D6878-17: TPO roofing membrane, tensile ≥14 MPa; density ~900 kg/m³",
    ))

    # BOARD — oriented strand board (OSB/3)
    add(BIMMaterial(
        name="board_osb_3",
        category="board",
        render_appearance=PBRAppearance(
            base_color=(0.75, 0.62, 0.40),
            metallic=0.0,
            roughness=0.82,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=3.5 * GPa,
            poisson_ratio=0.30,
            yield_strength=11.0 * MPa,
            tensile_strength=6.0 * MPa,
            shear_modulus=_G(3.5 * GPa, 0.30),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.13,
            specific_heat=1700.0,
            thermal_expansion=6e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="D", fire_resistance_hours=0.5),
        density=600.0,
        source="EN 300:2006 OSB/3: E_m=3500 MPa, f_m=16 MPa; density ~600 kg/m³",
    ))

    # CONCRETE — reinforced concrete (generic, representative)
    add(BIMMaterial(
        name="concrete_reinforced",
        category="concrete",
        render_appearance=PBRAppearance(
            base_color=(0.65, 0.65, 0.63),
            metallic=0.0,
            roughness=0.85,
            ior=1.50,
            opacity=1.0,
        ),
        structural=_concrete(30.0),
        thermal=_concrete_thermal,
        fire=_concrete_fire,
        density=2500.0,
        source="IS 456:2000; ACI 318-19: reinforced normal-weight concrete, ρ=2500 kg/m³",
    ))

    # MASONRY — autoclaved aerated concrete (AAC) block
    add(BIMMaterial(
        name="masonry_aac_block",
        category="masonry",
        render_appearance=PBRAppearance(
            base_color=(0.92, 0.92, 0.90),
            metallic=0.0,
            roughness=0.80,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=2.0 * GPa,
            poisson_ratio=0.20,
            yield_strength=4.0 * MPa,
            tensile_strength=0.4 * MPa,
            shear_modulus=_G(2.0 * GPa, 0.20),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.16,
            specific_heat=1000.0,
            thermal_expansion=8.0e-6,
            emissivity=0.90,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=4.0),
        density=600.0,
        source="ASTM C1693-18: AAC masonry units; EN 771-4:2011; density 500–700 kg/m³; EN 13501-1 A1",
    ))

    # PLASTER — gypsum finish coat
    add(BIMMaterial(
        name="plaster_gypsum_finish",
        category="plaster",
        render_appearance=PBRAppearance(
            base_color=(0.97, 0.96, 0.94),
            metallic=0.0,
            roughness=0.60,
            ior=1.50,
            opacity=1.0,
        ),
        structural=StructuralProps(
            elastic_modulus=8.0 * GPa,
            poisson_ratio=0.22,
            yield_strength=6.0 * MPa,
            tensile_strength=2.0 * MPa,
            shear_modulus=_G(8.0 * GPa, 0.22),
        ),
        thermal=ThermalProps(
            thermal_conductivity=0.40,
            specific_heat=1090.0,
            thermal_expansion=17e-6,
            emissivity=0.92,
        ),
        fire=FireProps(rating_class="A1", fire_resistance_hours=1.0),
        density=1100.0,
        source="ASTM C28-00: gypsum plaster; BS EN 13279-1:2008; EN 13501-1 A1",
    ))

    return cat


CATALOGUE: dict[str, BIMMaterial] = _build_catalogue()


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

def find_material(name: str) -> dict:
    """
    Look up a material by name (case-insensitive).

    Returns::

        {"ok": True,  "material": <BIMMaterial>}   # found
        {"ok": False, "reason": <str>}              # not found
    """
    key = name.strip().lower()
    mat = CATALOGUE.get(key)
    if mat is not None:
        return {"ok": True, "material": mat}
    return {
        "ok": False,
        "reason": f"Material '{name}' not found in catalogue. "
                  f"Available keys: {sorted(CATALOGUE)[:10]} …",
    }


def list_by_category(category: str) -> list[BIMMaterial]:
    """
    Return all materials belonging to *category*, sorted by name.

    Returns an empty list for unknown categories.
    """
    matches = [m for m in CATALOGUE.values() if m.category == category]
    return sorted(matches, key=lambda m: m.name)
