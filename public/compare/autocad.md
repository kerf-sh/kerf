---
slug: autocad
competitor: "AutoCAD"
category: drafting
left: kerf
right: autocad
hero_tagline: "Industry-standard 2D drafting + .dwg ecosystem — different primary jobs."
reviewed_at: 2026-05-19
order: 1
features:
  # D1 — Geometry & core CAD
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "Parametric constraints: geometric + dimensional; OSNAP + inference; dynamic input"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-DA1B3D1A-7A9C-4B10-9B3F-8F5E8B2C4D7A"
    kerf:
      status: yes
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: partial
      note: "Solid 3D extrude/revolve/sweep present but not history-based parametric"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-3D-MODELING"
    kerf:
      status: yes
      note: "OCCT feature tree with full parametric history"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Direct edit (push-pull)"
    competitor:
      status: yes
      note: "PRESSPULL command; 3D solid direct editing; grips-based face manipulation"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-PRESSPULL"
    kerf:
      status: yes
      note: "push_pull (planar + curved), move_face, delete_face wired as ops"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/direct_edit.py"

  - domain: D1
    feature: "Fillet / chamfer (constant)"
    competitor:
      status: yes
      note: "FILLET and CHAMFER commands for 2D and 3D; well-established workflow"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-FILLET"
    kerf:
      status: yes
      note: "Wired; constant-radius fillet + chamfer"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Industry-defining 2D drafting: dimension styles, leaders, tolerances, GD&T callouts"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-DIMENSIONING"
    kerf:
      status: partial
      note: "Template-based; not live B-rep projection; no UI panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "GD&T on drawings / MBD / PMI"
    competitor:
      status: yes
      note: "GD&T feature control frames, datum labels, surface texture symbols in drawing"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-GDT-OVERVIEW"
    kerf:
      status: partial
      note: "Data model only (kerf-gdnt); no UI placement on drawings"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py"

  - domain: D1
    feature: "Patterns (linear/polar) + mirror"
    competitor:
      status: yes
      note: "ARRAY (rectangular/polar/path) + MIRROR; 2D and 3D"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-ARRAY"
    kerf:
      status: yes
      note: "Linear/polar patterns + mirror wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: paid
      note: "Available in AutoCAD Mechanical toolset add-on; not in base AutoCAD"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-mechanical"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF (K-factor); no auto corner-relief"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: no
      note: "AutoCAD has no parametric assembly environment; XREF for multi-file; no mate constraints"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-XREF"
    kerf:
      status: yes
      note: "Wired; coincident/concentric/parallel + BOM panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: no
      note: "No parametric configurations; use dynamic blocks or separate drawing files"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-DYNAMIC-BLOCKS"
    kerf:
      status: yes
      note: "Engine complete; ConfigurationsPanel.jsx wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: partial
      note: "Surface commands (SURFBLEND, SURFPATCH, etc.) present but not NURBS-class tools"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-SURFACE-MODELING"
    kerf:
      status: yes
      note: "blend_srf, network_srf (Gordon), patch_srf_fit, match_srf, G3 blends wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: yes
      note: "UNION, SUBTRACT, INTERSECT solid Boolean operations"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-BOOLEAN-OPERATIONS"
    kerf:
      status: yes
      note: "OCCT Boolean ops; no graceful failure handling / fuzzy heal"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  # D6 — Electronics / EDA / silicon
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: paid
      note: "AutoCAD Electrical toolset: schematic capture, wire numbering, ERC; separate paid SKU"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "Schematic viewer wired (KiCad round-trip); ERC overlay"
      evidence: "packages/kerf-electronics/src/kerf_electronics/kicad_io.py"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: no
      note: "AutoCAD has no PCB layout capability; Electrical toolset is schematic-only"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "PCB viewer wired (read-only); tscircuit + KiCad round-trip"
      evidence: "packages/kerf-electronics/src/kerf_electronics/kicad_io.py"

  - domain: D6
    feature: "DRC / ERC"
    competitor:
      status: paid
      note: "ERC in AutoCAD Electrical toolset only; no PCB DRC"
      source: "https://help.autodesk.com/view/ACDLT/2025/ENU/?guid=GUID-ELECTRICAL-ERC"
    kerf:
      status: yes
      note: "DRC overlay wired; IPC-2221B manufacturing presets"
      evidence: "packages/kerf-electronics/src/kerf_electronics/drc.py"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No SI analysis in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "IBIS 5.1 parser + Bergeron channel + PRBS eye envelope (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si_eye_wizard.py"

  - domain: D6
    feature: "EMC (radiated/shielding/limits)"
    competitor:
      status: no
      note: "No EMC analysis in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Closed-form EMC wizard; no full-wave (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/emc_wizard.py"

  - domain: D6
    feature: "PDN (DC IR-drop + AC sweep)"
    competitor:
      status: no
      note: "No PDN analysis in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Frequency-domain Z(ω) + target-Z + decap optimiser (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/pdn_wizard.py"

  - domain: D6
    feature: "SPICE"
    competitor:
      status: no
      note: "No SPICE simulation; AutoCAD Electrical is schematic-diagram only"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "Real ngspice wired; binary .raw not yet parsed"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  # D7 — Manufacturing / CAM
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: no
      note: "No CAM in AutoCAD; requires separate Autodesk CAM product (Fusion / HSMXpress)"
      source: "https://www.autodesk.com/products/autocad/overview"
    kerf:
      status: yes
      note: "3-axis CAM with tool DB, CAMView wired"
      evidence: "packages/kerf-cam/src/kerf_cam"

  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC/Mach3)"
    competitor:
      status: no
      note: "No G-code output; not a CAM tool"
      source: "https://www.autodesk.com/products/autocad/overview"
    kerf:
      status: yes
      note: "Fanuc/GRBL/LinuxCNC/Mach3 posts; no G41/42 cutter-comp"
      evidence: "packages/kerf-cam/src/kerf_cam/posts"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: no
      note: "No nesting in AutoCAD base; nesting tools via 3rd-party add-ons only"
      source: "https://www.autodesk.com/products/autocad/overview"
    kerf:
      status: yes
      note: "Minkowski-sum NFP + IFP + bottom-left fill; 57.6% L-shape util (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/nesting"

  # D8 — Civil / infrastructure / geo
  - domain: D8
    feature: "Horizontal+vertical alignment (clothoid, SSD)"
    competitor:
      status: paid
      note: "Civil 3D product (separate SKU); Map 3D in AutoCAD toolset covers geospatial not civil alignments"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-map-3d"
    kerf:
      status: yes
      note: "Clothoid + SSD engine; AASHTO exhibit validated (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/horizontal_alignment.py"

  - domain: D8
    feature: "Corridor / cross-section"
    competitor:
      status: paid
      note: "Civil 3D only; not in Map 3D toolset included with AutoCAD"
      source: "https://www.autodesk.com/products/civil-3d/overview"
    kerf:
      status: yes
      note: "Divided highway + reverse-crown + urban curb-gutter templates (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/corridor.py"

  - domain: D8
    feature: "Survey / COGO"
    competitor:
      status: paid
      note: "AutoCAD Map 3D has basic geospatial; Civil 3D has full COGO traverse/closure"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-map-3d"
    kerf:
      status: yes
      note: "Traverse adjust, resection COGO (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil"

  - domain: D8
    feature: "Geodesy / projections (Vincenty, TM, UTM, LCC)"
    competitor:
      status: paid
      note: "Map 3D toolset: coordinate system library, reprojection; not Vincenty-depth geodesy"
      source: "https://help.autodesk.com/view/MAP/2025/ENU/?guid=GUID-COORDINATE-SYSTEMS"
    kerf:
      status: yes
      note: "Vincenty + TM + UTM + LCC deep geodesy (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/crs.py"

  - domain: D8
    feature: "Hydrology (rational/SCS/TR-55)"
    competitor:
      status: no
      note: "No hydrology calculation engine in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Rational method / SCS / TR-55; no 2D/unsteady (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/pile/liquefaction)"
    competitor:
      status: no
      note: "No geotechnical analysis in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Seed-Idriss CSR + SPT/CPT CRR + Tokimatsu liquefaction; Loma Prieta validated (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil"

  # D10 — Electrical / energy / PLC
  - domain: D10
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: paid
      note: "AutoCAD Electrical toolset: wire numbers, from-to lists, connector reports; no 3D harness routing"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "WiringView wired; WireViz + 3D harness router"
      evidence: "packages/kerf-wiring/src/kerf_wiring/harness3d.py"

  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB/motion)"
    competitor:
      status: no
      note: "AutoCAD Electrical is schematic-focused; no IEC 61131-3 PLC programming environment"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired"
      evidence: "packages/kerf-plc/src/kerf_plc/power_flow.py"

  - domain: D10
    feature: "NEC power distribution + point-to-point SC"
    competitor:
      status: paid
      note: "AutoCAD Electrical: panel schedule report; no NEC load-flow or short-circuit calc"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-electrical"
    kerf:
      status: yes
      note: "Deep NEC load calc + SC (backend)"
      evidence: "packages/kerf-energy/src/kerf_energy"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "No solar PV analysis in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + global MPPT + mismatch loss (backend)"
      evidence: "packages/kerf-energy/src/kerf_energy"

  # D11 — Tolerancing / metrology / QA
  - domain: D11
    feature: "Limits & fits (ISO 286)"
    competitor:
      status: paid
      note: "AutoCAD Mechanical toolset: fits and tolerances table; ISO 286 hole/shaft selection"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-mechanical"
    kerf:
      status: yes
      note: "Full ISO 286 limits & fits engine (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt"

  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS/MC)"
    competitor:
      status: paid
      note: "AutoCAD Mechanical toolset: some stackup assistance; not a dedicated stackup tool"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-mechanical"
    kerf:
      status: yes
      note: "WC/RSS/MC tolerance stackup; Monte-Carlo LCG bug to fix (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt"

  # Cross-cutting / platform
  - domain: D1
    feature: "Persistent face naming"
    competitor:
      status: partial
      note: "Handle-based entity naming in 3D solid; not full topological face-name persistence"
      source: "https://help.autodesk.com/view/ACD/2025/ENU/?guid=GUID-3D-MODELING"
    kerf:
      status: partial
      note: "Two disconnected systems (Python DAG vs OCCT faceNaming.js); not unified"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D7
    feature: "Feeds & speeds + tool-life"
    competitor:
      status: no
      note: "No feeds/speeds or tool-life calculation in AutoCAD; CAM tools sold separately"
      source: "https://www.autodesk.com/products/autocad/overview"
    kerf:
      status: yes
      note: "Taylor extended + Gilbert economic speed (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/tool_db.py"

  - domain: D6
    feature: "Battery/BMS, motor/gate/LED driver"
    competitor:
      status: no
      note: "No electronic component sizing tools in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets"
    kerf:
      status: yes
      note: "Battery/BMS + motor/gate/LED driver sizing calculators (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/battery"

  - domain: D8
    feature: "Pavement design (AASHTO '93)"
    competitor:
      status: no
      note: "No pavement design in Map 3D or any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-map-3d"
    kerf:
      status: yes
      note: "Full AASHTO 1993 pavement design engine (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil"

  - domain: D10
    feature: "Firmware build/upload/monitor/debug"
    competitor:
      status: no
      note: "No firmware toolchain in any AutoCAD toolset"
      source: "https://www.autodesk.com/products/autocad/overview"
    kerf:
      status: yes
      note: "FirmwareActions + debug panel wired"
      evidence: "packages/kerf-firmware/src"

  - domain: D7
    feature: "Moldflow / fill sim"
    competitor:
      status: no
      note: "No moldflow simulation in AutoCAD; separate Moldflow product (Autodesk Moldflow)"
      source: "https://www.autodesk.com/products/moldflow/overview"
    kerf:
      status: yes
      note: "Hele-Shaw front tracking + weld-line + air-trap detection (backend)"
      evidence: "packages/kerf-mold/src/kerf_mold"

  - domain: D1
    feature: "Hole wizard (standards/tapped/cbore)"
    competitor:
      status: paid
      note: "AutoCAD Mechanical toolset: hole callouts and standard hole types in 2D; no 3D hole wizard"
      source: "https://www.autodesk.com/products/autocad/included-toolsets/autocad-mechanical"
    kerf:
      status: no
      note: "Bare cylinder punch only; no standards-based hole wizard"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"
---

# Kerf vs AutoCAD

AutoCAD is a 40+ year incumbent — the tool that defined 2D drafting for architecture, engineering, and construction, and the originator of the .dwg format that is the de-facto exchange standard for 2D documentation. Subscription pricing is ~US$255/mo or ~US$2,030/yr (as of May 2026). Kerf is NOT a drafting-first tool and is not positioned as an AutoCAD replacement for production AEC work. AutoCAD owns 2D drafting + .dwg; Kerf is a 3D parametric CAD with drawing export, multi-discipline scope, and a chat-native workflow. They solve different primary problems — the honest comparison is below.

**DWG interchange:** Kerf imports DWG (Tier 1 via libredwg bridge). Kerf does NOT export DWG natively — it writes DXF instead (same .dwg/.dxf family; broadly compatible with AutoCAD and AutoCAD LT).

## Where AutoCAD is strong

- **40+ years as the 2D drafting standard.** AutoCAD invented the drafting command line, dynamic blocks, paper-space/model-space workflows, linetypes, dimension styles, and layer standards that every downstream AEC tool speaks. Its 2D drafting depth is unmatched.
- **.dwg format ownership.** AutoCAD is the native format owner for .dwg — the de-facto exchange format for AEC documentation worldwide. Every tool in the industry can read and write .dwg because AutoCAD established it.
- **Dynamic blocks.** Block definitions with visibility states, action parameters, and stretch/array actions enable re-usable parametric 2D elements that Kerf does not replicate.
- **Paper-space/model-space workflow.** Full paper-space with multi-scale viewports, plot styles, and title-block management — the definitive 2D-to-print workflow.
- **Sheet sets and CAD standards.** Sheet Set Manager coordinates multi-drawing project output; CAD Standards Manager enforces layer, linetypes, and text style compliance across drawings.
- **Express Tools and productivity macros.** 50+ built-in productivity tools (Overkill, Super Hatch, Quick Select, etc.) and deep AutoLISP / .NET API for custom automation.
- **AEC verticals.** Civil 3D, AutoCAD Architecture, AutoCAD MEP, Plant 3D, and AutoCAD Electrical extend the core drafting engine for every AEC sub-discipline.
- **40+ year community and training ecosystem.** Official Autodesk courses, textbooks, YouTube, and a massive certified practitioner base.

## Where Kerf differs

- **MIT open-core, dramatically lower cost.** AutoCAD is ~US$2,030/yr (as of May 2026). Kerf is MIT-licensed — free locally on any OS, no Autodesk account, no seat subscription.
- **3D parametric-first.** Kerf's OCCT feature tree (pad, pocket, revolve, loft), constraint sketcher, persistent face IDs, and assembly joints are a parametric CAD environment, not a 3D solid modeller added on top of a drafting engine.
- **Chat-native workflow.** Describe a feature, constraint, or routing change in plain language; the LLM edits the source backed by live doc-search. AutoCAD has a limited AI Assist but no source-level LLM editing.
- **Multi-discipline in one workspace.** Full EDA (schematic + PCB + DRC + Gerber / IPC-2581), jewelry tooling (ring v4, gemstones v2), mechanical CAD, and BIM-adjacent primitives — disciplines AutoCAD covers only through separate vertical products.
- **BYO LLM / BYO key.** Bring your own Anthropic or OpenAI API key; zero billing flows through Kerf. AutoCAD has no configurable LLM we're aware of (as of May 2026).
- **In-box pre-compliance simulation.** SI, EMC, PDN, and PCB thermal analysis wizards ship in-box with no extension gating.
- **Cross-platform.** Runs in the browser or as a single binary on Windows, macOS, and Linux. AutoCAD is Windows-primary (macOS version is feature-restricted).
- **kerf-sdk Python scripting.** HTTP/JSON-RPC from your own machine — a first-class API interface.

## Honest gaps — where Kerf is behind today

- **2D drafting depth.** AutoCAD's 2D drafting toolset — dynamic blocks, paper-space viewports, dimension styles, Express Tools, sheet sets, CAD standards — is irreplaceable for production 2D documentation work. Kerf is 3D-first; its 2D drawing output is multi-sheet but not a full AutoCAD drafting environment.
- **No AutoLISP / VBA / .NET API.** AutoCAD's deep scripting ecosystem (AutoLISP, .NET API, VBA macros, Express Tools) is a different paradigm from Kerf's HTTP/JSON-RPC SDK.
- **No .dwg export.** Kerf writes DXF, not native .dwg. For workflows that require round-trip .dwg editing in AutoCAD or AutoCAD LT, this is a real limitation.
- **No AEC vertical tools.** Civil 3D, AutoCAD Architecture, AutoCAD MEP, Plant 3D, and AutoCAD Electrical workflows are not available in Kerf.
- **No paper-space / model-space.** Kerf's multi-sheet drawings use view projection from 3D models; it does not replicate AutoCAD's paper-space multi-scale viewport workflow.
- **No sheet sets.** AutoCAD's Sheet Set Manager for coordinating multi-drawing project output has no Kerf equivalent.
- **Command-line driven power-user workflow.** AutoCAD's keyboard-driven command line is the paradigm for power users. Kerf replaces it with chat, which is a different model not all users will prefer.

## Side by side

| Feature | AutoCAD | Kerf |
|---|---|---|
| License | ⚠️ Proprietary subscription | ✅ MIT open-core |
| Cost | ⚠️ ~US$255/mo or ~US$2,030/yr (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Platform | ⚠️ Windows primary; macOS (feature-restricted) | ✅ Browser + Win/macOS/Linux binary |
| Design intent | ✅ 2D drafting-first with 3D modelling | ✅ 3D parametric-first with drawing export |
| 2D drafting depth | ✅ Industry-defining: dynamic blocks, paper-space, dimension styles | ⚠️ Drawing views + dimensions; 2D is not primary |
| 3D parametric modeling | ⚠️ Solid/surface 3D; not competitive with Inventor/Fusion | ✅ OCCT feature tree — full parametric history |
| Constraint sketcher | ⚠️ Basic 2D constraints | ✅ Sketcher v2 — full parametric constraints |
| Dynamic blocks | ✅ Full dynamic blocks | ❌ Not available |
| Paper-space / viewports | ✅ Full paper-space multi-scale viewports | ⚠️ Drawing sheets with view projection |
| Sheet sets | ✅ Sheet Set Manager | ❌ Not available |
| .dwg native read | ✅ Native format owner | ✅ DWG import Tier 1 (libredwg bridge) |
| .dwg native write | ✅ Native | ⚠️ Writes DXF (not native DWG) |
| STEP / IGES / IFC | ✅ STEP / IGES; IFC via Architecture vertical | ✅ STEP / IGES / IFC import + STEP export |
| AutoLISP / .NET / VBA | ✅ Deep automation ecosystem | ❌ Different paradigm (HTTP/JSON-RPC SDK) |
| Python scripting | ⚠️ pyautocad (community); no official PyPI SDK | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| Chat / LLM workflow | ⚠️ AI Assist (limited; not source-level) | ✅ Chat-native — edits feature-tree source |
| Electronics / PCB | ❌ No PCB design | ✅ Full EDA — schematic, routing, DRC, Gerber |
| Jewelry tooling | ❌ None | ✅ 40-module jewelry suite |
| CAM / fabrication | ❌ No CAM | ✅ 3-axis CAM + tool DB; 5-axis 3+2 |
| Civil 3D / AEC verticals | ✅ Full civil infrastructure + MEP + Plant 3D | ❌ Not available |
| BYO LLM / key | ❌ No configurable LLM | ✅ BYO key (kerf_byo) |
| Open source | ❌ Proprietary | ✅ MIT — full codebase on GitHub |
