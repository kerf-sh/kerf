/**
 * Landing — production marketing page.
 *
 * Sections (top → bottom):
 *   1. Hero — single-line headline, two CTAs (Try it free / Read the
 *      docs), a small "Run it locally" install snippet, and the three-
 *      pane editor illustration above the fold (>=lg) or below (mobile).
 *   2. Output strip — tiny pills listing the real engineering artifacts
 *      Kerf emits (STEP, IFC, gerber, G-code, SPICE, FEM, BOM).
 *   3. Pipeline divider — sketch → feature → assembly → drawing → CAM.
 *   4. Capability tour — capability cards, each with a domain
 *      illustration, grouped into mechanical / electronics / arch /
 *      engineering / sharing.
 *   5. Chat loop — single-frame view of how an LLM turn shapes geometry.
 *   6. Recently shipped — drawn from docs/whats-new.md and the most
 *      recent ROADMAP ✅ rows. Links into the docs.
 *   7. Roadmap glimpse — "what's next" tiles + link to roadmap.
 *   8. Local vs hosted — same product, two ways to run it.
 *   9. Pricing teaser — three plan cards linking to /pricing.
 *  10. CTA strip — try / GitHub.
 *  11. Footer (own component).
 *
 * Palette is locked to ink-* / kerf-* / cyan-edge / magenta-edge from
 * src/index.css. No raster assets — everything inline SVG.
 *
 * Density note: spacing is tuned for competitive density (Linear/Vercel
 * style) — section padding ~py-12/14, card gaps ~gap-4/5, card insets
 * ~p-5/6. Don't pad this page back out without checking with a designer.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Code2,
  Layers,
  PenTool,
  FileText,
  Boxes,
  Sparkles,
  Server,
  Zap,
  Check,
  CircuitBoard,
  Workflow,
  Share2,
  Building2,
  Activity,
  Wrench,
  GitBranch,
  Cpu,
  Terminal,
  Radio,
  Copy,
  Gem,
  Settings2,
  ChevronRight,
  Wind,
  Stethoscope,
  Telescope,
  Clock,
  Box,
  Anchor,
  HardHat,
  TreePine,
} from 'lucide-react'
import { useState } from 'react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import { useAuth } from '../store/auth.js'
import Button from '../components/Button.jsx'
import { useCloudConfig } from '../cloud/useCloudConfig.js'
import DomainSpotlights from '../components/landing/DomainSpotlights.jsx'
import KernelDepth from '../components/landing/KernelDepth.jsx'
import {
  HeroIllustration,
  JscadIllustration,
  FeatureTreeIllustration,
  SketcherIllustration,
  DrawingIllustration,
  CircuitIllustration,
  LibraryIllustration,
  WorkshopIllustration,
  ChatLoopIllustration,
  FemIllustration,
  TopoIllustration,
  CamIllustration,
  BimIllustration,
  GitIllustration,
  ScriptingIllustration,
  PipelineIllustration,
  SketchShortcutsIllustration,
  SketchToJscadIllustration,
  SpiceSimIllustration,
  RfAnalysisIllustration,
  RevitParityIllustration,
  StairsMepIllustration,
  ViewportScaleIllustration,
  FineGrainedUndoIllustration,
  TolerancePlusMatesIllustration,
} from '../components/illustrations/index.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'
const INSTALL_CMD = 'pip install -e .[mech]'
const RUN_CMD = 'kerf-server --migrate'

/* -------------------------------------------------------------------------- */
/* Section: Hero                                                               */
/* -------------------------------------------------------------------------- */

function Hero() {
  const authed = useAuth((s) => !!s.accessToken)
  return (
    <section className="relative overflow-hidden">
      <HeroBackdrop />

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="grid lg:grid-cols-[1fr_1.15fr] gap-8 lg:gap-12 items-center">
          <div>
            <span
              className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono"
              aria-label="Verticals and licence summary"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-kerf-300 animate-pulse" />
              open source · jewelry · mech · electronic
            </span>

            <h1 className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4.25rem] font-semibold tracking-[-0.03em] leading-[1.02]">
              Chat-driven CAD.
              <br />
              <span className="relative inline-block">
                <span className="relative z-10 text-kerf-300">Real</span>
                <span
                  aria-hidden
                  className="absolute left-0 right-0 -bottom-2 h-2.5 bg-kerf-300/15 -skew-x-12 rounded-sm"
                />
              </span>{' '}
              geometry kernel underneath.
            </h1>

            <p className="mt-4 text-lg text-ink-300 leading-relaxed max-w-xl">
              Three verticals in one workspace — jewelry, mechanical,
              electronic — sitting on a validated B-rep + NURBS kernel with a
              parametric history DAG. Parametric edits survive across fillets
              and booleans via persistent face IDs.{' '}
              <Link
                to="/docs/whats-new"
                className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200 transition-colors"
              >
                See what shipped →
              </Link>
            </p>

            <ul
              className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2 max-w-xl text-[11px] font-mono text-ink-400"
              aria-label="Per-vertical capability summary"
            >
              <li className="rounded-md border border-ink-800 bg-ink-900/50 px-2.5 py-1.5">
                <span className="text-kerf-300">jewelry</span> · 40 modules
              </li>
              <li className="rounded-md border border-ink-800 bg-ink-900/50 px-2.5 py-1.5">
                <span className="text-kerf-300">mech</span> · weld · forming · AM · moldflow · CAM
              </li>
              <li className="rounded-md border border-ink-800 bg-ink-900/50 px-2.5 py-1.5">
                <span className="text-kerf-300">electronic</span> · SI · EMC · PDN · thermal
              </li>
            </ul>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              {authed ? (
                <Button as={Link} to="/projects" variant="primary" size="lg">
                  Open Kerf
                  <ArrowRight size={16} />
                </Button>
              ) : (
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Try it free
                  <ArrowRight size={16} />
                </Button>
              )}
              <Button as={Link} to="/docs/getting-started" variant="outline" size="lg">
                Read the docs
              </Button>
            </div>

            <RunLocallyChip />

            <ul
              className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono"
              aria-label="Quiet credibility footnotes"
            >
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                ~23,959 tests green · 0 failing
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                MIT licensed
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                Python plugin monorepo
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                no card required
              </li>
            </ul>
          </div>

          <div className="relative hidden md:block rounded-[2rem] p-6 -m-6">
            <div className="relative rounded-2xl border border-ink-800 bg-ink-900/40 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden aspect-[3/2]">
              <HeroIllustration className="block w-full h-full" />
            </div>
            <div
              aria-hidden
              className="absolute inset-0 -z-10 rounded-[2rem] bg-kerf-300/[0.05] blur-3xl"
            />
            {/* small floating chips around the hero illustration to read at a glance */}
            <FloatingChip className="hidden lg:flex absolute -top-3 -left-4" icon={Sparkles} label="LLM tool surface" />
            <FloatingChip className="hidden lg:flex absolute -bottom-3 -right-4" icon={GitBranch} label="GitHub sync" />
          </div>
        </div>

        <LogoStrip />
      </div>
    </section>
  )
}

function FloatingChip({ icon: Icon, label, className = '' }) {
  return (
    <div
      className={
        'items-center gap-1.5 rounded-full border border-ink-700 bg-ink-900/85 backdrop-blur px-2.5 py-1 text-[10px] font-mono text-ink-200 shadow-lg shadow-black/40 ' +
        className
      }
    >
      <Icon size={11} className="text-kerf-300" />
      {label}
    </div>
  )
}

function RunLocallyChip() {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    const text = `${INSTALL_CMD}\n${RUN_CMD}`
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {})
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div className="mt-4 flex flex-col gap-1 rounded-lg border border-ink-800 bg-ink-900/60 px-3 py-2 font-mono text-xs text-ink-300 max-w-full sm:max-w-md">
      <div className="flex items-start gap-2 min-w-0">
        <Terminal size={12} className="text-kerf-300 shrink-0 mt-1" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-ink-500 shrink-0">$</span>
            <span className="text-ink-100 break-all">{INSTALL_CMD}</span>
          </div>
          <div className="flex items-center gap-2 min-w-0 mt-0.5">
            <span className="text-ink-500 shrink-0">$</span>
            <span className="text-ink-100 break-all">{RUN_CMD}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={copy}
          aria-label="Copy install commands"
          className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800 transition-colors shrink-0"
        >
          {copied ? <Check size={12} className="text-kerf-300" /> : <Copy size={12} />}
        </button>
      </div>
      <p className="text-[10px] text-ink-500 pl-5">
        Python 3.11+ · Postgres · or{' '}
        <code className="text-ink-400">curl kerf.sh/install.sh | sh</code>
      </p>
    </div>
  )
}

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
        }}
      />
      <div
        className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[700px] opacity-50"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(255,214,51,0.18) 0%, rgba(255,214,51,0.04) 35%, transparent 70%)',
        }}
      />
    </div>
  )
}

function LogoStrip() {
  // The "trusted by" strip is honest: list the technologies under the
  // hood, not vapor logos. Pure typographic, low-key.
  const items = [
    'JSCAD',
    'tscircuit',
    'planegcs',
    'FEniCSx',
    'OpenCAMlib',
    'IfcOpenShell',
    'FreeRouting',
    'TechDraw',
    'KiCad',
  ]
  return (
    <div className="mt-10 lg:mt-12 flex flex-col items-center gap-3">
      <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-500">
        Built on open kernels
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
        {items.map((it) => (
          <li
            key={it}
            className="font-mono text-sm text-ink-400 hover:text-ink-200 transition-colors"
          >
            {it}
          </li>
        ))}
      </ul>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Output formats strip                                               */
/* -------------------------------------------------------------------------- */

const OUTPUT_FORMATS = [
  { label: 'STEP', sub: 'validated B-rep' },
  { label: 'STL · 3MF', sub: 'mesh export' },
  { label: 'IFC4', sub: 'BIM' },
  { label: 'gerber', sub: 'PCB fab' },
  { label: 'G-code', sub: 'CNC posts' },
  { label: 'SPICE', sub: 'circuit sim' },
  { label: 'FEM mesh', sub: 'CalculiX · gmsh' },
  { label: 'PDF · DXF', sub: 'drawings' },
  { label: 'BOM CSV', sub: 'with prices' },
  { label: 'Touchstone', sub: 'S-parameters' },
]

function OutputStrip() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-7xl px-6 py-8 lg:py-10">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-500">
            Real artefacts out the other side
          </p>
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-500/70">
            no proprietary lock-in
          </p>
        </div>
        <ul className="flex flex-wrap gap-2">
          {OUTPUT_FORMATS.map((f) => (
            <li
              key={f.label}
              className="inline-flex items-center gap-2 rounded-md border border-ink-800 bg-ink-900/50 px-2.5 py-1"
            >
              <span className="font-mono text-xs text-kerf-300">{f.label}</span>
              <span className="font-mono text-[10px] text-ink-500">{f.sub}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Pipeline divider                                                   */
/* -------------------------------------------------------------------------- */

function PipelineDivider() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-6 lg:py-8">
        <PipelineIllustration className="block w-full h-auto" />
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Capability tour                                                    */
/* -------------------------------------------------------------------------- */

export const CAPABILITY_GROUPS = [
  {
    id: 'mech',
    eyebrow: 'Mechanical · code-first CAD',
    title: 'JSCAD, validated B-rep, and a real sketcher.',
    body: 'Code-first parametric geometry, real solid-modeling parity with FreeCAD/SolidWorks, and a constraints-solved 2D sketcher that drives every feature. Process-sim suite alongside: weld, forming, AM, moldflow, CAM.',
    cards: [
      {
        icon: Code2,
        title: 'JSCAD code authoring',
        body: 'Plain JavaScript with @jscad/modeling. Worker-based eval, IndexedDB mesh cache, file-revisions undo for every keystroke.',
        Illustration: JscadIllustration,
      },
      {
        icon: Layers,
        title: 'Validated B-rep features',
        body: 'Pad, Pocket, Revolve, Fillet (G1/G2), Chamfer, Shell, Hole, Draft, Sweep (corrected-Frenet mode), symmetric Loft, plus NURBS surfacing (sweep2 / network / blend) and direct face/edge gumballs. Persistent face IDs survive parameter edits.',
        Illustration: FeatureTreeIllustration,
      },
      {
        icon: PenTool,
        title: '2D parametric sketcher',
        body: 'planegcs solver. 12+ constraints. Trim, extend, ellipse, B-spline, fillet, mirror, linear/polar patterns. Arc/circle edge projection. Multi-loop holes.',
        Illustration: SketcherIllustration,
      },
      {
        icon: Zap,
        title: 'FreeCAD sketch shortcuts',
        body: 'feature_boss_with_draft, feature_cut_from_sketch, feature_hole_pattern_from_sketch — single LLM calls that land a 2D profile straight into a B-rep feature with the right downstream metadata.',
        Illustration: SketchShortcutsIllustration,
      },
      {
        icon: Workflow,
        title: 'Sketch → JSCAD',
        body: 'extrude_sketch_to_jscad LLM tool. Import a .sketch profile into a JSCAD program; reactive re-eval when the sketch changes; sketch-import errors surface in the viewport.',
        Illustration: SketchToJscadIllustration,
      },
      {
        icon: FileText,
        title: 'TechDraw 2D drawings',
        body: 'Multi-sheet drawings. Linear, aligned, radius, diameter, angular, baseline, chain, ordinate dims. GD&T frames per Y14.5. Hatching, leaders, balloons, centerlines.',
        Illustration: DrawingIllustration,
      },
    ],
  },
  {
    id: 'cae',
    eyebrow: 'Engineering · CAE + CAM',
    title: 'FEM, topology, tolerance, CAM — one chain.',
    body: 'Push a part through linear-static and modal FEM, density-field topology optimisation, worst-case / RSS / Monte-Carlo tolerance with assembly-mate-aware chain-walking, and emit posted G-code. All open-source solvers under the hood.',
    cards: [
      {
        icon: Activity,
        title: 'FEM analysis',
        body: 'FEniCSx primary (UFL, multiphysics-ready) + CalculiX second-solver. Linear static, modal (SLEPc), multi-body bonded contact. Deformed-shape 3D overlay with stress colouring.',
        Illustration: FemIllustration,
      },
      {
        icon: Sparkles,
        title: 'Topology optimisation',
        body: 'Density-field SIMP via FEniCSx. Multi-body conformal meshing. Marching cubes + NURBS surface fitting → real STEP output you can edit downstream.',
        Illustration: TopoIllustration,
      },
      {
        icon: Wrench,
        title: 'CAM toolpaths',
        body: 'OpenCAMlib + pythonOCC. 2.5D face/contour/pocket/drill/profile, 3D parallel + waterline, lathe X-Z. LinuxCNC / GRBL / Mach3 / Fanuc post-processors.',
        Illustration: CamIllustration,
      },
      {
        icon: Activity,
        title: 'Tolerance + mates',
        body: 'Worst-case · RSS · Monte-Carlo dimension stacks. tolerance_auto_chain walks the assembly-mate graph by BFS between two feature refs and builds the dimension chain for you. Mates UI is back with BREP face/edge picker.',
        Illustration: TolerancePlusMatesIllustration,
      },
    ],
  },
  {
    id: 'electronics',
    eyebrow: 'Electronics · schematic to gerber',
    title: 'PCB design with SI / EMC / PDN / thermal pre-compliance.',
    tagline: 'Two authoring styles, one fabrication target.',
    body: 'atopile (.ato) for code-first parametric circuits and tscircuit (.tsx) for visual-first JSX authoring — both compile to the same CircuitJSON and gerber outputs. Full layer stack and manual routing, FreeRouting autoroute, SPICE simulation via ngspice, RF/S-parameters via scikit-rf, plus signal-integrity, EMC, PDN, and thermal pre-compliance checks in one tool — all cross-linked to mechanical assemblies.',
    cards: [
      {
        icon: CircuitBoard,
        title: 'Schematic + PCB',
        body: 'TSX → CircuitJSON. Manual trace routing, copper pours, layer stack, DRC + ERC, net classes, length tuning, diff-pair match, via stitching, push-pull router.',
        Illustration: CircuitIllustration,
      },
      {
        icon: Cpu,
        title: 'SPICE + autoroute',
        body: 'Server-side ngspice via /run-spice. V/I probes on the schematic. FreeRouting JAR for autoroute, KiCad import for both schematics and footprint libraries.',
        Illustration: SpiceSimIllustration,
      },
      {
        icon: Radio,
        title: 'RF analysis',
        body: 'scikit-rf S-parameters: VSWR, return / insertion loss, Rollett K, max available gain. Smith chart SVG. Touchstone import. openEMS field solver on the way.',
        Illustration: RfAnalysisIllustration,
      },
    ],
  },
  {
    id: 'arch',
    eyebrow: 'Architecture · BIM that compiles',
    title: '.bim text-DSL → IFC4 buildings.',
    body: 'A code-first BIM authoring loop. Walls, slabs, openings, spaces, levels, families, schedules, views, sheets, MEP routing, curtain walls — all compiled via IfcOpenShell and rendered with web-ifc in the browser.',
    cards: [
      {
        icon: Building2,
        title: '.bim → IFC4 compiler',
        body: 'Text or JSON DSL describing walls / slabs / openings / spaces / levels / sites compiles to IFC4 via IfcOpenShell. Rendered in Three.js via web-ifc.',
        Illustration: BimIllustration,
      },
      {
        icon: Layers,
        title: 'Revit-parity authoring',
        body: 'Families (.family.json), schedules (.schedule.json), views (.view.json), sheets (.sheet.json). Categories + hosted refs, type vs instance, phasing, view filters.',
        Illustration: RevitParityIllustration,
      },
      {
        icon: Workflow,
        title: 'Stairs · railings · MEP',
        body: 'Stairs, railings, curtain walls, and MEP routing for ducts / pipes / conduits. Sheet revisions tracked alongside cloud git history.',
        Illustration: StairsMepIllustration,
      },
    ],
  },
  {
    id: 'silicon',
    eyebrow: 'Silicon · IC / ASIC design',
    tagline: 'From RTL to GDS-II in a conversation.',
    title: 'RTL synthesis, PnR, DRC/LVS, and GDS-II — open PDKs.',
    body: 'Full RTL-to-GDS-II flow via Yosys, OpenROAD, Magic, Netgen and KLayout. Sky130 and GF180MCU PDKs bundled. Static timing via OpenSTA. FPGA bitstream for iCE40 and ECP5 via nextpnr. Post-layout SPICE with SPEF annotation.',
    cards: [
      {
        icon: Cpu,
        title: 'RTL synthesis (Yosys)',
        body: 'Synthesise Verilog/SystemVerilog to a gate netlist. Technology mapping for Sky130, GF180MCU and nextpnr-compatible FPGA targets. Synth report surfaced in chat.',
      },
      {
        icon: Activity,
        title: 'Place & route (OpenROAD)',
        body: 'Floorplan, placement, CTS and global/detailed routing. DEF/LEF round-trip. SDC/UPF constraints authored and applied in the same chat session.',
      },
      {
        icon: CircuitBoard,
        title: 'DRC + LVS + GDS-II',
        body: 'DRC and LVS via Magic + Netgen. Sky130B and GF180MCU rule decks bundled. Final GDS-II stream via KLayout — submit-ready for CMP / Efabless shuttle.',
      },
    ],
  },
  {
    id: 'firmware',
    eyebrow: 'Firmware · Embedded systems',
    tagline: 'From bare metal to .hex in a conversation.',
    title: 'C / C++ / Rust on ARM + RISC-V — .hex/.elf out.',
    body: 'arm-none-eabi-gcc, cargo cross, FreeRTOS, Zephyr, cppcheck, clang-tidy, OpenOCD/pyOCD flash and debug — all wired through the chat loop. Linker scripts, peripheral HAL scaffolding, MCUboot OTA. .hex and .elf are universal; load them on any debugger.',
    cards: [
      {
        icon: Cpu,
        title: 'Build + static analysis',
        body: 'arm-none-eabi-gcc and cargo cross for ARM Cortex-M and RISC-V targets. cppcheck + clang-tidy on every build turn. MISRA-C 2012 advisory subset via cppcheck addons.',
      },
      {
        icon: Code2,
        title: 'RTOS scaffolding',
        body: 'FreeRTOS task / queue / semaphore / timer scaffolding generated in chat. Zephyr DTS and Kconfig authoring with LLM-aware binding schema. West build wired end-to-end.',
      },
      {
        icon: Terminal,
        title: 'Flash + debug (OpenOCD)',
        body: 'OpenOCD and pyOCD flash and SWD/JTAG debug. GDB server through the chat loop: set breakpoints, inspect memory and registers — all from a conversation.',
      },
    ],
  },
  {
    id: 'aerospace',
    eyebrow: 'Aerospace · Structural engineering',
    tagline: 'From airframe sketch to STEP and Mystran in a conversation.',
    title: 'Parametric airframes, FEM, composites — STEP/Mystran out.',
    body: 'Parametric wing, fuselage and control surfaces. FEM via FEniCSx with Mystran BDF export. Composites lay-up (CFRP/GFRP) with ABD matrix and draping simulation. CFD mesh prep for SU2 and OpenFOAM. GD&T per AS9100/Y14.5. STEP AP242 out.',
    cards: [
      {
        icon: Activity,
        title: 'Structural FEM + Mystran',
        body: 'Linear static and modal FEM via FEniCSx (shell / beam / solid). Mystran BDF deck generation with GRID, CQUAD4, MAT1/MAT8, PSHELL, SPC and LOAD sections. Margin of safety computed automatically.',
      },
      {
        icon: Layers,
        title: 'Composites lay-up',
        body: 'Ply stack-up per zone: fibre angle, thickness, material. Laminate ABD matrix computed analytically. Interlaminar shear checks. Draping simulation flags manufacturability issues.',
      },
      {
        icon: Workflow,
        title: 'STEP AP242 + CFD prep',
        body: 'STEP AP214/AP242 with PMI via OpenCascade. SU2 config and OpenFOAM blockMesh/snappyHexMesh generation from STEP geometry. GD&T per AS9100 Rev D on TechDraw sheets.',
      },
    ],
  },
  {
    id: 'sharing',
    eyebrow: 'Library · Workshop · Cloud · SDK',
    title: 'Open sharing, curated parts, real git, scriptable.',
    body: 'A community Workshop for forking projects, a curated Library of parts with live distributor pricing (DigiKey / Mouser / LCSC), a real-git backend with GitHub sync, and a Python SDK for driving the same tool surface from your own machine.',
    cards: [
      {
        icon: Boxes,
        title: 'Library',
        body: 'Drop-in parts. Yours, the community’s, curated. Verified-publisher accounts (Adafruit, McMaster-style) seed common components. Live pricing via DigiKey / Mouser / LCSC.',
        Illustration: LibraryIllustration,
      },
      {
        icon: Share2,
        title: 'Workshop',
        body: 'Publish a project; fork what others built. One click publishes to the Workshop, where anyone can browse, like, or fork it as a starting point. Same MIT code that runs locally.',
        Illustration: WorkshopIllustration,
      },
      {
        icon: GitBranch,
        title: 'Cloud git + GitHub',
        body: 'pygit2 backend, multi-lane lattice graph, GitHub OAuth, AES-GCM-encrypted tokens, S3 storer for stateless serverless deploys, .step-ref pointers for big binaries.',
        Illustration: GitIllustration,
      },
      {
        icon: Terminal,
        title: 'kerf-sdk · Python SDK',
        body: 'pip install kerf-sdk. JSON-RPC over /v1/rpc, API-token auth, same tool surface the chat LLM uses — drive parameter sweeps and CI bakes from your own machine.',
        Illustration: ScriptingIllustration,
      },
      {
        icon: Zap,
        title: 'Viewport at scale',
        body: 'Frustum culling (S1) + InstancedMesh batching (S2) in Three.js. Assemblies with hundreds of identical components render at interactive frame rates.',
        Illustration: ViewportScaleIllustration,
      },
      {
        icon: GitBranch,
        title: 'Fine-grained undo',
        body: 'Every file edit appends to file_revisions. Phase-4 diff-based storage + SHA-256 dedup shrinks revision DB ~82×. Cmd+Z restores from any point; deleted files resurrect from history.',
        Illustration: FineGrainedUndoIllustration,
      },
    ],
  },
]

function CapabilityTour() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            What you can build
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            One workspace.
            <br />
            <span className="text-ink-300">Every CAD discipline.</span>
          </h2>
        </div>

        <div className="flex flex-col gap-12 lg:gap-14">
          {CAPABILITY_GROUPS.map((g) => (
            <CapabilityGroup key={g.id} group={g} />
          ))}
        </div>
      </div>
    </section>
  )
}

function CapabilityGroup({ group }) {
  return (
    <div>
      <div className="mb-5 max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-kerf-300">
          {group.eyebrow}
        </p>
        <h3 className="mt-1.5 font-display text-2xl sm:text-3xl font-semibold tracking-[-0.02em] text-ink-100">
          {group.title}
        </h3>
        {group.tagline && (
          <p className="mt-1 text-sm font-semibold text-kerf-300 tracking-tight">
            {group.tagline}
          </p>
        )}
        <p className="mt-2 text-sm text-ink-300 leading-relaxed">{group.body}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {group.cards.map((c) =>
          c.Illustration ? (
            <CapabilityCard key={c.title} {...c} />
          ) : (
            <CapabilityTextCard key={c.title} {...c} />
          ),
        )}
      </div>
    </div>
  )
}

function CapabilityCard({ icon: Icon, title, body, Illustration }) {
  return (
    <article className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 overflow-hidden transition-colors hover:border-ink-700 hover:bg-ink-900/60">
      <div className="aspect-[16/10] bg-ink-950/60 border-b border-ink-800 overflow-hidden">
        <Illustration className="block w-full h-full" />
      </div>
      <div className="p-5">
        <div className="flex items-center gap-2.5 mb-1.5">
          <span className="grid place-items-center w-7 h-7 rounded-md bg-kerf-300/10 border border-kerf-300/30 text-kerf-300 group-hover:bg-kerf-300/20 transition-colors">
            <Icon size={13} />
          </span>
          <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
            {title}
          </h3>
        </div>
        <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
      </div>
    </article>
  )
}

function CapabilityTextCard({ icon: Icon, title, body }) {
  // A leaner card that drops the illustration slot — used to round out
  // sub-groups where we don't have (or don't need) a bespoke SVG.
  return (
    <article className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 transition-colors hover:border-ink-700 hover:bg-ink-900/60">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="grid place-items-center w-7 h-7 rounded-md bg-kerf-300/10 border border-kerf-300/30 text-kerf-300">
          <Icon size={13} />
        </span>
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
    </article>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Per-domain deep-dives                                             */
/* -------------------------------------------------------------------------- */

const DOMAINS = [
  {
    icon: Gem,
    label: 'Jewelry',
    sub: '40 modules · ring/shank/seat/setting libraries',
    href: '/domains/jewelry',
    color: 'text-pink-400',
    bg: 'bg-pink-400/10 border-pink-400/30 group-hover:bg-pink-400/20',
  },
  {
    icon: Settings2,
    label: 'Mechanical',
    sub: 'B-rep features · weld · forming · AM · moldflow · CAM',
    href: '/domains/mechanical',
    color: 'text-cyan-400',
    bg: 'bg-cyan-400/10 border-cyan-400/30 group-hover:bg-cyan-400/20',
  },
  {
    icon: CircuitBoard,
    label: 'Electronics',
    sub: 'SI · EMC · PDN · thermal pre-compliance in one tool',
    href: '/domains/electronics',
    color: 'text-emerald-400',
    bg: 'bg-emerald-400/10 border-emerald-400/30 group-hover:bg-emerald-400/20',
  },
  {
    icon: Building2,
    label: 'Architecture',
    sub: 'Parametric massing, section views, drawings',
    href: '/domains/architecture',
    color: 'text-violet-400',
    bg: 'bg-violet-400/10 border-violet-400/30 group-hover:bg-violet-400/20',
  },
  {
    icon: Wind,
    label: 'Composites',
    sub: 'Ply layup · CLT solver · drape · cure cycle',
    href: '/domains/composites',
    color: 'text-yellow-400',
    bg: 'bg-yellow-400/10 border-yellow-400/30 group-hover:bg-yellow-400/20',
  },
  {
    icon: Stethoscope,
    label: 'Dental',
    sub: 'Crowns · surgical guides · aligner staging',
    href: '/domains/dental',
    color: 'text-rose-400',
    bg: 'bg-rose-400/10 border-rose-400/30 group-hover:bg-rose-400/20',
  },
  {
    icon: Telescope,
    label: 'Optics',
    sub: 'Ray tracing · Zemax import · opto-mechanical STEP',
    href: '/domains/optics',
    color: 'text-sky-400',
    bg: 'bg-sky-400/10 border-sky-400/30 group-hover:bg-sky-400/20',
  },
  {
    icon: Clock,
    label: 'Horology',
    sub: 'Escapement · gear train · mainspring · watch case',
    href: '/domains/horology',
    color: 'text-amber-400',
    bg: 'bg-amber-400/10 border-amber-400/30 group-hover:bg-amber-400/20',
  },
  {
    icon: Workflow,
    label: 'Piping / P&ID',
    sub: 'ISO 10628 · isometric · ASME B31.3 stress',
    href: '/domains/piping',
    color: 'text-teal-400',
    bg: 'bg-teal-400/10 border-teal-400/30 group-hover:bg-teal-400/20',
  },
  {
    icon: Box,
    label: 'Packaging',
    sub: 'ECMA dielines · fold sim · blank nesting · DXF',
    href: '/domains/packaging',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10 border-orange-400/30 group-hover:bg-orange-400/20',
  },
  {
    icon: Layers,
    label: 'Mold / Injection',
    sub: 'Core/cavity · mold base · gating · moldflow',
    href: '/domains/mold',
    color: 'text-indigo-400',
    bg: 'bg-indigo-400/10 border-indigo-400/30 group-hover:bg-indigo-400/20',
  },
  {
    icon: TreePine,
    label: 'Woodworking',
    sub: 'Joinery · cabinet designer · CNC routing · cut list',
    href: '/domains/woodworking',
    color: 'text-lime-400',
    bg: 'bg-lime-400/10 border-lime-400/30 group-hover:bg-lime-400/20',
  },
  {
    icon: Anchor,
    label: 'Marine / Naval',
    sub: 'Hull form · hydrostatics · resistance · scantlings',
    href: '/domains/marine',
    color: 'text-blue-400',
    bg: 'bg-blue-400/10 border-blue-400/30 group-hover:bg-blue-400/20',
  },
  {
    icon: HardHat,
    label: 'Civil',
    sub: 'Hydrology · geotech · pavement · IFC interchange',
    href: '/domains/civil',
    color: 'text-stone-400',
    bg: 'bg-stone-400/10 border-stone-400/30 group-hover:bg-stone-400/20',
  },
  {
    icon: Cpu,
    label: 'Silicon',
    sub: 'RTL · synth · PnR · DRC/LVS · GDS-II · open PDKs',
    href: '/domains/silicon',
    color: 'text-fuchsia-400',
    bg: 'bg-fuchsia-400/10 border-fuchsia-400/30 group-hover:bg-fuchsia-400/20',
  },
  {
    icon: Terminal,
    label: 'Firmware',
    sub: 'arm-none-eabi · cargo · FreeRTOS · OpenOCD',
    href: '/domains/firmware',
    color: 'text-green-400',
    bg: 'bg-green-400/10 border-green-400/30 group-hover:bg-green-400/20',
  },
  {
    icon: Activity,
    label: 'Aerospace',
    sub: 'Parametric airframes · FEM · composites · STEP/Mystran',
    href: '/domains/aerospace',
    color: 'text-blue-300',
    bg: 'bg-blue-300/10 border-blue-300/30 group-hover:bg-blue-300/20',
  },
]

function PerDomain() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Built for your discipline
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Domain-specific workflows.
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-4 gap-4">
          {DOMAINS.map((d) => (
            <Link
              key={d.label}
              to={d.href}
              className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors flex flex-col gap-3"
            >
              <span
                className={`grid place-items-center w-9 h-9 rounded-lg border transition-colors ${d.bg} ${d.color}`}
              >
                <d.icon size={16} />
              </span>
              <div>
                <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
                  {d.label}
                </h3>
                <p className="text-sm text-ink-400 mt-0.5">{d.sub}</p>
              </div>
              <ChevronRight
                size={14}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-ink-600 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all"
              />
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Compare                                                            */
/* -------------------------------------------------------------------------- */

const COMPARE_LINKS = [
  { label: 'Kerf vs FreeCAD', href: '/compare/freecad' },
  { label: 'Kerf vs Fusion 360', href: '/compare/fusion' },
  { label: 'Kerf vs KiCad', href: '/compare/kicad' },
  { label: 'Kerf vs Rhino', href: '/compare/rhino' },
  { label: 'Kerf vs Revit', href: '/compare/revit' },
]

function Compare() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/50">
      <div className="mx-auto max-w-7xl px-6 py-10 lg:py-12">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-1">
              How we stack up
            </p>
            <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-[-0.02em]">
              Compare Kerf
            </h2>
          </div>

          <div className="flex flex-wrap gap-3">
            {COMPARE_LINKS.map((c) => (
              <Link
                key={c.label}
                to={c.href}
                className="inline-flex items-center gap-1.5 rounded-lg border border-ink-800 bg-ink-900/40 px-3 py-2 text-sm text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors"
              >
                {c.label}
                <ArrowRight size={12} className="text-ink-500" />
              </Link>
            ))}
            <Link
              to="/compare"
              className="inline-flex items-center gap-1.5 rounded-lg border border-kerf-300/30 bg-kerf-300/5 px-3 py-2 text-sm text-kerf-300 hover:bg-kerf-300/10 transition-colors font-medium"
            >
              All comparisons
              <ArrowRight size={12} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Chat loop                                                          */
/* -------------------------------------------------------------------------- */

function ChatLoop() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            The chat loop
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            From a sentence to a part.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Every chat turn is a small, deliberate program. The model picks
            tools from a small fixed surface — file ops, validation,
            doc-search — edits the source, then re-renders. Or skip chat
            and drive the same surface from Python with{' '}
            <Link
              to="/docs/llm-tools"
              className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200 transition-colors"
            >
              kerf-sdk
            </Link>
            .
          </p>
        </div>

        <div className="hidden sm:block rounded-2xl border border-ink-800 bg-ink-950/60 backdrop-blur p-4 sm:p-6 lg:p-8">
          <div className="w-full aspect-[16/5] overflow-hidden">
            <ChatLoopIllustration className="block w-full h-full" />
          </div>
        </div>

        <div className="mt-5 grid sm:grid-cols-3 gap-4">
          <FactCard
            icon={Workflow}
            title="Small tool surface"
            body="file ops · object ops · validation · BOM · 4 create_* scaffolders"
          />
          <FactCard
            icon={Sparkles}
            title="Doc-search backed"
            body="search_kerf_docs reads /docs/llm/*.md before editing"
          />
          <FactCard
            icon={Terminal}
            title="Scriptable too"
            body="kerf-sdk on PyPI · JSON-RPC over /v1/rpc · bring your own LLM"
          />
        </div>
      </div>
    </section>
  )
}

function FactCard({ icon: Icon, title, body }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
      <div className="flex items-center gap-2 text-ink-300 mb-2">
        <Icon size={14} className="text-kerf-300" />
        <span className="font-display text-sm font-semibold tracking-tight text-ink-100">
          {title}
        </span>
      </div>
      <p className="text-xs text-ink-400 leading-relaxed font-mono">{body}</p>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Recently shipped                                                   */
/* -------------------------------------------------------------------------- */

// Pulled from ROADMAP.md ✅ shipped rows — most recent first. Keep to 9
// (3×3 on lg). The full list lives in /roadmap and ROADMAP.md.
const SHIPPED = [
  {
    title: 'FreeCAD Tier 2 import',
    domain: 'Imports',
    body: 'Sketcher constraints + Spreadsheet → .equations. TechDraw drawings → .drawing. Materials library. Completes the FreeCAD design round-trip after Tier 1 (PartDesign).',
    docHref: '/docs/imports',
  },
  {
    title: 'IFC import (Tier 1 + 2)',
    domain: 'Architecture',
    body: '.ifc → .bim DSL: walls / slabs / openings / spaces / levels. Tier 2: families + schedules + views. Bidirectional round-trip with existing IFC4 export.',
    docHref: '/docs/bim-format',
  },
  {
    title: 'NURBS Phase 4 — trim, matchSrf, G3 viz',
    domain: 'Mechanical',
    body: 'Trim-by-curve (C2) + matchSrf G1/G2 (C3) + curvature-comb G3 visualisation (C4). Closes out the NURBS Phase 4 surface-depth roadmap.',
    docHref: '/docs/feature-format',
  },
  {
    title: 'SubD with edge creases',
    domain: 'Mechanical',
    body: 'Catmull-Clark SubD with per-edge crease weights [0..1]. Smooth / crease / corner vertex classification. Hard-edge control without leaving SubD mode.',
    docHref: '/docs/feature-format',
  },
  {
    title: '3D-print G-code slicing',
    domain: 'CAM',
    body: 'Mesh → printable G-code via CuraEngine subprocess. Perimeters, infill, supports, retraction. kerf-slicing plugin; AGPLv3 extra isolated at subprocess boundary.',
    docHref: '/docs/capabilities',
  },
  {
    title: 'SDK: Rust + Go + Lua',
    domain: 'Scripting',
    body: 'kerf-sdk-rs / kerf-sdk-go / kerf-sdk-lua. Same JSON-RPC wire format as Python + TS. Targets embedded scripting in existing CAD plugin ecosystems.',
    docHref: '/docs/v1-rpc',
  },
  {
    title: 'PLC structured text (.plc.st)',
    domain: 'Electronics',
    body: 'IEC 61131-3 Structured Text editor + offline MATIEC lint. Companion to .circuit.tsx — describe ladder logic alongside the PCB it controls.',
    docHref: '/docs/electronics',
  },
  {
    title: 'Quad remesher',
    domain: 'Mechanical',
    body: 'Quad-dominant remeshing via Instant Meshes. Distinct from the triangle mesh.remesh op — produces structured quads for SubD prep and FEM meshing.',
    docHref: '/docs/capabilities',
  },
  {
    title: 'Persistent face naming — complete',
    domain: 'Mechanical',
    body: 'All 7 tasks shipped: face-name emission, role taxonomy, boolean carry-over, pattern propagation, mate-ref migration, resolveFaceRef name-first fallback, DB backfill.',
    docHref: '/docs/feature-format',
  },
]

function RecentlyShipped() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Recently shipped
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Moving fast, in public.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              Six highlights from the most recent sprint. The full list
              lives in{' '}
              <Link
                to="/docs/whats-new"
                className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
              >
                What&apos;s New
              </Link>
              , and the long view in{' '}
              <a
                href={`${GITHUB_URL}/blob/main/ROADMAP.md`}
                target="_blank"
                rel="noreferrer"
                className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
              >
                ROADMAP.md
              </a>
              .
            </p>
          </div>
          <Link
            to="/docs/whats-new"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            all updates
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SHIPPED.map((s) => (
            <Link
              key={s.title}
              to={s.docHref}
              className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-kerf-300/40 hover:bg-ink-900/70 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/30 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-emerald-300">
                  <Check size={10} strokeWidth={3} />
                  shipped
                </span>
                <span className="inline-flex items-center rounded-full bg-ink-800/80 border border-ink-700 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink-400">
                  {s.domain}
                </span>
              </div>
              <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100 mb-1.5 group-hover:text-kerf-200 transition-colors">
                {s.title}
              </h3>
              <p className="text-sm text-ink-300 leading-relaxed">{s.body}</p>
              <ArrowRight
                size={14}
                className="absolute right-5 bottom-5 text-ink-500 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all"
              />
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Roadmap glimpse                                                    */
/* -------------------------------------------------------------------------- */

const ROADMAP = [
  {
    title: 'FEM / CFD depth',
    body: 'Nonlinear static, explicit dynamics, acoustics, fatigue already in; Navier-Stokes + heat transfer in progress. Target: CalculiX / Z88 / Mystran scope.',
    status: 'in_flight',
  },
  {
    title: 'Interactive diff-pair routing',
    body: 'Diff-pair data layer shipped. In progress: push-and-shove UI, real-time impedance check, live length-delta display during routing.',
    status: 'in_flight',
  },
  {
    title: 'Broader ECAD import',
    body: 'Allegro / PADS / gEDA / Eagle → .circuit.tsx parsers. KiCad Tier 1 + 2 already landed; each legacy format gets its own parser.',
    status: 'next',
  },
  {
    title: 'Full joint system + direct edit',
    body: 'Gear / pin-slot / rack-pinion joints (cam-follower already shipped). Direct face-push edits that insert into the parametric DAG without breaking the feature tree.',
    status: 'next',
  },
  {
    title: 'Render: caustics + dispersion',
    body: 'Two-tier render path: a backend Blender Cycles worker for hero / catalog output (spectral dispersion, caustics — metered) and a progressive in-browser path tracer for free previews and offline self-host. Self-host docker image bundled.',
    status: 'next',
  },
  {
    title: 'BIM family library + structural grid',
    body: 'Walls / slabs / stairs / MEP already ship. Next: parametric family library, structural grid, site + earthwork, and material catalogue.',
    status: 'next',
  },
]

function RoadmapGlimpse() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              On the way
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              What we&apos;re building next.
            </h2>
          </div>
          <div className="hidden sm:flex items-center gap-4">
            <Link
              to="/roadmap"
              className="inline-flex items-center gap-1.5 rounded-md bg-kerf-300 text-ink-950 px-3 h-9 text-sm font-medium tracking-tight hover:bg-kerf-200 transition-colors"
            >
              See full roadmap
              <ArrowRight size={14} />
            </Link>
            <a
              href={`${GITHUB_URL}/blob/main/ROADMAP.md`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
            >
              ROADMAP.md
              <ArrowRight size={14} />
            </a>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {ROADMAP.map((r) => {
            const isInFlight = r.status === 'in_flight'
            const isNext = r.status === 'next'
            const pillCls = isInFlight
              ? 'bg-kerf-300/10 border border-kerf-300/30 text-kerf-300'
              : isNext
                ? 'bg-cyan-edge/10 border border-cyan-edge/30 text-cyan-300'
                : 'bg-ink-900 border border-ink-800 text-ink-400'
            return (
              <div
                key={r.title}
                aria-label={r.title}
                className={
                  'rounded-xl border border-dashed bg-ink-900/30 p-4 transition-colors ' +
                  (isInFlight
                    ? 'border-kerf-300/30 hover:bg-ink-900/50'
                    : isNext
                      ? 'border-cyan-edge/30 hover:bg-ink-900/50'
                      : 'border-ink-700 hover:border-kerf-300/30 hover:bg-ink-900/50')
                }
              >
                <span
                  className={
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest mb-2 ' +
                    pillCls
                  }
                >
                  <span aria-hidden>{isInFlight ? '●' : isNext ? '◐' : '○'}</span>
                  {isInFlight ? 'in flight' : isNext ? 'up next' : 'planned'}
                </span>
                <h3 className="font-display text-sm font-semibold tracking-tight text-ink-100 mb-1">
                  {r.title}
                </h3>
                <p className="text-xs text-ink-400 leading-relaxed">{r.body}</p>
              </div>
            )
          })}
        </div>

        {/* Mobile CTA */}
        <div className="mt-6 flex sm:hidden">
          <Link
            to="/roadmap"
            className="inline-flex items-center gap-1.5 rounded-md bg-kerf-300 text-ink-950 px-3 h-9 text-sm font-medium tracking-tight hover:bg-kerf-200 transition-colors"
          >
            See full roadmap
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Local vs Hosted                                                    */
/* -------------------------------------------------------------------------- */

const SHARED_FEATURES = [
  'Full editor: JSCAD, B-rep, sketcher, drawings, electronics, BIM',
  'FEM · topology · tolerance · CAM',
  'Library, BOM, Workshop sharing',
  'File revisions = unlimited undo',
  'Workspaces with member roles',
  'Free-form tags for multi-domain projects',
]

function LocalVsHosted() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="text-center mb-8 max-w-2xl mx-auto">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Local or hosted
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Same product. Two ways to run it.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Every line of code is open source — including billing,
            Workshop, and git sync. We host the binary as a service so you
            don&apos;t have to operate Postgres yourself.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <RunCard
            icon={<Server size={16} />}
            label="Local install"
            sub="MIT · self-host"
            ctaText="Install locally"
            ctaTo="/docs/getting-started"
            extra="Bring your own LLM API key"
            features={SHARED_FEATURES}
          />
          <RunCard
            icon={<Zap size={16} />}
            label="Hosted"
            sub="we run it for you"
            highlighted
            ctaText="Sign up free"
            ctaTo="/signup"
            extra="Metered LLM tokens + storage"
            features={SHARED_FEATURES}
            extras={['Daily backups', 'GitHub OAuth + branch sync', 'USD billing, ZAR settlement']}
          />
        </div>
      </div>
    </section>
  )
}

function RunCard({ icon, label, sub, ctaText, ctaTo, features, extras = [], extra, highlighted }) {
  return (
    <div
      className={
        'rounded-2xl border bg-ink-900/40 backdrop-blur p-5 flex flex-col gap-4 ' +
        (highlighted
          ? 'border-kerf-300/40 ring-1 ring-kerf-300/20'
          : 'border-ink-800')
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center w-9 h-9 rounded-lg bg-kerf-300/15 border border-kerf-300/30 text-kerf-300">
            {icon}
          </span>
          <div>
            <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100">
              {label}
            </h3>
            <p className="text-xs text-ink-400 font-mono">{sub}</p>
          </div>
        </div>
        {highlighted ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-kerf-300 text-ink-950 text-[10px] font-mono font-semibold uppercase tracking-widest px-2.5 py-0.5">
            zero-ops
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-ink-800 text-ink-300 text-[10px] font-mono uppercase tracking-widest px-2.5 py-0.5">
            MIT
          </span>
        )}
      </div>

      <ul className="flex flex-col gap-2">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-ink-200">
            <Check size={13} className="mt-1 text-kerf-300 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
        {extras.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-ink-200">
            <Check size={13} className="mt-1 text-kerf-300 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="rounded-md bg-ink-950/60 border border-ink-800 px-3 py-1.5">
        <p className="text-xs text-ink-400 font-mono">{extra}</p>
      </div>

      <Button
        as={Link}
        to={ctaTo}
        variant={highlighted ? 'primary' : 'outline'}
        size="md"
        className="w-full"
      >
        {ctaText}
        <ArrowRight size={14} />
      </Button>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Pricing teaser                                                     */
/* -------------------------------------------------------------------------- */

function PricingTeaser() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/40">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Pricing
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              No seats. No tiers. Just usage.
            </h2>
          </div>
          <Link
            to="/pricing"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            see full pricing
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <TeaserPlan
            label="Free"
            price="$0"
            note="forever"
            bullets={['50 MB · public projects', '100k in + 20k out free tokens/mo', 'Cheap-tier models · Workshop publish']}
            ctaTo="/signup"
            ctaText="Sign up"
          />
          <TeaserPlan
            highlighted
            label="Studio"
            price="$9"
            note="per month"
            bullets={['5 GB · private projects', '$8/mo LLM credits at cost · any model', 'Wallet top-up for overage']}
            ctaTo="/signup"
            ctaText="Start Studio"
          />
          <TeaserPlan
            label="Pro"
            price="$29"
            note="per month"
            bullets={['20 GB · higher worker concurrency', '$20/mo LLM credits at cost', 'Same wallet · same at-cost overage']}
            ctaTo="/pricing"
            ctaText="See pricing"
          />
        </div>

        <p className="mt-4 text-center text-xs text-ink-500 font-mono">
          At-cost LLM pricing · live provider rates · MIT self-host always free
        </p>
      </div>
    </section>
  )
}

function TeaserPlan({ label, price, note, bullets, ctaTo, ctaText, highlighted }) {
  return (
    <div
      className={
        'relative rounded-2xl border p-5 bg-ink-900/40 backdrop-blur transition-colors ' +
        (highlighted
          ? 'border-kerf-300/40 ring-1 ring-kerf-300/20'
          : 'border-ink-800 hover:border-ink-700')
      }
    >
      <div className="flex items-baseline justify-between mb-1">
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {label}
        </h3>
        {highlighted && (
          <span className="text-[10px] font-mono uppercase tracking-widest text-kerf-300">
            popular
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2 mb-3">
        <span className="font-display text-3xl font-semibold tracking-tight text-ink-100">
          {price}
        </span>
        <span className="text-xs text-ink-400 font-mono">{note}</span>
      </div>
      <ul className="flex flex-col gap-1.5 mb-4">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-2 text-sm text-ink-300">
            <span className="mt-2 w-1 h-1 rounded-full bg-ink-500 shrink-0" />
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <Link
        to={ctaTo}
        className={
          'inline-flex items-center justify-center gap-1.5 w-full h-9 rounded-md text-sm font-medium transition-colors ' +
          (highlighted
            ? 'bg-kerf-300 text-ink-950 hover:bg-kerf-200'
            : 'bg-ink-800 text-ink-100 border border-ink-700 hover:border-ink-600')
        }
      >
        {ctaText}
        <ArrowRight size={13} />
      </Link>
    </div>
  )
}


/* -------------------------------------------------------------------------- */
/* CTA strip (between sections)                                                */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  const authed = useAuth((s) => !!s.accessToken)
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-kerf-300/10 blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Cut your first part.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free and ship a model in the next ten minutes — or
                clone the repo and self-host. Both paths are first-class.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {authed ? (
                <Button as={Link} to="/projects" variant="primary" size="lg">
                  Open Kerf
                  <ArrowRight size={16} />
                </Button>
              ) : (
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Try it free
                  <ArrowRight size={16} />
                </Button>
              )}
              <Button as={Link} to="/library" variant="outline" size="lg">
                Browse the library
              </Button>
              <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="lg">
                <Github size={16} />
                Contribute on GitHub
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function Landing() {
  const { cloudEnabled } = useCloudConfig()
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <Hero />
      <OutputStrip />
      <PipelineDivider />
      <PerDomain />
      <KernelDepth />
      <CapabilityTour />
      <DomainSpotlights />
      <Compare />
      <ChatLoop />
      <RecentlyShipped />
      <RoadmapGlimpse />
      <LocalVsHosted />
      {cloudEnabled && <PricingTeaser />}
      <CTAStrip />
      <Footer />
    </div>
  )
}
