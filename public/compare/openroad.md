---
slug: openroad
competitor: OpenROAD
category: cad-silicon
left: kerf
right: openroad
hero_tagline: "OpenROAD automates RTL-to-GDS-II — Kerf wraps it so you describe intent and the tool figures out the rest."
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
