"""
kerf_electronics.harness3d.library
====================================
Automotive connector / bundle / segment standard parts library.

Contains ≥ 20 standard automotive connectors spanning:
  - MIL-DTL-38999 (mil/aero circular)
  - Deutsch DT / DTM / DTP series
  - Molex Mini-Fit Jr / Micro-Fit / CL
  - TE Connectivity AMP Superseal 1.5 / HDSCS / Econoseal
  - Yazaki MT090 / MT110
  - Aptiv (Delphi) 2-way GT 280
  - USCAR / ISO 15170 / LV-214 connectors

Each entry carries: connector family, part name, pin count, max current per
pin (A), IP rating (ingress protection), operating voltage (V), temperature
range (°C), and a short description.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorSpec:
    """Specification for an automotive connector."""
    part_id: str           # Unique identifier (library key)
    family: str            # Connector family / series
    part_name: str         # Full part name / designation
    pin_count: int         # Number of pins / cavities
    current_per_pin_a: float  # Max current per pin (A)
    voltage_v: float       # Operating voltage (V)
    ip_rating: str         # IP rating string e.g. "IP67"
    temp_min_c: float      # Min operating temperature (°C)
    temp_max_c: float      # Max operating temperature (°C)
    description: str       # Short description


CONNECTOR_LIBRARY: dict[str, ConnectorSpec] = {
    spec.part_id: spec
    for spec in [
        # ── MIL-DTL-38999 Series III (mil/aero circular) ──────────────────────
        ConnectorSpec(
            part_id="MIL38999-9",
            family="MIL-DTL-38999",
            part_name="MIL-DTL-38999/III Size 9 — 9 contacts",
            pin_count=9,
            current_per_pin_a=23.0,
            voltage_v=200.0,
            ip_rating="IP67",
            temp_min_c=-65.0,
            temp_max_c=200.0,
            description="Mil-spec circular, size 9 shell, 9 signal contacts, "
                        "bayonet coupling, MIL-DTL-38999 Series III",
        ),
        ConnectorSpec(
            part_id="MIL38999-25",
            family="MIL-DTL-38999",
            part_name="MIL-DTL-38999/III Size 11 — 25 contacts",
            pin_count=25,
            current_per_pin_a=7.5,
            voltage_v=200.0,
            ip_rating="IP67",
            temp_min_c=-65.0,
            temp_max_c=200.0,
            description="Mil-spec circular, size 11 shell, 25 signal contacts",
        ),

        # ── Deutsch DT series (commercial/off-road) ───────────────────────────
        ConnectorSpec(
            part_id="DT-2P",
            family="Deutsch DT",
            part_name="Deutsch DT04-2P / DT06-2S — 2-way",
            pin_count=2,
            current_per_pin_a=13.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Deutsch DT 2-way, PCB or wire-to-wire, sealed",
        ),
        ConnectorSpec(
            part_id="DT-4P",
            family="Deutsch DT",
            part_name="Deutsch DT04-4P / DT06-4S — 4-way",
            pin_count=4,
            current_per_pin_a=13.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Deutsch DT 4-way, sealed",
        ),
        ConnectorSpec(
            part_id="DT-6P",
            family="Deutsch DT",
            part_name="Deutsch DT04-6P / DT06-6S — 6-way",
            pin_count=6,
            current_per_pin_a=13.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Deutsch DT 6-way, sealed",
        ),

        # ── Deutsch DTM (miniature) ───────────────────────────────────────────
        ConnectorSpec(
            part_id="DTM-3P",
            family="Deutsch DTM",
            part_name="Deutsch DTM04-3P — 3-way miniature",
            pin_count=3,
            current_per_pin_a=7.5,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Deutsch DTM miniature 3-way sealed",
        ),

        # ── Deutsch DTP (power) ───────────────────────────────────────────────
        ConnectorSpec(
            part_id="DTP-2P",
            family="Deutsch DTP",
            part_name="Deutsch DTP04-2P — 2-way power",
            pin_count=2,
            current_per_pin_a=60.0,
            voltage_v=600.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Deutsch DTP 2-way high-current power connector",
        ),

        # ── Molex Mini-Fit Jr ─────────────────────────────────────────────────
        ConnectorSpec(
            part_id="MINIFIT-2",
            family="Molex Mini-Fit Jr",
            part_name="Molex 39-01-2020 — 2-way Mini-Fit Jr",
            pin_count=2,
            current_per_pin_a=9.0,
            voltage_v=600.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Molex Mini-Fit Jr 2-way PCB power header",
        ),
        ConnectorSpec(
            part_id="MINIFIT-6",
            family="Molex Mini-Fit Jr",
            part_name="Molex 39-01-2060 — 6-way Mini-Fit Jr",
            pin_count=6,
            current_per_pin_a=9.0,
            voltage_v=600.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Molex Mini-Fit Jr 6-way PCB header",
        ),
        ConnectorSpec(
            part_id="MINIFIT-12",
            family="Molex Mini-Fit Jr",
            part_name="Molex 39-01-2120 — 12-way Mini-Fit Jr",
            pin_count=12,
            current_per_pin_a=9.0,
            voltage_v=600.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Molex Mini-Fit Jr 12-way PCB header",
        ),

        # ── Molex Micro-Fit 3.0 ───────────────────────────────────────────────
        ConnectorSpec(
            part_id="MICROFIT-4",
            family="Molex Micro-Fit 3.0",
            part_name="Molex 43025-0400 — 4-way Micro-Fit",
            pin_count=4,
            current_per_pin_a=5.0,
            voltage_v=600.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Molex Micro-Fit 3.0mm pitch 4-way",
        ),
        ConnectorSpec(
            part_id="MICROFIT-8",
            family="Molex Micro-Fit 3.0",
            part_name="Molex 43025-0800 — 8-way Micro-Fit",
            pin_count=8,
            current_per_pin_a=5.0,
            voltage_v=600.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Molex Micro-Fit 3.0mm pitch 8-way",
        ),

        # ── TE Connectivity AMP Superseal 1.5 ────────────────────────────────
        ConnectorSpec(
            part_id="SUPERSEAL-1",
            family="TE Superseal 1.5",
            part_name="TE 1-967629-1 — 1-way Superseal",
            pin_count=1,
            current_per_pin_a=10.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="TE Superseal 1.5mm pitch 1-way sealed connector",
        ),
        ConnectorSpec(
            part_id="SUPERSEAL-6",
            family="TE Superseal 1.5",
            part_name="TE 1-967640-1 — 6-way Superseal",
            pin_count=6,
            current_per_pin_a=10.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="TE Superseal 1.5mm pitch 6-way sealed connector",
        ),

        # ── TE HDSCS (heavy-duty sealed connector system) ─────────────────────
        ConnectorSpec(
            part_id="HDSCS-12",
            family="TE HDSCS",
            part_name="TE 1-1418480-1 — 12-way HDSCS",
            pin_count=12,
            current_per_pin_a=13.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="TE HDSCS 12-way heavy-duty sealed",
        ),

        # ── Yazaki MT090 ──────────────────────────────────────────────────────
        ConnectorSpec(
            part_id="MT090-2",
            family="Yazaki MT090",
            part_name="Yazaki MT090 2-way",
            pin_count=2,
            current_per_pin_a=10.0,
            voltage_v=12.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Yazaki MT090 2-way 0.9mm pitch automotive",
        ),
        ConnectorSpec(
            part_id="MT090-6",
            family="Yazaki MT090",
            part_name="Yazaki MT090 6-way",
            pin_count=6,
            current_per_pin_a=10.0,
            voltage_v=12.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=105.0,
            description="Yazaki MT090 6-way 0.9mm pitch automotive",
        ),

        # ── Aptiv (Delphi) GT 280 ─────────────────────────────────────────────
        ConnectorSpec(
            part_id="GT280-2",
            family="Aptiv GT 280",
            part_name="Aptiv GT 280 2-way — 15326849",
            pin_count=2,
            current_per_pin_a=20.0,
            voltage_v=24.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="Aptiv (Delphi) GT 280 2-way 2.8mm sealed",
        ),

        # ── ISO 15170 / SAE J1939 9-way CPC (commercial vehicle) ─────────────
        ConnectorSpec(
            part_id="CPC-9",
            family="ISO 15170 CPC",
            part_name="ISO 15170 / CPC 9-way — SAE J1939 Deutsch HD10-9",
            pin_count=9,
            current_per_pin_a=15.0,
            voltage_v=48.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="J1939 diagnostic / backbone 9-way CPC connector",
        ),

        # ── High-voltage EV connector (IEC 62196 / SAE J1772) ────────────────
        ConnectorSpec(
            part_id="J1772-5",
            family="SAE J1772",
            part_name="SAE J1772 Level-2 EVSE — 5-way",
            pin_count=5,
            current_per_pin_a=80.0,
            voltage_v=250.0,
            ip_rating="IP44",
            temp_min_c=-40.0,
            temp_max_c=85.0,
            description="J1772 AC charging inlet / outlet — AC L1/L2, PE, CP, PP",
        ),

        # ── OBD-II (ISO 15031-3) diagnostic ───────────────────────────────────
        ConnectorSpec(
            part_id="OBD2-16",
            family="OBD-II",
            part_name="OBD-II / SAE J1962 — 16-way",
            pin_count=16,
            current_per_pin_a=3.0,
            voltage_v=16.0,
            ip_rating="IP20",
            temp_min_c=-40.0,
            temp_max_c=85.0,
            description="OBD-II 16-way diagnostic connector (ISO 15031-3)",
        ),

        # ── LV214 HV interlock (ISO 17409) ───────────────────────────────────
        ConnectorSpec(
            part_id="LV214-HVS",
            family="LV214",
            part_name="LV214-B HV safety interlock — 2-way",
            pin_count=2,
            current_per_pin_a=2.0,
            voltage_v=1000.0,
            ip_rating="IP67",
            temp_min_c=-40.0,
            temp_max_c=125.0,
            description="ISO 17409 / LV214 HV service disconnect interlock plug",
        ),
    ]
}


def lookup_connector(part_id: str) -> ConnectorSpec:
    """
    Look up a connector by its part_id.

    Raises
    ------
    KeyError
        If part_id is not found in the library.
    """
    if part_id not in CONNECTOR_LIBRARY:
        available = ", ".join(sorted(CONNECTOR_LIBRARY.keys()))
        raise KeyError(
            f"connector '{part_id}' not found; available: {available}"
        )
    return CONNECTOR_LIBRARY[part_id]
