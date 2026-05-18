/**
 * /compare/kicad — Kerf vs KiCad
 *
 * Web-grounded (last reviewed 2026-05-18). KiCad 10.0 shipped March 2026
 * (10.0.2 in May 2026): GPL v3, fully free, cross-platform. It now natively
 * exports IPC-2581 *and* ODB++, gained an overhauled track-tuning system with
 * time-domain constraints, design variants, a graphical DRC rule editor, and
 * Allegro/PADS/gEDA importers. ngspice is built in. KiCad's depth and
 * community on the pure-PCB side are formidable.
 *
 * Kerf covers much of the same electronics ground and adds a unified
 * mechanical CAD workspace, a simulation triad (Monte-Carlo SPICE corner
 * analysis, 2-D finite-difference thermal, SI/PDN/EMC pre-compliance
 * wizards), chat-native editing, and the kerf-sdk — but does not match
 * KiCad's EDA maturity, library breadth, or community today.
 *
 * Simulation honesty note: Kerf's SI/EMC/PDN wizards use reduced-order
 * analytical models, not full-wave EM solvers. They are useful for early-stage
 * risk assessment; they are NOT a substitute for ANSYS HFSS, Allegro PI/SI,
 * or an accredited compliance test lab.
 */
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import { makeCompareMeta } from './compareMeta.js'
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

const meta = makeCompareMeta('kicad')

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                               */
/* -------------------------------------------------------------------------- */

const TABLE = [
  /* ── Licensing & platform ─────────────────────────────────────────────── */
  { group: 'Licensing & platform', feature: 'License',
    competitor: `${GOOD} GPL v3 (free, copyleft)`,
    kerf: `${GOOD} MIT open-core (permissive)` },
  { group: 'Licensing & platform', feature: 'Cost',
    competitor: `${GOOD} Free, no restrictions, no seats`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted` },
  { group: 'Licensing & platform', feature: 'Platform',
    competitor: `${GOOD} Win / macOS / Linux desktop`,
    kerf: `${GOOD} Browser (hosted) + single-binary local` },
  { group: 'Licensing & platform', feature: 'Maturity',
    competitor: `${GOOD} v10 (2026), long lineage`,
    kerf: `${WEAK} Early-stage, < 2 yr public` },

  /* ── Schematic capture ─────────────────────────────────────────────────── */
  { group: 'Schematic capture', feature: 'Hierarchical schematic',
    competitor: `${GOOD} Eeschema — dozens of sheets, shared pins`,
    kerf: `${GOOD} Hierarchical schematic + sheet borders` },
  { group: 'Schematic capture', feature: 'Buses / net classes',
    competitor: `${GOOD} Buses, net classes, aggregate classes`,
    kerf: `${GOOD} Buses, net classes` },
  { group: 'Schematic capture', feature: 'ERC',
    competitor: `${GOOD} Mature ERC + per-violation exclusions w/ comments`,
    kerf: `${GOOD} ERC + configurable severity levels` },
  { group: 'Schematic capture', feature: 'SPICE simulation',
    competitor: `${GOOD} ngspice — AC/DC/transient, built-in plotter`,
    kerf: `${GOOD} SPICE + model library + Monte-Carlo corner runs` },
  { group: 'Schematic capture', feature: 'Pin assignment / swap',
    competitor: `${GOOD} Gate/pin swap in Eeschema`,
    kerf: `${GOOD} Pin-swap via DRC + netlist re-check` },

  /* ── PCB layout ────────────────────────────────────────────────────────── */
  { group: 'PCB layout', feature: 'Interactive routing',
    competitor: `${GOOD} Pcbnew push & shove (mature)`,
    kerf: `${GOOD} Shove router` },
  { group: 'PCB layout', feature: 'Length / skew tuning',
    competitor: `${GOOD} Overhauled tuner, time-domain constraints (v10)`,
    kerf: `${GOOD} Length tuning` },
  { group: 'PCB layout', feature: 'Differential pairs',
    competitor: `${GOOD} Diff-pair routing + interactive tuning`,
    kerf: `${WEAK} Length tuning; diff-pair workflow lighter` },
  { group: 'PCB layout', feature: 'Via stitching / copper pour',
    competitor: `${GOOD} Stitching vias, keepouts, zones/pours`,
    kerf: `${GOOD} Via stitching + copper pour` },
  { group: 'PCB layout', feature: 'Autorouter',
    competitor: `${WEAK} Freerouting (external plugin)`,
    kerf: `${GOOD} FreeRouting integrated` },
  { group: 'PCB layout', feature: 'DRC',
    competitor: `${GOOD} Graphical rule editor + custom expressions (v10)`,
    kerf: `${GOOD} DRC + IPC-2221B manufacturing presets` },
  { group: 'PCB layout', feature: 'Stackup / impedance',
    competitor: `${GOOD} Stackup editor + impedance calculator`,
    kerf: `${GOOD} Flex stackup + impedance via SI wizard` },

  /* ── High-speed / pre-compliance (analytical) ──────────────────────────── */
  { group: 'High-speed / pre-compliance', feature: 'Signal integrity (SI)',
    competitor: `${WEAK} Limited; external tools recommended`,
    kerf: `${GOOD} si_eye_wizard — eye-diagram estimate, crosstalk budget (analytical)` },
  { group: 'High-speed / pre-compliance', feature: 'Power-delivery network (PDN)',
    competitor: `${WEAK} Basic decap guidelines; no automated PDN analysis`,
    kerf: `${GOOD} pdn_wizard — target impedance, decap placement (analytical)` },
  { group: 'High-speed / pre-compliance', feature: 'EMC / radiated emissions',
    competitor: `${WEAK} No EMC analysis`,
    kerf: `${GOOD} emc_wizard — FCC §15.109 / CISPR 32 Class B 10 m-equivalent (analytical, reduced-order)` },
  { group: 'High-speed / pre-compliance', feature: 'IBIS model import',
    competitor: `${WEAK} Not natively supported`,
    kerf: `${GOOD} ibis_reader — I/O buffer model import for SI analysis` },
  { group: 'High-speed / pre-compliance', feature: 'RF / S-parameters',
    competitor: `${WEAK} Third-party plugins`,
    kerf: `${GOOD} scikit-rf integration — S-parameter analysis, port match` },
  { group: 'High-speed / pre-compliance', feature: 'Full-wave EM solver',
    competitor: `${GAP} Not included`,
    kerf: `${GAP} Not included — see simulation scope note` },

  /* ── Thermal analysis ───────────────────────────────────────────────────── */
  { group: 'Thermal analysis', feature: 'Board-level thermal',
    competitor: `${WEAK} No built-in thermal simulation`,
    kerf: `${GOOD} thermal_board — 2-D finite-difference steady-state heat map` },
  { group: 'Thermal analysis', feature: 'Component junction temp',
    competitor: `${WEAK} Manual θJA calculations`,
    kerf: `${GOOD} Junction temperature estimate from θJA + dissipation` },

  /* ── SPICE / simulation depth ───────────────────────────────────────────── */
  { group: 'SPICE & simulation', feature: 'SPICE corner / Monte-Carlo',
    competitor: `${WEAK} ngspice; single nominal run; no automated corners`,
    kerf: `${GOOD} sim_corner — min/typ/max + Monte-Carlo yield estimate` },
  { group: 'SPICE & simulation', feature: 'Simulation model library',
    competitor: `${GOOD} ngspice + community model files`,
    kerf: `${GOOD} Built-in model library; import SPICE .lib` },

  /* ── Fabrication output ─────────────────────────────────────────────────── */
  { group: 'Fabrication output', feature: 'Gerber / Excellon / P&P',
    competitor: `${GOOD} Full plot suite`,
    kerf: `${GOOD} Gerber / Excellon / P&P` },
  { group: 'Fabrication output', feature: 'IPC-2581',
    competitor: `${GOOD} Native export (v10)`,
    kerf: `${GOOD} IPC-2581 fab pack` },
  { group: 'Fabrication output', feature: 'ODB++',
    competitor: `${GOOD} Native export, single archive (v10)`,
    kerf: `${GOOD} ODB++ export` },
  { group: 'Fabrication output', feature: 'IPC-D-356A netlist',
    competitor: `${GOOD} KiCad / OrCAD / PADS / CSV / IPC-D-356A`,
    kerf: `${GOOD} IPC-D-356A + KiCad/OrCAD/PADS/CSV` },
  { group: 'Fabrication output', feature: 'QIF inspection data',
    competitor: `${GAP} Not supported`,
    kerf: `${GOOD} qif_reader — ISO 23952 QIF file import/export` },
  { group: 'Fabrication output', feature: 'Variants / DNP',
    competitor: `${GOOD} Design variants (v10)`,
    kerf: `${GOOD} Assembly variants (DNP)` },
  { group: 'Fabrication output', feature: 'Panelisation',
    competitor: `${WEAK} KiKit (community plugin)`,
    kerf: `${GOOD} Panelize built in` },
  { group: 'Fabrication output', feature: 'Test point / fixture',
    competitor: `${WEAK} Manual / scripted`,
    kerf: `${GOOD} Test-point and fixture tooling` },
  { group: 'Fabrication output', feature: 'BOM cost / DFM',
    competitor: `${WEAK} BOM export; cost via external`,
    kerf: `${GOOD} BOM cost + DFM checks` },

  /* ── MCAD / cross-domain ────────────────────────────────────────────────── */
  { group: 'MCAD & cross-domain', feature: 'Board STEP / IDF',
    competitor: `${GOOD} STEP export + IDF`,
    kerf: `${GOOD} IDF MCAD bridge + board STEP (valid B-rep kernel)` },
  { group: 'MCAD & cross-domain', feature: 'Mechanical CAD (same tool)',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Full B-rep, sketcher, drawings, sheet metal — same workspace` },
  { group: 'MCAD & cross-domain', feature: '3D viewer',
    competitor: `${GOOD} Built-in 3D viewer (raytraced)`,
    kerf: `${GOOD} Real-time 3D board view + mechanical overlay` },

  /* ── Ecosystem & SDK ────────────────────────────────────────────────────── */
  { group: 'Ecosystem & SDK', feature: 'Component libraries',
    competitor: `${GOOD} Huge official + community libs (v10 added 952 symbols)`,
    kerf: `${WEAK} Library mgmt + distributors; smaller catalog` },
  { group: 'Ecosystem & SDK', feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits circuit source per turn, doc-search backed` },
  { group: 'Ecosystem & SDK', feature: 'Scripting',
    competitor: `${GOOD} Python (in-process) + IPC socket API`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC from your machine` },
  { group: 'Ecosystem & SDK', feature: 'Importers',
    competitor: `${GOOD} Allegro / PADS / gEDA / Eagle (v10)`,
    kerf: `${GOOD} Eagle / Allegro / PADS / gEDA / KiCad import` },
  { group: 'Ecosystem & SDK', feature: 'Community & docs',
    competitor: `${GOOD} Very large, well-documented`,
    kerf: `${WEAK} Early-stage, growing` },
]

/* -------------------------------------------------------------------------- */
/* Simulation scope callout                                                     */
/* -------------------------------------------------------------------------- */

function SimHonestyCallout() {
  return (
    <aside
      aria-label="Simulation scope and limitations"
      className="mb-10 rounded-xl border border-kerf-300/30 bg-kerf-300/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-kerf-200 mb-1">
        Simulation scope — what Kerf does and does not claim
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        Kerf's SI, EMC, and PDN analysis tools use{' '}
        <strong className="text-ink-100">reduced-order analytical models</strong>{' '}
        — transmission-line equations, IBIS-based edge-rate estimates, and PDN
        impedance curves. The EMC wizard outputs an FCC §15.109 / CISPR 32 Class
        B 10&nbsp;m-equivalent emission estimate. These are useful for early-stage
        risk triage and design-rule feedback, but they are{' '}
        <strong className="text-ink-100">not</strong> a substitute for full-wave
        EM solvers (ANSYS HFSS, CST, etc.), power-integrity platforms, or an
        accredited pre-compliance / compliance test lab. Neither is KiCad — it
        does not perform EMC analysis at all.
      </p>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* Migration section                                                            */
/* -------------------------------------------------------------------------- */

function MigrationSection() {
  return (
    <Section title="Migrating from KiCad — what to expect">
      <div className="flex flex-col gap-6">
        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            Schematic capture (Eeschema → Kerf schematic)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            KiCad schematic files (.kicad_sch) import via Kerf's KiCad-oriented
            import path. Hierarchical sheets, buses, net classes, and component
            references carry across. Power symbols and ERC exclusions require a
            review pass. Kerf's ERC rule set overlaps substantially with
            KiCad's but uses configurable severity levels rather than KiCad's
            per-pin type matrix — expect a handful of new or suppressed
            violations on first open.
          </p>
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            PCB layout (Pcbnew → Kerf PCB)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            Board outline, copper pours, via stitching, and most routing import
            cleanly. KiCad 10's custom DRC expression rules do not translate
            directly — remap them to Kerf's IPC-2221B presets or custom
            clearance rules. Diff-pair tuning constraints need re-entry; Kerf's
            diff-pair workflow is lighter than Pcbnew's interactive tuner.
            Stackup parameters (layer count, dielectric, Cu weight) import and
            feed the SI wizard automatically.
          </p>
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            SPICE simulation (ngspice → Kerf SPICE + sim_corner)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            SPICE netlist (.sp) and subcircuit (.lib) files import directly.
            Transient, AC, and DC sweep analyses port without changes. To use
            sim_corner, annotate device models with min/typ/max parameter
            variants — Kerf sweeps them automatically and reports worst-case
            yield. ngspice's custom plotting scripts do not carry across; use
            Kerf's built-in waveform viewer.
          </p>
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            Fabrication output (KiCad plot → Kerf fab pack)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            Gerber, Excellon drill, and pick-and-place CSV regenerate from
            Kerf's fab pack — no manual re-configuration needed. IPC-2581 and
            ODB++ export natively. If you were using KiKit for panelisation,
            switch to Kerf's built-in panelise tool; common panel configs
            (2×2, V-score, mouse-bite) are supported without scripting.
          </p>
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            Component libraries (KiCad official → Kerf library)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            Kerf's component catalog is substantially smaller than KiCad's
            official + community library. For commodity passives and major ICs,
            coverage is good; for long-tail parts, Kerf's distributor-linked
            BOM tool pulls live stock and datasheet links. The kerf-sdk lets
            you script custom symbol/footprint generation from a datasheet.
          </p>
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900/30 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink-100 mb-2">
            Python scripting (KiCad Python IPC → kerf-sdk)
          </h3>
          <p className="text-sm text-ink-300 leading-relaxed">
            KiCad exposes an in-process Python console and an IPC socket API.
            Kerf's kerf-sdk is out-of-process over HTTP/JSON-RPC from your own
            machine. Common automation tasks — generating footprints from a
            spreadsheet, exporting drill reports, running DRC headlessly — all
            have direct kerf-sdk equivalents. The same interface the LLM uses
            internally is the one your scripts call.
          </p>
        </div>
      </div>
    </Section>
  )
}

/* -------------------------------------------------------------------------- */
/* Page component                                                               */
/* -------------------------------------------------------------------------- */

export default function KicadPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        aria-label="Kerf vs KiCad comparison"
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
      >
        <Breadcrumb />

        {/* Hero */}
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs KiCad
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            KiCad is the reference open-source EDA suite. Version 10 (March
            2026) is genuinely deep: native IPC-2581 and ODB++ output, an
            overhauled track tuner with time-domain constraints, design
            variants, a graphical DRC rule editor, and a very large community.
            Kerf covers much of the same electronics ground and adds a unified
            mechanical CAD workspace, a simulation triad (Monte-Carlo SPICE
            corners, 2-D board thermal, and analytical SI/PDN/EMC pre-compliance
            wizards), and chat-driven editing — but KiCad's pure-PCB maturity
            and library breadth are hard to match today.
          </p>
        </header>

        {/* Where KiCad is strong */}
        <Section title="Where KiCad is strong">
          <ul className="flex flex-col gap-3" aria-label="KiCad strengths">
            <Li>
              <strong className="text-ink-100">Deep, mature EDA tooling.</strong>{' '}
              Eeschema and Pcbnew have been refined over many years with an
              enormous community validating edge cases on real boards across
              every industry.
            </Li>
            <Li>
              <strong className="text-ink-100">Best-in-class free DRC.</strong>{' '}
              KiCad 10 added a graphical DRC rule editor on top of its custom
              expression language — fine-grained, professional design-rule
              control with per-violation exclusions that exceeds Kerf's
              IPC-2221B presets.
            </Li>
            <Li>
              <strong className="text-ink-100">Native IPC-2581 and ODB++.</strong>{' '}
              Both modern fabrication interchange formats export natively,
              including a single ODB++ archive — no plugins or post-processing
              required.
            </Li>
            <Li>
              <strong className="text-ink-100">Overhauled high-speed tuning.</strong>{' '}
              Version 10's rewritten track-tuning system supports time-domain
              constraints and per-layer tuning profiles for serious high-speed
              differential and multi-gigabit work.
            </Li>
            <Li>
              <strong className="text-ink-100">Integrated ngspice.</strong>{' '}
              AC, DC-sweep, and transient simulation with a built-in plotter and
              mature model libraries — verify analogue behaviour before layout
              without a separate simulator.
            </Li>
            <Li>
              <strong className="text-ink-100">Vast component libraries.</strong>{' '}
              Tens of thousands of official symbols and footprints, plus a large
              community contribution stream (v10 alone added 952 symbols).
              Long-tail parts are almost always present.
            </Li>
            <Li>
              <strong className="text-ink-100">Strong importers.</strong>{' '}
              Allegro, PADS, gEDA/Lepton, and Eagle import eases migration off
              proprietary platforms — no equivalent in Kerf today.
            </Li>
            <Li>
              <strong className="text-ink-100">Completely free and offline.</strong>{' '}
              GPL v3, no seat limits, no commercial restrictions, fully offline,
              cross-platform. The ideal cost structure for open-hardware
              projects.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf differs */}
        <Section title="Where Kerf differs">
          <ul className="flex flex-col gap-3" aria-label="Kerf differentiators">
            <Li>
              <strong className="text-ink-100">Mechanical + electronics in one workspace.</strong>{' '}
              B-rep CAD, sketcher v2, drawings, sheet metal, and the full EDA
              stack are co-resident. The kernel produces valid B-rep geometry,
              which feeds 3D board STEP export cleanly without a separate MCAD
              bridge step.
            </Li>
            <Li>
              <strong className="text-ink-100">Simulation triad.</strong>{' '}
              Three capabilities KiCad does not ship: (1){' '}
              <strong className="text-ink-200">sim_corner</strong> runs
              min/typ/max and Monte-Carlo yield estimates on SPICE circuits;
              (2){' '}
              <strong className="text-ink-200">thermal_board</strong> computes
              a 2-D finite-difference steady-state heat map of the populated
              board; (3) the{' '}
              <strong className="text-ink-200">si_eye_wizard</strong>,{' '}
              <strong className="text-ink-200">pdn_wizard</strong>, and{' '}
              <strong className="text-ink-200">emc_wizard</strong> give
              analytical SI/PDN/EMC pre-compliance estimates. All are
              reduced-order models — useful for early-stage triage, not
              a full EM solver replacement.
            </Li>
            <Li>
              <strong className="text-ink-100">IBIS model import.</strong>{' '}
              ibis_reader ingests I/O buffer models for edge-rate-aware SI
              analysis. KiCad has no native IBIS support.
            </Li>
            <Li>
              <strong className="text-ink-100">QIF inspection data (ISO 23952).</strong>{' '}
              qif_reader imports and exports Quality Information Framework files
              — useful for boards going through CMM or automated optical
              inspection where the fab requires QIF hand-off. KiCad does not
              support QIF.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a schematic change, routing constraint, or DRC rule in
              plain language; the LLM edits the circuit source directly, backed
              by live doc-search so it does not invent API surface that does not
              exist.
            </Li>
            <Li>
              <strong className="text-ink-100">RF built in.</strong>{' '}
              scikit-rf S-parameter analysis and port matching are first-class
              — a workflow KiCad addresses only via third-party plugins.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core + hosted.</strong>{' '}
              The core is permissive MIT (vs KiCad's copyleft GPL), with a
              hosted browser option and a single-binary local install via brew
              or curl.
            </Li>
            <Li>
              <strong className="text-ink-100">Cost / DFM and fixtures built in.</strong>{' '}
              BOM cost, DFM checks, panelise, and test-point/fixture tooling
              ship in-box rather than as community plugins.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul className="flex flex-col gap-3" aria-label="Areas where KiCad leads">
            <Li>
              <strong className="text-ink-100">KiCad's DRC is more powerful.</strong>{' '}
              Kerf covers IPC-2221B presets and standard clearance rules;
              KiCad 10's custom-expression language plus graphical rule editor
              give expert teams considerably more per-net and per-layer control.
            </Li>
            <Li>
              <strong className="text-ink-100">Much smaller component library.</strong>{' '}
              KiCad's official + community libraries dwarf Kerf's catalog today.
              Long-tail industrial and specialist parts are frequently missing.
            </Li>
            <Li>
              <strong className="text-ink-100">SPICE depth is partial.</strong>{' '}
              Kerf's SPICE + model lib is functional and sim_corner adds corner
              analysis, but ngspice's sweep syntax, convergence aids, and
              plotter polish are more mature.
            </Li>
            <Li>
              <strong className="text-ink-100">Diff-pair workflow is lighter.</strong>{' '}
              KiCad's interactive differential-pair routing and time-domain
              tuning are more refined than Kerf's today.
            </Li>
            <Li>
              <strong className="text-ink-100">No full-wave EM solver.</strong>{' '}
              Kerf's EMC / SI tools are analytical, not full-wave. For
              post-layout verification at multi-GHz frequencies, external
              full-wave tooling remains essential — as it does with KiCad.
            </Li>
            <Li>
              <strong className="text-ink-100">Far less community documentation.</strong>{' '}
              KiCad has years of tutorials, forum answers, and videos; Kerf's
              community is early-stage.
            </Li>
            <Li>
              <strong className="text-ink-100">Importer maturity.</strong>{' '}
              Kerf now imports Eagle, Allegro, PADS, gEDA, and KiCad — the same
              set as KiCad 10 — but these importers are newer and may not handle
              all edge cases that KiCad&rsquo;s production-hardened importers do.
            </Li>
          </ul>
        </Section>

        {/* Simulation scope callout */}
        <SimHonestyCallout />

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="KiCad" />
          <TableFooter />
        </Section>

        {/* Migration notes */}
        <MigrationSection />

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
