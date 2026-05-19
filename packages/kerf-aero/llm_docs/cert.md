# kerf-aero Certification Artefact Templates

## Overview

`kerf_aero.cert` provides Markdown template generators for two major airborne
certification standards:

| Standard | Full name | Domain |
|----------|-----------|--------|
| **DO-178C** | RTCA/DO-178C — Software Considerations in Airborne Systems and Equipment Certification (2011) | Airborne software (e.g. autopilot firmware, kerf-firmware DAL builds) |
| **DO-254** | RTCA/DO-254 — Design Assurance Guidance for Airborne Electronic Hardware (2000) | Airborne electronic hardware (e.g. FPGAs, ASICs — kerf-silicon T-256/T-257 submissions) |

These templates **lower the activation energy** for certification; they are
scaffolding the engineer must review and complete.  Kerf does not certify
aircraft or aircraft components.

---

## DAL Classifier

The Design Assurance Level (DAL) is determined from the **failure condition
severity** of the function the item performs, per ARP 4761 / AC 25.1309:

```python
from kerf_aero.cert.dal_classifier import classify_dal

classify_dal("catastrophic")  # -> "A"
classify_dal("hazardous")     # -> "B"
classify_dal("major")         # -> "C"
classify_dal("minor")         # -> "D"
classify_dal("no_effect")     # -> "E"
```

| Severity | DAL | Meaning |
|----------|-----|---------|
| catastrophic | A | Prevents continued safe flight and landing |
| hazardous    | B | Large reduction in safety margins or crew workload |
| major        | C | Significant reduction in safety margins |
| minor        | D | Slight reduction in safety margins / nuisance |
| no_effect    | E | No impact on safety or operational capability |

`no_effect` also accepts `"no effect"` and `"no-effect"` (space and hyphen
variants). All inputs are case-insensitive.

### Artefact lists

```python
from kerf_aero.cert.dal_classifier import (
    required_artefacts_do178c,
    required_artefacts_do254,
)

# Returns a list[str] of required artefact names for DAL B software
required_artefacts_do178c("B")

# Returns a list[str] of required artefact names for DAL B hardware
required_artefacts_do254("B")
```

DAL E returns a single-element list noting that no life-cycle data is required
under either standard.

---

## DO-178C Templates

### Supported document types

| doc_type | Document |
|----------|----------|
| `PSAC`   | Plan for Software Aspects of Certification |
| `SDP`    | Software Development Plan |
| `SVP`    | Software Verification Plan |
| `SCMP`   | Software Configuration Management Plan |
| `SQAP`   | Software Quality Assurance Plan |
| `HLR`    | High-Level Requirements |
| `LLR`    | Low-Level Requirements |
| `SDD`    | Software Design Description |
| `SVCP`   | Software Verification Cases and Procedures |

### Usage

```python
from kerf_aero.cert.do178c.templates import generate_template

project = {
    "project_name": "AutopilotFW",
    "dal": "B",
    "aircraft_type": "Fixed-wing UAV",
    "applicant": "Acme Avionics Inc.",
    "version": "1.0",
    "date": "2026-05-19",
    "author": "J. Smith",
    "dqa": "DER-12345",
}

psac_md = generate_template("PSAC", project)
sdp_md  = generate_template("SDP",  project)
svp_md  = generate_template("SVP",  project)
```

All unrecognised or missing keys produce `[FILL IN]` placeholders.

### Key sections per document

**PSAC** — System Overview · Certification Basis · Software Life-Cycle ·
Stage of Involvement · Software Life-Cycle Data · Schedule ·
Tool Qualification · Alternative Methods

**SDP** — Development Environment · Requirements Process · Design Process ·
Coding Process · Integration Process · Traceability

**SVP** — Verification Environment · HLR Verification · LLR Verification ·
Source Code Verification · Structural Coverage Analysis (DAL-dependent) ·
Independence · Regression Strategy

**SCMP** — Configuration Identification · Baselines · Change Control ·
Problem Reporting · Status Accounting · Archive · CM Audits

**SQAP** — Organisation · Plan Compliance Reviews · Process Audits ·
Transition Criteria · Non-Conformance Management · QA Records

**HLR** — System Context · Traceability Table · Functional Requirements ·
Performance Requirements · Safety Requirements · Derived Requirements

**LLR** — HLR Traceability · Inputs · Outputs · Processing Requirements ·
Timing Requirements

**SDD** — Architecture · Partitions · Execution Model · Module Descriptions ·
Data Design · LLR-to-Code Traceability Index

**SVCP** — Test Environment · HLR Normal-Range and Robustness Tests ·
LLR Tests · Structural Coverage Objectives · Regression Suite

---

## DO-254 Templates

### Supported document types

| doc_type | Document |
|----------|----------|
| `PHAC`   | Plan for Hardware Aspects of Certification |
| `HDP`    | Hardware Development Plan |
| `HVVP`   | Hardware Verification and Validation Plan |
| `HPAP`   | Hardware Process Assurance Plan |

### Usage

```python
from kerf_aero.cert.do254.templates import generate_template

project = {
    "project_name": "FPGAFlightController",
    "hardware_type": "FPGA",           # or "ASIC" / "PCB"
    "dal": "B",
    "aircraft_type": "Rotorcraft",
    "applicant": "Kerf Silicon GmbH",
    "version": "1.0",
    "date": "2026-05-19",
    "author": "A. Johnson",
    "der": "DER-67890",
}

phac_md = generate_template("PHAC", project)
hdp_md  = generate_template("HDP",  project)
hvvp_md = generate_template("HVVP", project)
hpap_md = generate_template("HPAP", project)
```

### Key sections per document

**PHAC** — System Overview · Hardware Overview & Function ·
Certification Basis · Hardware Life-Cycle · Requirements ·
Stage of Involvement · Life-Cycle Data Control · Tool Assessment ·
Previously Developed Hardware

**HDP** — Development Environment · HDL & Coding Standards · EDA Toolchain ·
Target Device · Requirements Process · Derived Requirements Feedback ·
Conceptual Design · Detailed Design (RTL, Synthesis, P&R, Bitstream/GDSII) ·
Integration · Traceability

**HVVP** — Simulation Environment · Formal Verification Environment ·
Hardware-in-the-Loop / Bench Test · Requirements Verification (Review,
Functional Simulation, Coverage) · Hardware Design Verification (RTL Reviews,
Timing Analysis, Equivalence Check) · Elemental Analysis (DAL A/B) ·
Validation · Independence

**HPAP** — HPA Organisation & Independence · Plan Compliance Reviews ·
Transition Criteria Audits · Spot Audits · Conformity Review (FCA + PCA) ·
Non-Conformance Management · HPA Records

---

## Combined import

```python
from kerf_aero.cert import classify_dal, do178c_template, do254_template

dal = classify_dal("hazardous")          # -> "B"
psac = do178c_template("PSAC", {...})
phac = do254_template("PHAC", {...})
```

---

## Notes for evaluators

- Templates follow the normative section structure of the respective RTCA
  standard but are **not** a substitute for an authoritative copy of the
  standard or for review by a qualified DER.
- The kerf-aero cert module is part of the open-core MIT-licensed packages;
  the generated Markdown may be used without restriction.
- Structural coverage objectives in the SVP template adapt automatically to
  the DAL provided in `project_meta` (MC/DC for A, decision for B, statement
  for C, none for D).
- DO-254 elemental analysis items appear only in DAL A and DAL B artefact
  lists, consistent with DO-254 §6.2 guidance.
