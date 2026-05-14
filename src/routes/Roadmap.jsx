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
    title: 'FreeCAD Tier 1 import',
    body: '.FCStd → .feature + .sketch + .assembly. Pure-Python parser, BRep-lifted geometry, PartDesign metadata, multi-Body assembly. 5 fixtures, integration tests, no FreeCAD install required.',
    status: 'shipped',
    area: 'Imports',
    docHref: '/docs/imports',
  },
  {
    title: 'NURBS booleans v1',
    body: 'feature_to_solid cap-then-boolean helper + feature_boolean (cut/fuse/common) on solids. 7 tasks shipped end-to-end. Sets up Phase 4 surface-direct work.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/nurbs-booleans-v1.md',
    docExternal: true,
  },
  {
    title: 'NURBS Phase 4 — surface booleans (C1, partial)',
    body: 'feature_surface_boolean Python tool + opSurfaceBoolean worker handler behind a binding probe. First 3 of 10 Capability-1 tasks shipped; T4–T10 next.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/nurbs-phase-4-full.md',
    docExternal: true,
  },
  {
    title: 'Persistent face naming',
    body: 'Sketch-anchored primary (Pad-A.TopCap) + topological-signature fallback. Dual-write target_face_name alongside legacy target_face_id — survives upstream sketch edits. T1+T2 shipped.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/persistent-face-naming.md',
    docExternal: true,
  },
  {
    title: '5-axis CAM v1',
    body: 'Constant-tilt finishing (UV iso-curves + per-point surface normal + tilt-about-tangent + ball-end tip math) and 3+2 indexed (rotate STL to drive-face Z).',
    status: 'shipped',
    area: 'CAM',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/5-axis-cam.md',
    docExternal: true,
  },
  {
    title: 'Wiring + harness diagrams',
    body: 'New .wiring file kind. WireViz YAML → SVG. kerf-wiring plugin, /run-wireviz pyworker route, opt-in GPLv3 extra (subprocess-isolated on hosted).',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/electronics',
  },
  {
    title: 'Sketch → JSCAD workflow',
    body: 'extrude_sketch_to_jscad LLM tool, viewport surfaces sketch-import errors, reactive re-eval on sketch edits, "Build 3D" affordance + file-tree backlink. Mesh-side analog of .feature.',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/sketch-to-jscad',
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
    title: 'Rhino-parity authoring',
    body: '.3dm round-trip, SubD (Catmull-Clark), layers + display modes, mesh tools, parametric graph (.graph, Grasshopper-equivalent), render-quality output, curve depth (12 ops).',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/feature-format',
  },
  {
    title: 'KiCad parity — full PCB depth',
    body: 'Hierarchical schematics, buses + diff pairs, net classes + DRC, length tuning, via stitching + teardrops, push-pull routing, ERC, per-pad mask/paste overrides.',
    status: 'shipped',
    area: 'Electronics',
    docHref: '/docs/circuit-format',
  },
  {
    title: 'FreeCAD-parity PartDesign + Sketcher',
    body: 'feature_helix, feature_draft, feature_mirror, feature_multi_transform, feature_rib. Sketcher extensions (carbon-copy, validate). Sketch → 3D shortcuts (boss_with_draft, cut_from_sketch, hole_pattern).',
    status: 'shipped',
    area: 'Mechanical',
    docHref: '/docs/freecad-sketch-shortcuts',
  },
  {
    title: 'FEM + Topology optimization',
    body: 'FEniCSx linear elasticity + SLEPc modal + multi-body multi-material BCs; CalculiX modal as second solver. Density-field SIMP topology with NURBS-driven STEP reconstruction.',
    status: 'shipped',
    area: 'CAE',
    docHref: '/docs/capabilities',
  },
  {
    title: 'SPICE + RF + autorouting',
    body: 'ngspice transient/DC + probe waveforms via uPlot. scikit-rf S-parameter analysis (VSWR, return loss, Smith chart). FreeRouting JAR for autoroute.',
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
    body: 'Multi-member workspaces with role-based access. go-git commits/branches/merge with multi-lane lattice graph view. GitHub OAuth + branch sync with AES-GCM-encrypted tokens.',
    status: 'shipped',
    area: 'Cloud',
    docHref: '/docs/cloud',
  },
  {
    title: 'Plugin monorepo + kerf-server',
    body: '19 plugin packages under packages/, discovered via Python entry points. kerf-server CLI. Six install personas (api-only / mech / electronics / bim / full / compute-only).',
    status: 'shipped',
    area: 'Architecture (stack)',
    docHref: '/docs/architecture',
  },
  {
    title: 'Server-side STEP pre-tessellation',
    body: 'AutoTessWorker wakes on Postgres LISTEN/NOTIFY, runs pyworker /run-tess on STEP uploads, stores GLB to object storage with content-hash idempotency. Cloud-only.',
    status: 'shipped',
    area: 'Performance',
    docHref: '/docs/architecture',
  },
  {
    title: 'Diff-based + compressed revisions',
    body: 'Every Nth revision is full content; in between are unified-diff payloads. 82× shrink measured on typical edit patterns. Reconstruction walks the chain to the nearest base.',
    status: 'shipped',
    area: 'Performance',
    docHref: '/docs/architecture',
  },
  {
    title: 'Cloud git → object-storage Storer',
    body: 'pygit2-based bulk-sync storer for bare repos on R2/S3. Crash-consistent ordering (objects before refs), optimistic concurrency via sentinel ETag, orphan batch cleanup.',
    status: 'shipped',
    area: 'Cloud',
    docHref: '/docs/architecture',
  },
  {
    title: 'Free-form project tags',
    body: 'projects.tags TEXT[] replaces the old single-enum project_type. Workshop filter chip strip, repeatable ?tag= URL params. Projects compose multiple domains (robot = mech + electronics).',
    status: 'shipped',
    area: 'Architecture (stack)',
    docHref: '/docs/concepts',
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

  /* ── 🚧 in flight ──────────────────────────────────────────────── */
  {
    title: 'NURBS Phase 4 — surface-direct booleans (C1)',
    body: 'Robust surface booleans accepting Face/Shell operands without a solid round-trip. First 3 of 10 tasks shipped (probe, worker handler, Python tool); T4–T10 cover inspector + WASM integration + escalation paths.',
    status: 'in_flight',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/nurbs-phase-4-full.md',
    docExternal: true,
  },
  {
    title: 'Persistent face naming (continued)',
    body: 'T1+T2 shipped (worker emitter + role taxonomy for fillet/chamfer/shell/cut/push_pull). T3–T7 cover boolean-op naming, pattern carry-over, mate-ref migration, and the resolveFaceRef name-first fallback.',
    status: 'in_flight',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/persistent-face-naming.md',
    docExternal: true,
  },

  /* ── 📋 next ───────────────────────────────────────────────────── */
  {
    title: 'NURBS Phase 4 C1 — tasks T4–T10',
    body: 'Inspector entry (C1-T5), FeatureView affordance, WASM integration test (C1-T8, three end-to-end scenarios), SetFuzzyValue fallback (C1-T9), custom WASM rebuild escalation (C1-T10).',
    status: 'next',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/nurbs-phase-4-full.md',
    docExternal: true,
  },
  {
    title: 'FreeCAD Tier 2 import',
    body: 'Sketcher constraints + Spreadsheet → .equations. TechDraw drawings + Materials Library. Tier 1 (Part + PartDesign → .feature + .sketch + .assembly) already shipped.',
    status: 'next',
    area: 'Imports',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/freecad-tier-1-import.md',
    docExternal: true,
  },

  /* ── 🔮 planned ────────────────────────────────────────────────── */
  {
    title: 'NURBS Phase 4 — full capabilities 2-4',
    body: 'Trim-by-curve, matchSrf, G3 continuity. Multi-year OCCT kernel work; tracked separately from Capability 1 (surface-direct booleans, in flight).',
    status: 'planned',
    area: 'Mechanical',
    docHref: 'https://github.com/kerf-sh/kerf/blob/main/docs/plans/nurbs-phase-4-full.md',
    docExternal: true,
  },
  {
    title: 'Slicing — plane-section / cross-section',
    body: 'CAD-side feature_section wraps BRepAlgoAPI_Section. Section-plane gumball in the viewport. Result stored as a .section wire — dimensionable, DXF-exportable, chainable into feature_pad.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Slicing — CNC layered',
    body: 'Stacked plane-sections at fixed Z heights for layered milling / waterjet / laser-cut-and-stack. Each layer is a 2D contour fed into the existing CAM contour op; post-processor adds Z-step retracts.',
    status: 'planned',
    area: 'CAM',
  },
  {
    title: 'Slicing — 3D-print G-code (FDM / SLA)',
    body: 'Mesh → printable G-code with perimeters, infill, supports, retraction. Open-source path: wrap CuraEngine or PrusaSlicer as a subprocess (AGPLv3 — subprocess boundary like WireViz).',
    status: 'planned',
    area: 'CAM',
  },
  {
    title: 'Rhino-parity: quad remesher',
    body: 'Quad-dominant remeshing — distinct from the existing triangle mesh.remesh op. Open-source path: Instant Meshes (MIT, ~10k LOC C++) as wasm or native subprocess. Useful for SubD prep + downstream FEM.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Sketcher: Bezier curves',
    body: 'Add bezier entity kind to .sketch (cubic B-spline already shipped). Draw via control-point clicks; Tangent / G1 / G2 continuity constraints between adjacent segments.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Sketcher: symmetry over arbitrary construction line',
    body: 'Extends the existing axis-aligned symmetry constraint to mirror a sub-selection across an arbitrary construction line. Carbon-copy + axis-aligned symmetry both already shipped.',
    status: 'planned',
    area: 'Mechanical',
  },
  {
    title: 'Revit parity: IFC import',
    body: 'Currently export IFC4; import is the reverse. IfcOpenShell parses .ifc → .bim DSL + level/wall/slab nodes. Tier 1: walls/slabs/spaces/levels. Tier 2: families + schedules + views.',
    status: 'planned',
    area: 'Architecture',
  },
  {
    title: 'Electrical: PLC structured text (.plc.st)',
    body: 'IEC 61131-3 Structured Text — Pascal-shaped DSL for ladder logic / function blocks. Tier 1: syntax highlight + offline MATIEC lint. Tier 2: optional OpenPLC sim against synthetic inputs.',
    status: 'planned',
    area: 'Electronics',
  },
  {
    title: 'Electronics: ML-assisted reroute',
    body: 'Phase 3 of autorouting. DeepPCB-style network suggests reroutes for the FreeRouting output. Phases 1 (FreeRouting integration) and 2 (push-and-shove) shipped earlier.',
    status: 'planned',
    area: 'Electronics',
  },
  {
    title: 'SDK: Rust + Go + Lua',
    body: 'crates.io/kerf-sdk · github.com/kerf-sh/kerf-sdk-go · luarocks/kerf-sdk. Same wire format as Python + TS (POST /v1/rpc). Targets existing CAD-plugin ecosystems where embedded scripting matters.',
    status: 'planned',
    area: 'Scripting',
    docHref: '/docs/v1-rpc',
  },
  {
    title: 'Electronics: openEMS RF field solver',
    body: 'Phase 2 of RF — full 3D EM field simulation alongside the shipped scikit-rf S-parameter analysis. Stub already exists; v2 wires the openEMS subprocess + voxel mesh.',
    status: 'planned',
    area: 'Electronics',
    docHref: '/docs/electronics',
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
