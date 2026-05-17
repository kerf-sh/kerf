/**
 * /compare/matrixgold — Kerf vs MatrixGold (Gemvision / Stuller)
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-17).
 *
 * MatrixGold is the industry-standard professional jewelry CAD suite from
 * Gemvision / Stuller. It runs as a deeply integrated Rhino + Grasshopper
 * plugin and has been the benchmark for goldsmith tooling — ring builders,
 * stone-setting wizards, pavé engines, wax-mill paths, supplier catalogs —
 * for well over a decade.
 *
 * Kerf's jewelry vertical (40 modules) covers the same core scope — ring v4,
 * settings v3, gemstones v2, chain v2, gem-seat v2, gem-cert, casting export,
 * full cost panel, PBR render — and extends into retail-workflow features
 * (appraisal, repair estimator, mount_finder, etc.) that are typically outside
 * MatrixGold's scope. The honest gap is years of goldsmith-specific UI polish,
 * the Grasshopper ecosystem, and established casthouse partnerships.
 */
import { useEffect } from 'react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import {
  Section,
  Li,
  CompareTable,
  TableFooter,
  FairnessNote,
  CTAStrip,
  Breadcrumb,
  HeadMeta,
  GOOD,
  WEAK,
  GAP,
} from './Freecad.jsx'

/* -------------------------------------------------------------------------- */
/* Inline meta (compareMeta.js does not include a matrixgold slug entry;      */
/* we mirror the exact shape makeCompareMeta() returns so HeadMeta works).    */
/* -------------------------------------------------------------------------- */
const BASE = 'https://kerf.sh'
const _slug = 'matrixgold'
const _canonical = `${BASE}/compare/${_slug}`
const meta = {
  title: 'Kerf vs MatrixGold — jewelry CAD compared',
  description:
    'MatrixGold is the professional standard for jewelry CAD. See how ' +
    "Kerf's 40-module jewelry vertical, open-core licence, and retail " +
    'workflow compare — honestly.',
  canonical: _canonical,
  ogImage: `${BASE}/og/compare-${_slug}.png`,
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Kerf vs MatrixGold — jewelry CAD compared',
    description:
      'MatrixGold is the professional standard for jewelry CAD. See how ' +
      "Kerf's 40-module jewelry vertical, open-core licence, and retail " +
      'workflow compare — honestly.',
    url: _canonical,
    image: `${BASE}/og/compare-${_slug}.png`,
    publisher: { '@type': 'Organization', name: 'Kerf', url: BASE },
  }),
  product: 'MatrixGold',
  slug: _slug,
}

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                              */
/* -------------------------------------------------------------------------- */
const TABLE = [
  // Licensing & platform
  {
    group: 'Licensing & platform',
    feature: 'License',
    competitor: `${WEAK} Proprietary; per-seat subscription or perpetual`,
    kerf: `${GOOD} MIT open-core`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Cost',
    competitor: `${WEAK} Several thousand USD per seat; Rhino base required`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Operating system',
    competitor: `${WEAK} Windows only`,
    kerf: `${GOOD} Browser (hosted) + single-binary local (macOS / Linux / Win)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Browser / hosted option',
    competitor: `${GAP} Desktop only`,
    kerf: `${GOOD} Hosted SaaS (sign up, design in-browser)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Maturity',
    competitor: `${GOOD} 15+ years of jewelry-specific UI polish`,
    kerf: `${WEAK} Early-stage, < 2 yr public`,
  },

  // Core jewelry — gemstones
  {
    group: 'Gemstones',
    feature: 'Gemstone catalog',
    competitor: `${GOOD} Extensive library incl. certified stones`,
    kerf: `${GOOD} Gemstones v2 — 12+ cuts incl. fancy shapes + coloured-stone accuracy`,
  },
  {
    group: 'Gemstones',
    feature: 'Gem-cert generation',
    competitor: `${WEAK} Via supplier integrations`,
    kerf: `${GOOD} Gem-cert output built in`,
  },
  {
    group: 'Gemstones',
    feature: 'Faceting render',
    competitor: `${GOOD} Photoreal gem dispersion / caustics`,
    kerf: `${WEAK} Faceting render; no caustics / dispersion`,
  },
  {
    group: 'Gemstones',
    feature: 'PBR material library',
    competitor: `${GOOD} Rich precious-metal + gem materials`,
    kerf: `${GOOD} PBR materials for metals and gems`,
  },

  // Settings
  {
    group: 'Settings',
    feature: 'Setting styles covered',
    competitor: `${GOOD} Prong, bezel, pavé, channel, halo, and more`,
    kerf: `${GOOD} Settings v3 — prong/bezel/channel/pavé/tension/flush/halo/3-stone/cluster/bar/bead/gypsy/illusion/invisible`,
  },
  {
    group: 'Settings',
    feature: 'Head & gallery library',
    competitor: `${GOOD} Extensive pre-built heads and galleries`,
    kerf: `${GOOD} Head/gallery library included`,
  },
  {
    group: 'Settings',
    feature: 'Gem seat / seat generation',
    competitor: `${GOOD} Seat generation from stone parameters`,
    kerf: `${GOOD} Gem-seat v2`,
  },
  {
    group: 'Settings',
    feature: 'Setting UI polish',
    competitor: `${GOOD} Goldsmith-refined; battle-tested workflows`,
    kerf: `${WEAK} Functional, but a younger UX`,
  },

  // Ring builders
  {
    group: 'Ring builders',
    feature: 'Ring profiles',
    competitor: `${GOOD} Large library of shank profiles`,
    kerf: `${GOOD} Ring v4 — 13+ profiles + sizer + shoulders`,
  },
  {
    group: 'Ring builders',
    feature: 'Ring styles',
    competitor: `${GOOD} Eternity, signet, stacking, composite, and more`,
    kerf: `${GOOD} Eternity / signet / stacking / contoured / composite builders`,
  },
  {
    group: 'Ring builders',
    feature: 'Sizing',
    competitor: `${GOOD} Automated ring sizing`,
    kerf: `${GOOD} Ring sizer built in`,
  },

  // Chain & findings
  {
    group: 'Chain & findings',
    feature: 'Chain / bracelet',
    competitor: `${GOOD} Chain builder with link library`,
    kerf: `${GOOD} Chain v2`,
  },
  {
    group: 'Chain & findings',
    feature: 'Findings library',
    competitor: `${GOOD} Clasps, bails, findings from supplier catalogs`,
    kerf: `${WEAK} Findings modules; no supplier catalog integration`,
  },

  // Decorative & surface
  {
    group: 'Decorative & surface',
    feature: 'Milgrain / filigree / granulation',
    competitor: `${WEAK} Via manual techniques or add-ons`,
    kerf: `${GOOD} Milgrain / filigree / granulation built in`,
  },
  {
    group: 'Decorative & surface',
    feature: 'Engraving / laser marking',
    competitor: `${WEAK} Basic engraving; laser via separate flow`,
    kerf: `${GOOD} Laser_marking module`,
  },
  {
    group: 'Decorative & surface',
    feature: 'Enamel',
    competitor: `${WEAK} Manual mesh modelling`,
    kerf: `${GOOD} Enamel module`,
  },

  // Production
  {
    group: 'Production export',
    feature: 'Casting / STL export',
    competitor: `${GOOD} STL + DLP/SLA casting prep, wax-mill paths`,
    kerf: `${GOOD} Casting / STL production export`,
  },
  {
    group: 'Production export',
    feature: 'Wax-carving plan',
    competitor: `${GOOD} Wax-mill toolpaths built in`,
    kerf: `${WEAK} Wax-carving plan module (no full mill-path generation)`,
  },
  {
    group: 'Production export',
    feature: 'CAD quality check',
    competitor: `${GOOD} Pre-production checks`,
    kerf: `${GOOD} cad_qc module`,
  },
  {
    group: 'Production export',
    feature: 'Hallmark / hallmarking',
    competitor: `${WEAK} Manual text placement`,
    kerf: `${GOOD} Hallmark module`,
  },

  // Retail workflow (Kerf differentiators)
  {
    group: 'Retail & workshop workflow',
    feature: 'Quote / cost panel',
    competitor: `${WEAK} Not a core MatrixGold feature`,
    kerf: `${GOOD} Full quote / cost panel built in`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Appraisal (insurance / replacement)',
    competitor: `${GAP} Out of scope for jewelry CAD`,
    kerf: `${GOOD} Appraisal module`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Repair estimator',
    competitor: `${GAP} Out of scope for jewelry CAD`,
    kerf: `${GOOD} Repair estimator module`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Mount finder',
    competitor: `${GAP} Not a feature`,
    kerf: `${GOOD} mount_finder module`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Family / mother\'s ring',
    competitor: `${WEAK} Manual construction`,
    kerf: `${GOOD} Family / mother\'s ring builder`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Watch / horology',
    competitor: `${GAP} Not in scope`,
    kerf: `${GOOD} Watch / horology module`,
  },
  {
    group: 'Retail & workshop workflow',
    feature: 'Stringing (pearl / bead)',
    competitor: `${WEAK} Manual construction`,
    kerf: `${GOOD} Stringing module`,
  },

  // Platform / scripting
  {
    group: 'Platform & scripting',
    feature: 'Grasshopper / visual scripting',
    competitor: `${GOOD} Full Grasshopper ecosystem via Rhino`,
    kerf: `${GAP} No visual node environment`,
  },
  {
    group: 'Platform & scripting',
    feature: 'Python scripting',
    competitor: `${GOOD} RhinoCommon / rhinoscriptsyntax`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC`,
  },
  {
    group: 'Platform & scripting',
    feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits source per turn`,
  },
  {
    group: 'Platform & scripting',
    feature: 'BYO LLM (bring your own key)',
    competitor: `${GAP} N/A`,
    kerf: `${GOOD} BYO API key supported`,
  },

  // Ecosystem
  {
    group: 'Ecosystem',
    feature: 'Plugin / vendor marketplace',
    competitor: `${GOOD} Established plugin ecosystem + Stuller catalog`,
    kerf: `${WEAK} Plugin API early-stage`,
  },
  {
    group: 'Ecosystem',
    feature: 'Casthouse partnerships',
    competitor: `${GOOD} Direct supplier integrations`,
    kerf: `${GAP} None yet`,
  },
  {
    group: 'Ecosystem',
    feature: 'Integration with mech / electronics',
    competitor: `${GAP} Separate tools required`,
    kerf: `${GOOD} OCCT B-rep + full EDA stack in same workspace`,
  },
  {
    group: 'Ecosystem',
    feature: 'Community & training',
    competitor: `${GOOD} Large, well-resourced; Stuller support`,
    kerf: `${WEAK} Early-stage, growing`,
  },
]

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function MatrixGoldPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main className="mx-auto max-w-4xl px-6 pt-12 pb-20">
        <Breadcrumb />

        {/* Hero */}
        <div className="mb-10">
          <p
            className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2"
            aria-label="Page category"
          >
            Compare
          </p>
          <h1
            className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight"
            aria-label="Kerf vs MatrixGold comparison"
          >
            Kerf vs MatrixGold
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            MatrixGold (Gemvision / Stuller) is the professional benchmark for
            jewelry CAD — a Rhino plugin with 15+ years of goldsmith-driven
            refinement, comprehensive stone-setting wizards, ring builders, wax
            mill paths, and direct casthouse integrations. Kerf's jewelry
            vertical covers the same core scope in 40 modules, plus retail
            workflow features (appraisal, repair, mount finder) rarely found in
            CAD tools. Below is an honest look at where each stands today.
          </p>
        </div>

        {/* Where MatrixGold is strong */}
        <Section title="Where MatrixGold is strong">
          <ul className="flex flex-col gap-3" aria-label="MatrixGold strengths">
            <Li>
              <strong className="text-ink-100">
                Industry-standard jewelry CAD.
              </strong>{' '}
              MatrixGold is the professional benchmark: ring builders, stone
              settings, pavé engines, gem libraries, and sizing tools have been
              refined over 15+ years of goldsmith feedback.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Built on Rhino + Grasshopper.
              </strong>{' '}
              Inherits Rhino's class-leading NURBS kernel and the full
              Grasshopper visual-scripting ecosystem — thousands of community
              components spanning generative patterns, structural optimisation,
              and custom parametric rigs.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Comprehensive setting builders.
              </strong>{' '}
              Prong, bezel, pavé, channel, halo, bar, cluster, and more — all
              with pre-built head and gallery libraries battle-tested in
              production.
            </Li>
            <Li>
              <strong className="text-ink-100">Wax-mill toolpaths.</strong>{' '}
              Generates full wax-carving mill paths for CNC wax milling — a
              production step Kerf's wax_carving module does not yet cover end-
              to-end.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Established casthouse partnerships.
              </strong>{' '}
              Stuller catalog integration, direct supplier ordering, and
              production-ready STL / casting workflows with established casthouses.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Professional rendering with gem dispersion.
              </strong>{' '}
              Photoreal renders with accurate caustics and gem dispersion via
              the V-Ray / KeyShot / Cycles ecosystem Rhino plugs into.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Vendor support and training.
              </strong>{' '}
              Stuller-backed support, a large training community, certified
              instructors, and an established plugin marketplace.
            </Li>
          </ul>
        </Section>

        {/* MatrixGold pain points */}
        <Section title="MatrixGold pain points">
          <ul
            className="flex flex-col gap-3"
            aria-label="MatrixGold pain points"
          >
            <Li>
              <strong className="text-ink-100">
                Rhino + paid plugin stack.
              </strong>{' '}
              MatrixGold requires a Rhino licence plus the MatrixGold plugin
              subscription — total cost runs several thousand USD per seat,
              with annual maintenance fees.
            </Li>
            <Li>
              <strong className="text-ink-100">Windows only.</strong>{' '}
              MatrixGold runs exclusively on Windows. macOS and Linux users are
              locked out.
            </Li>
            <Li>
              <strong className="text-ink-100">Per-seat licensing.</strong>{' '}
              Each designer needs a separate seat licence; studios pay per
              workstation.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Separate from CAD-CAM-electronics workflows.
              </strong>{' '}
              Mechanical CAD, PCB/electronics, drawings, and costing all require
              separate tools — nothing integrates natively.
            </Li>
            <Li>
              <strong className="text-ink-100">Learning curve.</strong>{' '}
              The Rhino + Grasshopper + MatrixGold stack is powerful but has a
              steep learning curve; training investment is significant.
            </Li>
            <Li>
              <strong className="text-ink-100">No native cloud collaboration.</strong>{' '}
              MatrixGold is a desktop application with no hosted option, no
              browser access, and no real-time collaboration built in.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf differs */}
        <Section title="Where Kerf differs">
          <ul
            className="flex flex-col gap-3"
            aria-label="Where Kerf differs from MatrixGold"
          >
            <Li>
              <strong className="text-ink-100">
                40 jewelry modules in scope.
              </strong>{' '}
              Kerf's jewelry vertical covers the same core domain: gemstones v2
              (12+ cuts including fancy shapes and coloured-stone accuracy),
              settings v3 (prong / bezel / channel / pavé / tension / flush /
              halo / 3-stone / cluster / bar / bead / gypsy / illusion /
              invisible), ring v4 (sizer + 13+ profiles + shoulders + eternity /
              signet / stacking / contoured / composite builders), gem-seat v2,
              chain v2, findings, gem-cert, casting / STL production export,
              full quote / cost panel, PBR materials, and faceting render.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Retail workflow built in — the differentiator.
              </strong>{' '}
              Appraisal (insurance / replacement value), repair estimator,
              mount_finder, family / mother's ring, wax_carving plan, cad_qc,
              filigree / granulation / milgrain, hinge, laser_marking,
              watch / horology, enamel, and stringing — these retail and
              workshop features are typically outside MatrixGold's scope
              entirely.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, free locally.</strong>{' '}
              The full jewelry workflow runs locally on an MIT licence at no
              cost. The hosted SaaS option is pay-as-you-go with no per-seat
              subscription.
            </Li>
            <Li>
              <strong className="text-ink-100">
                In-browser, any OS.
              </strong>{' '}
              Sign up and design in the browser — no Windows dependency, no
              installer. A single binary also installs locally via brew or curl.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a ring modification in plain language and the LLM edits
              the feature tree directly, backed by doc-search so it doesn't
              invent API surface. No Grasshopper node-wiring required for
              standard parametric changes.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Integrated with mechanical and electronics.
              </strong>{' '}
              OCCT B-rep feature tree, full EDA stack (schematic / routing /
              DRC / Gerber / IPC-2581), multi-sheet drawings, and ASME Y14.5
              GD&T are in the same workspace — disciplines that require separate
              tools in the MatrixGold stack.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk Python scripting.</strong>{' '}
              Automate ring templates, setting layouts, and cost panels from any
              Python script over HTTP/JSON-RPC on your own machine.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul
            className="flex flex-col gap-3"
            aria-label="Areas where Kerf is behind MatrixGold"
          >
            <Li>
              <strong className="text-ink-100">
                Years of jewelry-specific UI polish.
              </strong>{' '}
              MatrixGold's goldsmith-driven UX has been refined through 15+
              years of workshop feedback. Kerf's jewelry UI is functional and
              growing, but noticeably younger.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No Grasshopper equivalent.
              </strong>{' '}
              Kerf has no visual parametric environment. Chat and the Python SDK
              fill part of that space for straightforward parametric changes,
              but not for advanced generative or procedural workflows.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No full wax-mill toolpath generation.
              </strong>{' '}
              Kerf has a wax_carving plan module for guiding manual carving, but
              does not generate CNC wax-milling toolpaths the way MatrixGold
              does.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No casthouse integrations.
              </strong>{' '}
              MatrixGold's Stuller catalog and direct casthouse ordering have no
              equivalent in Kerf yet.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Rendering is basic.
              </strong>{' '}
              Kerf provides PBR materials and faceting render but no caustics or
              gem dispersion. Photoreal jewelry renders still need an external
              renderer.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Smaller community.
              </strong>{' '}
              MatrixGold has a large, Stuller-backed community with certified
              instructors and extensive training material. Kerf's ecosystem is
              early-stage.
            </Li>
          </ul>
        </Section>

        {/* Migration notes */}
        <Section title="Migrating from MatrixGold">
          <ul
            className="flex flex-col gap-3"
            aria-label="Migration notes from MatrixGold to Kerf"
          >
            <Li>
              <strong className="text-ink-100">
                Setting and gemstone concepts map directly.
              </strong>{' '}
              Prong counts, bezel wall height, pavé row spacing, stone cut and
              diameter — the parameters you use in MatrixGold translate
              directly to Kerf's settings v3 and gemstones v2 inputs. The
              module names differ; the jewelry logic is the same.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Ring builder concepts carry over.
              </strong>{' '}
              Shank profile, width, depth, comfort fit, finger size — ring v4's
              parameter set covers the same territory as MatrixGold's ring
              builders. Export to STL for casting is the same final step.
            </Li>
            <Li>
              <strong className="text-ink-100">
                The retail / appraisal workflow is the differentiator.
              </strong>{' '}
              If your studio handles insurance appraisals, repair estimates, or
              customer-facing quotes alongside CAD, these workflows have no
              MatrixGold equivalent. They are first-class in Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">
                STEP / STL round-trip for existing assets.
              </strong>{' '}
              Existing MatrixGold models export to STEP or STL and import into
              Kerf cleanly. You can continue refining pieces in Kerf without
              rebuilding from scratch.
            </Li>
            <Li>
              <strong className="text-ink-100">
                The gap is jewelry-specific UI depth.
              </strong>{' '}
              The biggest adjustment is that MatrixGold's goldsmith-workflow UX
              is more refined in areas like pavé layout fine-tuning and wax-path
              generation. Expect to encounter rough edges in Kerf on complex
              production pieces.
            </Li>
          </ul>
        </Section>

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="MatrixGold" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
