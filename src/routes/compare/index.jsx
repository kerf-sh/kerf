/**
 * /compare — hub page linking to each tool comparison.
 *
 * Structure:
 *   1. Hero ("How does Kerf compare?")
 *   2. Per-category section, in order: Mechanical → Electronic → BIM →
 *      Jewelry & NURBS → DCC → Drafting. Each section has a category
 *      heading + one-line description, an optional category-wide feature
 *      matrix (Kerf vs every competitor in the category), and the existing
 *      cards that link out to the deep per-CAD comparison page.
 *   3. FairnessNote footer + shared site Footer.
 *
 * The category matrices are intentionally derived from rows that already
 * live on the per-CAD <CompareTable>s (Freecad.jsx, Kicad.jsx, …). That
 * keeps every verdict traceable to a real comparison page and avoids
 * inventing capability claims here.
 *
 * Drafting is a singleton (AutoCAD only) so it skips the matrix and shows
 * just the card.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Code2,
  CircuitBoard,
  Gem,
  Building2,
  Cloud,
  Box,
  Cog,
  PencilRuler,
  Mountain,
  Film,
  Sparkles,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import { FairnessNote, GOOD, WEAK, GAP, NA } from './Freecad.jsx'
import CategoryMatrix from './CategoryMatrix.jsx'

/* -------------------------------------------------------------------------- */
/* Cards — preserved from previous hub (visuals unchanged)                    */
/* -------------------------------------------------------------------------- */

const CARDS = [
  // — Mechanical CAD
  {
    slug: 'freecad',
    icon: Code2,
    label: 'FreeCAD',
    category: 'Mechanical',
    tagline: 'Open-source parametric B-rep modeller',
    blurb:
      'FreeCAD 1.0 is a mature, LGPL, desktop parametric CAD package with a built-in Assembly workbench, FEM, and a decade-old workbench community. We compare it honestly against Kerf.',
  },
  {
    slug: 'fusion',
    icon: Cloud,
    label: 'Fusion 360',
    category: 'Mechanical',
    tagline: 'Cloud-connected mechanical CAD',
    blurb:
      "Fusion 360 pioneered cloud-connected parametric CAD with CAM, FEM, and generative design. See where it leads and where Kerf's open-core, chat-driven approach differs.",
  },
  {
    slug: 'solidworks',
    icon: Cog,
    label: 'SOLIDWORKS',
    category: 'Mechanical',
    tagline: 'Industry-standard mechanical CAD',
    blurb:
      "SOLIDWORKS is the dominant Parasolid-kernel mech CAD with a 30-year vendor lead. We document the maturity gap and where Kerf's multi-discipline scope earns its keep.",
  },
  {
    slug: 'onshape',
    icon: Cloud,
    label: 'Onshape',
    category: 'Mechanical',
    tagline: 'Browser-native real-time-collab CAD',
    blurb:
      "Onshape pioneered real-time multi-user CAD in the browser with proprietary FeatureScript. The closest peer to Kerf in shape — see where the open-core MIT model and chat-driven UX differ.",
  },
  {
    slug: 'inventor',
    icon: Cog,
    label: 'Inventor',
    category: 'Mechanical',
    tagline: "Autodesk's mechanical CAD",
    blurb:
      "Inventor is Autodesk's professional mech CAD with Dynamic Simulation, Frame Generator, Tube & Pipe, and a deep PDM ecosystem. Honest gap analysis vs Kerf's open-core multi-discipline scope.",
  },
  {
    slug: 'autocad',
    icon: PencilRuler,
    label: 'AutoCAD',
    category: 'Drafting',
    tagline: 'Industry-standard 2D drafting + 3D modelling',
    blurb:
      "AutoCAD owns 2D drafting and .dwg interchange after 40+ years. Kerf's 3D-first parametric workspace is a different shape — see how they overlap and where each wins.",
  },

  // — Electronic CAD
  {
    slug: 'kicad',
    icon: CircuitBoard,
    label: 'KiCad',
    category: 'Electronic',
    tagline: 'Open-source EDA suite',
    blurb:
      "KiCad 10 (2026) is a deep, free EDA suite with native IPC-2581/ODB++ and a huge library. See where it leads and where Kerf's unified electronics + mechanical workspace differs.",
  },
  {
    slug: 'altium',
    icon: CircuitBoard,
    label: 'Altium Designer',
    category: 'Electronic',
    tagline: 'Industrial-grade PCB design',
    blurb:
      "Altium Designer is the industrial reference for PCB layout — interactive push-and-shove routing, HDI/RF specialization. We document the gaps and where Kerf's integrated SI/EMC/PDN/thermal pre-compliance differs.",
  },

  // — BIM + civil
  {
    slug: 'revit',
    icon: Building2,
    label: 'Revit',
    category: 'BIM',
    tagline: 'Industry-standard BIM platform',
    blurb:
      "Revit is Autodesk's dominant BIM platform for AEC, with full MEP and family authoring. We compare its depth with Kerf's lighter, IFC-capable open-core workspace.",
  },
  {
    slug: 'civil3d',
    icon: Mountain,
    label: 'Civil 3D',
    category: 'BIM',
    tagline: 'Civil infrastructure design',
    blurb:
      "Civil 3D owns corridor modelling, pipe networks, and surveying in the AEC stack. See where Kerf's civil-engineering calc modules (hydrology / geotech / pavement / surveying) complement.",
  },

  // — Jewelry
  {
    slug: 'rhino',
    icon: Gem,
    label: 'Rhino',
    category: 'Jewelry & NURBS',
    tagline: 'NURBS & jewelry CAD (MatrixGold / RhinoGold)',
    blurb:
      'Rhino 8 with MatrixGold / RhinoGold is the professional reference for NURBS surfacing and jewelry. Honest gaps and real capabilities on both sides.',
  },
  {
    slug: 'matrixgold',
    icon: Sparkles,
    label: 'MatrixGold',
    category: 'Jewelry & NURBS',
    tagline: 'Industry-standard jewelry CAD',
    blurb:
      "MatrixGold is the industry-standard jewelry plugin stack on Rhino. We document its setting/casting depth and where Kerf's 40-module retail workflow (appraisal / repair / mount-finder) differs.",
  },

  // — DCC (mesh / render)
  {
    slug: 'blender',
    icon: Box,
    label: 'Blender',
    category: 'DCC',
    tagline: 'Mesh / DCC tool (not a B-rep CAD)',
    blurb:
      "Blender is a world-class mesh / DCC tool with Cycles + Geometry Nodes. Different category from Kerf — we show where they overlap for product visualisation and where each wins.",
  },
  {
    slug: 'max3ds',
    icon: Film,
    label: '3ds Max',
    category: 'DCC',
    tagline: 'Archviz & game-art DCC',
    blurb:
      "3ds Max with Arnold / V-Ray / Corona is the archviz + game-art standard. We document the render-depth gap and where Kerf's engineering-CAD workflow earns its place.",
  },
]

/* -------------------------------------------------------------------------- */
/* Category matrices                                                          */
/*                                                                            */
/* Every cell here is sourced from the corresponding row on the per-CAD page  */
/* (Freecad/Fusion/Solidworks/Onshape/Inventor/Kicad/Altium/Revit/Civil3d/    */
/* Rhino/MatrixGold/Blender/Max3ds). The Kerf column collapses the per-page   */
/* Kerf wording into a tighter label that reads cleanly across columns.       */
/* -------------------------------------------------------------------------- */

/* — Mechanical: 5 competitors (FreeCAD, Fusion, SOLIDWORKS, Onshape,
 *   Inventor) + Kerf. 16 rows. */
const MECH_COMPETITORS = [
  { slug: 'freecad', label: 'FreeCAD' },
  { slug: 'fusion', label: 'Fusion 360' },
  { slug: 'solidworks', label: 'SOLIDWORKS' },
  { slug: 'onshape', label: 'Onshape' },
  { slug: 'inventor', label: 'Inventor' },
]

const MECH_FEATURES = [
  /* — Licensing & platform */
  {
    group: 'Licensing & platform',
    name: 'License',
    cells: {
      freecad: `${GOOD} LGPL v2.1+`,
      fusion: `${WEAK} Proprietary subscription`,
      solidworks: `${WEAK} Perpetual + maint / sub`,
      onshape: `${WEAK} Proprietary SaaS sub`,
      inventor: `${WEAK} Proprietary subscription`,
      kerf: `${GOOD} MIT open-core`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Cost',
    cells: {
      freecad: `${GOOD} Free, no subscription`,
      fusion: `${WEAK} ~US$680/yr; startup tier`,
      solidworks: `${WEAK} ~$4k perpetual + ~$1.5k/yr`,
      onshape: `${WEAK} ~US$1,500–2,100/yr`,
      inventor: `${WEAK} ~US$2,545/yr single-user`,
      kerf: `${GOOD} Free local; pay-as-you-go hosted`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'OS / cross-platform',
    cells: {
      freecad: `${GOOD} Win / macOS / Linux`,
      fusion: `${GOOD} Windows + macOS`,
      solidworks: `${WEAK} Windows only`,
      onshape: `${GOOD} Browser-native (any OS)`,
      inventor: `${WEAK} Windows only`,
      kerf: `${GOOD} Browser + binary on Win/macOS/Linux`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Offline / self-host',
    cells: {
      freecad: `${GOOD} Fully offline desktop`,
      fusion: `${WEAK} Many features cloud-tied`,
      solidworks: `${GOOD} Full offline (perpetual)`,
      onshape: `${GAP} Browser-only`,
      inventor: `${GOOD} Full offline`,
      kerf: `${GOOD} pip install 'kerf[server]' + kerf serve (BYO Postgres)`,
    },
  },

  /* — Modeling */
  {
    group: 'Modeling',
    name: 'Parametric B-rep kernel',
    cells: {
      freecad: `${GOOD} Part Design WB (OCCT)`,
      fusion: `${GOOD} Timeline (HSMWorks lineage)`,
      solidworks: `${GOOD} Parasolid feature tree`,
      onshape: `${GOOD} Part Studios (OCCT under)`,
      inventor: `${GOOD} ShapeManager feature tree`,
      kerf: `${GOOD} OCCT feature tree; 620 kernel tests`,
    },
  },
  {
    group: 'Modeling',
    name: 'Constraint sketcher',
    cells: {
      freecad: `${GOOD} Sketcher WB (mature)`,
      fusion: `${GOOD} Full parametric sketcher`,
      solidworks: `${GOOD} Relations manager`,
      onshape: `${GOOD} Full parametric sketcher`,
      inventor: `${GOOD} 2D + 3D sketcher`,
      kerf: `${GOOD} Sketcher v2 — all major constraints`,
    },
  },
  {
    group: 'Modeling',
    name: 'Sheet metal',
    cells: {
      freecad: `${GOOD} SheetMetal WB`,
      fusion: `${GOOD} Full sheet-metal workspace`,
      solidworks: `${GOOD} Flange + mitre + flat pattern`,
      onshape: `${GOOD} Full sheet-metal workspace`,
      inventor: `${GOOD} Punch/die + flat pattern`,
      kerf: `${GOOD} Flange + unfold + flat-pattern DXF`,
    },
  },
  {
    group: 'Modeling',
    name: 'NURBS / surfacing',
    cells: {
      freecad: `${WEAK} Surface WB (limited)`,
      fusion: `${GOOD} T-spline sculpt workspace`,
      solidworks: `${GOOD} SurfaceWorks-class (Premium)`,
      onshape: `${WEAK} Limited surface tooling`,
      inventor: `${GOOD} Lofted / swept NURBS`,
      kerf: `${WEAK} NURBS Phase 4 — trim-by-curve, G3`,
    },
  },

  /* — Assemblies */
  {
    group: 'Assemblies',
    name: 'Assembly / mates',
    cells: {
      freecad: `${GOOD} Built-in Assembly WB (1.0)`,
      fusion: `${GOOD} Full joint system`,
      solidworks: `${GOOD} Full mate system; gear/cam`,
      onshape: `${GOOD} Full mate system`,
      inventor: `${GOOD} Flush/angle/tangent/insert`,
      kerf: `${GOOD} Full joint system — rigid/revolute/slider/cam/gear/pin-slot`,
    },
  },
  {
    group: 'Assemblies',
    name: 'Motion / dynamic simulation',
    cells: {
      freecad: `${WEAK} Via add-ons`,
      fusion: `${GOOD} Motion + interference`,
      solidworks: `${GOOD} Motion analysis (add-in)`,
      onshape: `${WEAK} Basic; sim via add-on`,
      inventor: `${GOOD} Full multi-body dynamics`,
      kerf: `${GAP} Not yet`,
    },
  },

  /* — Drawings & docs */
  {
    group: 'Drawings & docs',
    name: '2D technical drawings',
    cells: {
      freecad: `${GOOD} TechDraw WB`,
      fusion: `${GOOD} Full drawing environment`,
      solidworks: `${GOOD} Sheet templates`,
      onshape: `${GOOD} Drawings workspace`,
      inventor: `${GOOD} ANSI / ISO templates`,
      kerf: `${GOOD} Multi-sheet drawings`,
    },
  },
  {
    group: 'Drawings & docs',
    name: 'GD&T (ASME Y14.5)',
    cells: {
      freecad: `${WEAK} TechDraw annotations`,
      fusion: `${GOOD} ASME / ISO GD&T`,
      solidworks: `${GOOD} DimXpert`,
      onshape: `${GOOD} ASME / ISO GD&T`,
      inventor: `${GOOD} ASME Y14.5 / ISO 1101`,
      kerf: `${GOOD} ASME Y14.5 datum + tolerance framework`,
    },
  },

  /* — CAM / fabrication */
  {
    group: 'CAM / fabrication',
    name: 'CNC CAM (3-axis)',
    cells: {
      freecad: `${GOOD} CAM/Path WB (rewritten)`,
      fusion: `${GOOD} HSMWorks-lineage CAM`,
      solidworks: `${WEAK} CAMWorks/HSMWorks add-in`,
      onshape: `${WEAK} Via App Store add-ons`,
      inventor: `${WEAK} HSMWorks/Fusion add-in`,
      kerf: `${GOOD} 3-axis CAM + tool DB in-box`,
    },
  },
  {
    group: 'CAM / fabrication',
    name: 'FEM / structural',
    cells: {
      freecad: `${GOOD} FEM WB — CalculiX/Elmer/Z88`,
      fusion: `${GOOD} In-box (extension / cloud)`,
      solidworks: `${GOOD} SW Simulation (add-in)`,
      onshape: `${WEAK} Paid third-party only`,
      inventor: `${GOOD} In-box Stress Analysis`,
      kerf: `${WEAK} Linear static + thermal + nonlinear plasticity; not full parity`,
    },
  },

  /* — Domain breadth & ecosystem */
  {
    group: 'Domain breadth & ecosystem',
    name: 'Multi-discipline (ECAD / jewelry)',
    cells: {
      freecad: `${WEAK} IDF MCAD bridge only`,
      fusion: `${GOOD} Fusion Electronics (EAGLE EOL ’26)`,
      solidworks: `${WEAK} SOLIDWORKS PCB (add-in)`,
      onshape: `${GAP} Mech CAD only`,
      inventor: `${WEAK} AnyCAD / Fusion bridge`,
      kerf: `${GOOD} Full EDA + 40-module jewelry in-box`,
    },
  },
  {
    group: 'Domain breadth & ecosystem',
    name: 'Real-time cloud collab',
    cells: {
      freecad: `${GAP} Desktop only`,
      fusion: `${GOOD} Cloud storage + collab`,
      solidworks: `${WEAK} 3DEXPERIENCE (separate)`,
      onshape: `${GOOD} Industry-leading concurrent edit`,
      inventor: `${WEAK} Fusion Team / Autodesk Docs`,
      kerf: `${WEAK} Hosted SaaS + cloud-git (in progress)`,
    },
  },
  {
    group: 'Domain breadth & ecosystem',
    name: 'STEP / IGES round-trip',
    cells: {
      freecad: `${GOOD} STEP/IGES/DXF/IFC/STL`,
      fusion: `${GOOD} STEP/IGES/DXF/F3D/DWG`,
      solidworks: `${GOOD} STEP/IGES/Parasolid/ACIS`,
      onshape: `${GOOD} STEP/IGES/Parasolid/ACIS/DXF`,
      inventor: `${GOOD} STEP/IGES/DWG/SAT`,
      kerf: `${GOOD} STEP/IGES/IFC/DXF/FreeCAD import`,
    },
  },
  {
    group: 'Domain breadth & ecosystem',
    name: 'Chat / LLM editing + BYO key',
    cells: {
      freecad: `${GAP} None`,
      fusion: `${GAP} None`,
      solidworks: `${GAP} None`,
      onshape: `${GAP} None`,
      inventor: `${GAP} None`,
      kerf: `${GOOD} Chat-native + BYO API key (kerf_byo)`,
    },
  },
]

/* — Electronic: KiCad + Altium + Kerf. 14 rows. */
const EDA_COMPETITORS = [
  { slug: 'kicad', label: 'KiCad' },
  { slug: 'altium', label: 'Altium Designer' },
]

const EDA_FEATURES = [
  /* — Licensing & platform */
  {
    group: 'Licensing & platform',
    name: 'License',
    cells: {
      kicad: `${GOOD} GPL v3 (free, copyleft)`,
      altium: `${WEAK} Proprietary per-seat sub`,
      kerf: `${GOOD} MIT open-core`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Cost',
    cells: {
      kicad: `${GOOD} Free, no seats`,
      altium: `${WEAK} ~$8–10k+ USD/seat/yr`,
      kerf: `${GOOD} Free local; pay-as-you-go hosted`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'OS / cross-platform',
    cells: {
      kicad: `${GOOD} Win / macOS / Linux`,
      altium: `${WEAK} Windows only`,
      kerf: `${GOOD} Browser + Win/macOS/Linux binary`,
    },
  },

  /* — Schematic */
  {
    group: 'Schematic capture',
    name: 'Hierarchical schematic',
    cells: {
      kicad: `${GOOD} Eeschema — dozens of sheets`,
      altium: `${GOOD} Multi-level hierarchical`,
      kerf: `${GOOD} Hierarchical + sheet borders`,
    },
  },
  {
    group: 'Schematic capture',
    name: 'ERC depth',
    cells: {
      kicad: `${GOOD} Mature ERC + exclusions`,
      altium: `${GOOD} Pin-type / bus / diff / custom`,
      kerf: `${GOOD} ERC + IPC-2221B presets`,
    },
  },
  {
    group: 'Schematic capture',
    name: 'SPICE simulation',
    cells: {
      kicad: `${GOOD} ngspice — AC/DC/transient`,
      altium: `${GOOD} Mixed-signal XSPICE`,
      kerf: `${GOOD} SPICE + model lib + Monte-Carlo`,
    },
  },

  /* — PCB layout */
  {
    group: 'PCB layout',
    name: 'Push-and-shove router',
    cells: {
      kicad: `${GOOD} Pcbnew (mature)`,
      altium: `${GOOD} Situs — gold-standard`,
      kerf: `${WEAK} Shove router (less mature)`,
    },
  },
  {
    group: 'PCB layout',
    name: 'Differential pairs / length tune',
    cells: {
      kicad: `${GOOD} Diff-pair + tuner (v10)`,
      altium: `${GOOD} Xsignals + interactive tune`,
      kerf: `${WEAK} Length tuning; diff-pair lighter`,
    },
  },
  {
    group: 'PCB layout',
    name: 'DRC rules system',
    cells: {
      kicad: `${GOOD} Graphical rule editor (v10)`,
      altium: `${GOOD} Query-language scoped rules`,
      kerf: `${GOOD} DRC + IPC-2221B presets`,
    },
  },

  /* — High-speed & pre-compliance */
  {
    group: 'High-speed & pre-compliance',
    name: 'Signal integrity (SI)',
    cells: {
      kicad: `${WEAK} External tools recommended`,
      altium: `${GOOD} HyperLynx SI; IBIS/Touchstone`,
      kerf: `${GOOD} si_eye_wizard — eye/crosstalk (analytical)`,
    },
  },
  {
    group: 'High-speed & pre-compliance',
    name: 'EMC pre-compliance',
    cells: {
      kicad: `${WEAK} No EMC analysis`,
      altium: `${WEAK} Via external HyperLynx EMC`,
      kerf: `${GOOD} emc_wizard — FCC §15.109 / CISPR 32`,
    },
  },
  {
    group: 'High-speed & pre-compliance',
    name: 'PDN analysis',
    cells: {
      kicad: `${WEAK} No automated PDN`,
      altium: `${GOOD} PDN Analyzer`,
      kerf: `${GOOD} pdn_wizard — Z target, decap placement`,
    },
  },
  {
    group: 'High-speed & pre-compliance',
    name: 'Thermal (board)',
    cells: {
      kicad: `${WEAK} Manual θJA calcs`,
      altium: `${WEAK} Via Altium 365 Sim / external`,
      kerf: `${GOOD} thermal_board — 2-D FD steady-state`,
    },
  },

  /* — Fabrication */
  {
    group: 'Fabrication output',
    name: 'IPC-2581 / ODB++ / Gerber',
    cells: {
      kicad: `${GOOD} Native IPC-2581 + ODB++ (v10)`,
      altium: `${GOOD} Full fab suite`,
      kerf: `${GOOD} Gerber/Excellon/IPC-2581/ODB++`,
    },
  },
  {
    group: 'Fabrication output',
    name: 'Panelisation',
    cells: {
      kicad: `${WEAK} KiKit (community plugin)`,
      altium: `${WEAK} CAMtastic (basic)`,
      kerf: `${GOOD} Panelize built in`,
    },
  },

  /* — Cross-domain & ecosystem */
  {
    group: 'Cross-domain & ecosystem',
    name: 'ECAD importers',
    cells: {
      kicad: `${GOOD} Allegro / PADS / gEDA / Eagle (v10)`,
      altium: `${GOOD} Broad legacy format support`,
      kerf: `${GOOD} Eagle / Allegro / PADS / gEDA / KiCad`,
    },
  },
  {
    group: 'Cross-domain & ecosystem',
    name: 'Mechanical CAD (same tool)',
    cells: {
      kicad: `${GAP} Separate tool required`,
      altium: `${GAP} External MCAD required`,
      kerf: `${GOOD} Full B-rep, sketcher, sheet metal`,
    },
  },
  {
    group: 'Cross-domain & ecosystem',
    name: 'Chat / LLM editing',
    cells: {
      kicad: `${GAP} None`,
      altium: `${GAP} None`,
      kerf: `${GOOD} Chat-native — edits circuit source`,
    },
  },
]

/* — BIM: Revit + Civil 3D + Kerf. 13 rows. */
const BIM_COMPETITORS = [
  { slug: 'revit', label: 'Revit' },
  { slug: 'civil3d', label: 'Civil 3D' },
]

const BIM_FEATURES = [
  /* — Licensing & platform */
  {
    group: 'Licensing & platform',
    name: 'License',
    cells: {
      revit: `${WEAK} Proprietary subscription`,
      civil3d: `${WEAK} Proprietary subscription`,
      kerf: `${GOOD} MIT open-core`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Cost',
    cells: {
      revit: `${WEAK} ~US$2,910/yr single-user`,
      civil3d: `${WEAK} AEC Collection ~$4,150/yr`,
      kerf: `${GOOD} Free local; pay-as-you-go hosted`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'OS / cross-platform',
    cells: {
      revit: `${WEAK} Windows only`,
      civil3d: `${WEAK} Windows only`,
      kerf: `${GOOD} Browser + Win/macOS/Linux binary`,
    },
  },

  /* — BIM authoring */
  {
    group: 'BIM authoring',
    name: 'Parametric family system',
    cells: {
      revit: `${GOOD} Deep family editor + shared params`,
      civil3d: `${WEAK} DWG blocks; not BIM families`,
      kerf: `${GOOD} Parametric .family.json — type/instance params, formulas`,
    },
  },
  {
    group: 'BIM authoring',
    name: 'Walls / doors / windows / slabs',
    cells: {
      revit: `${GOOD} Full parametric building elements`,
      civil3d: `${NA} Not a building tool`,
      kerf: `${GOOD} Parametric walls/doors/windows/slabs/stairs/ramps`,
    },
  },
  {
    group: 'BIM authoring',
    name: 'MEP / coordination',
    cells: {
      revit: `${GOOD} Revit MEP + Navisworks`,
      civil3d: `${NA} Civil scope, not building MEP`,
      kerf: `${GAP} Not yet`,
    },
  },

  /* — Civil infrastructure */
  {
    group: 'Civil infrastructure',
    name: 'Corridor / alignment modelling',
    cells: {
      revit: `${WEAK} Not a civil-infra tool`,
      civil3d: `${GOOD} Full corridor + alignment design`,
      kerf: `${GAP} Not available`,
    },
  },
  {
    group: 'Civil infrastructure',
    name: 'Gravity / pressure pipe networks',
    cells: {
      revit: `${WEAK} Building plumbing only`,
      civil3d: `${GOOD} Storm + sanitary + pressure`,
      kerf: `${GAP} Not available`,
    },
  },
  {
    group: 'Civil infrastructure',
    name: 'Hydrology / geotech / pavement',
    cells: {
      revit: `${GAP} Not applicable`,
      civil3d: `${WEAK} Exports to HEC-RAS / external`,
      kerf: `${GOOD} TR-55 + Coulomb + AASHTO modules`,
    },
  },

  /* — Interop */
  {
    group: 'Interoperability',
    name: 'IFC import',
    cells: {
      revit: `${GOOD} Certified IFC 2x3 / 4`,
      civil3d: `${WEAK} Via Autodesk pipeline`,
      kerf: `${GOOD} IFC Tier 2 import`,
    },
  },
  {
    group: 'Interoperability',
    name: 'AutoCAD DWG / DXF',
    cells: {
      revit: `${GOOD} DWG import/export`,
      civil3d: `${GOOD} Built on AutoCAD`,
      kerf: `${WEAK} DXF/DWG import; DXF export`,
    },
  },

  /* — Cross-domain & ecosystem */
  {
    group: 'Cross-domain & ecosystem',
    name: 'Mechanical CAD / electronics in same tool',
    cells: {
      revit: `${GAP} Separate tools required`,
      civil3d: `${GAP} Separate tools required`,
      kerf: `${GOOD} OCCT B-rep + EDA in same workspace`,
    },
  },
  {
    group: 'Cross-domain & ecosystem',
    name: 'Chat / LLM editing',
    cells: {
      revit: `${GAP} None`,
      civil3d: `${GAP} None`,
      kerf: `${GOOD} Chat-native — edits source per turn`,
    },
  },
]

/* — Jewelry & NURBS: Rhino + MatrixGold + Kerf. 14 rows. */
const JEWELRY_COMPETITORS = [
  { slug: 'rhino', label: 'Rhino' },
  { slug: 'matrixgold', label: 'MatrixGold' },
]

const JEWELRY_FEATURES = [
  /* — Licensing & platform */
  {
    group: 'Licensing & platform',
    name: 'License',
    cells: {
      rhino: `${WEAK} Proprietary; perpetual`,
      matrixgold: `${WEAK} Proprietary; Rhino required`,
      kerf: `${GOOD} MIT open-core`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Cost',
    cells: {
      rhino: `${WEAK} ~US$995 full / $595 upgrade`,
      matrixgold: `${WEAK} Several thousand USD/seat + Rhino`,
      kerf: `${GOOD} Free local; pay-as-you-go hosted`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'OS / hosted option',
    cells: {
      rhino: `${WEAK} Win + macOS desktop`,
      matrixgold: `${WEAK} Windows only`,
      kerf: `${GOOD} Hosted SaaS + local binary (all OSes)`,
    },
  },

  /* — Modeling */
  {
    group: 'Modeling',
    name: 'NURBS surfacing',
    cells: {
      rhino: `${GOOD} Class-leading kernel (G0–G3)`,
      matrixgold: `${GOOD} Rhino kernel inherited`,
      kerf: `${WEAK} NURBS Phase 4 — trim-by-curve, G3`,
    },
  },
  {
    group: 'Modeling',
    name: 'SubD / mesh authoring',
    cells: {
      rhino: `${GOOD} SubD with creases (Rhino 8)`,
      matrixgold: `${GOOD} Rhino SubD inherited`,
      kerf: `${GOOD} SubD authoring with creases; quad remesh + surfacing`,
    },
  },
  {
    group: 'Modeling',
    name: 'Parametric solids (B-rep)',
    cells: {
      rhino: `${WEAK} Via Grasshopper / plugins`,
      matrixgold: `${WEAK} Via Rhino plugins`,
      kerf: `${GOOD} OCCT feature tree — pad/pocket/loft`,
    },
  },

  /* — Jewelry core */
  {
    group: 'Jewelry core',
    name: 'Ring builders',
    cells: {
      rhino: `${GOOD} MatrixGold / RhinoGold builders`,
      matrixgold: `${GOOD} Large shank library + styles`,
      kerf: `${GOOD} Ring v4 + 31-template library`,
    },
  },
  {
    group: 'Jewelry core',
    name: 'Gemstones / cuts',
    cells: {
      rhino: `${GOOD} Extensive gem libraries`,
      matrixgold: `${GOOD} Catalog incl. certified stones`,
      kerf: `${GOOD} Gemstones v2 — 30 cuts + report`,
    },
  },
  {
    group: 'Jewelry core',
    name: 'Settings (prong / bezel / pavé / channel)',
    cells: {
      rhino: `${GOOD} Mature stone-setting wizards`,
      matrixgold: `${GOOD} Prong/bezel/pavé/channel/halo`,
      kerf: `${GOOD} Settings v3/v4 + gem-seat v2`,
    },
  },
  {
    group: 'Jewelry core',
    name: 'Chain / findings',
    cells: {
      rhino: `${GOOD} Dedicated chain + findings`,
      matrixgold: `${GOOD} Supplier-catalog findings`,
      kerf: `${WEAK} Chain v2 + findings; no supplier cat`,
    },
  },
  {
    group: 'Jewelry core',
    name: 'Casting / wax-mill export',
    cells: {
      rhino: `${GOOD} STL + wax-mill paths`,
      matrixgold: `${GOOD} STL + DLP/SLA + wax-mill paths`,
      kerf: `${WEAK} Casting export; no wax-mill paths`,
    },
  },

  /* — Retail & workshop */
  {
    group: 'Retail & workshop workflow',
    name: 'Quote / cost panel',
    cells: {
      rhino: `${GAP} Not a Rhino feature`,
      matrixgold: `${WEAK} Not core MatrixGold`,
      kerf: `${GOOD} Full quote / cost panel built in`,
    },
  },
  {
    group: 'Retail & workshop workflow',
    name: 'Appraisal / repair / mount-finder',
    cells: {
      rhino: `${GAP} Out of scope`,
      matrixgold: `${GAP} Out of scope`,
      kerf: `${GOOD} Appraisal + repair + mount_finder`,
    },
  },

  /* — Cross-domain & ecosystem */
  {
    group: 'Cross-domain & ecosystem',
    name: 'Mech / electronics (same tool)',
    cells: {
      rhino: `${WEAK} Mech via Grasshopper; no EDA`,
      matrixgold: `${GAP} Separate tools required`,
      kerf: `${GOOD} OCCT B-rep + full EDA stack in-box`,
    },
  },
  {
    group: 'Cross-domain & ecosystem',
    name: 'Chat / LLM editing + BYO key',
    cells: {
      rhino: `${GAP} None`,
      matrixgold: `${GAP} None`,
      kerf: `${GOOD} Chat-native + BYO API key`,
    },
  },
]

/* — DCC: Blender + 3ds Max + Kerf. 14 rows. */
const DCC_COMPETITORS = [
  { slug: 'blender', label: 'Blender' },
  { slug: 'max3ds', label: '3ds Max' },
]

const DCC_FEATURES = [
  /* — Licensing & platform */
  {
    group: 'Licensing & platform',
    name: 'License',
    cells: {
      blender: `${GOOD} GPL v2+ (free, copyleft)`,
      max3ds: `${WEAK} Autodesk subscription`,
      kerf: `${GOOD} MIT open-core`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'Cost',
    cells: {
      blender: `${GOOD} Free, no subscription`,
      max3ds: `${WEAK} ~$235/mo or ~$1,875/yr`,
      kerf: `${GOOD} Free local; pay-as-you-go hosted`,
    },
  },
  {
    group: 'Licensing & platform',
    name: 'OS / cross-platform',
    cells: {
      blender: `${GOOD} Win / macOS / Linux`,
      max3ds: `${WEAK} Windows only`,
      kerf: `${GOOD} Browser + Win/macOS/Linux binary`,
    },
  },

  /* — Geometry kernel */
  {
    group: 'Geometry kernel',
    name: 'B-rep solid kernel',
    cells: {
      blender: `${WEAK} BMesh half-edge — no B-rep`,
      max3ds: `${WEAK} Poly / Edit Poly — no B-rep`,
      kerf: `${GOOD} OCCT B-rep — exact rational`,
    },
  },
  {
    group: 'Geometry kernel',
    name: 'Parametric history (feature DAG)',
    cells: {
      blender: `${WEAK} Linear Modifier Stack`,
      max3ds: `${WEAK} Linear Modifier Stack`,
      kerf: `${GOOD} OCCT feature tree + persistent face IDs`,
    },
  },
  {
    group: 'Geometry kernel',
    name: 'Constraint sketcher',
    cells: {
      blender: `${GAP} None`,
      max3ds: `${GAP} None`,
      kerf: `${GOOD} Sketcher v2 — geom + dim constraints`,
    },
  },
  {
    group: 'Geometry kernel',
    name: 'STEP / IGES B-rep interop',
    cells: {
      blender: `${GAP} Mesh export only (glTF/FBX/OBJ)`,
      max3ds: `${WEAK} Via FBX/DWG; STEP plugin import`,
      kerf: `${GOOD} STEP / IGES / 3DM round-trip`,
    },
  },

  /* — Rendering */
  {
    group: 'Rendering',
    name: 'Path-traced renderer',
    cells: {
      blender: `${GOOD} Cycles + Eevee (benchmark)`,
      max3ds: `${GOOD} Arnold built-in`,
      kerf: `${WEAK} Cycles backend + browser path tracer; no animation / caustics`,
    },
  },
  {
    group: 'Rendering',
    name: 'Third-party render plugins',
    cells: {
      blender: `${GOOD} V-Ray, Octane, LuxCore, etc.`,
      max3ds: `${GOOD} V-Ray, Corona, Redshift, Octane`,
      kerf: `${GAP} No render plugin API yet`,
    },
  },
  {
    group: 'Rendering',
    name: 'Animation / rigging',
    cells: {
      blender: `${GOOD} Full skeletal, NLA, cloth sim`,
      max3ds: `${GOOD} Biped / CAT / particles`,
      kerf: `${GAP} No animation or rigging`,
    },
  },

  /* — Engineering modules */
  {
    group: 'Engineering modules',
    name: 'GD&T / 2D technical drawings',
    cells: {
      blender: `${GAP} No GD&T or drawings`,
      max3ds: `${GAP} No GD&T or drawings`,
      kerf: `${GOOD} ASME Y14.5 + multi-sheet drawings`,
    },
  },
  {
    group: 'Engineering modules',
    name: 'Electronics / PCB',
    cells: {
      blender: `${GAP} Not applicable`,
      max3ds: `${GAP} Not applicable`,
      kerf: `${GOOD} Full EDA — schematic, routing, DRC`,
    },
  },
  {
    group: 'Engineering modules',
    name: 'CNC CAM',
    cells: {
      blender: `${GAP} No CAM`,
      max3ds: `${GAP} No CAM`,
      kerf: `${GOOD} 3-axis CAM + tool DB; 5-axis 3+2`,
    },
  },

  /* — Ecosystem */
  {
    group: 'Ecosystem',
    name: 'Chat / LLM editing',
    cells: {
      blender: `${GAP} None`,
      max3ds: `${GAP} None`,
      kerf: `${GOOD} Chat-native — edits feature tree`,
    },
  },
]

/* -------------------------------------------------------------------------- */
/* Per-category section definitions                                           */
/* -------------------------------------------------------------------------- */

const CATEGORY_SECTIONS = [
  {
    key: 'Mechanical',
    blurb:
      'Parametric B-rep history modellers — the workhorses for product design, sheet metal, drawings, and CAM.',
    competitors: MECH_COMPETITORS,
    features: MECH_FEATURES,
  },
  {
    key: 'Electronic',
    blurb:
      'PCB schematic capture, routing, DRC, and fabrication output — plus pre-compliance analysis (SI / EMC / PDN / thermal).',
    competitors: EDA_COMPETITORS,
    features: EDA_FEATURES,
  },
  {
    key: 'BIM',
    blurb:
      'Building and civil-infrastructure modelling, IFC interchange, and structural / civil engineering calc modules.',
    competitors: BIM_COMPETITORS,
    features: BIM_FEATURES,
  },
  {
    key: 'Jewelry & NURBS',
    blurb:
      'Class-A NURBS surfacing and the jewelry vertical — ring builders, gem libraries, setting wizards, and casting.',
    competitors: JEWELRY_COMPETITORS,
    features: JEWELRY_FEATURES,
  },
  {
    key: 'DCC',
    blurb:
      'Mesh / DCC tools with deep rendering and animation — different category from B-rep CAD, but with real visualisation overlap.',
    competitors: DCC_COMPETITORS,
    features: DCC_FEATURES,
  },
  {
    key: 'Drafting',
    blurb:
      "2D drafting and the .dwg ecosystem. Kerf is 3D-first parametric — we cover the overlap on the dedicated page.",
    /* singleton — no matrix, just the card */
  },
]

/* -------------------------------------------------------------------------- */
/* Card (visual preserved from previous hub)                                  */
/* -------------------------------------------------------------------------- */

function CompareCard({ slug, icon: Icon, label, tagline, blurb }) {
  return (
    <Link
      to={`/compare/${slug}`}
      className="group relative flex flex-col rounded-2xl border border-ink-800 bg-ink-900/40 p-5 sm:p-6 hover:border-ink-700 hover:bg-ink-900/70 transition-colors"
      aria-label={`Read full Kerf vs ${label} comparison`}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-9 h-9 rounded-lg bg-kerf-300/10 border border-kerf-300/30 text-kerf-300 shrink-0">
            <Icon size={16} />
          </span>
          <div>
            <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
              Kerf vs {label}
            </h3>
            <p className="text-xs text-ink-400 font-mono mt-0.5">{tagline}</p>
          </div>
        </div>
        <ArrowRight
          size={15}
          className="text-ink-500 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all shrink-0 mt-1"
        />
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{blurb}</p>
    </Link>
  )
}

/* -------------------------------------------------------------------------- */
/* Legend strip (compact, shared, accessible)                                 */
/* -------------------------------------------------------------------------- */

function MatrixLegend() {
  return (
    <p className="mt-3 text-xs text-ink-500 font-mono" aria-label="Verdict legend">
      Legend: {GOOD} solid · {WEAK} partial / early · {GAP} not available ·{' '}
      {NA} not applicable
    </p>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function CompareHub() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      <main
        className="mx-auto max-w-5xl px-6 pt-14 pb-20"
        aria-label="Compare Kerf against other CAD and EDA tools"
      >
        {/* Hero */}
        <div className="mb-12">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            How does Kerf compare?
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            These tools are genuinely excellent — many are decades old, deeply
            validated, and free or affordable. Kerf is young by comparison.
            Each category below opens with a side-by-side feature matrix that
            credits every competitor's real strengths first, marks Kerf's gaps
            without spin, and links out to a full per-tool comparison for the
            detail behind every cell.
          </p>
        </div>

        {/* Per-category sections */}
        {CATEGORY_SECTIONS.map((section) => {
          const cards = CARDS.filter((c) => c.category === section.key)
          if (cards.length === 0) return null
          return (
            <section
              key={section.key}
              className="mb-14 last:mb-0 scroll-mt-20"
              aria-label={`${section.key} comparisons`}
            >
              <header className="mb-4">
                <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100">
                  {section.key}
                </h2>
                <p className="mt-1 text-sm text-ink-400 leading-relaxed max-w-2xl">
                  {section.blurb}
                </p>
              </header>

              {/* Category-wide matrix — skipped for singleton categories. */}
              {section.features && section.competitors && (
                <div className="mb-6">
                  <CategoryMatrix
                    category={section.key}
                    competitors={section.competitors}
                    features={section.features}
                  />
                  <MatrixLegend />
                </div>
              )}

              {/* Cards — same visual as before, one column on mobile. */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {cards.map((card) => (
                  <CompareCard key={card.slug} {...card} />
                ))}
              </div>
            </section>
          )
        })}

        {/* Fairness footer — same component used on every comparison page */}
        <FairnessNote />
      </main>

      <Footer />
    </div>
  )
}
