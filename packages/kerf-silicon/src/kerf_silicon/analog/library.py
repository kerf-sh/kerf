"""library.py — Analog cell library registry.

Registry
--------
Maps family names to their generator modules.

Supported families (SKY130 only in v1)
---------------------------------------
- ``opamp_2stage``        : two-stage Miller-compensated PMOS-input op-amp
- ``comparator_strongarm``: strong-arm latched comparator (clocked)
- ``bandgap_brokaw``      : Brokaw bandgap voltage reference

Public API
----------
    instantiate(family, params) -> AnalogCell
    list_families()            -> list[str]
    AnalogCell                 : exported dataclass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Shared result dataclass (re-exported from here so modules avoid circular
# imports by importing from library, not from each other).
# ---------------------------------------------------------------------------

@dataclass
class AnalogCell:
    """A loaded/generated analog cell descriptor.

    Attributes
    ----------
    name:
        Canonical cell name, e.g. ``"opamp_2stage_sky130"``.
    pdk:
        PDK identifier, e.g. ``"sky130"``.
    descriptor:
        Full JSON descriptor dict (cell_name, layers, polygons, devices, nets).
    lvs_reference:
        Golden LVS netlist dict (empty dict for stub cells).
    params:
        Sizing parameters passed to the generator.
    """
    name: str
    pdk: str
    descriptor: dict[str, Any]
    lvs_reference: dict[str, Any]
    params: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, str] = {
    "opamp_2stage":         "kerf_silicon.analog.opamp_2stage",
    "comparator_strongarm": "kerf_silicon.analog.comparator_strongarm",
    "bandgap_brokaw":       "kerf_silicon.analog.bandgap_brokaw",
}


def list_families() -> list[str]:
    """Return the list of supported analog cell families."""
    return sorted(_REGISTRY.keys())


def instantiate(family: str, params: dict[str, Any] | None = None) -> AnalogCell:
    """Instantiate an analog cell from the library.

    Parameters
    ----------
    family:
        One of ``"opamp_2stage"``, ``"comparator_strongarm"``,
        ``"bandgap_brokaw"``.
    params:
        Family-specific sizing parameters.  See each family module's
        docstring for accepted keys.

    Returns
    -------
    AnalogCell

    Raises
    ------
    KeyError
        If ``family`` is not in the registry.
    """
    if family not in _REGISTRY:
        raise KeyError(
            f"Unknown analog cell family '{family}'. "
            f"Available: {list_families()}"
        )

    import importlib
    mod = importlib.import_module(_REGISTRY[family])
    return mod.generate(params)
