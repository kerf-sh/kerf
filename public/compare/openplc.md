---
slug: openplc
competitor: OpenPLC
category: cad-firmware
left: kerf
right: openplc
hero_tagline: "OpenPLC brings IEC 61131-3 logic to open hardware — Kerf connects the logic to the PCB that runs it."
reviewed_at: 2026-05-24
features:
  - domain: D10
    feature: "PLC IEC 61131-3 ladder/ST"
    competitor:
      status: yes
      note: "LD, ST, FBD, SFC, IL — all five IEC 61131-3 languages in OpenPLC Editor (Beremiz-based)"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired in-browser; chat-native ST generation"
      evidence: "packages/kerf-plc/"
  - domain: D10
    feature: "Firmware build/upload/monitor/debug"
    competitor:
      status: yes
      note: "OpenPLC Runtime compiles IEC 61131-3 to C++, deploys to target; web dashboard for monitor"
      source: "https://www.openplcproject.com/runtime"
    kerf:
      status: yes
      note: "FirmwareActions + debug panel wired; build/upload/monitor/debug in-browser"
      evidence: "src/components/FirmwareActions"
  - domain: D10
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: no
      note: "OpenPLC has no wiring harness or cable design tooling"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "WiringView with WireViz + 3D harness router wired"
      evidence: "src/components/WiringView"
  - domain: D10
    feature: "NEC power distribution + point-to-point SC"
    competitor:
      status: no
      note: "OpenPLC has no power distribution or short-circuit analysis"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "NEC power distribution + point-to-point short-circuit (backend)"
      evidence: "packages/kerf-electrical/"
  - domain: D10
    feature: "AC load-flow (Ybus / Newton-Raphson)"
    competitor:
      status: no
      note: "OpenPLC has no load-flow or power-systems analysis"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "Full polar-form Newton-Raphson load-flow; 3+5-bus validated (backend)"
      evidence: "packages/kerf-electrical/loadflow.py"
  - domain: D10
    feature: "OTA delivery endpoint (cloud)"
    competitor:
      status: no
      note: "OpenPLC has no OTA delivery; firmware must be flashed manually per device"
      source: "https://github.com/thiagoralves/OpenPLC_Editor"
    kerf:
      status: yes
      note: "POST /firmware/ota/release (Ed25519-signed) + GET /firmware/ota/check; C backends for ESP32/STM32/SAMD"
      evidence: "packages/kerf-firmware/src/kerf_firmware/routes.py"
  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "OpenPLC has no solar PV or energy modelling capability"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + global MPPT + mismatch loss + partial shading (backend)"
      evidence: "packages/kerf-electrical/solarpv/shading.py"
  - domain: D10
    feature: "Protection coordination (TCC) / arc-flash"
    competitor:
      status: no
      note: "OpenPLC has no protection coordination or arc-flash analysis"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "IEEE C37.112 U1-U5 TCC + IEEE 1584-2018 arc-flash incident energy (backend)"
      evidence: "packages/kerf-electrical/"
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: no
      note: "OpenPLC has no schematic capture or ERC; hardware design is outside its scope"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "Schematic capture + ERC wired; KiCad round-trip import/export"
      evidence: "src/components/SchematicView"
  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: no
      note: "OpenPLC has no PCB layout tooling"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "PCB layout viewer wired (KiCad round-trip + tscircuit); DRC overlay included"
      evidence: "src/components/PCBView"
  - domain: D6
    feature: "EMC (radiated/shielding/limits)"
    competitor:
      status: no
      note: "OpenPLC has no EMC pre-compliance analysis"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "emc_wizard: FCC §15.109 + CISPR 32 closed-form radiated/conducted limits (backend)"
      evidence: "packages/kerf-emc/"
  - domain: D6
    feature: "PDN (DC IR-drop + AC sweep)"
    competitor:
      status: no
      note: "OpenPLC has no PDN or power integrity analysis"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "pdn_wizard: Z(ω) target-Z, DC IR-drop, decap optimiser (backend)"
      evidence: "packages/kerf-si/pdn/ac_impedance.py"
  - domain: D9
    feature: "Controls — classical (Routh/Bode/RL/PID tune)"
    competitor:
      status: partial
      note: "PID function blocks per IEC 61131-3 are supported; no Bode/root-locus/graphical tuning"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "Classical controls: Routh stability, Bode, root locus, PID auto-tune (backend)"
      evidence: "packages/kerf-controls/"
  - domain: D9
    feature: "Controls — state-space / LQR / Kalman"
    competitor:
      status: no
      note: "OpenPLC has no state-space, LQR, or Kalman filter tooling"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "State-space, LQR (CARE), Luenberger observer, discrete ZOH c2d (backend)"
      evidence: "packages/kerf-controls/statespace.py"
  - domain: D1
    feature: "Parametric solid modelling (B-rep)"
    competitor:
      status: no
      note: "OpenPLC has no mechanical CAD or solid modelling capability"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "Full OCCT B-rep, constraint sketcher, sheet metal, assemblies — all in-browser"
      evidence: "src/components/CADView"
  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC/Mach3)"
    competitor:
      status: no
      note: "OpenPLC has no CAM or G-code toolpath capability"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "G-code post for Fanuc, GRBL, LinuxCNC, Mach3; 3-axis toolpaths wired in CAMView"
      evidence: "src/components/CAMView"
  - domain: D14
    feature: "BOM + distributor pricing"
    competitor:
      status: no
      note: "OpenPLC has no BOM management or distributor pricing integration"
      source: "https://www.openplcproject.com/reference"
    kerf:
      status: yes
      note: "BOM management + real-time distributor pricing (Octopart/Mouser/Digi-Key) in-browser"
      evidence: "src/components/BOMView"
---

# Kerf + OpenPLC

OpenPLC is not a competitor to Kerf. It is a complementary open-source PLC runtime and IDE that Kerf integrates with to bridge the gap between hardware design (PCB, enclosure) and the IEC 61131-3 control logic that runs on that hardware. This page explains what OpenPLC does, what Kerf adds on top, and why they are stronger together.

## What OpenPLC is

OpenPLC is an open-source IEC 61131-3 compliant PLC (Programmable Logic Controller) runtime and editor developed by Thiago Rodrigues Alves. It implements all five IEC 61131-3 programming languages:

- **LD** — Ladder Diagram
- **ST** — Structured Text
- **FBD** — Function Block Diagram
- **SFC** — Sequential Function Chart
- **IL** — Instruction List (deprecated but supported)

OpenPLC Runtime runs on Linux (Raspberry Pi, BeagleBone, industrial SBCs), Windows, and Arduino-compatible hardware. The OpenPLC Editor (based on Beremiz) is a cross-platform IDE for writing and compiling IEC 61131-3 programs. The runtime compiles to C++ and runs without a commercial PLC licence. It is used in industrial automation education, open hardware SCADA systems, and research.

## Where they converge

Both OpenPLC and Kerf target hardware engineers who are building control systems — whether for industrial automation, building management, or custom machinery. Both are open-source (OpenPLC: Apache 2.0; Kerf: MIT). Both acknowledge that the software and the hardware are not separate concerns: OpenPLC runs on real hardware (Raspberry Pi, ESP32, Arduino); Kerf designs that hardware (PCB schematic, layout, enclosure, pre-compliance simulation).

## What Kerf adds

Kerf integrates OpenPLC as a companion for hardware projects that include a programmable control element:

- **PCB design for the hardware that runs OpenPLC.** Design the I/O board, the relay driver, the sensor frontend, or the custom SBC carrier in Kerf's PCB workspace. Pre-compliance simulate the power supply, the I/O bus isolation, and the EMC protection circuits before ordering. The PCB and the PLC program that runs on it live in the same Kerf project.
- **Chat-native PLC logic generation.** Describe the control logic — "on rising edge of DI1, start FAN_MOTOR timer for 30s; stop if DI2 is active" — and the LLM generates OpenPLC Structured Text code backed by IEC 61131-3 doc-search.
- **Enclosure design.** Model the DIN-rail enclosure or panel in Kerf's mechanical workspace. Sheet metal flat patterns, enclosure cutouts for I/O connectors, and DIN rail mounting geometry are all in the same project.
- **Unified project and version control.** PLC program, PCB design, BOM, and enclosure model are in one Kerf project with cloud-git versioning — a complete machine build history.

## Where OpenPLC is stronger on its own

- **Runtime depth.** An experienced PLC programmer using OpenPLC directly has access to the full runtime configuration — scan cycle tuning, modbus mapping, I/O pin assignment, hardware driver configuration — without LLM abstraction.
- **Hardware abstraction layer.** OpenPLC's HAL covers Raspberry Pi GPIO, Arduino analogWrite/digitalRead, and Modbus TCP/RTU slave — a broad set of hardware targets that Kerf's integration wraps at a higher level.
- **Community and educational resources.** OpenPLC has a dedicated user community, instructional videos, and industrial automation curriculum built around it. Kerf's PLC integration is a bridge, not a replacement for that learning.
- **CODESYS compatibility.** OpenPLC's code is importable/exportable in ways compatible with some CODESYS workflows. Kerf does not target full CODESYS interop.

## Feature matrix

| Feature | Kerf | OpenPLC (standalone) |
|---|---|---|
| License | MIT (Kerf) + Apache 2.0 (OpenPLC) | Apache 2.0 |
| IEC 61131-3 languages | ST (chat-native generation) | LD, ST, FBD, SFC, IL |
| Runtime targets | Via OpenPLC: RPi, Arduino, Linux | RPi, BeagleBone, Arduino, Linux, Windows |
| Chat-native logic generation | Yes | No |
| PCB design for target hardware | In-box (full Kerf PCB workflow) | Not included |
| Enclosure / mechanical | In-box (Kerf mechanical) | Not included |
| Pre-compliance simulation | In-box (SI/EMC/PDN/thermal) | Not included |
| Hardware I/O pin mapping | Via OpenPLC config | OpenPLC Editor + HAL |
| Modbus TCP/RTU | Via OpenPLC runtime | Yes (built-in) |
| OTA delivery (cloud endpoint) | ✅ POST /firmware/ota/release — Ed25519-signed; ESP32/STM32/SAMD backends | ❌ Not included (manual flash only) |
| BOM management | In-box (Kerf BOM + distributors) | Not included |
| Project version control | Cloud git (Kerf) | External (git manually) |
| Python scripting | kerf-sdk on PyPI | None (runtime is C++) |
| Open source | Yes (MIT + Apache) | Yes (Apache 2.0) |

## Both produce IEC 61131-3 Structured Text

OpenPLC and Kerf's OpenPLC integration both produce IEC 61131-3 Structured Text (ST) programs that compile to the OpenPLC runtime. ST programs generated by Kerf's chat interface are standard IEC 61131-3 text — open the `.st` file in the OpenPLC Editor directly, inspect it, modify it, and compile it independently of Kerf. No proprietary format or lock-in.

---
*Last reviewed: 2026-05-19. OpenPLC information sourced from openplcproject.com and the OpenPLC GitHub repository. Kerf capabilities reflect the current shipped product.*
