"""instantiate_analog_cell.py — LLM tool surface for the analog cell library.

LLM tool
--------
    ``instantiate_analog_cell(family, params)``

Callable by the LLM agent as:

    result = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})

The function returns a dict suitable for direct JSON serialisation, with the
cell's layout descriptor, LVS-clean flag, and a characterisation summary.

Supported families
------------------
- ``"opamp_2stage"``        : GBW-parameterised Miller-compensated op-amp
- ``"comparator_strongarm"``: clocked strong-arm latch (stub in v1)
- ``"bandgap_brokaw"``      : Brokaw bandgap reference (stub in v1)

Response schema
---------------
    {
      "ok": bool,
      "cell_name": str,
      "pdk": str,
      "params": dict,
      "descriptor": {...},        # layer + polygon + device list
      "lvs": {
        "clean": bool,
        "reference_cell_count": int,
        "summary": str
      },
      "characterisation": {
        "oracle_path": str,       # "analytic" | "ngspice" | "stub"
        "gbw_hz_requested": float | null,
        "gbw_hz_achieved": float | null,
        "within_20pct": bool | null,
        "dc_gain_dB": float | null,
        "notes": [str, ...]
      },
      "error": str | null
    }

Example
-------
    >>> from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
    >>> r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
    >>> r["ok"]
    True
    >>> r["lvs"]["clean"]
    True
"""

from __future__ import annotations

from typing import Any

from kerf_silicon.analog.library import instantiate, list_families


def instantiate_analog_cell(
    family: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instantiate an analog cell and return a characterisation report.

    Parameters
    ----------
    family:
        Cell family name — one of ``"opamp_2stage"``,
        ``"comparator_strongarm"``, ``"bandgap_brokaw"``.
    params:
        Optional dict of sizing parameters.  Family-specific keys:

        opamp_2stage
            - ``gbw_hz``  (float) : gain-bandwidth product target (Hz)
            - ``idd_ua``  (float) : supply current budget (µA)
            - ``pdk``     (str)   : PDK name (default ``"sky130"``)

        comparator_strongarm
            - ``offset_mv`` (float) : input-referred offset target (mV)
            - ``pdk``       (str)

        bandgap_brokaw
            - ``iref_ua`` (float) : reference current in µA
            - ``pdk``     (str)

    Returns
    -------
    dict
        Serialisable result dict (see module docstring for schema).
    """
    if params is None:
        params = {}

    try:
        cell = instantiate(family, params)
    except KeyError as exc:
        return {
            "ok": False,
            "cell_name": None,
            "pdk": None,
            "params": params,
            "descriptor": None,
            "lvs": {"clean": False, "reference_cell_count": 0, "summary": ""},
            "characterisation": {
                "oracle_path": "none",
                "gbw_hz_requested": None,
                "gbw_hz_achieved": None,
                "within_20pct": None,
                "dc_gain_dB": None,
                "notes": [],
            },
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "cell_name": None,
            "pdk": None,
            "params": params,
            "descriptor": None,
            "lvs": {"clean": False, "reference_cell_count": 0, "summary": ""},
            "characterisation": {
                "oracle_path": "none",
                "gbw_hz_requested": None,
                "gbw_hz_achieved": None,
                "within_20pct": None,
                "dc_gain_dB": None,
                "notes": [],
            },
            "error": f"{type(exc).__name__}: {exc}",
        }

    # ---- LVS check -------------------------------------------------------
    lvs_info = _lvs_check(cell)

    # ---- Characterisation ------------------------------------------------
    char_info = _characterise(family, params)

    return {
        "ok": True,
        "cell_name": cell.name,
        "pdk": cell.pdk,
        "params": cell.params,
        "descriptor": cell.descriptor,
        "lvs": lvs_info,
        "characterisation": char_info,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lvs_check(cell: Any) -> dict[str, Any]:
    """Run a structural LVS check against the cell's golden reference netlist.

    Uses ``kerf_silicon.lvs`` for the op-amp (which has a golden .lvs.json).
    Stub cells (comparator, bandgap) return a pending result.
    """
    lvs_ref = cell.lvs_reference
    if not lvs_ref or not lvs_ref.get("cells"):
        return {
            "clean": False,
            "reference_cell_count": 0,
            "summary": "LVS PENDING — golden netlist not yet available for this cell.",
        }

    # Build reference Netlist from the JSON
    from kerf_silicon.lvs.extractor import Netlist, CellInstance, Net
    from kerf_silicon.lvs.compare import lvs_match

    ref_cells = [
        CellInstance(
            ref=c["ref"],
            cell_type=c["type"],
            ports=c.get("ports", []),
        )
        for c in lvs_ref["cells"]
    ]
    ref_nets = [
        Net(name=n["name"], pin_refs=list(n.get("pin_refs", [])))
        for n in lvs_ref.get("nets", [])
    ]
    reference = Netlist(cells=ref_cells, nets=ref_nets)

    # Build extracted Netlist from the descriptor's device list
    desc = cell.descriptor
    devices = desc.get("devices", [])
    ext_cells = [
        CellInstance(
            ref=d["ref"],
            cell_type=d["type"],
            ports=list(d.get("ports", {}).keys()),
        )
        for d in devices
    ]
    # Build nets from device port bindings
    net_to_pins: dict[str, list[str]] = {}
    for d in devices:
        for port_name, net_name in d.get("ports", {}).items():
            net_to_pins.setdefault(net_name, []).append(f"{d['ref']}/{port_name}")
    ext_nets = [
        Net(name=net_name, pin_refs=pins)
        for net_name, pins in net_to_pins.items()
    ]
    extracted = Netlist(cells=ext_cells, nets=ext_nets)

    report = lvs_match(extracted, reference)

    return {
        "clean": report.matched,
        "reference_cell_count": len(ref_cells),
        "summary": report.summary,
    }


def _characterise(family: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the family's characterise() function and normalise the result."""
    import importlib
    _family_modules = {
        "opamp_2stage":         "kerf_silicon.analog.opamp_2stage",
        "comparator_strongarm": "kerf_silicon.analog.comparator_strongarm",
        "bandgap_brokaw":       "kerf_silicon.analog.bandgap_brokaw",
    }
    mod_name = _family_modules.get(family)
    if mod_name is None:
        return {
            "oracle_path": "none",
            "gbw_hz_requested": None,
            "gbw_hz_achieved": None,
            "within_20pct": None,
            "dc_gain_dB": None,
            "notes": [f"No characterise() for family '{family}'."],
        }

    mod = importlib.import_module(mod_name)
    result = mod.characterise(params)

    if family == "opamp_2stage":
        return {
            "oracle_path": result.oracle_path,
            "gbw_hz_requested": result.gbw_hz_requested,
            "gbw_hz_achieved": result.gbw_hz_achieved,
            "within_20pct": result.within_20pct,
            "dc_gain_dB": result.dc_gain_dB,
            "notes": result.notes,
        }
    elif family == "comparator_strongarm":
        return {
            "oracle_path": result.oracle_path,
            "offset_target_mv": result.offset_target_mv,
            "offset_achieved_mv": getattr(result, "offset_achieved_mv", None),
            "within_target": getattr(result, "within_target", None),
            "w_um": getattr(result, "w_um", None),
            "l_um": getattr(result, "l_um", None),
            "gbw_hz_requested": None,
            "gbw_hz_achieved": None,
            "within_20pct": None,
            "dc_gain_dB": None,
            "notes": result.notes,
        }
    elif family == "bandgap_brokaw":
        return {
            "oracle_path": result.oracle_path,
            "iref_ua": result.iref_ua,
            "vref_target_v": result.vref_target_v,
            "vref_achieved_v": getattr(result, "vref_achieved_v", None),
            "vref_within_5pct": getattr(result, "vref_within_5pct", None),
            "tc_ctat_mv_per_k": getattr(result, "tc_ctat_mv_per_k", None),
            "tc_ptat_mv_per_k": getattr(result, "tc_ptat_mv_per_k", None),
            "tc_net_mv_per_k": getattr(result, "tc_net_mv_per_k", None),
            "tc_sign_correct": getattr(result, "tc_sign_correct", None),
            "r2_r1_ratio": getattr(result, "r2_r1_ratio", None),
            "gbw_hz_requested": None,
            "gbw_hz_achieved": None,
            "within_20pct": None,
            "dc_gain_dB": None,
            "notes": result.notes,
        }
    else:
        return {
            "oracle_path": "unknown",
            "gbw_hz_requested": None,
            "gbw_hz_achieved": None,
            "within_20pct": None,
            "dc_gain_dB": None,
            "notes": [],
        }
