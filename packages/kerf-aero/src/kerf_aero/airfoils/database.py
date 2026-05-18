"""
AIRFOIL_CATALOGUE — registry of curated airfoil entries.

Each entry is a dict with keys:
  slug        : str   — unique identifier, matches selig_load() key
  name        : str   — human-readable display name
  category    : str   — one of: symmetric, general-aviation, sailplane,
                        low-reynolds, high-lift, vintage, propeller,
                        transonic, research
  source      : str   — primary data source / report
  description : str   — one-line description
"""

from __future__ import annotations

from typing import TypedDict


class AirfoilEntry(TypedDict):
    slug: str
    name: str
    category: str
    source: str
    description: str


AIRFOIL_CATALOGUE: list[AirfoilEntry] = [
    # ── Symmetric NACA 00xx ──────────────────────────────────────────────
    {
        "slug": "naca0006",
        "name": "NACA 0006",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Ultra-thin symmetric section; used in control surfaces and struts.",
    },
    {
        "slug": "naca0009",
        "name": "NACA 0009",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Thin symmetric section; common in horizontal tails.",
    },
    {
        "slug": "naca0012",
        "name": "NACA 0012",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Most widely studied symmetric airfoil; benchmark for CFD/wind-tunnel testing.",
    },
    {
        "slug": "naca0015",
        "name": "NACA 0015",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Moderate-thickness symmetric section; used in helicopter rotor blades.",
    },
    {
        "slug": "naca0018",
        "name": "NACA 0018",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Thick symmetric section; used in wind-turbine blades and vertical tails.",
    },
    {
        "slug": "naca0021",
        "name": "NACA 0021",
        "category": "symmetric",
        "source": "NACA TR-460",
        "description": "Very thick symmetric section; used in VAWT designs.",
    },
    # ── General-aviation cambered NACA ──────────────────────────────────
    {
        "slug": "naca2412",
        "name": "NACA 2412",
        "category": "general-aviation",
        "source": "NACA TR-460",
        "description": "Classic general-aviation airfoil; Cessna 172 wing root.",
    },
    {
        "slug": "naca4412",
        "name": "NACA 4412",
        "category": "general-aviation",
        "source": "NACA TR-460",
        "description": "Higher-camber 4-digit section; light aircraft and UAVs.",
    },
    {
        "slug": "naca2415",
        "name": "NACA 2415",
        "category": "general-aviation",
        "source": "NACA TR-460",
        "description": "Slightly thicker variant of NACA 2412; improved stall behaviour.",
    },
    {
        "slug": "naca4415",
        "name": "NACA 4415",
        "category": "general-aviation",
        "source": "NACA TR-460",
        "description": "Thick cambered 4-digit; good for slow-speed aircraft.",
    },
    {
        "slug": "naca6412",
        "name": "NACA 6412",
        "category": "general-aviation",
        "source": "NACA TR-460",
        "description": "High-camber 4-digit section; vintage trainer aircraft.",
    },
    # ── NACA 5-digit series ──────────────────────────────────────────────
    {
        "slug": "naca23012",
        "name": "NACA 23012",
        "category": "general-aviation",
        "source": "NACA TR-537",
        "description": "Most common 5-digit section; Piper PA-28, many GA aircraft.",
    },
    {
        "slug": "naca23015",
        "name": "NACA 23015",
        "category": "general-aviation",
        "source": "NACA TR-537",
        "description": "Thicker 23-series; used at wing roots.",
    },
    {
        "slug": "naca23018",
        "name": "NACA 23018",
        "category": "general-aviation",
        "source": "NACA TR-537",
        "description": "Thick 23-series section for high-lift root applications.",
    },
    # ── Wortmann FX sailplane series ─────────────────────────────────────
    {
        "slug": "fx60-126",
        "name": "Wortmann FX 60-126",
        "category": "sailplane",
        "source": "Wortmann 1965 / UIUC APLDB",
        "description": "Classic laminar-flow sailplane section; ASW-12 wing.",
    },
    {
        "slug": "fx60-100",
        "name": "Wortmann FX 60-100",
        "category": "sailplane",
        "source": "Wortmann 1965 / UIUC APLDB",
        "description": "Thin Wortmann section for tip regions of sailplane wings.",
    },
    {
        "slug": "fx63-137",
        "name": "Wortmann FX 63-137",
        "category": "sailplane",
        "source": "Wortmann 1971 / UIUC APLDB",
        "description": "High-lift Wortmann section; ASK-21 and many 15-m class gliders.",
    },
    # ── Eppler low-Reynolds series ───────────────────────────────────────
    {
        "slug": "e374",
        "name": "Eppler E374",
        "category": "low-reynolds",
        "source": "Eppler 1990 / UIUC APLDB",
        "description": "Low-Re competition glider section; excellent L/D at Re=200k.",
    },
    {
        "slug": "e387",
        "name": "Eppler E387",
        "category": "low-reynolds",
        "source": "Eppler 1990 / UIUC APLDB",
        "description": "Benchmark low-Re airfoil; extensively tested at NASA Langley.",
    },
    {
        "slug": "e423",
        "name": "Eppler E423",
        "category": "low-reynolds",
        "source": "Eppler 1990 / UIUC APLDB",
        "description": "High-lift low-Re section; small UAVs and model aircraft.",
    },
    {
        "slug": "e1098",
        "name": "Eppler E1098",
        "category": "propeller",
        "source": "Eppler 1990 / UIUC APLDB",
        "description": "Optimised for propeller and fan blade applications.",
    },
    # ── Selig high-lift low-Re series ────────────────────────────────────
    {
        "slug": "s1223",
        "name": "Selig S1223",
        "category": "high-lift",
        "source": "Selig et al. 1995 / UIUC APLDB",
        "description": "Highest-lift low-Re airfoil; CL_max ≈ 2.2 at Re=200k.",
    },
    {
        "slug": "sd7037",
        "name": "Selig-Donovan SD7037",
        "category": "low-reynolds",
        "source": "Selig & Donovan 1989 / UIUC APLDB",
        "description": "Versatile low-Re section; radio-control sailplanes.",
    },
    {
        "slug": "sd7032",
        "name": "Selig-Donovan SD7032",
        "category": "low-reynolds",
        "source": "Selig & Donovan 1989 / UIUC APLDB",
        "description": "Low-Re section optimised for span-efficiency.",
    },
    {
        "slug": "sd7080",
        "name": "Selig-Donovan SD7080",
        "category": "low-reynolds",
        "source": "Selig & Donovan 1989 / UIUC APLDB",
        "description": "Thin low-Re section; indoor free-flight models.",
    },
    # ── Clark vintage series ─────────────────────────────────────────────
    {
        "slug": "clarky",
        "name": "Clark Y",
        "category": "vintage",
        "source": "Clark 1922 / NACA TN-292",
        "description": "Flat-bottomed vintage section; Ryan NYP Spirit of St. Louis.",
    },
    {
        "slug": "clarkyh",
        "name": "Clark YH",
        "category": "vintage",
        "source": "Clark 1922 / NACA",
        "description": "Modified Clark Y with reflexed trailing edge for pitch stability.",
    },
    # ── Liebeck high-lift series ─────────────────────────────────────────
    {
        "slug": "la203a",
        "name": "Liebeck LA203A",
        "category": "high-lift",
        "source": "Liebeck 1973 / AIAA J.",
        "description": "Optimally designed high-lift section using prescribed velocity distribution.",
    },
    {
        "slug": "l1003",
        "name": "Liebeck L1003",
        "category": "high-lift",
        "source": "Liebeck 1978 / NASA CR",
        "description": "High-lift section with Stratford recovery; used on ultra-light aircraft.",
    },
    # ── NACA 6-series / transonic ────────────────────────────────────────
    {
        "slug": "naca64a010",
        "name": "NACA 64A010",
        "category": "transonic",
        "source": "NACA / UIUC APLDB",
        "description": "Thin symmetric 6-series section; supersonic and transonic fighters.",
    },
    {
        "slug": "naca64a412",
        "name": "NACA 64A412",
        "category": "transonic",
        "source": "NACA / UIUC APLDB",
        "description": "Cambered 6-series section; jet trainer and light-attack aircraft.",
    },
    # ── Research / other ─────────────────────────────────────────────────
    {
        "slug": "raf6",
        "name": "RAF 6",
        "category": "vintage",
        "source": "Royal Aircraft Factory 1918",
        "description": "Classic RAF wartime section; SE5a fighter aircraft.",
    },
    {
        "slug": "goe398",
        "name": "Goettingen 398",
        "category": "research",
        "source": "AVA Goettingen / UIUC APLDB",
        "description": "German research section; used in inter-war aircraft designs.",
    },
    {
        "slug": "mh60",
        "name": "Martin Hepperle MH60",
        "category": "low-reynolds",
        "source": "Hepperle 1997 / JavaFoil database",
        "description": "Modern low-Re section for indoor slow-flyers and micro-UAVs.",
    },
    {
        "slug": "ag35",
        "name": "Gopalarathnam AG35",
        "category": "low-reynolds",
        "source": "Gopalarathnam et al. 2002 / UIUC APLDB",
        "description": "High-performance low-Re section for electric-powered sailplanes.",
    },
    {
        "slug": "s2091",
        "name": "Selig S2091",
        "category": "low-reynolds",
        "source": "Selig et al. 1995 / UIUC APLDB",
        "description": "Medium-camber low-Re section; electric-powered UAVs.",
    },
    {
        "slug": "rg15",
        "name": "Riegels-Goettingen RG15",
        "category": "low-reynolds",
        "source": "Riegels 1961 / UIUC APLDB",
        "description": "Classic thin low-Re section; RC gliders and small UAVs.",
    },
    {
        "slug": "ch10",
        "name": "Cheeseman CH10",
        "category": "research",
        "source": "Cheeseman / UIUC APLDB",
        "description": "Research section with gentle stall characteristics.",
    },
    {
        "slug": "naca63a215",
        "name": "NACA 63A215",
        "category": "general-aviation",
        "source": "NACA / UIUC APLDB",
        "description": "Laminar-flow 6-series cambered section; T-38 Talon wing.",
    },
    {
        "slug": "eppler562",
        "name": "Eppler E562",
        "category": "sailplane",
        "source": "Eppler 1990 / UIUC APLDB",
        "description": "High-performance sailplane section; optimised for 15-m class.",
    },
]

# Quick lookup by slug
_CATALOGUE_BY_SLUG: dict[str, AirfoilEntry] = {
    entry["slug"]: entry for entry in AIRFOIL_CATALOGUE
}


def get_entry(slug: str) -> AirfoilEntry:
    """
    Return the catalogue entry for a given slug.

    Raises
    ------
    KeyError
        If slug is not in the catalogue.
    """
    if slug not in _CATALOGUE_BY_SLUG:
        raise KeyError(f"Airfoil slug {slug!r} not in AIRFOIL_CATALOGUE")
    return _CATALOGUE_BY_SLUG[slug]


def list_by_category(category: str) -> list[AirfoilEntry]:
    """Return all catalogue entries for a given category string."""
    return [e for e in AIRFOIL_CATALOGUE if e["category"] == category]
