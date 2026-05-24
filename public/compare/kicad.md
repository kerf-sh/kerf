---
slug: kicad
competitor: "KiCad"
category: cad-electronic
left: kerf
right: kicad
hero_tagline: "Open-source EDA suite — GPL vs MIT, deep vs integrated."
reviewed_at: 2026-05-19
order: 1
features:
  # ── D6 Electronics / EDA / Silicon ──────────────────────────────────────
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: yes
      note: "Eeschema — hierarchical sheets, hierarchical labels, full ERC"
      source: "https://docs.kicad.org/8.0/en/eeschema/eeschema.html"
    kerf:
      status: yes
      note: "Schematic capture + KiCad round-trip; viewer wired"
      evidence: "packages/kerf-electronics/src/kerf_electronics/schematic/capture.py"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: yes
      note: "Pcbnew — full PCB editor, push-shove router"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: yes
      note: "PCB viewer + KiCad round-trip via kicad_io; view-only editing"
      evidence: "packages/kerf-electronics/src/kerf_electronics/kicad_io.py"

  - domain: D6
    feature: "Interactive PCB editing (route/place)"
    competitor:
      status: yes
      note: "Pcbnew — full interactive routing, component placement"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: no
      note: "View-only; no cursor-driven interactive route/place in UI"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routing/push_shove.py"

  - domain: D6
    feature: "Push-and-shove router"
    competitor:
      status: yes
      note: "Pcbnew shove router — walks around/shoves obstacles, DRC-clean"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: yes
      note: "Shove router engine (younger, less battle-tested than KiCad)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routing/push_shove.py"

  - domain: D6
    feature: "Autoroute (FreeRouting)"
    competitor:
      status: yes
      note: "FreeRouting plugin ships with KiCad; DSN→SES round-trip"
      source: "https://www.kicad.org/discover/pcb-design/"
    kerf:
      status: yes
      note: "FreeRouting v1.9.0 JAR integrated; SHA-256 pinned (9084a48…); DSN→SES round-trip"
      evidence: "packages/kerf-electronics/src/kerf_electronics/freerouting/freerouting.py"

  - domain: D6
    feature: "Differential pairs / length tuning"
    competitor:
      status: yes
      note: "Route Differential Pair + skew/length tuning in Pcbnew"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: partial
      note: "Length tuning tool; diff-pair routing lighter than KiCad"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/length_tuning.py"

  - domain: D6
    feature: "DRC / ERC"
    competitor:
      status: yes
      note: "Graphical custom DRC rule editor (v10); full ERC in Eeschema"
      source: "https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html"
    kerf:
      status: yes
      note: "DRC overlay wired; ERC + IPC-2221B presets"
      evidence: "packages/kerf-electronics/src/kerf_electronics/drc.py"

  - domain: D6
    feature: "SPICE simulation"
    competitor:
      status: yes
      note: "ngspice built in — AC/DC/transient/noise/FFT with graphical plotter"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Real ngspice wired; binary .raw parse gap noted"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No native SI; community recommends external tools (openEMS etc.)"
      source: "https://forum.kicad.info/t/signal-integrity-with-pcbnew-layouts/8652"
    kerf:
      status: yes
      note: "si_eye_wizard + IBIS 5.1 parser + Bergeron channel (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si_eye_wizard.py"

  - domain: D6
    feature: "EMC (radiated/shielding/limits)"
    competitor:
      status: no
      note: "No EMC pre-compliance analysis in KiCad"
      source: "https://forum.kicad.info/t/signal-integrity-with-pcbnew-layouts/8652"
    kerf:
      status: yes
      note: "emc_wizard — FCC §15.109 + CISPR 32 (analytical, backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/emc_wizard.py"

  - domain: D6
    feature: "PDN (DC IR-drop + AC sweep)"
    competitor:
      status: no
      note: "No integrated PDN/power-integrity analysis in KiCad"
      source: "https://forum.kicad.info/t/open-source-power-analysis-tool/21652"
    kerf:
      status: yes
      note: "pdn_wizard + ac_impedance: Z(ω), target-Z, decap optimiser"
      evidence: "packages/kerf-electronics/src/kerf_electronics/pdn/ac_impedance.py"

  - domain: D6
    feature: "PCB thermal"
    competitor:
      status: no
      note: "No board-level thermal solver; manual θJA calculations only"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: partial
      note: "thermal_board — 2-D FD steady-state (backend); lumped Rθ"
      evidence: "packages/kerf-electronics/src/kerf_electronics/thermal_board.py"

  - domain: D6
    feature: "Stackup / impedance calculator"
    competitor:
      status: yes
      note: "PCB Calculator: trace-width (IPC-2221), transmission-line Z0"
      source: "https://docs.kicad.org/8.0/en/pcb_calculator/pcb_calculator.html"
    kerf:
      status: yes
      note: "stackup impedance calculator; controlled-impedance via routing"
      evidence: "packages/kerf-electronics/src/kerf_electronics/stackup/impedance.py"

  - domain: D6
    feature: "Gerber / Excellon export"
    competitor:
      status: yes
      note: "Gerber + Excellon drill output; long-standing KiCad capability"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: yes
      note: "Gerber + Excellon in-box via fab bundle"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/gerber.py"

  - domain: D6
    feature: "IPC-2581 export"
    competitor:
      status: yes
      note: "Native IPC-2581 export added in KiCad 10 (March 2026)"
      source: "https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/"
    kerf:
      status: yes
      note: "IPC-2581 writer in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/ipc2581.py"

  - domain: D6
    feature: "ODB++ export"
    competitor:
      status: yes
      note: "ODB++ export added in KiCad 10; complete fab+assembly archive"
      source: "https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/"
    kerf:
      status: yes
      note: "ODB++ writer in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/odbpp/writer.py"

  - domain: D6
    feature: "3D PCB viewer (STEP export)"
    competitor:
      status: yes
      note: "3D viewer with STEP, VRML, GLB export; STEP for MCAD hand-off"
      source: "https://docs.kicad.org/8.0/en/getting_started_in_kicad/getting_started_in_kicad.html"
    kerf:
      status: yes
      note: "Board 3D view + STEP export via board_step.py"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/board_step.py"

  - domain: D6
    feature: "ECAD importers (Allegro / PADS / gEDA / Eagle)"
    competitor:
      status: yes
      note: "Allegro, PADS, gEDA importers in KiCad 10; Eagle in v7+"
      source: "https://www.kicad.org/blog/2026/02/Three-New-Importers-in-KiCad-10-Allegro-PADS-and-gEDA/"
    kerf:
      status: yes
      note: "Eagle / Allegro / PADS / gEDA / KiCad import via kicad_io"
      evidence: "packages/kerf-electronics/src/kerf_electronics/kicad_io.py"

  - domain: D6
    feature: "Component / symbol library"
    competitor:
      status: yes
      note: "Thousands of symbols, footprints, 3D models; database-lib support"
      source: "https://docs.kicad.org/8.0/en/kicad/kicad.html"
    kerf:
      status: yes
      note: "Component library + distributor pricing via atopile/library"
      evidence: "packages/kerf-electronics/src/kerf_electronics/atopile/library.py"

  - domain: D6
    feature: "Design variants"
    competitor:
      status: yes
      note: "Design variants (BOM + DNP overrides) added in KiCad 10"
      source: "https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/"
    kerf:
      status: yes
      note: "Variant/DNP overrides via tools/variants.py"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/variants.py"

  - domain: D6
    feature: "Panelisation"
    competitor:
      status: no
      note: "No built-in panel tool; KiKit is a community plugin, not in-box"
      source: "https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html"
    kerf:
      status: yes
      note: "Panelize built-in (skyline + array) via tools/panelize.py"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/panelize.py"

  - domain: D6
    feature: "Monte-Carlo SPICE corner analysis"
    competitor:
      status: no
      note: "ngspice has .mc command but no guided process-corner sweep"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "sim_corner: min/typ/max sweeps + yield estimation (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/sim_corner.py"

  - domain: D6
    feature: "Analog PVT-corner sim"
    competitor:
      status: no
      note: "No analog IC corner simulation; KiCad is PCB-level, not IC-level"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "60-corner (5P×3V×4T) + MC Pelgrom mismatch (backend)"
      evidence: "packages/kerf-electronics/src/kerf_silicon/analog/pvt.py"

  - domain: D6
    feature: "Silicon synth (Yosys) / STA / GDS / DRC / LVS"
    competitor:
      status: no
      note: "KiCad is PCB-level EDA; no RTL synthesis or IC physical design"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Yosys synth + OpenLane P&R + STA + GDS + LVS (backend)"
      evidence: "packages/kerf-silicon/src/kerf_silicon/bridges/yosys_bridge.py"

  - domain: D6
    feature: "Antenna / link budget"
    competitor:
      status: no
      note: "No RF/antenna link-budget tool in KiCad"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Antenna element + link budget calculators (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/antenna/element.py"

  - domain: D6
    feature: "Battery/BMS, motor/gate/LED driver sizing"
    competitor:
      status: no
      note: "No power-component sizing wizards in KiCad"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Battery/BMS, gate-drive, motor-drive, LED-driver sizing (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/charger/bms.py"

  # ── D10 Electrical / Energy / PLC ───────────────────────────────────────
  - domain: D10
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: no
      note: "KiCad is PCB/schematic EDA; no cable/harness design tool"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "WiringView wired; harness3d 3D router + formboard + report"
      evidence: "packages/kerf-electronics/src/kerf_electronics/harness3d/router.py"

  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB/motion)"
    competitor:
      status: no
      note: "KiCad has no PLC programming or IEC 61131-3 support"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired (D10 domain)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "KiCad has no solar PV system simulation"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + MPPT (backend, D10)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  # ── D1 Mechanical CAD ────────────────────────────────────────────────────
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: no
      note: "KiCad has no parametric mechanical CAD or constraint sketcher"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "PlaneGCS WASM constraint sketcher wired in-browser"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/board_step.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: no
      note: "No MCAD assembly workspace in KiCad (separate tool required)"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "OCCT assembly + mates wired; BOM panel"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab/board_step.py"

  # ── D14 Cost / Materials / LCA ───────────────────────────────────────────
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "KiCad has no manufacturing cost estimation"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "Should-cost engine; 6 processes + Boothroyd-Dewhurst (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/bom_cost.py"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: no
      note: "KiCad has no multi-objective material selection framework"
      source: "https://docs.kicad.org/8.0/en/introduction/introduction.html"
    kerf:
      status: yes
      note: "200 materials, Pareto frontier, weighted-score (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/bom_cost.py"
---

# Kerf vs KiCad

KiCad 10.0 (March 2026) is a free, GPL-licensed, cross-platform EDA suite. It now natively exports IPC-2581 and ODB++, gained an overhauled track-tuning system with time-domain constraints, design variants, a graphical DRC rule editor, and Allegro/PADS/gEDA importers. ngspice is built in. KiCad's depth and community on the pure-PCB side are formidable. Kerf covers much of the same electronics ground and adds a unified mechanical CAD workspace, a simulation triad (Monte-Carlo SPICE corner analysis, 2-D finite-difference thermal, SI/PDN/EMC pre-compliance wizards), chat-native editing, and the kerf-sdk — but does not match KiCad's EDA maturity, library breadth, or community today.

**Simulation honesty note:** Kerf's SI/EMC/PDN wizards use reduced-order analytical models, not full-wave EM solvers. They are useful for early-stage risk assessment; they are NOT a substitute for ANSYS HFSS, Allegro PI/SI, or an accredited compliance test lab.

## Where KiCad is strong

- **GPL-licensed, truly free, no seat restrictions.** KiCad is free for commercial use with no revenue caps, no seat limits, and no cloud-account requirement.
- **Mature, battle-tested EDA workflow.** Decades of development, a large community, and millions of real-world boards validate its PCB workflow. Kerf is newer.
- **Push-and-shove routing (Pcbnew).** The Pcbnew router is a mature, production-tested push-and-shove engine. Kerf's shove router is younger.
- **Vast component libraries.** KiCad's built-in symbol and footprint libraries are enormous and actively maintained by the community. Kerf's libraries are smaller.
- **Differential pair + track tuning (v10).** Mature diff-pair routing and interactive length tuning with time-domain constraints shipped in v10.
- **Native IPC-2581 + ODB++ (v10).** KiCad now exports both advanced fab formats natively.
- **ngspice simulation.** AC/DC/transient SPICE with a built-in plotter — mature and well-integrated.
- **ECAD importer breadth (v10).** Allegro, PADS, gEDA, Eagle importers ship in-box.

## Where Kerf differs

- **MIT open-core vs GPL.** Kerf is permissively MIT-licensed — you can embed it in proprietary commercial products. KiCad's GPL has copyleft implications for products that link against it.
- **Mechanical CAD in the same workspace.** KiCad requires a separate MCAD tool (FreeCAD, SolidWorks, etc.). Kerf ships an OCCT B-rep modeller, constraint sketcher, sheet metal, and CAM in the same workspace.
- **Chat-native workflow.** Describe a routing rule, schematic change, or simulation setup in plain language; the LLM edits the source backed by live doc-search. KiCad has no LLM integration we're aware of (as of May 2026).
- **Monte-Carlo SPICE corner analysis.** `sim_corner` runs min/typ/max parameter sweeps across process corners with yield estimation — beyond KiCad's baseline ngspice.
- **SI / PDN / EMC pre-compliance wizards.** `si_eye_wizard`, `pdn_wizard`, `emc_wizard` (FCC §15.109 + CISPR 32), and `thermal_board` (2-D FD steady-state) — no comparable equivalents in KiCad as far as we're aware (as of May 2026).
- **Jewelry and architecture in the same tool.** Kerf's multi-discipline scope spans electronics, mechanical, jewelry, and BIM-adjacent workflows in one workspace.
- **kerf-sdk Python scripting.** HTTP/JSON-RPC from your own machine — the same interface the LLM uses internally.
- **Hosted SaaS option.** Design in the browser without installing anything locally.

## Honest gaps — where Kerf is behind today

- **EDA maturity and routing polish.** KiCad's EDA workflow is older, more battle-tested, and more widely validated. Kerf's shove router is less mature.
- **Library breadth.** KiCad's symbol and footprint libraries are substantially larger than Kerf's today.
- **ECAD community and learning resources.** The KiCad community is enormous. Kerf's electronics community is early-stage.
- **Differential pair routing.** KiCad's diff-pair + interactive tuning system is more mature than Kerf's current offering.
- **Pure-PCB depth.** For teams whose entire workflow is pure PCB design without mechanical CAD, KiCad's EDA depth and zero-cost model are hard to beat.

## Side by side

| Feature | KiCad | Kerf |
|---|---|---|
| License | ✅ GPL v3 (free, copyleft) | ✅ MIT open-core (permissive) |
| Cost | ✅ Free, no restrictions, no seats | ✅ Free local; pay-as-you-go hosted |
| Platform | ✅ Win / macOS / Linux desktop | ✅ Browser + single-binary local |
| Hierarchical schematic | ✅ Eeschema — dozens of sheets | ✅ Hierarchical + sheet borders |
| ERC | ✅ Mature ERC + exclusions | ✅ ERC + IPC-2221B presets |
| SPICE simulation | ✅ ngspice — AC/DC/transient | ✅ SPICE + model library + Monte-Carlo corner runs |
| Push-and-shove router | ✅ Pcbnew (mature) | ✅ Shove router (younger) |
| Differential pairs / length tune | ✅ Diff-pair + tuner (v10) | ⚠️ Length tuning; diff-pair lighter |
| DRC rules system | ✅ Graphical rule editor (v10) | ✅ DRC + IPC-2221B presets |
| IPC-2581 / ODB++ / Gerber | ✅ Native IPC-2581 + ODB++ (v10) | ✅ Gerber/Excellon/IPC-2581/ODB++ |
| Signal integrity (SI) | ⚠️ External tools recommended | ✅ si_eye_wizard — eye/crosstalk (analytical) |
| EMC pre-compliance | ⚠️ No EMC analysis | ✅ emc_wizard — FCC §15.109 / CISPR 32 |
| PDN analysis | ⚠️ No automated PDN | ✅ pdn_wizard — Z target, decap placement |
| Thermal (board) | ⚠️ Manual θJA calcs | ✅ thermal_board — 2-D FD steady-state |
| Panelisation | ⚠️ KiKit (community plugin) | ✅ Panelize built in |
| ECAD importers | ✅ Allegro / PADS / gEDA / Eagle (v10) | ✅ Eagle / Allegro / PADS / gEDA / KiCad |
| Mechanical CAD (same tool) | ❌ Separate tool required | ✅ Full B-rep, sketcher, sheet metal |
| Chat / LLM editing | ❌ None | ✅ Chat-native — edits circuit source |
| Hosted / cloud option | ❌ Desktop only | ✅ Hosted SaaS + local install |
