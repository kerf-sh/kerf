"""DAL (Design Assurance Level) classifier.

Maps a failure-condition severity description to the corresponding
RTCA DO-178C / DO-254 DAL letter per ARP 4761 / AC 25.1309:

    Catastrophic  -> DAL A  (prevents continued safe flight and landing)
    Hazardous     -> DAL B  (large reduction in safety margins or crew workload)
    Major         -> DAL C  (significant reduction in safety margins)
    Minor         -> DAL D  (slight reduction in safety margins / comfort)
    No Effect     -> DAL E  (no impact on operational capability)
"""

from __future__ import annotations

_SEVERITY_MAP: dict[str, str] = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no_effect": "E",
    # common aliases
    "no effect": "E",
    "no-effect": "E",
}

_VALID_DALS = {"A", "B", "C", "D", "E"}


def classify_dal(severity: str) -> str:
    """Return the DAL letter for *severity*.

    Parameters
    ----------
    severity:
        One of ``"catastrophic"``, ``"hazardous"``, ``"major"``,
        ``"minor"``, ``"no_effect"`` (case-insensitive).  Hyphen and
        space variants are also accepted for ``no_effect``.

    Returns
    -------
    str
        Single letter ``"A"`` through ``"E"``.

    Raises
    ------
    ValueError
        If *severity* is not a recognised failure-condition category.
    """
    key = severity.strip().lower()
    if key not in _SEVERITY_MAP:
        valid = ", ".join(sorted(_SEVERITY_MAP.keys()))
        raise ValueError(
            f"Unknown severity {severity!r}. "
            f"Valid values: {valid}"
        )
    return _SEVERITY_MAP[key]


def dal_description(dal: str) -> str:
    """Return a one-line description of *dal*.

    Parameters
    ----------
    dal:
        DAL letter ``"A"`` through ``"E"`` (case-insensitive).

    Raises
    ------
    ValueError
        If *dal* is not ``"A"`` ... ``"E"``.
    """
    upper = dal.strip().upper()
    if upper not in _VALID_DALS:
        raise ValueError(f"Invalid DAL {dal!r}. Must be A, B, C, D, or E.")
    descriptions = {
        "A": "Catastrophic — prevents continued safe flight and landing",
        "B": "Hazardous — large reduction in safety margins or functional capabilities",
        "C": "Major — significant reduction in safety margins or crew workload increase",
        "D": "Minor — slight reduction in safety margins; nuisance to crew",
        "E": "No Effect — no impact on operational capability or safety",
    }
    return descriptions[upper]


def required_artefacts_do178c(dal: str) -> list[str]:
    """Return the list of DO-178C artefacts required for *dal*.

    Higher assurance levels (A, B) require all artefacts; lower levels
    may omit certain LLR and structural coverage items per Table A-1
    and Table A-5 of RTCA DO-178C.

    Parameters
    ----------
    dal:
        DAL letter ``"A"`` through ``"E"``.

    Returns
    -------
    list[str]
        Artefact names in roughly document-lifecycle order.
    """
    upper = dal.strip().upper()
    if upper not in _VALID_DALS:
        raise ValueError(f"Invalid DAL {dal!r}.")

    # Core planning documents — required for all levels A-D; E exempt from cert
    planning = [
        "PSAC — Plan for Software Aspects of Certification",
        "SDP — Software Development Plan",
        "SVP — Software Verification Plan",
        "SCMP — Software Configuration Management Plan",
        "SQAP — Software Quality Assurance Plan",
    ]

    # Requirements and design
    requirements = [
        "HLR — High-Level Requirements",
        "HLR Traceability to System Requirements",
        "LLR — Low-Level Requirements",
        "LLR Traceability to High-Level Requirements",
        "SDD — Software Design Description",
        "SDD Traceability to Low-Level Requirements",
        "Source Code",
        "Source Code Traceability to Low-Level Requirements",
        "Executable Object Code",
    ]

    # Verification results
    verification_common = [
        "HLR Review Results",
        "LLR Review Results",
        "SDD Review Results",
        "Source Code Review Results",
        "Test Cases and Procedures",
        "Test Results",
        "Test Coverage Analysis — Requirements-Based",
    ]

    # Structural coverage (statement / decision / MC/DC)
    structural_a = [
        "Structural Coverage — Statement Coverage",
        "Structural Coverage — Decision Coverage",
        "Structural Coverage — MC/DC (DAL A only)",
    ]
    structural_b = [
        "Structural Coverage — Statement Coverage",
        "Structural Coverage — Decision Coverage",
    ]
    structural_c = [
        "Structural Coverage — Statement Coverage",
    ]

    # Configuration management records
    cm_records = [
        "Software Configuration Index (SCI)",
        "Software Accomplishment Summary (SAS)",
        "Problem Reports",
        "Change Control Records",
    ]

    if upper == "E":
        # DAL E: no software life-cycle data required per DO-178C §2.5
        return ["No DO-178C software life-cycle data required for DAL E"]

    artefacts = planning + requirements + verification_common

    if upper == "A":
        artefacts += structural_a
    elif upper == "B":
        artefacts += structural_b
    elif upper == "C":
        artefacts += structural_c
    # DAL D: no structural coverage required

    artefacts += cm_records
    return artefacts


def required_artefacts_do254(dal: str) -> list[str]:
    """Return the list of DO-254 artefacts required for *dal*.

    Based on RTCA DO-254 Table A-1 (hardware life-cycle data).

    Parameters
    ----------
    dal:
        DAL letter ``"A"`` through ``"E"``.
    """
    upper = dal.strip().upper()
    if upper not in _VALID_DALS:
        raise ValueError(f"Invalid DAL {dal!r}.")

    if upper == "E":
        return ["No DO-254 hardware life-cycle data required for DAL E"]

    planning = [
        "PHAC — Plan for Hardware Aspects of Certification",
        "HDP — Hardware Development Plan",
        "HVVP — Hardware Verification and Validation Plan",
        "HPAP — Hardware Process Assurance Plan",
    ]

    design = [
        "Hardware Requirements (derived and allocated)",
        "Hardware Requirements Traceability to System Requirements",
        "Conceptual Design Data",
        "Detailed Design Data — Schematics",
        "Detailed Design Data — HDL Source (VHDL/Verilog/SystemVerilog)",
        "Detailed Design Data — Synthesis and Place-and-Route Constraints",
        "Hardware Design Description (HDD)",
    ]

    verification_common = [
        "Hardware Verification Procedures",
        "Hardware Verification Results",
        "Requirements-Based Test Coverage Analysis",
        "Hardware Configuration Management Records",
        "Hardware Accomplishment Summary (HAS)",
        "Problem Reports",
    ]

    advanced = [
        "Elemental Analysis (DAL A/B)",
        "Independence Evidence (DAL A/B)",
    ]

    artefacts = planning + design + verification_common
    if upper in ("A", "B"):
        artefacts += advanced

    return artefacts
