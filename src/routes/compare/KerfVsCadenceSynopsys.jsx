/**
 * /compare/cadence-synopsys — Kerf vs Cadence / Synopsys (silicon EDA)
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-19).
 *
 * Cadence (Virtuoso, Allegro, Innovus, Genus, Spectre) and Synopsys (Design
 * Compiler, IC Compiler II, PrimeTime, VCS, Formality) are the dominant
 * proprietary EDA stacks for chip design — RTL synthesis, place-and-route,
 * timing closure, sign-off, and DRC/LVS against foundry PDKs. Both are
 * six-figure annual contracts, Windows/Linux only, and closed source.
 *
 * Kerf ships GDS-II import/export, a SPICE netlist flow, and a PCB-level SI /
 * PDN / EMC analytical toolkit. It does not replace Virtuoso, IC Compiler, or
 * PrimeTime for tape-out. The comparison is honest about that gap, and focuses
 * instead on where Kerf serves silicon teams upstream (early design / pre-
 * silicon validation) or downstream (package / board design alongside chip
 * layout).
 */
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
/* Inline meta (no compareMeta entry needed for new slugs)                    */
/* -------------------------------------------------------------------------- */

const meta = {
  title: 'Kerf vs Cadence / Synopsys — silicon EDA compared',
  description:
    'Cadence and Synopsys own chip tape-out. See where Kerf fits for ' +
    'early silicon design, GDS-II interop, PCB co-design, and LLM-native workflows.',
  canonical: 'https://kerf.sh/compare/cadence-synopsys',
  ogImage: 'https://kerf.sh/og/compare-cadence-synopsys.png',
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Kerf vs Cadence / Synopsys — silicon EDA compared',
    description:
      'Cadence and Synopsys own chip tape-out. See where Kerf fits for ' +
      'early silicon design, GDS-II interop, PCB co-design, and LLM-native workflows.',
    url: 'https://kerf.sh/compare/cadence-synopsys',
    image: 'https://kerf.sh/og/compare-cadence-synopsys.png',
    publisher: { '@type': 'Organization', name: 'Kerf', url: 'https://kerf.sh' },
  }),
}

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                              */
/* -------------------------------------------------------------------------- */

const TABLE = [
  /* ── Licensing & cost ─────────────────────────────────────────────────── */
  {
    group: 'Licensing & cost',
    feature: 'License',
    competitor: `${WEAK} Proprietary; NDA-gated PDK access`,
    kerf: `${GOOD} MIT open-core (permissive)`,
  },
  {
    group: 'Licensing & cost',
    feature: 'Cost',
    competitor: `${WEAK} Six-figure USD/yr per seat per tool`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted`,
  },
  {
    group: 'Licensing & cost',
    feature: 'OS / platform',
    competitor: `${WEAK} Linux + Windows (no browser)`,
    kerf: `${GOOD} Browser + single-binary (Win/macOS/Linux)`,
  },
  {
    group: 'Licensing & cost',
    feature: 'Access model',
    competitor: `${WEAK} Enterprise contract + license server`,
    kerf: `${GOOD} Free local install; hosted SaaS; kerf_byo API key`,
  },

  /* ── Schematic capture ─────────────────────────────────────────────────── */
  {
    group: 'Schematic capture',
    feature: 'Analog / mixed-signal schematic',
    competitor: `${GOOD} Virtuoso Schematic Editor (industry standard)`,
    kerf: `${WEAK} SPICE netlist flow; no custom analog symbol env`,
  },
  {
    group: 'Schematic capture',
    feature: 'Digital RTL / block diagram',
    competitor: `${GOOD} Genus / DC Explorer — RTL-to-netlist`,
    kerf: `${GAP} No RTL synthesis`,
  },
  {
    group: 'Schematic capture',
    feature: 'ERC',
    competitor: `${GOOD} Virtuoso ERC + PDK design rules`,
    kerf: `${GOOD} ERC + IPC-2221B presets (board-level)`,
  },

  /* ── Simulation ────────────────────────────────────────────────────────── */
  {
    group: 'Simulation',
    feature: 'SPICE simulation',
    competitor: `${GOOD} Spectre (Cadence) / HSPICE (Synopsys) — industry gold standard`,
    kerf: `${GOOD} SPICE + model library + Monte-Carlo corner runs`,
  },
  {
    group: 'Simulation',
    feature: 'Timing / STA',
    competitor: `${GOOD} PrimeTime / Tempus — gold-standard static timing`,
    kerf: `${GAP} No gate-level STA`,
  },
  {
    group: 'Simulation',
    feature: 'Power / IR drop',
    competitor: `${GOOD} Voltus / RedHawk — chip-level power analysis`,
    kerf: `${GAP} Board-level PDN wizard only`,
  },
  {
    group: 'Simulation',
    feature: 'Monte-Carlo / corners',
    competitor: `${GOOD} Spectre APS + Virtuoso ADE XL corner sweeps`,
    kerf: `${GOOD} sim_corner — min/typ/max + Monte-Carlo yield estimate`,
  },

  /* ── Layout ────────────────────────────────────────────────────────────── */
  {
    group: 'Layout',
    feature: 'Analog custom layout (full-custom)',
    competitor: `${GOOD} Virtuoso Layout Suite — industry reference`,
    kerf: `${GAP} No full-custom IC layout editor`,
  },
  {
    group: 'Layout',
    feature: 'Place-and-route (digital)',
    competitor: `${GOOD} Innovus (Cadence) / IC Compiler II (Synopsys)`,
    kerf: `${GAP} No digital P&R`,
  },
  {
    group: 'Layout',
    feature: 'GDS-II import / export',
    competitor: `${GOOD} Native GDS-II for tape-out`,
    kerf: `${GOOD} GDS-II import/export — interop with foundry data`,
  },
  {
    group: 'Layout',
    feature: 'PCB layout (board-level)',
    competitor: `${WEAK} Allegro PCB (separate Cadence product)`,
    kerf: `${GOOD} Integrated PCB schematic + routing + DRC`,
  },

  /* ── Verification & sign-off ───────────────────────────────────────────── */
  {
    group: 'Verification & sign-off',
    feature: 'DRC / LVS (foundry rule deck)',
    competitor: `${GOOD} Calibre (Mentor/Siemens) / Pegasus — sign-off DRC/LVS`,
    kerf: `${GAP} No foundry-rule-deck DRC/LVS`,
  },
  {
    group: 'Verification & sign-off',
    feature: 'Formal verification',
    competitor: `${GOOD} Formality (Synopsys) / JasperGold (Cadence)`,
    kerf: `${GAP} No formal verification`,
  },
  {
    group: 'Verification & sign-off',
    feature: 'Pre-compliance SI / EMC (PCB)',
    competitor: `${WEAK} Not the scope of IC EDA tools`,
    kerf: `${GOOD} si_eye_wizard / emc_wizard / pdn_wizard (analytical, board-level)`,
  },

  /* ── Interop ───────────────────────────────────────────────────────────── */
  {
    group: 'Interoperability',
    feature: 'GDS-II / OASIS',
    competitor: `${GOOD} Both tools read/write GDS-II and OASIS natively`,
    kerf: `${GOOD} GDS-II import/export; OASIS via conversion`,
  },
  {
    group: 'Interoperability',
    feature: 'SPICE netlist (.sp / .spi)',
    competitor: `${GOOD} Both read foundry SPICE models`,
    kerf: `${GOOD} SPICE netlist import + model library`,
  },
  {
    group: 'Interoperability',
    feature: 'STEP / mechanical co-design',
    competitor: `${WEAK} Allegro IDF / STEP (separate flow)`,
    kerf: `${GOOD} STEP B-rep + IDF MCAD bridge in same workspace`,
  },

  /* ── Ecosystem & AI ───────────────────────────────────────────────────── */
  {
    group: 'Ecosystem & AI',
    feature: 'Chat / LLM editing',
    competitor: `${GAP} None (as of 2026)`,
    kerf: `${GOOD} Chat-native — edits circuit source per turn, doc-search backed`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Scripting / automation',
    competitor: `${GOOD} SKILL (Cadence) / Tcl — deep in-process APIs`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC from your machine`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Community / support',
    competitor: `${GOOD} Dedicated FAE, support contracts, training programs`,
    kerf: `${WEAK} Early-stage community; GitHub issues`,
  },
]

/* -------------------------------------------------------------------------- */
/* Interop callout                                                             */
/* -------------------------------------------------------------------------- */

function InteropCallout() {
  return (
    <aside
      aria-label="GDS-II and SPICE interoperability"
      className="mb-10 rounded-xl border border-kerf-300/30 bg-kerf-300/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-kerf-200 mb-1">
        Interop story — GDS-II and SPICE as the common language
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        Kerf reads and writes{' '}
        <strong className="text-ink-100">GDS-II</strong> — the foundry
        interchange format both Cadence and Synopsys tools produce. SPICE
        netlists (.sp / .spi) import directly; foundry model libraries load
        via the built-in model library interface. This means Kerf can sit
        alongside a tape-out flow for early-stage exploration, package /
        board co-design, or SPICE corner analysis — without replacing the
        sign-off tools.
      </p>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* Scope callout                                                               */
/* -------------------------------------------------------------------------- */

function ScopeCallout() {
  return (
    <aside
      aria-label="Scope disclaimer"
      className="mb-10 rounded-xl border border-amber-500/30 bg-amber-500/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-amber-200 mb-1">
        Scope — Kerf does not replace tape-out EDA
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        Cadence Virtuoso / Innovus and Synopsys Design Compiler / IC Compiler
        II are the tools teams use to tape out silicon. Kerf does not have a
        full-custom IC layout editor, a digital place-and-route engine, a
        static timing analyser, or a foundry-rule-deck DRC/LVS engine. If your
        job is taping out a chip, you need one of these platforms. Where Kerf
        fits is upstream (SPICE corner analysis, early schematic exploration)
        and at the board / package boundary (PCB design, STEP co-design, SI /
        PDN / EMC pre-compliance) — alongside, not instead of, a Cadence or
        Synopsys flow.
      </p>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* Page component                                                              */
/* -------------------------------------------------------------------------- */

export default function KerfVsCadenceSynopsysPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        aria-label="Kerf vs Cadence and Synopsys comparison"
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
      >
        <Breadcrumb />

        {/* Hero */}
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs Cadence / Synopsys
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Cadence (Virtuoso, Innovus, Genus, Spectre) and Synopsys (Design
            Compiler, IC Compiler II, PrimeTime, VCS) are the dominant
            proprietary EDA platforms for silicon tape-out. Both are decades
            old, deeply validated against foundry PDKs, and priced at six
            figures per seat per year. Kerf is in a different cost bracket and
            scope category — but it does share GDS-II interop, a SPICE netlist
            flow, and Monte-Carlo corner analysis, and it fills the board /
            package design and pre-silicon exploration space that neither
            Cadence nor Synopsys makes affordable for small teams.
          </p>
        </header>

        <ScopeCallout />

        {/* Where Cadence / Synopsys is strong */}
        <Section title="Where Cadence and Synopsys are strong">
          <ul className="flex flex-col gap-3" aria-label="Cadence and Synopsys strengths">
            <Li>
              <strong className="text-ink-100">Gold-standard tape-out flow.</strong>{' '}
              Virtuoso, Innovus, Design Compiler, and IC Compiler II are the
              tools every major foundry and fabless team uses from RTL to GDSII.
              The sign-off ecosystem (PrimeTime, Voltus, Calibre) is trusted
              for production tape-out at every node.
            </Li>
            <Li>
              <strong className="text-ink-100">Spectre and HSPICE simulation depth.</strong>{' '}
              Cadence Spectre and Synopsys HSPICE are the industry simulation
              references for analog, RF, and mixed-signal circuits — handling
              foundry model complexity and convergence edge cases that simpler
              engines cannot.
            </Li>
            <Li>
              <strong className="text-ink-100">Foundry PDK integration.</strong>{' '}
              Both vendors ship validated design-kit integrations for TSMC,
              Samsung, GlobalFoundries, and others. PDK-aware DRC, LVS, and
              parasitic extraction are first-class.
            </Li>
            <Li>
              <strong className="text-ink-100">Static timing analysis (STA).</strong>{' '}
              PrimeTime and Tempus are the sign-off STA references. No open
              tool matches them for multi-corner, multi-mode analysis at
              advanced nodes.
            </Li>
            <Li>
              <strong className="text-ink-100">Enterprise support and FAE access.</strong>{' '}
              Dedicated field application engineers, training programs, and
              long-term support contracts give teams a guaranteed escalation path
              for production-critical flows.
            </Li>
            <Li>
              <strong className="text-ink-100">Decades of validation.</strong>{' '}
              Both platforms have been shaped by every major process node from
              micron to 2 nm. The edge-case handling depth is unmatched.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf wins */}
        <Section title="Where Kerf wins">
          <ul className="flex flex-col gap-3" aria-label="Kerf differentiators">
            <Li>
              <strong className="text-ink-100">GDS-II interop at zero cost.</strong>{' '}
              Kerf reads and writes GDS-II natively — the foundry interchange
              format. For teams reviewing layout data, writing tooling that
              manipulates GDSII, or passing data between tools, there is no
              per-seat cost.
            </Li>
            <Li>
              <strong className="text-ink-100">SPICE + Monte-Carlo corners out of the box.</strong>{' '}
              sim_corner sweeps min/typ/max and Monte-Carlo parameter variants
              automatically and reports worst-case yield estimates — useful for
              early-stage design-space exploration before committing to a full
              Spectre/HSPICE run.
            </Li>
            <Li>
              <strong className="text-ink-100">PCB and package co-design in the same tool.</strong>{' '}
              Integrated schematic capture, push-and-shove PCB routing, IDF
              MCAD bridge, and STEP co-design are all in-box. Cadence covers
              this with Allegro (a separate product and contract); Synopsys
              does not natively offer a PCB tool.
            </Li>
            <Li>
              <strong className="text-ink-100">Board-level SI / PDN / EMC pre-compliance.</strong>{' '}
              Kerf's analytical si_eye_wizard, pdn_wizard, and emc_wizard cover
              the board-boundary concerns that IC EDA tools do not address.
              For early-stage risk triage on a board receiving your chip, these
              are useful before a full-wave simulation run.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a schematic change or simulation setup in plain language;
              the LLM edits the circuit source directly, backed by live
              doc-search. No equivalent exists in either Cadence or Synopsys
              products as of 2026.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, free local install.</strong>{' '}
              The core is permissive MIT. A single binary installs via brew or
              curl — no license server, no NDA, no contract. Accessible to
              independent researchers, hardware startups, and university labs.
            </Li>
            <Li>
              <strong className="text-ink-100">Mechanical CAD co-resident.</strong>{' '}
              B-rep parametric CAD, constraint sketcher, sheet metal, and GD&T
              drawings are in the same workspace as the electronics tools. This
              matters for chip package, heatsink, and enclosure co-design.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Cadence and Synopsys lead">
          <ul className="flex flex-col gap-3" aria-label="Areas where Cadence and Synopsys lead">
            <Li>
              <strong className="text-ink-100">No full-custom IC layout.</strong>{' '}
              Kerf has no Virtuoso-equivalent layout editor — no device-level
              transistor layout, no via-stacking, no latch-up prevention
              tooling. This is the core of what Cadence Virtuoso does.
            </Li>
            <Li>
              <strong className="text-ink-100">No digital place-and-route.</strong>{' '}
              Innovus and IC Compiler II handle millions of cells with physical
              legality constraints tied to the foundry tech file. Kerf has no
              equivalent.
            </Li>
            <Li>
              <strong className="text-ink-100">No static timing analysis.</strong>{' '}
              PrimeTime and Tempus are non-negotiable for tape-out sign-off.
              Kerf has no gate-level timing engine.
            </Li>
            <Li>
              <strong className="text-ink-100">No foundry DRC / LVS.</strong>{' '}
              Calibre-class foundry rule deck DRC and LVS are required for tape-
              out; Kerf's DRC is board-level (IPC-2221B presets) only.
            </Li>
            <Li>
              <strong className="text-ink-100">Simulation depth gap.</strong>{' '}
              Spectre and HSPICE handle analog convergence, RF noise, and
              parasitic-aware simulation at a depth Kerf's SPICE engine does
              not match. For sign-off analog simulation, use the vendor tools.
            </Li>
            <Li>
              <strong className="text-ink-100">No enterprise support or SLA.</strong>{' '}
              Kerf has no FAE program or support contract. Early-stage community
              only.
            </Li>
          </ul>
        </Section>

        <InteropCallout />

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="Cadence / Synopsys" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
