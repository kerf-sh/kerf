"""
measured_pbr_data.py
====================

Raw catalogue entries for the measured PBR material library (T-214).

Extends the BIM catalogue (T-115) with jewelry, automotive, fabric, organic,
and special materials — aligned with three.js MeshPhysicalMaterial parameters.

Field semantics
---------------
base_color          : (r, g, b) linear-sRGB, 0..1
metalness           : 0.0 (dielectric) .. 1.0 (conductor)
roughness           : 0.0 (mirror) .. 1.0 (fully diffuse)
ior                 : refractive index at 589 nm
transmission        : 0.0 (opaque) .. 1.0 (fully transmissive)
clearcoat           : clearcoat layer weight 0..1
clearcoat_roughness : roughness of the clearcoat layer
sheen               : sheen layer weight 0..1 (fabric, velvet)
sheen_color         : (r, g, b) tint of the sheen lobe
anisotropy          : anisotropic specular elongation −1..1
anisotropy_rotation : rotation of the anisotropy axis [rad, 0..2π]
subsurface          : subsurface scattering weight 0..1
subsurface_color    : (r, g, b) SSS tint
subsurface_radius   : (r, g, b) scattering radii [mm] per-channel

Sources
-------
- Mathon et al. (2012) "Optical constants of jewelry alloys" — gold/silver/platinum
  reflectance at sodium D line (polished specimens).
- Palik, "Handbook of Optical Constants of Solids" Vol. 1/2 (1985/1991) —
  copper, titanium, chrome IOR/extinction.
- Ward, G.J. (1992) "Measuring and modeling anisotropic reflection" —
  brushed-metal anisotropy convention adopted in Cycles/three.js.
- Ghosh et al. (2010) "Practical modeling and acquisition of layered facial
  reflectance" — skin SSS radii (red/green/blue mm).
- Ngan et al. (2005) "Experimental analysis of BRDF models" — velvet sheen.
- Jakob et al. (2014) "Discrete stochastic microfacet models" — silk and
  fabric anisotropy.
- Weidlich & Wilkie (2007) "Arbitrarily Layered Micro-Facet Surfaces" —
  clearcoat formulation for automotive paints.
- GIA Gem Reference Guide (Liddicoat, 1995) — jade, marble IOR.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

RGB = Tuple[float, float, float]

EntryDict = Dict[str, object]


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _e(
    name: str,
    category: str,
    base_color: RGB,
    metalness: float,
    roughness: float,
    ior: float,
    *,
    transmission: float = 0.0,
    clearcoat: float = 0.0,
    clearcoat_roughness: float = 0.0,
    sheen: float = 0.0,
    sheen_color: RGB = (1.0, 1.0, 1.0),
    anisotropy: float = 0.0,
    anisotropy_rotation: float = 0.0,
    subsurface: float = 0.0,
    subsurface_color: RGB = (1.0, 1.0, 1.0),
    subsurface_radius: RGB = (1.0, 1.0, 1.0),
    description: str = "",
) -> EntryDict:
    return {
        "name": name,
        "category": category,
        "base_color": base_color,
        "metalness": metalness,
        "roughness": roughness,
        "ior": ior,
        "transmission": transmission,
        "clearcoat": clearcoat,
        "clearcoat_roughness": clearcoat_roughness,
        "sheen": sheen,
        "sheen_color": sheen_color,
        "anisotropy": anisotropy,
        "anisotropy_rotation": anisotropy_rotation,
        "subsurface": subsurface,
        "subsurface_color": subsurface_color,
        "subsurface_radius": subsurface_radius,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Catalogue entries
# ---------------------------------------------------------------------------

_ENTRIES: List[EntryDict] = [

    # -----------------------------------------------------------------------
    # JEWELRY — gold alloys
    # Reflectance: Mathon et al. 2012, Fig. 3 (polished specimens, R_D values
    # converted to linear sRGB via inverse 2.2-gamma).
    # -----------------------------------------------------------------------

    _e(
        "gold_24k",
        "jewelry",
        base_color=(1.000, 0.766, 0.336),
        metalness=1.0,
        roughness=0.05,
        ior=0.470,
        clearcoat=0.0,
        description="Pure 24-karat yellow gold — mirror-polish finish. "
                    "Reflectance from Mathon et al. 2012.",
    ),
    _e(
        "gold_18k_yellow",
        "jewelry",
        base_color=(0.965, 0.734, 0.371),
        metalness=1.0,
        roughness=0.07,
        ior=0.470,
        description="18-karat yellow gold alloy (75% Au). Mathon et al. 2012.",
    ),
    _e(
        "gold_14k_yellow",
        "jewelry",
        base_color=(0.940, 0.730, 0.412),
        metalness=1.0,
        roughness=0.09,
        ior=0.470,
        description="14-karat yellow gold alloy (58.5% Au). Mathon et al. 2012.",
    ),
    _e(
        "gold_18k_white",
        "jewelry",
        base_color=(0.917, 0.911, 0.892),
        metalness=1.0,
        roughness=0.06,
        ior=0.470,
        description="18-karat white gold (Pd-whitened). Mathon et al. 2012.",
    ),
    _e(
        "gold_18k_rose",
        "jewelry",
        base_color=(0.965, 0.700, 0.580),
        metalness=1.0,
        roughness=0.07,
        ior=0.470,
        description="18-karat rose gold (Au-Cu alloy). Mathon et al. 2012.",
    ),

    # -----------------------------------------------------------------------
    # JEWELRY — platinum & silver
    # -----------------------------------------------------------------------

    _e(
        "platinum",
        "jewelry",
        base_color=(0.860, 0.846, 0.832),
        metalness=1.0,
        roughness=0.06,
        ior=2.330,
        description="Platinum 950 alloy — high polish. Mathon et al. 2012; "
                    "Palik Vol. 2 (Pt complex IOR).",
    ),
    _e(
        "silver_sterling",
        "jewelry",
        base_color=(0.972, 0.960, 0.915),
        metalness=1.0,
        roughness=0.06,
        ior=0.135,
        description="Sterling silver 925 — polished. Mathon et al. 2012; "
                    "Palik Vol. 1 (Ag).",
    ),
    _e(
        "silver_fine",
        "jewelry",
        base_color=(0.985, 0.978, 0.945),
        metalness=1.0,
        roughness=0.05,
        ior=0.135,
        description="Fine silver 999 — mirror finish. Mathon et al. 2012.",
    ),

    # -----------------------------------------------------------------------
    # JEWELRY — titanium & copper
    # -----------------------------------------------------------------------

    _e(
        "titanium_jewelry",
        "jewelry",
        base_color=(0.610, 0.595, 0.585),
        metalness=1.0,
        roughness=0.15,
        ior=2.486,
        description="Grade 23 Ti-6Al-4V ELI jewelry grade — brushed finish. "
                    "Palik Vol. 2 (Ti).",
    ),
    _e(
        "copper_polished",
        "jewelry",
        base_color=(0.955, 0.638, 0.538),
        metalness=1.0,
        roughness=0.08,
        ior=0.469,
        description="Electrolytic polished copper. Palik Vol. 1 (Cu); "
                    "Mathon et al. 2012.",
    ),

    # -----------------------------------------------------------------------
    # AUTOMOTIVE — candy / special paint
    # Candy paints: deep saturated base + strong clearcoat (Weidlich & Wilkie
    # 2007; automotive OEM technical data).
    # -----------------------------------------------------------------------

    _e(
        "automotive_candy_red",
        "automotive",
        base_color=(0.70, 0.02, 0.02),
        metalness=0.0,
        roughness=0.40,
        ior=1.50,
        clearcoat=1.0,
        clearcoat_roughness=0.05,
        description="Candy-red automotive basecoat + lacquer clearcoat. "
                    "Weidlich & Wilkie 2007 layered model.",
    ),
    _e(
        "automotive_candy_blue",
        "automotive",
        base_color=(0.02, 0.08, 0.72),
        metalness=0.0,
        roughness=0.40,
        ior=1.50,
        clearcoat=1.0,
        clearcoat_roughness=0.05,
        description="Candy-blue automotive basecoat + lacquer clearcoat.",
    ),
    _e(
        "automotive_candy_green",
        "automotive",
        base_color=(0.04, 0.35, 0.04),
        metalness=0.0,
        roughness=0.42,
        ior=1.50,
        clearcoat=1.0,
        clearcoat_roughness=0.05,
        description="Candy-green automotive basecoat + lacquer clearcoat.",
    ),

    # -----------------------------------------------------------------------
    # AUTOMOTIVE — pearlescent / metallic flake
    # -----------------------------------------------------------------------

    _e(
        "automotive_pearlescent",
        "automotive",
        base_color=(0.94, 0.92, 0.88),
        metalness=0.0,
        roughness=0.35,
        ior=1.52,
        clearcoat=0.9,
        clearcoat_roughness=0.04,
        sheen=0.4,
        sheen_color=(1.0, 0.95, 0.90),
        description="Pearl-white automotive paint — TiO2 mica flake iridescence "
                    "approximated via sheen layer.",
    ),
    _e(
        "automotive_metallic_flake",
        "automotive",
        base_color=(0.50, 0.50, 0.52),
        metalness=0.8,
        roughness=0.30,
        ior=1.50,
        clearcoat=0.95,
        clearcoat_roughness=0.04,
        description="Silver metallic flake basecoat — aluminium flake in "
                    "resin binder; metalness blended.",
    ),

    # -----------------------------------------------------------------------
    # AUTOMOTIVE — carbon fiber, chrome, brushed aluminum
    # -----------------------------------------------------------------------

    _e(
        "automotive_carbon_fiber",
        "automotive",
        base_color=(0.05, 0.05, 0.06),
        metalness=0.0,
        roughness=0.15,
        ior=1.54,
        clearcoat=0.8,
        clearcoat_roughness=0.03,
        anisotropy=0.80,
        anisotropy_rotation=0.785,  # 45° — weave axis
        description="2×2 twill carbon-fibre weave + epoxy + clearcoat. "
                    "Anisotropy encodes weave direction.",
    ),
    _e(
        "automotive_chrome",
        "automotive",
        base_color=(0.85, 0.87, 0.90),
        metalness=1.0,
        roughness=0.03,
        ior=3.130,
        description="Electrolytic chrome plate — near-mirror finish. "
                    "Palik Vol. 2 (Cr).",
    ),
    _e(
        "automotive_brushed_aluminum",
        "automotive",
        base_color=(0.85, 0.86, 0.88),
        metalness=1.0,
        roughness=0.20,
        ior=1.390,
        anisotropy=0.70,
        anisotropy_rotation=0.0,
        description="Brushed 6061-T6 aluminium trim. Ward 1992 anisotropy "
                    "convention; Palik Vol. 1 (Al).",
    ),

    # -----------------------------------------------------------------------
    # AUTOMOTIVE — leather
    # -----------------------------------------------------------------------

    _e(
        "automotive_leather_smooth",
        "automotive",
        base_color=(0.12, 0.06, 0.03),
        metalness=0.0,
        roughness=0.45,
        ior=1.52,
        sheen=0.3,
        sheen_color=(0.20, 0.12, 0.08),
        subsurface=0.05,
        subsurface_color=(0.20, 0.10, 0.06),
        subsurface_radius=(1.5, 0.8, 0.4),
        description="Smooth automotive leather — dark brown. Sheen accounts "
                    "for surface sheen; light SSS for hide depth.",
    ),
    _e(
        "automotive_leather_perforated",
        "automotive",
        base_color=(0.08, 0.04, 0.02),
        metalness=0.0,
        roughness=0.55,
        ior=1.52,
        sheen=0.2,
        sheen_color=(0.15, 0.08, 0.05),
        description="Perforated automotive bucket-seat leather — matte variant.",
    ),

    # -----------------------------------------------------------------------
    # FABRIC
    # Fabric sheen / anisotropy: Ngan et al. 2005; Jakob et al. 2014.
    # -----------------------------------------------------------------------

    _e(
        "fabric_denim",
        "fabric",
        base_color=(0.06, 0.12, 0.30),
        metalness=0.0,
        roughness=0.88,
        ior=1.46,
        sheen=0.6,
        sheen_color=(0.08, 0.15, 0.35),
        anisotropy=0.3,
        anisotropy_rotation=1.5708,  # 90° — weft thread direction
        description="Indigo 14-oz selvedge denim — cotton twill weave. "
                    "Sheen from Jakob et al. 2014.",
    ),
    _e(
        "fabric_silk",
        "fabric",
        base_color=(0.95, 0.92, 0.82),
        metalness=0.0,
        roughness=0.25,
        ior=1.55,
        sheen=0.8,
        sheen_color=(1.0, 0.97, 0.90),
        anisotropy=0.7,
        anisotropy_rotation=0.0,
        description="Natural silk charmeuse — satin weave, high anisotropy. "
                    "Jakob et al. 2014.",
    ),
    _e(
        "fabric_velvet",
        "fabric",
        base_color=(0.30, 0.03, 0.08),
        metalness=0.0,
        roughness=0.95,
        ior=1.46,
        sheen=1.0,
        sheen_color=(0.50, 0.05, 0.12),
        description="Crushed velvet — pile fabric with strong retro-reflective "
                    "sheen. Ngan et al. 2005.",
    ),
    _e(
        "fabric_cotton",
        "fabric",
        base_color=(0.92, 0.90, 0.86),
        metalness=0.0,
        roughness=0.92,
        ior=1.46,
        sheen=0.3,
        sheen_color=(0.95, 0.93, 0.88),
        description="Plain-weave white cotton shirting — diffuse with slight "
                    "fibre sheen.",
    ),
    _e(
        "fabric_wool",
        "fabric",
        base_color=(0.65, 0.55, 0.42),
        metalness=0.0,
        roughness=0.96,
        ior=1.53,
        sheen=0.5,
        sheen_color=(0.70, 0.60, 0.46),
        subsurface=0.02,
        subsurface_color=(0.70, 0.60, 0.46),
        subsurface_radius=(0.5, 0.3, 0.2),
        description="Worsted wool suiting — medium-grey. Sheen from fibre "
                    "scales; micro-SSS for yarn depth.",
    ),
    _e(
        "fabric_linen",
        "fabric",
        base_color=(0.82, 0.76, 0.58),
        metalness=0.0,
        roughness=0.93,
        ior=1.47,
        sheen=0.25,
        sheen_color=(0.85, 0.80, 0.62),
        anisotropy=0.2,
        anisotropy_rotation=0.0,
        description="Natural linen — plain-weave bast fibre; warm-beige tint.",
    ),

    # -----------------------------------------------------------------------
    # ORGANIC — skin
    # Skin SSS radii: Ghosh et al. 2010, Table 1 (mm, linear values).
    # -----------------------------------------------------------------------

    _e(
        "skin_light",
        "organic",
        base_color=(0.93, 0.70, 0.56),
        metalness=0.0,
        roughness=0.55,
        ior=1.40,
        clearcoat=0.15,
        clearcoat_roughness=0.30,
        subsurface=0.80,
        subsurface_color=(0.98, 0.60, 0.40),
        subsurface_radius=(5.0, 2.5, 1.0),
        description="Fair Caucasian skin tone. SSS radii from Ghosh et al. 2010. "
                    "Thin clearcoat approximates oil-film on skin surface.",
    ),
    _e(
        "skin_medium",
        "organic",
        base_color=(0.72, 0.47, 0.32),
        metalness=0.0,
        roughness=0.58,
        ior=1.40,
        clearcoat=0.12,
        clearcoat_roughness=0.30,
        subsurface=0.75,
        subsurface_color=(0.80, 0.42, 0.25),
        subsurface_radius=(4.5, 2.0, 0.8),
        description="Medium olive/brown skin tone. Ghosh et al. 2010.",
    ),
    _e(
        "skin_dark",
        "organic",
        base_color=(0.25, 0.14, 0.07),
        metalness=0.0,
        roughness=0.60,
        ior=1.40,
        clearcoat=0.10,
        clearcoat_roughness=0.35,
        subsurface=0.60,
        subsurface_color=(0.35, 0.18, 0.09),
        subsurface_radius=(3.5, 1.5, 0.6),
        description="Deep brown skin tone. Ghosh et al. 2010.",
    ),

    # -----------------------------------------------------------------------
    # ORGANIC — wax, soap
    # -----------------------------------------------------------------------

    _e(
        "wax",
        "organic",
        base_color=(0.98, 0.92, 0.72),
        metalness=0.0,
        roughness=0.20,
        ior=1.44,
        transmission=0.0,
        subsurface=0.70,
        subsurface_color=(1.0, 0.95, 0.78),
        subsurface_radius=(8.0, 6.0, 3.0),
        description="Beeswax / paraffin candle body — translucent SSS material.",
    ),
    _e(
        "soap",
        "organic",
        base_color=(0.90, 0.88, 0.82),
        metalness=0.0,
        roughness=0.30,
        ior=1.46,
        transmission=0.25,
        subsurface=0.50,
        subsurface_color=(0.92, 0.90, 0.84),
        subsurface_radius=(3.0, 2.5, 2.0),
        description="Glycerin bar soap — milky semi-translucent.",
    ),

    # -----------------------------------------------------------------------
    # ORGANIC — jade, marble variants
    # IOR from GIA Gem Reference Guide (Liddicoat 1995).
    # -----------------------------------------------------------------------

    _e(
        "jade_nephrite",
        "organic",
        base_color=(0.20, 0.55, 0.28),
        metalness=0.0,
        roughness=0.25,
        ior=1.62,
        subsurface=0.30,
        subsurface_color=(0.25, 0.65, 0.32),
        subsurface_radius=(1.5, 1.2, 0.8),
        description="Nephrite jade — waxy translucent green. GIA gem optics; "
                    "SSS for translucency depth.",
    ),
    _e(
        "marble_white_carrara",
        "organic",
        base_color=(0.96, 0.96, 0.95),
        metalness=0.0,
        roughness=0.18,
        ior=1.55,
        subsurface=0.20,
        subsurface_color=(0.98, 0.97, 0.96),
        subsurface_radius=(2.0, 1.8, 1.5),
        description="White Carrara marble — polished. GIA (1995); Palik Vol. 2 "
                    "(calcite IOR 1.55). SSS for depth under polish.",
    ),
    _e(
        "marble_nero_marquina",
        "organic",
        base_color=(0.04, 0.04, 0.04),
        metalness=0.0,
        roughness=0.15,
        ior=1.55,
        subsurface=0.05,
        subsurface_color=(0.06, 0.05, 0.05),
        subsurface_radius=(0.5, 0.4, 0.3),
        description="Nero Marquina black marble — high-gloss polished.",
    ),
    _e(
        "marble_verde_alpi",
        "organic",
        base_color=(0.10, 0.35, 0.18),
        metalness=0.0,
        roughness=0.16,
        ior=1.55,
        subsurface=0.10,
        subsurface_color=(0.12, 0.40, 0.20),
        subsurface_radius=(1.0, 0.8, 0.5),
        description="Verde Alpi green serpentine marble — polished.",
    ),

    # -----------------------------------------------------------------------
    # SPECIAL — glass variants
    # IOR: sodalime 1.52 (ASTM C1036-21).
    # -----------------------------------------------------------------------

    _e(
        "glass_clear",
        "special",
        base_color=(0.95, 0.97, 0.98),
        metalness=0.0,
        roughness=0.02,
        ior=1.52,
        transmission=0.97,
        description="Clear sodalime float glass — near-perfect transmission. "
                    "ASTM C1036-21.",
    ),
    _e(
        "glass_frosted",
        "special",
        base_color=(0.88, 0.90, 0.92),
        metalness=0.0,
        roughness=0.55,
        ior=1.52,
        transmission=0.82,
        description="Acid-etched / sandblasted frosted glass — diffuse "
                    "transmission via roughness.",
    ),
    _e(
        "glass_dichroic",
        "special",
        base_color=(0.60, 0.85, 0.95),
        metalness=0.0,
        roughness=0.04,
        ior=1.52,
        transmission=0.70,
        clearcoat=0.8,
        clearcoat_roughness=0.02,
        sheen=0.6,
        sheen_color=(0.80, 0.20, 0.90),
        description="Dichroic glass — thin-film interference iridescence "
                    "approximated by sheen layer.",
    ),

    # -----------------------------------------------------------------------
    # SPECIAL — liquids
    # -----------------------------------------------------------------------

    _e(
        "liquid_water",
        "special",
        base_color=(0.85, 0.92, 0.98),
        metalness=0.0,
        roughness=0.03,
        ior=1.333,
        transmission=0.98,
        description="Still water surface at 20 °C — IOR from NIST data.",
    ),
    _e(
        "liquid_oil",
        "special",
        base_color=(0.90, 0.82, 0.50),
        metalness=0.0,
        roughness=0.04,
        ior=1.470,
        transmission=0.75,
        description="Vegetable / mineral oil — amber tint; IOR ~1.47 (typical "
                    "for soybean / paraffin oil).",
    ),
    _e(
        "liquid_honey",
        "special",
        base_color=(0.88, 0.58, 0.08),
        metalness=0.0,
        roughness=0.06,
        ior=1.484,
        transmission=0.60,
        subsurface=0.20,
        subsurface_color=(0.90, 0.62, 0.10),
        subsurface_radius=(2.0, 1.5, 0.8),
        description="Raw honey — viscous amber; IOR ~1.484 (USDA measured). "
                    "SSS for depth in thick layer.",
    ),

    # -----------------------------------------------------------------------
    # SPECIAL — foam, snow, sand
    # -----------------------------------------------------------------------

    _e(
        "foam",
        "special",
        base_color=(0.96, 0.96, 0.96),
        metalness=0.0,
        roughness=0.98,
        ior=1.10,
        subsurface=0.35,
        subsurface_color=(0.97, 0.97, 0.97),
        subsurface_radius=(3.0, 3.0, 3.0),
        description="Open-cell polyurethane foam — highly diffuse with micro SSS "
                    "through cell walls.",
    ),
    _e(
        "snow",
        "special",
        base_color=(0.97, 0.98, 1.00),
        metalness=0.0,
        roughness=0.95,
        ior=1.31,
        transmission=0.15,
        subsurface=0.60,
        subsurface_color=(0.95, 0.97, 1.00),
        subsurface_radius=(6.0, 7.0, 8.5),
        description="Fresh compacted snow — IOR 1.31 (ice crystal Hallett 1965). "
                    "Volumetric SSS for depth.",
    ),
    _e(
        "sand_dry",
        "special",
        base_color=(0.82, 0.74, 0.55),
        metalness=0.0,
        roughness=0.98,
        ior=1.55,
        description="Dry beach sand — quartz grains; Lambertian-like surface. "
                    "IOR of fused quartz (Palik Vol. 1).",
    ),

    # -----------------------------------------------------------------------
    # Additional JEWELRY entries
    # -----------------------------------------------------------------------

    _e(
        "gold_24k_brushed",
        "jewelry",
        base_color=(1.000, 0.766, 0.336),
        metalness=1.0,
        roughness=0.22,
        ior=0.470,
        anisotropy=0.65,
        anisotropy_rotation=0.0,
        description="24-karat gold — hairline-brushed finish. Anisotropy from "
                    "Ward 1992; reflectance Mathon et al. 2012.",
    ),
    _e(
        "silver_oxidised",
        "jewelry",
        base_color=(0.35, 0.33, 0.30),
        metalness=0.8,
        roughness=0.60,
        ior=0.135,
        description="Sterling silver with patina oxidation — reduced reflectance. "
                    "Mathon et al. 2012.",
    ),

    # -----------------------------------------------------------------------
    # Additional AUTOMOTIVE entries
    # -----------------------------------------------------------------------

    _e(
        "automotive_matte_black",
        "automotive",
        base_color=(0.02, 0.02, 0.02),
        metalness=0.0,
        roughness=0.92,
        ior=1.50,
        description="Matte black automotive wrap / paint — near-zero gloss.",
    ),
    _e(
        "automotive_satin_silver",
        "automotive",
        base_color=(0.78, 0.78, 0.80),
        metalness=0.6,
        roughness=0.45,
        ior=1.50,
        clearcoat=0.5,
        clearcoat_roughness=0.15,
        description="Satin silver automotive trim — partial metalness, "
                    "semi-gloss clearcoat.",
    ),

    # -----------------------------------------------------------------------
    # Additional FABRIC entries
    # -----------------------------------------------------------------------

    _e(
        "fabric_satin",
        "fabric",
        base_color=(0.88, 0.82, 0.74),
        metalness=0.0,
        roughness=0.18,
        ior=1.55,
        sheen=0.7,
        sheen_color=(0.92, 0.87, 0.78),
        anisotropy=0.75,
        anisotropy_rotation=0.0,
        description="Silk-satin weave — very low roughness, high anisotropy. "
                    "Jakob et al. 2014.",
    ),
    _e(
        "fabric_burlap",
        "fabric",
        base_color=(0.60, 0.50, 0.32),
        metalness=0.0,
        roughness=0.97,
        ior=1.47,
        sheen=0.15,
        sheen_color=(0.65, 0.54, 0.34),
        description="Jute burlap — coarse open-weave vegetable fibre.",
    ),

    # -----------------------------------------------------------------------
    # Additional ORGANIC entries
    # -----------------------------------------------------------------------

    _e(
        "organic_amber",
        "organic",
        base_color=(0.92, 0.55, 0.10),
        metalness=0.0,
        roughness=0.10,
        ior=1.540,
        transmission=0.70,
        subsurface=0.30,
        subsurface_color=(0.94, 0.60, 0.14),
        subsurface_radius=(4.0, 2.5, 1.0),
        description="Fossil amber — warm orange-yellow; GIA Gem Reference Guide "
                    "(Liddicoat 1995) IOR 1.54.",
    ),
    _e(
        "organic_cork",
        "organic",
        base_color=(0.72, 0.56, 0.34),
        metalness=0.0,
        roughness=0.96,
        ior=1.45,
        subsurface=0.10,
        subsurface_color=(0.75, 0.58, 0.36),
        subsurface_radius=(0.8, 0.6, 0.4),
        description="Natural bottle cork — low-density anisotropic porous "
                    "suberin structure.",
    ),

    # -----------------------------------------------------------------------
    # Additional SPECIAL entries
    # -----------------------------------------------------------------------

    _e(
        "glass_borosilicate",
        "special",
        base_color=(0.95, 0.97, 0.99),
        metalness=0.0,
        roughness=0.01,
        ior=1.474,
        transmission=0.98,
        description="Borosilicate (Pyrex-type) glass — IOR 1.474 (Schott N-BK7 "
                    "equivalent). Near-zero roughness.",
    ),
    _e(
        "liquid_mercury",
        "special",
        base_color=(0.76, 0.78, 0.80),
        metalness=1.0,
        roughness=0.02,
        ior=1.730,
        description="Liquid mercury — mirror-like metal surface at room "
                    "temperature. Palik Vol. 2 (Hg).",
    ),
    _e(
        "ice",
        "special",
        base_color=(0.88, 0.94, 1.00),
        metalness=0.0,
        roughness=0.08,
        ior=1.309,
        transmission=0.85,
        subsurface=0.30,
        subsurface_color=(0.90, 0.96, 1.00),
        subsurface_radius=(5.0, 6.5, 8.0),
        description="Clear lake ice — IOR 1.309 (Hallett 1965). SSS for "
                    "volumetric scattering through depth.",
    ),
]


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def get_all_entries() -> List[EntryDict]:
    """Return the raw catalogue list (copy)."""
    return list(_ENTRIES)
