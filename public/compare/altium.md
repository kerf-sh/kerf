---
slug: altium
competitor: "Altium Designer"
category: cad-electronic
left: kerf
right: altium
hero_tagline: "Industrial-grade PCB design — Situs router vs MIT open-core EDA."
reviewed_at: 2026-05-19
order: 2
features:
  # ── D6 Schematic capture ───────────────────────────────────────────────────
  - name: "Schematic capture (KiCad round-trip, ERC)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Eeschema-class; KiCad 6/7/8/9 native format; multi-sheet"
      source: "https://www.altium.com/documentation/altium-designer/working-with-schematics"
      tier: paid
    kerf:
      status: "[x]"
      notes: "KiCad round-trip viewer wired (read-only)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/schematic/capture.py"

  - name: "Hierarchical schematic (multi-sheet, port-based)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Hierarchical + multi-board schematics; sheet symbols and ports"
      source: "https://www.altium.com/documentation/altium-designer/hierarchical-design"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Hierarchical sheets + port propagation"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/hier_schematic.py"

  - name: "Multi-channel schematic (repeated blocks)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Full multi-channel design with room replication"
      source: "https://www.altium.com/documentation/altium-designer/multi-channel-design"
      tier: paid
    kerf:
      status: "[~]"
      notes: "Hierarchical sheets cover repeated blocks; no Altium-style room replication"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/hier_schematic.py"

  - name: "ERC depth"
    domain: D6
    competitor:
      status: "yes"
      notes: "Pin-type / bus / diff-pair / custom rules ERC"
      source: "https://www.altium.com/documentation/altium-designer/erc-violations-reference"
      tier: paid
    kerf:
      status: "[x]"
      notes: "ERC + IPC-2221B presets"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/erc.py"

  - name: "Component library management"
    domain: D6
    competitor:
      status: "yes"
      notes: "Altium Library system + Concord Pro + Manufacturer Part Search"
      source: "https://www.altium.com/documentation/altium-designer/component-management"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Library management + BOM/distributor integration"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/lib_mgmt.py"

  - name: "Design variants / BOM variants"
    domain: D6
    competitor:
      status: "yes"
      notes: "Design variants + variant BOM + ActiveBOM"
      source: "https://www.altium.com/documentation/altium-designer/design-variants"
      tier: paid
    kerf:
      status: "[x]"
      notes: "BOM variants engine"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/variants.py"

  # ── D6 PCB layout ─────────────────────────────────────────────────────────
  - name: "Interactive PCB editing (route/place)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Full interactive cursor PCB editor"
      source: "https://www.altium.com/documentation/altium-designer/pcb-design-workflow"
      tier: paid
    kerf:
      status: "[ ]"
      notes: "View-only; no cursor interactive editing today"
      kerf_note: "Requires frontend canvas PCB editor (cad-core UI work). Backend router is ready; UI layer is the gap."
      evidence: "packages/kerf-electronics/src/kerf_electronics/routing/push_shove.py"

  - name: "Push-and-shove router (Situs engine)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Gold-standard Situs push-and-shove + slide + gloss"
      source: "https://www.altium.com/documentation/altium-designer/interactive-routing"
      tier: paid
    kerf:
      status: "[~]"
      notes: "Shove router engine present; less mature than Situs"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/shove_router.py"

  - name: "Autoroute (FreeRouting)"
    domain: D6
    competitor:
      status: "yes"
      notes: "ActiveRoute interactive guided autorouter"
      source: "https://www.altium.com/documentation/altium-designer/autorouting-with-activeroute"
      tier: paid
    kerf:
      status: "[x]"
      notes: "FreeRouting v1.9.0 integrated; SHA-256 pinned; DSN→SES round-trip via autoroute_circuit tool"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/autoroute.py"

  - name: "Differential pairs routing + length tuning"
    domain: D6
    competitor:
      status: "yes"
      notes: "Diff-pair routing + interactive tuning + phase matching"
      source: "https://www.altium.com/documentation/altium-designer/working-with-differential-pairs"
      tier: paid
    kerf:
      status: "[~]"
      notes: "Length tuning present; differential-pair routing lighter"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/diffpair.py"

  - name: "Net classes and design rules"
    domain: D6
    competitor:
      status: "yes"
      notes: "Full rule engine: clearances, net classes, constraint regions"
      source: "https://www.altium.com/documentation/altium-designer/pcb-design-rules"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Net-class system + rule presets"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/net_classes.py"

  - name: "DRC / ERC"
    domain: D6
    competitor:
      status: "yes"
      notes: "Comprehensive DRC with 100+ rule types"
      source: "https://www.altium.com/documentation/altium-designer/pcb-design-rules-violations-reference"
      tier: paid
    kerf:
      status: "[x]"
      notes: "DRC overlay wired + IPC-2221B presets"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/drc_presets.py"

  - name: "HDI stack-up (buried/blind/micro-via)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Buried / blind / micro-via, back-drill, rigid-flex layer stack"
      source: "https://www.altium.com/documentation/altium-designer/layer-stack-manager"
      tier: paid
    kerf:
      status: "[~]"
      notes: "Via types supported; HDI rule depth lighter than Altium"
      evidence: "packages/kerf-electronics/src/kerf_electronics/stackup/impedance.py"

  - name: "Impedance-controlled stack-up"
    domain: D6
    competitor:
      status: "yes"
      notes: "Layer Stack Manager with embedded impedance calculator"
      source: "https://www.altium.com/documentation/altium-designer/layer-stack-manager"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Impedance calculator integrated with stack-up"
      evidence: "packages/kerf-electronics/src/kerf_electronics/stackup/impedance.py"

  - name: "Rigid-flex PCB stack-up"
    domain: D6
    competitor:
      status: "yes"
      notes: "Rigid-flex design rules + bend-zone DRC"
      source: "https://www.altium.com/documentation/altium-designer/rigid-flex-pcb-design"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Flex stack-up modelling"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/flex_stackup.py"

  - name: "Multi-board design (MB3D workspace)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Multi-board 3D workspace — connectors, board-to-board clearance"
      source: "https://www.altium.com/documentation/altium-designer/multi-board-design"
      tier: paid
    kerf:
      status: "[ ]"
      notes: "Single-board per project today; no multi-board equivalent"
      evidence: "packages/kerf-electronics/src/kerf_electronics/plugin.py"

  - name: "3D PCB editor (STEP import, clearance)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Native 3D PCB with STEP import, 3D clearance DRC, 3D body management"
      source: "https://www.altium.com/documentation/altium-designer/3d-pcb-design"
      tier: paid
    kerf:
      status: "[~]"
      notes: "Board 3D view via STEP; shallower clearance DRC"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/fab.py"

  - name: "Via stitching / copper pour / teardrops"
    domain: D6
    competitor:
      status: "yes"
      notes: "Via stitching, copper pour, teardrops, pad/via push"
      source: "https://www.altium.com/documentation/altium-designer/copper-pour"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Via stitching + copper pour tooling"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/via_stitching.py"

  - name: "Panelisation"
    domain: D6
    competitor:
      status: "yes"
      notes: "Embedded Board Array (panelisation) with V-cut / tab routing"
      source: "https://www.altium.com/documentation/altium-designer/panelizing-boards"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Panelize built in"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/panelize.py"

  # ── D6 Simulation / analysis ──────────────────────────────────────────────
  - name: "SPICE simulation (mixed-signal)"
    domain: D6
    competitor:
      status: "yes"
      notes: "XSPICE mixed-signal simulation built in"
      source: "https://www.altium.com/documentation/altium-designer/simulation-xspice"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Real ngspice wired; binary .raw not yet parsed"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  - name: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    domain: D6
    competitor:
      status: "yes"
      notes: "HyperLynx SI: IBIS/Touchstone, DDR wizard, full-wave coupling"
      source: "https://www.altium.com/documentation/altium-designer/signal-integrity"
      tier: paid
    kerf:
      status: "[x]"
      notes: "si_eye_wizard (analytical) + IBIS 5.1 parser + Bergeron channel (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si_eye_wizard.py"

  - name: "PDN (DC IR-drop + AC sweep)"
    domain: D6
    competitor:
      status: "yes"
      notes: "PDN Analyzer: per-net Z sweep, ripple, decap optimisation"
      source: "https://www.altium.com/documentation/altium-designer/pdn-analyzer"
      tier: paid
    kerf:
      status: "[x]"
      notes: "pdn_wizard: target-Z, decap placement, plane resonance (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/pdn_wizard.py"

  - name: "EMC (radiated/shielding/limits)"
    domain: D6
    competitor:
      status: "yes"
      notes: "HyperLynx EMC (separate licence); no built-in FCC/CISPR limit checker"
      source: "https://www.altium.com/documentation/altium-designer/signal-integrity"
      tier: paid
    kerf:
      status: "[x]"
      notes: "emc_wizard: FCC §15.109 + CISPR 32 (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/emc_wizard.py"

  - name: "PCB thermal (board-level)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Altium 365 thermal simulation / external HyperLynx Thermal"
      source: "https://www.altium.com/altium-365/thermal-simulation"
      tier: paid
    kerf:
      status: "[~]"
      notes: "thermal_board 2-D FD steady-state (backend); lumped Rθ model"
      evidence: "packages/kerf-electronics/src/kerf_electronics/thermal_board.py"

  - name: "Analog PVT corner simulation"
    domain: D6
    competitor:
      status: "yes"
      notes: "Via HyperLynx AMS or Altium SPICE + manual corner sweeps"
      source: "https://www.altium.com/documentation/altium-designer/simulation-xspice"
      tier: paid
    kerf:
      status: "[x]"
      notes: "60 PVT corners (5P×3V×4T) + MC mismatch; bandgap ±31mV (backend)"
      evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py"

  - name: "Antenna / link budget"
    domain: D6
    competitor:
      status: "yes"
      notes: "RF design rules + antenna tuning; HyperLynx for full-wave RF"
      source: "https://www.altium.com/documentation/altium-designer/rf-microstrip-transmission-lines"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Antenna element models + link-budget calculator (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/antenna/tools.py"

  # ── D6 Manufacturing / fab output ─────────────────────────────────────────
  - name: "Gerber / Excellon NC drill output"
    domain: D6
    competitor:
      status: "yes"
      notes: "Gerber RS-274X, Excellon, ODB++, IPC-2581, IPC-D-356A all native"
      source: "https://www.altium.com/documentation/altium-designer/generating-gerber-files"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Gerber/Excellon in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/fab.py"

  - name: "ODB++ output"
    domain: D6
    competitor:
      status: "yes"
      notes: "ODB++ native export"
      source: "https://www.altium.com/documentation/altium-designer/generating-odb-plus-plus-files"
      tier: paid
    kerf:
      status: "[x]"
      notes: "ODB++ export in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/odbpp_export.py"

  - name: "IPC-2581 output"
    domain: D6
    competitor:
      status: "yes"
      notes: "IPC-2581 native export (A/B)"
      source: "https://www.altium.com/documentation/altium-designer/ipc-2581-export"
      tier: paid
    kerf:
      status: "[x]"
      notes: "IPC-2581 in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/fab_bundle.py"

  - name: "IPC-D-356A netlist output"
    domain: D6
    competitor:
      status: "yes"
      notes: "IPC-D-356A netlist (bed-of-nails test) native"
      source: "https://www.altium.com/documentation/altium-designer/generating-ipc-d-356a-netlist-files"
      tier: paid
    kerf:
      status: "[x]"
      notes: "IPC-D-356A in-box"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/ipc_netlist.py"

  - name: "IDF MCAD bridge"
    domain: D6
    competitor:
      status: "yes"
      notes: "MCAD CoDesigner: live SOLIDWORKS/Creo/Inventor/CATIA bidirectional link"
      source: "https://www.altium.com/documentation/altium-designer/mcad-ecad-collaboration"
      tier: paid
    kerf:
      status: "[~]"
      notes: "IDF MCAD bridge + board STEP; no live push from Kerf to MCAD"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/idf_export.py"

  - name: "PCB layer tools (flip/mirror/layer mapping)"
    domain: D6
    competitor:
      status: "yes"
      notes: "Full layer management, mirroring, and cross-section views"
      source: "https://www.altium.com/documentation/altium-designer/pcb-layers-and-objects"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Layer tools wired"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/pcb_layer_tools.py"

  - name: "Test point management"
    domain: D6
    competitor:
      status: "yes"
      notes: "IPC-D-356A test point rules + DFT checker"
      source: "https://www.altium.com/documentation/altium-designer/test-point-usage-reporting"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Test-point placement and reporting"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/testpoint.py"

  # ── D6 Silicon / digital ───────────────────────────────────────────────────
  - name: "Silicon synth (Yosys) / STA / GDS / formal"
    domain: D6
    competitor:
      status: "no"
      notes: "Altium is PCB-focused; silicon RTL flow not in scope"
      source: "https://www.altium.com/documentation/altium-designer/pcb-design-workflow"
      tier: paid
    kerf:
      status: "[x]"
      notes: "Yosys synth + STA + GDS + DRC + LVS + formal — deep, zero UI (backend)"
      evidence: "packages/kerf-silicon/src/kerf_silicon/formal/equiv.py"

  # ── D10 Wiring / harness ──────────────────────────────────────────────────
  - name: "Wiring/harness (WireViz + 3D router)"
    domain: D10
    competitor:
      status: "addon"
      notes: "Harness design via Altium Harness Designer (separate product); no WireViz"
      source: "https://www.altium.com/products/harness-design"
      tier: paid
    kerf:
      status: "[x]"
      notes: "WireViz runner + 3D harness router wired (WiringView)"
      evidence: "packages/kerf-wiring/src/kerf_wiring/wireviz_runner.py"

  # ── D7 Manufacturing outputs ───────────────────────────────────────────────
  - name: "ActiveBOM / Octopart supply-chain integration"
    domain: D7
    competitor:
      status: "yes"
      notes: "ActiveBOM with Octopart + Altium 365 supply-chain analytics"
      source: "https://www.altium.com/documentation/altium-designer/activebom"
      tier: paid
    kerf:
      status: "[x]"
      notes: "BOM cost tool + distributor pricing integration"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tools/bom_cost.py"

  - name: "DFM checks (PCB)"
    domain: D7
    competitor:
      status: "yes"
      notes: "DFM rules + Altium 365 manufacturing portal checks"
      source: "https://www.altium.com/documentation/altium-designer/dfm-checks"
      tier: paid
    kerf:
      status: "[~]"
      notes: "DFM rule checker (backend, mesh-based)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/dfm/rules.py"

  - name: "Trace current / IPC-2221 ampacity"
    domain: D7
    competitor:
      status: "yes"
      notes: "IPC-2221 trace current DRC rule built in"
      source: "https://www.altium.com/documentation/altium-designer/pcb-design-rules-violations-reference"
      tier: paid
    kerf:
      status: "[x]"
      notes: "IPC-2221 trace ampacity calculator"
      evidence: "packages/kerf-electronics/src/kerf_electronics/tracecurrent/ampacity.py"
---

# Kerf vs Altium Designer

Altium Designer is the commercial ECAD benchmark: industry-leading push-and-shove interactive routing (Situs engine), ActiveRoute autorouter, hierarchical and multi-board schematics, a mature rules system, HDI/RF stack-up tooling, 3D PCB editor, MCAD CoDesigner (SOLIDWORKS / CREO / Inventor / CATIA), signal-integrity via HyperLynx / Touchstone I/O, and a cloud-collaboration overlay in Altium 365. It is Windows-only, subscription-priced (~$8,000–$10,000+ USD/seat/yr, as of May 2026), and widely considered the gold standard for serious PCB engineering work. Kerf does not match Altium's interactive routing polish or HDI/RF depth. Where Kerf differs: open-core MIT, multi-discipline (mech + jewelry + ECAD), chat-driven editing, BYO LLM, integrated simulation pre-compliance suite, IPC-2581 + IPC-D-356A + IDF exports, and a significantly lower price of entry.

## Where Altium is strong

- **Gold-standard Situs push-and-shove router.** Altium's interactive routing engine is the industry reference for complex PCB layout — push, slide, and gloss algorithms that handle dense HDI boards with confidence. Kerf's shove router is less mature.
- **Comprehensive HDI/RF tooling.** Buried/blind/micro-via, back-drill, rigid-flex, layer-stack manager with impedance calculation, and full RF design rules — a complete stack for high-density and high-frequency boards.
- **HyperLynx SI integration.** IBIS/Touchstone I/O, DDR wizard, and back-annotation of signal-integrity results from HyperLynx into Altium's layout environment.
- **PDN Analyzer.** Per-net impedance sweep, ripple analysis, and decoupling capacitor optimisation — a mature tool integrated into the layout flow.
- **Multi-board design (MB3D workspace).** Design, place, and check multiple interconnected PCBs in a single 3D workspace — a capability Kerf does not have today.
- **MCAD CoDesigner.** A live bidirectional ECAD↔MCAD link with SOLIDWORKS, Creo, Inventor, and CATIA — synchronising component placement, board outline, and keepouts without an intermediate file.
- **Production-hardened 30+ year lineage.** Altium has been refined through decades of demanding PCB projects across aerospace, automotive, and medical device manufacturing.
- **Altium 365 cloud collaboration.** A cloud overlay for concurrent multi-user access, design review, and supply chain visibility — though it adds cost on top of the base subscription.

## Where Kerf differs

- **MIT open-core, dramatically lower cost.** Altium is ~$8,000–$10,000+/seat/yr (as of May 2026). Kerf is MIT-licensed — free locally with pay-as-you-go cloud compute. No seat fee, no annual renewal, no commercial-use restriction.
- **Cross-platform.** Kerf runs in the browser (hosted SaaS) or as a single local binary on Windows, macOS, and Linux. Altium is Windows-only.
- **Mechanical CAD in the same workspace.** Altium requires a separate MCAD tool for enclosure and product design. Kerf ships an OCCT B-rep modeller, constraint sketcher, sheet metal, 3-axis CAM, and 5-axis 3+2 CAM in the same workspace as the PCB editor.
- **Chat-native workflow and BYO LLM.** Describe a routing rule, schematic change, or simulation setup in plain language; the LLM edits the source backed by live doc-search. Bring your own Anthropic or OpenAI API key. Altium has no LLM integration we're aware of (as of May 2026).
- **In-box pre-compliance simulation suite.** `si_eye_wizard` (SI + eye diagram), `pdn_wizard` (per-net impedance, decap optimisation), `emc_wizard` (FCC §15.109 + CISPR 32), and `thermal_board` (2-D FD steady-state) — all in-box without an HyperLynx licence.
- **IPC-D-356A netlist and IDF exports in-box.** Kerf includes IPC-D-356A netlist output and IDF MCAD bridge without add-in.
- **40-module jewelry domain.** Ring v4, gemstones v2, settings v3/v4, chain v2, and casting export — an entire vertical Altium has no scope for.
- **kerf-sdk Python scripting.** Automate over HTTP/JSON-RPC from your own machine — the same interface the LLM uses internally.

## Honest gaps — where Kerf is behind today

- **Interactive routing maturity.** Altium's Situs engine is the gold standard. Kerf's shove router handles most boards well but is younger and less battle-tested on dense HDI layouts.
- **HDI depth.** Altium's HDI rule depth, buried/blind/micro-via checking, and back-drill tooling are more mature than Kerf's current offering.
- **Multi-board projects.** Altium's MB3D workspace has no Kerf equivalent today.
- **MCAD CoDesigner live link.** Altium's live bidirectional SOLIDWORKS/Creo/Inventor link is more polished than Kerf's IDF MCAD bridge (no live push from Kerf to MCAD today).
- **HyperLynx SI depth.** Altium's HyperLynx integration provides full-wave-coupled SI analysis that Kerf's analytical wizard models do not replicate. For compliance-lab-grade SI work, HyperLynx is more appropriate.
- **Production tooling maturity.** 30+ years of refining Altium's DRC, design rules, and output generators means the production flow is extremely hardened. Kerf is newer.
- **Community and learning resources.** The Altium Designer user community is very large. Kerf's is early-stage.

## Side by side

| Feature | Altium Designer | Kerf |
|---|---|---|
| License | ⚠️ Proprietary subscription | ✅ MIT open-core |
| Cost | ⚠️ ~$8,000–$10,000+ USD/seat/yr (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Platform | ⚠️ Windows only | ✅ Browser + Win/macOS/Linux binary |
| Push-and-shove router | ✅ Situs — gold-standard | ⚠️ Shove router (less mature) |
| ActiveRoute autorouter | ✅ Interactive guided autorouting | ✅ FreeRouting integrated |
| Differential pairs | ✅ Diff-pair routing + tuning (mature) | ⚠️ Length tuning; diff-pair lighter |
| HDI stackup & via types | ✅ Buried / blind / micro-via, back-drill | ⚠️ Via types; HDI rule depth lighter |
| Multi-board (MB3D) | ✅ Multi-board design workspace | ❌ Single-board per project today |
| 3D PCB editor | ✅ Native 3D PCB — STEP import, clearance | ⚠️ Board 3D view; shallower |
| ERC depth | ✅ Pin-type / bus / diff / custom rules | ✅ ERC + IPC-2221B presets |
| SPICE simulation | ✅ Mixed-signal XSPICE | ✅ SPICE + model library |
| Signal integrity (SI) | ✅ HyperLynx SI; IBIS/Touchstone | ✅ si_eye_wizard (analytical) |
| PDN analysis | ✅ PDN Analyzer | ✅ pdn_wizard — Z target, decap placement |
| EMC pre-compliance | ⚠️ Via external HyperLynx EMC | ✅ emc_wizard — FCC §15.109 / CISPR 32 |
| Thermal (board) | ⚠️ Via Altium 365 Sim / external | ✅ thermal_board — 2-D FD steady-state |
| MCAD CoDesigner | ✅ SOLIDWORKS / CREO / Inventor / CATIA | ⚠️ IDF MCAD bridge + board STEP |
| Mechanical CAD (same tool) | ❌ External MCAD required | ✅ Full B-rep, sketcher, sheet metal, CAM |
| IPC-2581 / ODB++ / Gerber | ✅ Full fab suite | ✅ Gerber/Excellon/IPC-2581/ODB++ |
| IPC-D-356A netlist | ✅ Full fab suite | ✅ IPC-D-356A in-box |
| Chat / LLM editing | ❌ None known (as of May 2026) | ✅ Chat-native — edits circuit source |
| Jewelry / architecture | ❌ Not applicable | ✅ 40-module jewelry + BIM-adjacent in-box |
| Cloud collaboration | ⚠️ Altium 365 (separate SaaS subscription) | ✅ Integrated hosted SaaS; cloud git built-in |
