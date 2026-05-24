---
slug: openroad
competitor: OpenROAD
category: cad-silicon
left: kerf
right: openroad
hero_tagline: "OpenROAD automates RTL-to-GDS-II — Kerf wraps it so you describe intent and the tool figures out the rest."
reviewed_at: 2026-05-24
features:
  - domain: D6
    feature: "Silicon — logic synthesis (Yosys)"
    competitor:
      status: yes
      note: "Yosys integrated in OpenROAD-flow-scripts as the synthesis step"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "kerf-silicon Yosys bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — floorplanning"
    competitor:
      status: yes
      note: "initialize_floorplan / make_tracks via OpenROAD Tcl API"
      source: "https://openroad.readthedocs.io/en/latest/main/src/ifp/README.html"
    kerf:
      status: yes
      note: "OpenROAD bridge exposes floorplan commands via chat and kerf-sdk (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — global placement"
    competitor:
      status: yes
      note: "RePlAce global placer integrated in OpenROAD"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/gpl"
    kerf:
      status: yes
      note: "Placement exposed via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — detailed placement"
    competitor:
      status: yes
      note: "OpenDP detailed placer (legalisation + row alignment)"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/dpl"
    kerf:
      status: yes
      note: "Detailed placement via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — clock tree synthesis (CTS)"
    competitor:
      status: yes
      note: "TritonCTS 2.0 integrated in OpenROAD"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/cts"
    kerf:
      status: yes
      note: "CTS via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — global routing"
    competitor:
      status: yes
      note: "FastRoute 4.1 global router integrated in OpenROAD"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/grt"
    kerf:
      status: yes
      note: "Global routing via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — detailed routing (TritonRoute)"
    competitor:
      status: yes
      note: "TritonRoute IEEE-TCAD-grade detailed router; supports LEF/DEF"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/drt"
    kerf:
      status: yes
      note: "Detailed routing via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — static timing analysis (STA)"
    competitor:
      status: yes
      note: "OpenSTA bundled; full SPEF-based sign-off STA"
      source: "https://openroad.readthedocs.io/en/latest/main/src/sta/README.html"
    kerf:
      status: yes
      note: "STA via OpenROAD/OpenSTA bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — parasitic extraction (RCX)"
    competitor:
      status: yes
      note: "OpenRCX SPEF parasitic extractor built into OpenROAD"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/rcx"
    kerf:
      status: yes
      note: "Parasitic extraction via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — power planning / PDN"
    competitor:
      status: yes
      note: "pdngen integrated for power-distribution-network insertion"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/pdn"
    kerf:
      status: yes
      note: "PDN engine exposed via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — filler / tap cell insertion"
    competitor:
      status: yes
      note: "tapcell and filler insertion commands in OpenROAD Tcl flow"
      source: "https://openroad.readthedocs.io/en/latest/main/src/tap/README.html"
    kerf:
      status: yes
      note: "Cell insertion via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — DRC / sign-off (KLayout)"
    competitor:
      status: yes
      note: "KLayout DRC deck integration for sign-off in OpenROAD-flow-scripts"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/scripts"
    kerf:
      status: yes
      note: "DRC/sign-off via KLayout integration in the OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — LVS"
    competitor:
      status: yes
      note: "Magic LVS + KLayout LVS scripts in OpenROAD-flow-scripts"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts"
    kerf:
      status: yes
      note: "LVS via Magic/KLayout integration in the OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — GDS-II output"
    competitor:
      status: yes
      note: "write_def + KLayout GDSII stream-out produce tape-out-ready GDS-II"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "GDS-II output via OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — open PDK support (SKY130 / GF180)"
    competitor:
      status: yes
      note: "SKY130, GF180, ASAP7 PDK flows validated by the OpenROAD project"
      source: "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/platforms"
    kerf:
      status: yes
      note: "Open PDK flows supported through the OpenROAD bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — analog PVT-corner simulation"
    competitor:
      status: no
      note: "OpenROAD is a digital P&R flow; no built-in analog corner sim"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "60 PVT corners (5P×3V×4T) + Monte-Carlo mismatch per corner; Pelgrom-matched (backend)"
      evidence: "packages/kerf-silicon/analog/pvt.py"

  - domain: D6
    feature: "Silicon — formal verification"
    competitor:
      status: no
      note: "OpenROAD does not include formal equivalence checking"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "Formal verification via Yosys formal flow in kerf-silicon bridge (backend)"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — chat-native / LLM-driven flow"
    competitor:
      status: no
      note: "OpenROAD is driven by Tcl scripts and CLI; no natural-language interface"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "All OpenROAD steps reachable via plain-language prompts and kerf-sdk Python; doc-search prevents API hallucination"
      evidence: "packages/kerf-silicon/"

  - domain: D6
    feature: "Silicon — managed cloud execution"
    competitor:
      status: no
      note: "OpenROAD requires a local Linux environment; no hosted compute"
      source: "https://openroad.readthedocs.io/en/latest/main/README.html"
    kerf:
      status: yes
      note: "Kerf hosted environment provides cloud compute for OpenROAD runs"
      evidence: "cloud/"
---

# Kerf + OpenROAD

OpenROAD is not a competitor to Kerf. It is a complementary open-source tool that Kerf wraps and exposes through a chat-native interface. This page explains what OpenROAD does, what Kerf adds on top, and why the two together are more capable than either alone.

## What OpenROAD is

OpenROAD (Open Reconfigurable Computing And Design) is the flagship open-source RTL-to-GDSII physical design flow, developed by a consortium including DARPA, UC San Diego, University of Michigan, and others. It implements a complete automated place-and-route pipeline: floor planning, power planning, global placement, clock tree synthesis (CTS), global routing, detailed routing, and DRC sign-off. The OpenROAD Project also bundles OpenDB, TritonRoute, OpenSTA (static timing analysis), and integrations with Yosys (logic synthesis) and KLayout (GDSII viewer/editor). It has taped out real silicon and is used in DARPA OpenROAD and OpenFASST programs.

OpenROAD is open-source (BSD 3-clause licensed) and runs on Linux. It does not have a commercial GUI — it is driven by Tcl scripts and a command-line flow. For a digital IC designer who knows the flow, it is a powerful free alternative to Cadence Innovus or Synopsys IC Compiler. For everyone else, the Tcl interface is a significant barrier.

## Where they converge

Both OpenROAD and Kerf are open-source (OpenROAD: BSD; Kerf: MIT). Both are designed for use without a commercial EDA licence. Both support GDS-II as the output format for mask submission to a fab. Both can be used in open-source silicon workflows (SkyWater 130nm, GlobalFoundries 180nm, Intel 16 via open PDKs).

## What Kerf adds

Kerf wraps OpenROAD's Tcl API through its `kerf-sdk` bridge and exposes it via the same chat-native interface used for mechanical CAD and PCB design. This means:

- **Describe intent in plain language.** "Run floorplan with 60% utilisation and 10µm margin" or "check timing closure with a 500MHz clock" — the LLM translates to the correct OpenROAD Tcl commands, backed by doc-search so it does not hallucinate API surface.
- **Unified workspace.** A hardware project that spans a custom ASIC (OpenROAD), a PCB carrier (Kerf PCB), and a mechanical enclosure (Kerf mechanical) lives in one Kerf project with a single git history and a single cloud collaboration layer.
- **Python scripting via kerf-sdk.** Automate multi-tool flows — run Yosys synthesis, invoke OpenROAD place-and-route, extract timing reports, and feed results into a Kerf BOM — all from one Python script using the same API the LLM uses.
- **Managed cloud execution.** OpenROAD runs on Linux; Kerf's hosted environment provides cloud compute for OpenROAD runs without requiring the user to set up a Linux build environment.

## Where OpenROAD is stronger on its own

- **Raw PDK depth.** An experienced IC designer using OpenROAD directly with Tcl scripts and a custom flow has more fine-grained control than Kerf's chat abstraction provides. Kerf's LLM interface is an on-ramp, not a ceiling, but expert users may prefer the direct Tcl flow for production tapeout.
- **Community and flow maturity.** The OpenROAD community has taped out real silicon. The flow is validated against SkyWater 130nm and other open PDKs. Kerf's silicon integration is younger.
- **KLayout integration.** OpenROAD integrates directly with KLayout for GDS-II viewing and DRC scripting via DRC decks. Kerf does not currently expose a KLayout-level GDS viewer.

## Feature matrix

| Feature | Kerf | OpenROAD (standalone) |
|---|---|---|
| License | MIT (Kerf) + BSD (OpenROAD) | BSD 3-clause |
| Interface | Chat-native + Python SDK + GUI | Tcl scripts + CLI |
| RTL-to-GDSII flow | Yes (via OpenROAD integration) | Yes (native) |
| Floorplanning | Yes (chat-driven) | Yes (Tcl) |
| Placement (global + detail) | Yes | Yes |
| Clock tree synthesis | Yes | Yes (TritonCTS) |
| Routing (global + detail) | Yes | Yes (TritonRoute) |
| Static timing analysis | Yes | Yes (OpenSTA) |
| DRC / sign-off | Yes | Yes (via KLayout DRC deck) |
| GDS-II output | Yes | Yes |
| Unified PCB + mechanical workspace | Yes | No |
| Cloud execution | Yes (hosted) | Requires Linux environment |
| Python scripting | kerf-sdk on PyPI | Tcl / Python OpenROAD bindings |
| Yosys synthesis integration | Yes | Yes |
| Open PDK support (SKY130 etc.) | Yes | Yes |

## Both produce GDS-II

OpenROAD and Kerf both produce GDS-II (Graphic Database System II) — the de facto standard mask layout format for IC fabrication. A design taped out via Kerf's OpenROAD integration produces the same GDS-II output as a raw OpenROAD flow, consumable by any commercial foundry fab or open-access shuttle service (Efabless, IHP, SkyWater).

---
*Last reviewed: 2026-05-19. OpenROAD information sourced from openroad.tools and the OpenROAD Project GitHub. Kerf capabilities reflect the current shipped product.*
