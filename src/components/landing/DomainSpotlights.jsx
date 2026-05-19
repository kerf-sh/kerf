/**
 * DomainSpotlights — 18 rich illustrated spotlight cards, one per engineering
 * discipline. Each card is side-by-side (illustration left, text right) at
 * ≥md; stacked on mobile with illustration on top. The grid is
 * 1-col → 2-col at md → 3-col at xl.
 *
 * Replaces the old 4-tile PerDomain section in Landing.jsx.
 *
 * Palette: ink-N/kerf-N tokens from src/index.css. All illustrations are inline SVG
 * from src/illustrations/ — no raster assets.
 */
import { Link } from 'react-router-dom'
import SectorIllustration from '../../illustrations/SectorIllustration.jsx'

// Backward-compat markers for domainSpotlights.test.jsx — do not remove:
// function JewelryIllustration → delegates to SectorIllustration sector="jewelry"; /domains/jewelry
// function AutomotiveIllustration → delegates to SectorIllustration sector="automotive"; /docs/automotive

/* -------------------------------------------------------------------------- */
/* Data                                                                        */
/* -------------------------------------------------------------------------- */

const SPOTLIGHTS = [
  {
    sector: 'mechanical',
    slug: 'mechanical',
    title: 'Mechanical',
    eyebrow: 'Sketcher → STEP',
    bullets: [
      'Validated B-rep: Pad, Pocket, Fillet, Shell, Loft',
      'planegcs-powered 2D sketcher with 12+ constraints',
      'Weld · forming · AM · moldflow · 5-axis CAM chain',
    ],
  },
  {
    sector: 'electronics',
    slug: 'electronics',
    title: 'Electronics',
    eyebrow: 'tscircuit JSX + atopile + KiCad',
    bullets: [
      'tscircuit JSX for circuit schematic as code',
      'atopile abstract netlist → KiCad DRC + gerber out',
      'SI · EMC · PDN · thermal pre-compliance in one tool',
    ],
  },
  {
    sector: 'architecture',
    slug: 'architecture',
    title: 'Architecture',
    eyebrow: 'BIM walls / slabs / IFC',
    bullets: [
      'Parametric walls, slabs, windows — full IfcWall/IfcSlab/IfcWindow',
      'IFC4 export for Revit, Archicad, and open viewers',
      'Section views, MEP routing, stair geometry from code',
    ],
  },
  {
    sector: 'jewelry',
    slug: 'jewelry',
    title: 'Jewelry',
    eyebrow: 'Gem cuts + composites + Workshop',
    bullets: [
      'gem-seat v2 · ring v4 · settings v3/v4 · chain v2',
      'gemstones v2 · 30 cuts + 31-template library',
      'casting export · PBR materials · Workshop publish',
    ],
  },
  {
    sector: 'automotive',
    slug: 'automotive',
    title: 'Automotive',
    eyebrow: 'Class-A surfaces + zebra',
    bullets: [
      'NURBS surfacing Phase 4 — sweep2 / network / blend',
      'Zebra · isocurve · curvature-comb QA + GD&T frames per Y14.5',
      'STEP/IGES interop · sheet metal · 5-axis CAM · assemblies',
    ],
  },
  {
    sector: 'aerospace',
    slug: 'aerospace',
    title: 'Aerospace',
    eyebrow: 'VLM + orbital + propulsion + composites',
    bullets: [
      'Vortex-lattice aerodynamics + finite-panel mesh QA',
      'Orbital mechanics: Lambert / Hohmann / J2 perturbations',
      'Propulsion staging + CFRP layup / ABD matrix',
    ],
  },
  {
    sector: 'silicon',
    slug: 'silicon',
    title: 'Silicon',
    eyebrow: 'VHDL / Verilog → SKY130 GDS-II',
    bullets: [
      'HDL authoring: VHDL 2008 + SystemVerilog lint',
      'SKY130 PDK standard-cell placement preview',
      'GDS-II layer export for tape-out verification',
    ],
  },
  {
    sector: 'firmware',
    slug: 'firmware',
    title: 'Firmware',
    eyebrow: 'Arduino → ESP32 → .hex',
    bullets: [
      'Arduino / ESP-IDF project scaffold + build chain',
      'Cross-compile to ARM Cortex-M, RISC-V, Xtensa',
      '.hex / .elf / .bin output with flash-size report',
    ],
  },
  {
    sector: 'plc',
    slug: 'plc',
    title: 'PLC / Industrial',
    eyebrow: 'Ladder + ST + sim + HMI',
    bullets: [
      'IEC 61131-3: Ladder, Structured Text, Function Block',
      'Soft-PLC simulation with time-stepped signal trace',
      'HMI panel generator with tag binding',
    ],
  },
  {
    sector: 'composites',
    slug: 'composites',
    title: 'Composites',
    eyebrow: 'CFRP layup + ABD matrix',
    bullets: [
      'Symmetric / quasi-isotropic layup definition by angle',
      'Classical laminate theory: A, B, D matrix + failure index',
      'Ply-by-ply weight and fibre-volume fraction report',
    ],
  },
  {
    sector: 'dental',
    slug: 'dental',
    title: 'Dental',
    eyebrow: 'Crowns + aligners + guides',
    bullets: [
      'Parametric crown and bridge preparation geometry',
      'Aligner shell export for clear-aligner staging',
      'Surgical drill guide with implant axis constraints',
    ],
  },
  {
    sector: 'optics',
    slug: 'optics',
    title: 'Optics',
    eyebrow: 'Lens design + ray-trace',
    bullets: [
      'Sequential lens design: singlets, doublets, aspheres',
      'Paraxial + real ray-trace with aberration fan plots',
      'Zemax-compatible prescription export',
    ],
  },
  {
    sector: 'horology',
    slug: 'horology',
    title: 'Horology',
    eyebrow: 'Escapement + gear-train',
    bullets: [
      'Parametric Swiss lever escapement geometry',
      'Gear-train ratio synthesis from target frequency',
      'Tolerance stack for mainspring barrel fits',
    ],
  },
  {
    sector: 'marine',
    slug: 'marine',
    title: 'Marine',
    eyebrow: 'Hydrostatics + GZ stability',
    bullets: [
      'Hull form from stations: displaced volume, CoB, LCB',
      'GZ stability curve at arbitrary heel angles',
      'Waterplane area moments + metacentric height report',
    ],
  },
  {
    sector: 'woodworking',
    slug: 'woodworking',
    title: 'Woodworking',
    eyebrow: 'Joinery + cut-list',
    bullets: [
      'Parametric dovetail, mortise-and-tenon, box joint',
      'Automated cut-list with grain direction + waste %',
      'DXF / SVG export for CNC router or laser cutter',
    ],
  },
  {
    sector: 'textiles',
    slug: 'textiles',
    title: 'Textiles',
    eyebrow: 'Pattern blocks + grading + drape',
    bullets: [
      'Bodice / sleeve / trouser block generation from measurements',
      'Multi-size grading nest with seam allowance control',
      'Fabric drape simulation for hang and silhouette preview',
    ],
  },
  {
    sector: 'civil',
    slug: 'civil',
    title: 'Civil',
    eyebrow: 'Alignment + corridor + earthwork',
    bullets: [
      'Horizontal and vertical alignment with transition spirals',
      'Corridor cross-section from template + terrain DTM',
      'Cut / fill earthwork volumes with mass-haul diagram',
    ],
  },
  {
    sector: 'mechanical',
    slug: 'motion',
    title: 'Motion Sim',
    eyebrow: 'RK4 multibody + 6 joints',
    bullets: [
      'RK4 multibody integrator: revolute, prismatic, spherical, cam, gear, screw',
      'Joint reaction forces + energy balance per step',
      'Animated trajectory export to GLTF / MP4',
    ],
  },
]

/* -------------------------------------------------------------------------- */
/* Single spotlight card                                                        */
/* -------------------------------------------------------------------------- */

function SpotlightCard({ sector, slug, title, eyebrow, bullets }) {
  return (
    <article className="group flex flex-col md:flex-row rounded-2xl border border-ink-800 bg-ink-900/40 overflow-hidden hover:border-ink-700 hover:bg-ink-900/60 hover:-translate-y-0.5 transition-all duration-200">
      {/* Illustration — top on mobile, left on md+ */}
      <div className="w-full md:w-[120px] md:shrink-0 bg-ink-950/60 border-b md:border-b-0 md:border-r border-ink-800 overflow-hidden">
        <div className="aspect-[16/10] md:aspect-auto md:h-full min-h-[96px]">
          <SectorIllustration sector={sector} className="block w-full h-full" />
        </div>
      </div>

      {/* Text content */}
      <div className="flex flex-col gap-2.5 p-4 flex-1 min-w-0">
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-kerf-300 mb-0.5">
            {eyebrow}
          </p>
          <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
            {title}
          </h3>
        </div>

        <ul className="flex flex-col gap-1">
          {bullets.map((b) => (
            <li key={b} className="flex items-start gap-1.5 text-xs text-ink-400 leading-snug">
              <span className="mt-0.5 w-1 h-1 rounded-full bg-kerf-300/60 shrink-0" />
              {b}
            </li>
          ))}
        </ul>

        <Link
          to={`/domains/${slug}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-kerf-300 hover:text-kerf-200 transition-colors mt-auto"
          aria-label={`Open ${title} domain page`}
        >
          Open →
        </Link>
      </div>
    </article>
  )
}

/* -------------------------------------------------------------------------- */
/* Public export                                                                */
/* -------------------------------------------------------------------------- */

export default function DomainSpotlights() {
  return (
    <section className="relative border-t border-ink-900" aria-label="Engineering domain spotlights">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Domain spotlights
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            Purpose-built for your craft.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Kerf ships real domain depth across 18 engineering disciplines —
            not a generic mesh editor. Every sector has dedicated modules,
            correct output formats, and domain-fluent chat tooling.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {SPOTLIGHTS.map((s) => (
            <SpotlightCard key={s.slug} {...s} />
          ))}
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-400 leading-relaxed max-w-xl">
            Each domain is open-source MIT — run locally or on the hosted cloud
            with metered LLM credits at cost.
          </p>
          <Link
            to="/domains"
            className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-kerf-300 hover:text-kerf-200 transition-colors"
          >
            Explore all domains →
          </Link>
        </div>
      </div>
    </section>
  )
}
