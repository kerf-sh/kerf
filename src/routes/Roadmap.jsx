/**
 * Roadmap — public-facing roadmap page.
 *
 * Source of truth: ROADMAP.md in the repo. This route hand-curates
 * ~50 of the most user-facing rows (✅ shipped · 🚧 in flight ·
 * 📋 next · 🔮 planned) and renders them as a filterable grid.
 *
 * Why hand-curated and not parsed-at-build? ROADMAP.md is dense
 * markdown — most rows are 200+ words of implementation detail. A
 * dumb parser would surface internals nobody on the landing page
 * needs. Curating in code keeps the prose user-facing; we accept
 * the small lag against ROADMAP.md as the trade.
 *
 * Style matches Landing.jsx: ink palette, kerf-300 accent, font-
 * display headers, font-mono chips, rounded-2xl cards with
 * ArrowRight bottom-right.
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  Filter as FilterIcon,
  ExternalLink,
} from 'lucide-react'
import clsx from 'clsx'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'
const ROADMAP_URL = `${GITHUB_URL}/blob/main/ROADMAP.md`

/* -------------------------------------------------------------------------- */
/* Status + area taxonomies                                                    */
/* -------------------------------------------------------------------------- */

const STATUSES = [
  { id: 'shipped', label: 'Shipped', emoji: '✅', tone: 'emerald' },
  { id: 'in_flight', label: 'In flight', emoji: '🚧', tone: 'kerf' },
  { id: 'next', label: 'Next', emoji: '📋', tone: 'cyan' },
  { id: 'planned', label: 'Planned', emoji: '🔮', tone: 'neutral' },
]

const STATUS_BY_ID = Object.fromEntries(STATUSES.map((s) => [s.id, s]))

const AREAS = [
  'Mechanical',
  'Electronics',
  'Architecture',
  'CAM',
  'CAE',
  'Imports',
  'Scripting',
  'Performance',
  'Architecture (stack)',
  'Cloud',
  'Docs',
]

/* -------------------------------------------------------------------------- */
/* Curated roadmap rows                                                        */
/* -------------------------------------------------------------------------- */
/*
 * Picked from ROADMAP.md `## Status overview`. Skips infra-internal
 * rows nobody outside Kerf cares about (e.g. "Brew formula + curl
 * install"). Order inside each status section is roughly recency-
 * weighted: newest shipped first, in-flight items, then next/planned.
 *
 * `docHref` is optional. Prefer in-app docs (/docs/<slug>) over
 * GitHub plan-docs — but link plan-docs for in-flight items that
 * don't yet have a polished doc page.
 */

const ITEMS = [
  /* ── ✅ shipped — recent / user-facing ─────────────────────────── */
  {
    title: 'FreeCAD Tier 2 import',
    body: 'Sketcher constraints + Spreadsheet → .equations. TechDraw drawings → .drawing. Materials library. Rounds out the full FreeCAD design-round-trip: Part + PartDesign + Sketcher + Spreadsheet + TechDraw.',
    status: 'shipped',
    area: 'Imports',
    docHref: '/docs/imports',
  },
  {
    title: 'IFC import (Tier 1 + 2)',
    body: '.ifc → .bim DSL via IfcOpenShell. Tier 1: walls / slabs / openings / spaces / levels / sites. Tier 2: families + schedules + views. Bidirectional round-trip alongside the existing IFC4 export.',
    status: 'shipped',
    area: 'Architecture',
    docHref: '/docs/bim-format',
  },
  {
    title: 'NURBS Phase 4 — trim-by-curve (C2)',
    body: 'Pure-Python UV-space trim-by-curve: project a 3D trim curve onto a NurbsSurface UV domain, compute PCurve from ISO/bisection intersection, trim the face, sew the result. Capability 2 of 4.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'NURBS Phase 4 — matchSrf (C3)',
    body: 'Parametric surface matching to G1/G2 continuity across a shared boundary edge. Adjusts one surface\'s boundary row in-place; works with both explicit control-point access and OCCT wrappers.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'NURBS Phase 4 — G3 curvature comb visualisation (C4)',
    body: 'surface_curvature_combs LLM tool: render porcupine plots of principal curvature deviation across a surface. Lets practitioners eyeball G3 quality without needing algorithmic enforcement.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'SubD with edge creases',
    body: 'Catmull-Clark subdivision with full per-edge crease tagging [0..1]. Smooth, crease, and corner vertex classification. Boundary edges can be fully creased for hard-edge control. SubD → B-rep bridge.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'Quad remesher',
    body: 'Quad-dominant remeshing via Instant Meshes. Distinct from the triangle mesh.remesh op — produces structured quads for SubD prep, downstream FEM meshing, and parametric mapping.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/capabilities',
  },
  {
    title: 'Persistent face naming — complete',
    body: 'All 7 tasks shipped: worker emitter, role taxonomy (fillet/chamfer/shell/cut/push_pull), boolean-op carry-over, pattern propagation, mate-ref migration, resolveFaceRef name-first fallback, and DB backfill script.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: '3D-print G-code slicing (Tier 1)',
    body: 'Mesh → printable G-code via CuraEngine subprocess. Perimeters, infill, supports, retraction. kerf-slicing plugin; AGPLv3 extra isolated at subprocess boundary like WireViz.',
    status: 'shipped',
    area: 'CAM',
    docHref: '/docs/capabilities',
  },
  {
    title: 'SDK: Rust + Go + Lua',
    body: 'kerf-sdk-rs on crates.io · kerf-sdk-go on pkg.go.dev · kerf-sdk-lua on LuaRocks. Same JSON-RPC wire format as Python + TS. Targets embedded scripting ecosystems in CAD plugins.',
    status: 'shipped',
    area: 'Scripting',
    docHref: '/docs/v1-rpc',
  },
  {
    title: 'PLC structured text (.plc.st)',
    body: 'IEC 61131-3 Structured Text editor in kerf-plc: syntax highlight + offline MATIEC lint. Companion to .circuit.tsx — describe ladder logic / function blocks alongside the PCB it controls.',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/electronics',
  },
  {
    title: 'FreeCAD Tier 1 import',
    body: '.FCStd → .feature + .sketch + .assembly. Pure-Python parser, BRep-lifted geometry, PartDesign metadata, multi-Body assembly. 5 fixtures, integration tests, no FreeCAD install required.',
    status: 'shipped',
    area: 'Imports',
    docHref: '/docs/imports',
  },
  {
    title: 'NURBS booleans + surface booleans (C1)',
    body: 'feature_to_solid cap-then-boolean + feature_boolean (cut/fuse/common) on solids. feature_surface_boolean Python tool for Face/Shell operands. Persistent face naming across all boolean results.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: '5-axis CAM',
    body: 'Constant-tilt finishing (UV iso-curves + per-point surface normal + tilt-about-tangent + ball-end tip) and 3+2 indexed (rotate STL to drive-face Z). CAM tool-DB integration; LinuxCNC / Fanuc posts.',
    status: 'shipped',
    area: 'CAM',
    docHref: '/docs/capabilities',
  },
  {
    title: 'Wiring + harness diagrams',
    body: 'New .wiring file kind. WireViz YAML → SVG. kerf-wiring plugin, /run-wireviz pyworker route, opt-in GPLv3 extra (subprocess-isolated on hosted).',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/electronics',
  },
  {
    title: 'kerf-sdk (Python + TypeScript)',
    body: 'pip install kerf-sdk · npm install kerf-sdk. JSON-RPC over /v1/rpc, API-token auth, namespaced wrappers (files / equations / configurations / revisions / docs). Bring your own LLM.',
    status: 'shipped',
    area: 'Scripting',
    docHref: '/docs/v1-rpc',
  },
  {
    title: 'Revit-parity authoring (BIM)',
    body: '.family / .schedule / .view / .sheet, categories, phasing, view filters, stairs, railings, MEP, curtain walls. Full BIM authoring on top of IFC4.',
    status: 'shipped',
    area: 'Architecture',
    docHref: '/docs/bim-format',
  },
  {
    title: 'KiCad parity — full PCB depth',
    body: 'Hierarchical schematics, buses + diff pairs, net classes + DRC, length tuning, via stitching + teardrops, push-pull routing, ERC, per-pad mask/paste overrides. PCB panelisation + IPC-D-356A netlist.',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/circuit-format',
  },
  {
    title: 'FEM + Topology optimization',
    body: 'FEniCSx linear elasticity + SLEPc modal + multi-body multi-material BCs; CalculiX modal as second solver. Density-field SIMP topology with NURBS-driven STEP reconstruction. ~23,959 tests green.',
    status: 'shipped',
    area: 'CAE',
    docHref: '/docs/capabilities',
  },
  {
    title: 'SPICE + RF + autorouting',
    body: 'ngspice transient/DC + probe waveforms via uPlot. scikit-rf S-parameter analysis (VSWR, return loss, Smith chart). FreeRouting JAR for autoroute. SPICE model library + EM field solver.',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/electronics',
  },
  {
    title: 'Mates UI + tolerance chain-walk',
    body: 'BREP face/edge picker — mate authoring is click+click. tolerance_auto_chain walks the assembly-mate graph by BFS between two feature refs; auto-builds the dimension chain.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/assemblies',
  },
  {
    title: 'Drawings: snap + projection + GD&T',
    body: 'Endpoint/midpoint/center/intersection snap end-to-end across every dimensioning tool. Multi-sheet, section hatching, leaders, balloons, GD&T frames, centerlines, break-lines.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/drawings',
  },
  {
    title: 'Equations + configurations',
    body: '.equations project-level parameters (mathjs); per-file variants round-trip in .part / .feature / .sketch. BOM groups by (file_id, config_id). LLM tools + integration scenarios.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/parametric',
  },
  {
    title: 'Library + BOM + distributors',
    body: 'KiCad-style Parts library with publisher verification, manufacturer-PR submissions, live pricing from DigiKey/Mouser/LCSC, BOM rollup with notes/MOQ/lead/alternates.',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/part-format',
  },
  {
    title: 'Workspaces + git + GitHub sync',
    body: 'Multi-member workspaces with role-based access. git commits/branches/merge with multi-lane lattice graph view. GitHub OAuth + branch sync with AES-GCM-encrypted tokens.',
    status: 'shipped',
    area: 'Cloud',
    docHref: '/docs/cloud',
  },
  {
    title: 'Plugin monorepo + kerf-server',
    body: 'Plugin packages under packages/, discovered via Python entry points. kerf-server CLI. Six install personas (api-only / mech / electronics / bim / full / compute-only).',
    status: 'shipped',
    area: 'Architecture (stack)',
    docHref: '/docs/architecture',
  },
  {
    title: 'Diff-based + compressed revisions',
    body: 'Every Nth revision is full content; in between are unified-diff payloads. 82× shrink on typical edit patterns. Reconstruction walks the chain to the nearest base.',
    status: 'shipped',
    area: 'Performance',
    docHref: '/docs/architecture',
  },
  {
    title: 'Doc-search LLM consolidation',
    body: '~30 domain-specific tools collapsed into a small fixed surface + search_kerf_docs over an embedded markdown corpus. Adding a new domain is a markdown change, not a code change.',
    status: 'shipped',
    area: 'Architecture (stack)',
    docHref: '/docs/llm-tools',
  },
  {
    title: 'KiCad / OpenSCAD / 3DM import',
    body: 'KiCad Tier 1 (.kicad_sch/.pcb → .circuit.tsx) + Tier 2 (libraries → Library Parts). OpenSCAD browser-side parser → .jscad. Rhino .3dm round-trip via rhino3dm.',
    status: 'shipped',
    area: 'Imports',
    docHref: '/docs/imports',
  },
  {
    title: 'Workshop thumbnail polish',
    body: 'User-triggered "Refresh thumbnail" button in editor header + publish flow. Gallery images can be pinned as project cover (star icon per card). is_primary partial unique index enforced at DB level.',
    status: 'shipped',
    area: 'Architecture (stack)',
  },

  /* ── 🚧 in flight ──────────────────────────────────────────────── */
  {
    title: 'FEM workbench depth',
    body: 'Expanding toward CalculiX / Z88 / Mystran scope: nonlinear static, explicit dynamics, acoustics FEM, fatigue, EM field simulation. cfd_potential.py ships; full Navier-Stokes + heat transfer in progress.',
    status: 'in_flight',
    area: 'CAE',
    docHref: '/docs/capabilities',
  },
  {
    title: 'CFD — potential flow + Navier-Stokes',
    body: '2-D incompressible potential flow landed (cfd_potential.py: Laplace solver, cylinder drag, Joukowski aerofoil). Full Navier-Stokes + incompressible heat-transfer routes are the active next step.',
    status: 'in_flight',
    area: 'CAE',
    docHref: '/docs/capabilities',
  },
  {
    title: 'Interactive diff-pair routing + tuning',
    body: 'Data-layer: diff pairs, impedance targets, length matching already shipped. In-progress: interactive push-and-shove routing UI with real-time differential-pair rules, live length delta visualisation.',
    status: 'in_flight',
    area: 'Electronics',
    docHref: '/docs/circuit-format',
  },
  {
    title: 'BIM parametric family system depth',
    body: 'Walls / doors / windows / slabs / stairs / ramps shipped. In-progress: full parametric family library, structural grid, site + earthwork, MEP system routing depth, and material catalogue.',
    status: 'in_flight',
    area: 'Architecture',
    docHref: '/docs/bim-format',
  },

  /* ── 📋 next ───────────────────────────────────────────────────── */
  {
    title: 'Broader ECAD import',
    body: 'Allegro (.brd), PADS (.asc), gEDA (.sch/.pcb), Eagle (.brd/.sch) → .circuit.tsx. KiCad Tier 1+2 already shipped. Each format gets its own parser + round-trip integration test.',
    status: 'next',
    area: 'Imports',
  },
  {
    title: 'Direct + parametric history coexistence',
    body: 'Parametric feature-tree is primary today. Next: allow direct face/edge edits to inject a "direct_edit" feature node into the DAG so the feature tree doesn\'t break on freeform pushes.',
    status: 'next',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'Full joint system',
    body: 'Cam-follower (cycloidal + harmonic rise/fall) already shipped in kerf-cad-core kinematics. Next: gear (spur/bevel/worm), pin-slot, and rack-and-pinion joints with motion-simulation output.',
    status: 'next',
    area: 'Mechanical',
    docHref: '/docs/assemblies',
  },
  {
    title: 'SubD authoring with crease tools',
    body: 'Catmull-Clark SubD with per-edge crease weights already ships. Next: viewport crease-painting UI (click-drag edges to tag creases), crease sharpness slider, and SubD → B-rep bridge in FeatureView.',
    status: 'next',
    area: 'Mechanical',
  },
  {
    title: 'Render: caustics + dispersion',
    body: 'Current renderer: ACES tonemap, HDRI environment, bloom. Next: photon-mapped caustics for glass/gem renders and wavelength-based dispersion for diamond / coloured-stone renders.',
    status: 'next',
    area: 'Mechanical',
  },

  /* ── 🔮 planned ────────────────────────────────────────────────── */
  {
    title: 'FreeCAD Tier 3 import',
    body: 'FEM meshes + results, Path (CAM) operations, Arch workbench geometry. Completes the full FreeCAD surface after Tier 1 (PartDesign) and Tier 2 (Sketcher + Spreadsheet + TechDraw).',
    status: 'planned',
    area: 'Imports',
  },
  {
    title: 'Slicing — cross-section + CNC layered',
    body: 'CAD-side feature_section wraps BRepAlgoAPI_Section. Result stored as a .section wire — dimensionable, DXF-exportable. CNC layered: stacked sections at fixed Z heights for waterjet / laser-cut-and-stack.',
    status: 'planned',
    area: 'CAM',
  },
  {
    title: 'Sketcher: Bézier curves',
    body: 'Add bezier entity kind to .sketch (cubic B-spline already shipped). Draw via control-point clicks; G1 / G2 continuity constraints between adjacent Bézier and B-spline segments.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Sketcher: symmetry over arbitrary line',
    body: 'Extends the existing axis-aligned symmetry constraint to mirror a sub-selection across an arbitrary construction line. Carbon-copy + axis-aligned symmetry both already shipped.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Electronics: ML-assisted reroute',
    body: 'Phase 3 of autorouting. Learned model suggests reroutes for the FreeRouting output. Phases 1 (FreeRouting integration) and 2 (push-and-shove) already shipped.',
    status: 'planned',
    area: 'Electronics',
  },
  {
    title: 'Electronics: openEMS RF field solver',
    body: 'Phase 2 of RF — full 3D EM field simulation alongside the shipped scikit-rf S-parameter analysis. Wires the openEMS subprocess + voxel mesh into the existing RF toolchain.',
    status: 'planned',
    area: 'Electronics',
    docHref: '/docs/electronics',
  },
  {
    title: 'Rhino-parity: quad remesher UI',
    body: 'kerf_quad_remesh tool already lands a quad mesh. Next: viewport affordance to pick target face count + alignment guides, and one-click SubD conversion from the result.',
    status: 'planned',
    area: 'Mechanical',
  },
]

/* -------------------------------------------------------------------------- */
/* Status pill component                                                       */
/* -------------------------------------------------------------------------- */

function StatusPill({ status }) {
  const meta = STATUS_BY_ID[status]
  if (!meta) return null
  // tone → tailwind palette
  const toneCls = {
    emerald:
      'bg-emerald-400/10 border border-emerald-400/30 text-emerald-300',
    kerf: 'bg-kerf-300/10 border border-kerf-300/40 text-kerf-300',
    cyan: 'bg-cyan-edge/10 border border-cyan-edge/30 text-cyan-300',
    neutral: 'bg-ink-800/80 border border-ink-700 text-ink-400',
  }[meta.tone]

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest',
        toneCls,
      )}
    >
      {status === 'shipped' ? (
        <Check size={10} strokeWidth={3} />
      ) : (
        <span aria-hidden>{meta.emoji}</span>
      )}
      {meta.label}
    </span>
  )
}

function AreaPill({ area }) {
  return (
    <span className="inline-flex items-center rounded-full bg-ink-900 border border-ink-800 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink-400">
      {area}
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/* Filter chip                                                                 */
/* -------------------------------------------------------------------------- */

function Chip({ active, onClick, children, count }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-3 h-7 text-xs font-mono uppercase tracking-widest',
        'border transition-colors select-none',
        active
          ? 'bg-kerf-300 text-ink-950 border-kerf-300 hover:bg-kerf-200'
          : 'bg-ink-900/60 text-ink-300 border-ink-800 hover:border-ink-700 hover:text-ink-100',
      )}
    >
      {children}
      {typeof count === 'number' && (
        <span
          className={clsx(
            'inline-flex items-center justify-center rounded-full text-[10px] tabular-nums px-1 min-w-[1.25rem] h-4',
            active
              ? 'bg-ink-950/15 text-ink-950'
              : 'bg-ink-800/80 text-ink-400',
          )}
        >
          {count}
        </span>
      )}
    </button>
  )
}

/* -------------------------------------------------------------------------- */
/* Item card                                                                   */
/* -------------------------------------------------------------------------- */

function ItemCard({ item }) {
  const { title, body, status, area, docHref, docExternal } = item
  const isLink = !!docHref
  const Comp = isLink ? (docExternal ? 'a' : Link) : 'div'

  const baseCls =
    'group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 transition-colors flex flex-col'
  const linkCls = isLink ? 'hover:border-kerf-300/40 hover:bg-ink-900/70' : ''

  const compProps = isLink
    ? docExternal
      ? { href: docHref, target: '_blank', rel: 'noreferrer' }
      : { to: docHref }
    : {}

  return (
    <Comp className={clsx(baseCls, linkCls)} {...compProps}>
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <StatusPill status={status} />
        <AreaPill area={area} />
      </div>
      <h3
        className={clsx(
          'font-display text-base font-semibold tracking-tight text-ink-100 mb-1.5',
          isLink && 'group-hover:text-kerf-200 transition-colors',
        )}
      >
        {title}
      </h3>
      <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
      {isLink && (
        <span className="mt-3 inline-flex items-center gap-1 text-[11px] font-mono text-ink-500 group-hover:text-kerf-300 transition-colors">
          {docExternal ? (
            <>
              plan doc
              <ExternalLink size={11} />
            </>
          ) : (
            <>
              docs
              <ArrowRight size={11} className="group-hover:translate-x-0.5 transition-transform" />
            </>
          )}
        </span>
      )}
    </Comp>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function Roadmap() {
  const [statusFilter, setStatusFilter] = useState('all')
  const [areaFilter, setAreaFilter] = useState('all')

  // Pre-compute counts so filter chips can show "(N)".
  const counts = useMemo(() => {
    const byStatus = { all: ITEMS.length }
    const byArea = { all: ITEMS.length }
    for (const it of ITEMS) {
      byStatus[it.status] = (byStatus[it.status] || 0) + 1
      byArea[it.area] = (byArea[it.area] || 0) + 1
    }
    return { byStatus, byArea }
  }, [])

  const filtered = useMemo(() => {
    return ITEMS.filter((it) => {
      if (statusFilter !== 'all' && it.status !== statusFilter) return false
      if (areaFilter !== 'all' && it.area !== areaFilter) return false
      return true
    })
  }, [statusFilter, areaFilter])

  // Group filtered items by status — even when a single status is
  // selected we still want the section header for context.
  const grouped = useMemo(() => {
    const buckets = STATUSES.map((s) => ({ ...s, items: [] }))
    const idx = Object.fromEntries(STATUSES.map((s, i) => [s.id, i]))
    for (const it of filtered) {
      buckets[idx[it.status]].items.push(it)
    }
    return buckets.filter((b) => b.items.length > 0)
  }, [filtered])

  // Area chips only show areas that have entries (avoids dead chips).
  const visibleAreas = useMemo(() => {
    return AREAS.filter((a) => counts.byArea[a])
  }, [counts])

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100 flex flex-col">
      <Header />

      {/* Hero */}
      <section className="relative border-b border-ink-900 overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-[radial-gradient(60%_60%_at_50%_0%,rgba(255,214,51,0.06),transparent_60%)]"
        />
        <div className="mx-auto max-w-7xl px-6 pt-14 pb-10 lg:pt-20 lg:pb-12">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Roadmap
          </p>
          <h1 className="mt-3 font-display text-4xl sm:text-5xl lg:text-[3.75rem] font-semibold tracking-[-0.025em] leading-[1.05]">
            What&apos;s done.{' '}
            <span className="text-kerf-300">What&apos;s next.</span>{' '}
            What&apos;s coming.
          </h1>
          <p className="mt-4 text-lg text-ink-300 leading-relaxed max-w-2xl">
            Public, current, and curated from{' '}
            <a
              href={ROADMAP_URL}
              target="_blank"
              rel="noreferrer"
              className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
            >
              ROADMAP.md
            </a>{' '}
            in the repo. For the dense per-task / per-test view (200+
            rows of implementation notes) read the markdown directly.
          </p>

          {/* Status legend */}
          <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
            {STATUSES.map((s) => (
              <span
                key={s.id}
                className="inline-flex items-center gap-2 text-ink-400"
              >
                <StatusPill status={s.id} />
                <span className="font-mono text-ink-500">
                  {counts.byStatus[s.id] || 0}
                </span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Filter strip */}
      <section className="border-b border-ink-900 bg-ink-950/80 backdrop-blur sticky top-16 z-20">
        <div className="mx-auto max-w-7xl px-6 py-4 flex flex-col gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-ink-500 pr-1">
              <FilterIcon size={11} />
              Status
            </div>
            <Chip
              active={statusFilter === 'all'}
              onClick={() => setStatusFilter('all')}
              count={counts.byStatus.all}
            >
              All
            </Chip>
            {STATUSES.map((s) => (
              <Chip
                key={s.id}
                active={statusFilter === s.id}
                onClick={() => setStatusFilter(s.id)}
                count={counts.byStatus[s.id] || 0}
              >
                {s.label}
              </Chip>
            ))}
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-ink-500 pr-1">
              <FilterIcon size={11} />
              Area
            </div>
            <Chip
              active={areaFilter === 'all'}
              onClick={() => setAreaFilter('all')}
              count={counts.byArea.all}
            >
              All
            </Chip>
            {visibleAreas.map((a) => (
              <Chip
                key={a}
                active={areaFilter === a}
                onClick={() => setAreaFilter(a)}
                count={counts.byArea[a]}
              >
                {a}
              </Chip>
            ))}
          </div>
        </div>
      </section>

      {/* Items */}
      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-6 py-10 lg:py-12">
          {grouped.length === 0 && (
            <div className="rounded-xl border border-dashed border-ink-800 bg-ink-900/30 p-10 text-center">
              <p className="font-display text-lg text-ink-200">
                No items match this filter combination.
              </p>
              <p className="mt-2 text-sm text-ink-400">
                Try clearing the area filter or pick a different status.
              </p>
              <button
                type="button"
                onClick={() => {
                  setStatusFilter('all')
                  setAreaFilter('all')
                }}
                className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-kerf-300 text-ink-950 px-3 h-9 text-sm font-medium hover:bg-kerf-200 transition-colors"
              >
                Reset filters
                <ArrowRight size={14} />
              </button>
            </div>
          )}

          {grouped.map((bucket, i) => (
            <section key={bucket.id} className={i > 0 ? 'mt-12' : ''}>
              <div className="flex items-end justify-between mb-5 gap-4">
                <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">
                  <span aria-hidden className="mr-2">
                    {bucket.emoji}
                  </span>
                  {bucket.label}
                  <span className="ml-3 font-mono text-sm text-ink-500 tabular-nums">
                    {bucket.items.length}
                  </span>
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {bucket.items.map((it) => (
                  <ItemCard key={`${it.status}-${it.title}`} item={it} />
                ))}
              </div>
            </section>
          ))}

          {/* Disclaimer / link to source */}
          <div className="mt-14 pt-8 border-t border-ink-900 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <p className="text-xs text-ink-500 leading-relaxed max-w-2xl">
              This page is hand-curated from{' '}
              <a
                href={ROADMAP_URL}
                target="_blank"
                rel="noreferrer"
                className="text-ink-300 hover:text-kerf-300 underline underline-offset-2"
              >
                ROADMAP.md
              </a>
              . The repo is the source of truth — for per-task breakdowns
              and design docs, read the markdown.
            </p>
            <div className="flex items-center gap-3">
              <a
                href={ROADMAP_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-ink-800 bg-ink-900/60 px-3 h-9 text-xs text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors font-mono"
              >
                <Github size={13} />
                ROADMAP.md
              </a>
              <Link
                to="/docs"
                className="inline-flex items-center gap-1.5 text-xs text-ink-400 hover:text-ink-100 transition-colors"
              >
                Docs
                <ArrowRight size={12} />
              </Link>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}
