"""
kerf_plc.examples.library — curated PLCopen XML industrial starter library.

Public API
----------
EXAMPLES : list[dict]
    10 example descriptors.  Each dict has keys:
    ``slug``, ``name``, ``category``, ``description``, ``file_path``.

load_example(slug) -> kerf_plc.plcopen.ast.Project
    Parse and return the named example as a fully-constructed Project AST.

list_categories() -> list[str]
    Distinct category strings across all examples, sorted.

examples_by_category(category) -> list[dict]
    Subset of EXAMPLES whose ``category`` matches *category* (case-sensitive).
"""
from __future__ import annotations

from pathlib import Path

from kerf_plc.plcopen.ast import Project
from kerf_plc.plcopen.reader import load as _load

# Directory that contains the PLCopen XML fixture files
_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests" / "fixtures" / "examples"
)


def _fp(filename: str) -> str:
    """Return the absolute path string for a fixture filename."""
    return str(_FIXTURES_DIR / filename)


# ---------------------------------------------------------------------------
# Example manifest
# ---------------------------------------------------------------------------

EXAMPLES: list[dict] = [
    {
        "slug": "traffic_light",
        "name": "Traffic Light Sequencer",
        "category": "motion",
        "description": (
            "Classic 3-phase traffic light controller with pedestrian crossing "
            "request and automatic phase timing using TON timers."
        ),
        "file_path": _fp("traffic_light.plc"),
    },
    {
        "slug": "elevator",
        "name": "Elevator Controller",
        "category": "motion",
        "description": (
            "Single-car 4-floor elevator: call registration, nearest-car "
            "dispatching, door open/close with safety edge, and emergency stop."
        ),
        "file_path": _fp("elevator.plc"),
    },
    {
        "slug": "water_treatment",
        "name": "Water Treatment Plant",
        "category": "process",
        "description": (
            "Municipal filtration and chlorination stage: feed pump, dosing "
            "pump, turbidity-triggered backwash, and chemical fault alarming."
        ),
        "file_path": _fp("water_treatment.plc"),
    },
    {
        "slug": "batch_reactor",
        "name": "Chemical Batch Reactor",
        "category": "process",
        "description": (
            "ISA-88 inspired batch sequence (charge → heat → react → cool → "
            "discharge) with high-pressure / high-temperature safety trips."
        ),
        "file_path": _fp("batch_reactor.plc"),
    },
    {
        "slug": "conveyor_sort",
        "name": "Conveyor Sorter",
        "category": "motion",
        "description": (
            "Optical size classifier on a conveyor belt: classifies packages "
            "at entry, actuates pneumatic diverters at three chutes, and "
            "detects jams."
        ),
        "file_path": _fp("conveyor_sort.plc"),
    },
    {
        "slug": "pick_and_place",
        "name": "Pick-and-Place Robot",
        "category": "motion",
        "description": (
            "Two-axis pneumatic pick-and-place: 8-step sequence, vacuum "
            "gripper with grip-confirm, step watchdog, and vacuum-loss fault."
        ),
        "file_path": _fp("pick_and_place.plc"),
    },
    {
        "slug": "parking_gate",
        "name": "Parking Barrier Gate",
        "category": "access_control",
        "description": (
            "Automated parking gate: ticket dispensing, card-reader exit, "
            "anti-crush reversal, IR under-beam sensor, and max-open timer."
        ),
        "file_path": _fp("parking_gate.plc"),
    },
    {
        "slug": "hvac_zone",
        "name": "HVAC Zone Controller",
        "category": "building",
        "description": (
            "Single HVAC zone: dead-band heating/cooling control, CO2-driven "
            "ventilation, occupancy-based night setback, and high-temp trip."
        ),
        "file_path": _fp("hvac_zone.plc"),
    },
    {
        "slug": "door_interlock",
        "name": "Safety Door Interlock",
        "category": "safety",
        "description": (
            "IEC 62061 Cat.3/PLd safety door interlock for a CNC cell: "
            "dual-channel monitoring, guard-lock solenoid, channel discrepancy "
            "fault, and supervised reset."
        ),
        "file_path": _fp("door_interlock.plc"),
    },
    {
        "slug": "garage_door",
        "name": "Garage Door Operator",
        "category": "access_control",
        "description": (
            "Residential garage door operator: single-button toggle state "
            "machine, IR photo-beam safety, auto-close timer, and travel "
            "watchdog fault detection."
        ),
        "file_path": _fp("garage_door.plc"),
    },
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_example(slug: str) -> Project:
    """
    Parse and return a PLCopen XML example by slug.

    Parameters
    ----------
    slug:
        One of the ``slug`` values in :data:`EXAMPLES`.

    Returns
    -------
    kerf_plc.plcopen.ast.Project
        Fully-parsed project AST.

    Raises
    ------
    KeyError
        If *slug* is not found in the example manifest.
    FileNotFoundError
        If the fixture file is missing from the package.
    """
    for entry in EXAMPLES:
        if entry["slug"] == slug:
            return _load(entry["file_path"])
    raise KeyError(f"No example with slug {slug!r}. Available: {[e['slug'] for e in EXAMPLES]}")


def list_categories() -> list[str]:
    """Return a sorted list of distinct category strings across all examples."""
    return sorted({entry["category"] for entry in EXAMPLES})


def examples_by_category(category: str) -> list[dict]:
    """Return all example descriptors whose ``category`` equals *category*."""
    return [entry for entry in EXAMPLES if entry["category"] == category]
