"""
measured_pbr.py
===============

Measured PBR material library — jewelry, automotive, fabric, organic, special.

Extends the BIM catalogue (T-115) into non-architectural domains.  All entries
carry parameters compatible with three.js ``MeshPhysicalMaterial`` and with the
T-106a Cycles translator output schema (``base_color``, ``metalness``,
``roughness``, ``ior``, ``transmission`` plus the physical-layer extensions
``clearcoat``, ``sheen``, ``anisotropy``, ``subsurface``).

Public API
----------
lookup(name)
    Case-insensitive name look-up.  Returns the raw catalogue dict or raises
    ``KeyError``.

by_category(category)
    Return all entries whose ``category`` matches *category* (case-insensitive),
    sorted alphabetically by ``name``.

to_pbr_dict(name)
    Return a dict shaped for both the T-106a Cycles translator and
    three.js ``MeshPhysicalMaterial``.

catalogue()
    Return the full mapping ``{name: entry_dict}`` (copy).

all_categories()
    Sorted list of distinct category strings.
"""

from __future__ import annotations

from typing import Any, Dict, List

from kerf_cad_core.materials.measured_pbr_data import get_all_entries


# ---------------------------------------------------------------------------
# Build index
# ---------------------------------------------------------------------------

def _build_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for entry in get_all_entries():
        key = entry["name"].lower()  # type: ignore[arg-type]
        idx[key] = entry
    return idx


_INDEX: Dict[str, Dict[str, Any]] = _build_index()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup(name: str) -> Dict[str, Any]:
    """Return the catalogue entry for *name* (case-insensitive).

    Raises
    ------
    KeyError
        If *name* is not in the catalogue.
    """
    key = name.strip().lower()
    entry = _INDEX.get(key)
    if entry is None:
        raise KeyError(
            f"Material {name!r} not found in the measured PBR catalogue. "
            f"Available names: {sorted(_INDEX)[:10]} …"
        )
    return dict(entry)


def by_category(category: str) -> List[Dict[str, Any]]:
    """Return all entries whose ``category`` matches *category*.

    The comparison is case-insensitive.  Returns an empty list for unknown
    categories.  Results are sorted alphabetically by ``name``.
    """
    cat_lower = category.strip().lower()
    matches = [
        dict(e)
        for e in _INDEX.values()
        if str(e.get("category", "")).lower() == cat_lower
    ]
    return sorted(matches, key=lambda e: e["name"])


def to_pbr_dict(name: str) -> Dict[str, Any]:
    """Return a PBR parameter dict for *name* (case-insensitive).

    The output is compatible with both:

    * three.js ``MeshPhysicalMaterial`` property names
    * the T-106a Blender Cycles translator payload

    Fields
    ------
    name, category, description
        Identity / provenance.
    base_color : (r, g, b)
        Linear-sRGB base/diffuse reflectance, 0..1 per channel.
    metalness : float
        0.0 = dielectric, 1.0 = pure conductor.
    roughness : float
        Microsurface roughness 0..1.
    ior : float
        Refractive index at 589 nm.
    transmission : float
        Transmitted light fraction 0..1.
    clearcoat : float
        Clearcoat layer weight 0..1.
    clearcoat_roughness : float
        Roughness of the clearcoat lobe.
    sheen : float
        Sheen lobe weight 0..1 (fabric, velvet).
    sheen_color : (r, g, b)
        Linear-sRGB tint of the sheen lobe.
    anisotropy : float
        Anisotropic specular elongation −1..1.
    anisotropy_rotation : float
        Rotation of the anisotropy tangent axis in radians.
    subsurface : float
        Subsurface scattering weight 0..1.
    subsurface_color : (r, g, b)
        SSS absorption tint.
    subsurface_radius : (r, g, b)
        Per-channel mean free path in millimetres.

    Raises
    ------
    KeyError
        If *name* is not in the catalogue.
    """
    entry = lookup(name)
    # All fields are already present in the entry; return a flat copy.
    return {
        "name":                 entry["name"],
        "category":             entry["category"],
        "description":          entry.get("description", ""),
        "base_color":           entry["base_color"],
        "metalness":            entry["metalness"],
        "roughness":            entry["roughness"],
        "ior":                  entry["ior"],
        "transmission":         entry["transmission"],
        "clearcoat":            entry["clearcoat"],
        "clearcoat_roughness":  entry["clearcoat_roughness"],
        "sheen":                entry["sheen"],
        "sheen_color":          entry["sheen_color"],
        "anisotropy":           entry["anisotropy"],
        "anisotropy_rotation":  entry["anisotropy_rotation"],
        "subsurface":           entry["subsurface"],
        "subsurface_color":     entry["subsurface_color"],
        "subsurface_radius":    entry["subsurface_radius"],
    }


def catalogue() -> Dict[str, Dict[str, Any]]:
    """Return a copy of the full catalogue as ``{name: entry_dict}``."""
    return {k: dict(v) for k, v in _INDEX.items()}


def all_categories() -> List[str]:
    """Return a sorted list of distinct category strings."""
    return sorted({str(e.get("category", "")) for e in _INDEX.values()})


__all__ = [
    "lookup",
    "by_category",
    "to_pbr_dict",
    "catalogue",
    "all_categories",
]
