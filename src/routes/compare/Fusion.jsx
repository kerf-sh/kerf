/**
 * /compare/fusion — Kerf vs Fusion 360
 *
 * Web-grounded (last reviewed 2026-05-18). Autodesk Fusion (formerly Fusion
 * 360) pioneered cloud-connected parametric CAD with integrated CAM, CAE,
 * and electronics. Commercial use is ~US$680/yr (~$85/mo); a restricted
 * free personal tier exists (must convert once non-commercial / >US$1,000
 * annual revenue); a startup programme is ~$150/3yr. Fusion Electronics is
 * the EAGLE-derived PCB workspace (standalone EAGLE end-of-life 2026-06-07),
 * with push & shove routing, base SPICE, and extension-gated signal
 * integrity / cooling. Generative design is cloud-based.
 *
 * Kerf is the closest peer to Fusion in shape — both cover multi-discipline
 * CAD/CAM/CAE/PCB in a single cloud-friendly workspace. Kerf's differentiators:
 * MIT open-core, chat-driven UX, no per-seat subscription, BYO LLM, a 40-module
 * jewelry domain, 620 analytic-oracle kernel tests, and in-box pre-compliance
 * simulation (SI/EMC/PDN/thermal) without extension gating.
 * Fusion's advantages: HSMWorks-lineage CAM, generative design, T-spline sculpt,
 * decades of vendor polish, and a massive community.
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

const meta = makeCompareMeta('fusion')

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                               */
/* -------------------------------------------------------------------------- */

const TABLE = [
  // Licensing & platform
  { group: 'Licensing & platform', feature: 'License',
    competitor: `${WEAK} Proprietary subscription`,
    kerf: `${GOOD} MIT open-core` },
  { group: 'Licensing & platform', feature: 'Cost',
    competitor: `${WEAK} ~US$680/yr (~$85/mo); startup ~$150/3yr`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted credits` },
  { group: 'Licensing & platform', feature: 'Free tier',
    competitor: `${WEAK} Personal-use only (non-commercial, <US$1k rev)`,
    kerf: `${GOOD} Full free local install, no revenue cap` },
  { group: 'Licensing & platform', feature: 'BYO LLM / model key',
    competitor: `${GAP} No — cloud LLM not user-configurable`,
    kerf: `${GOOD} BYO key (kerf_byo bucket) — use own Anthropic/OpenAI key` },
  { group: 'Licensing & platform', feature: 'Offline / self-host',
    competitor: `${WEAK} Limited offline; many features cloud-tied`,
    kerf: `${GOOD} Full offline: pip install 'kerf[server]' + kerf serve (BYO Postgres)` },
  { group: 'Licensing & platform', feature: 'Open source',
    competitor: `${GAP} Proprietary`,
    kerf: `${GOOD} MIT — full codebase on GitHub` },
  { group: 'Licensing & platform', feature: 'OS support',
    competitor: `${GOOD} Windows + macOS (desktop app)`,
    kerf: `${GOOD} Browser (hosted) + binary local on Win / macOS / Linux` },
  { group: 'Licensing & platform', feature: 'Maturity',
    competitor: `${GOOD} Millions of users, > 10 yr`,
    kerf: `${WEAK} Early-stage, < 2 yr public` },

  // Modeling
  { group: 'Modeling', feature: 'Parametric B-rep',
    competitor: `${GOOD} Timeline-based modelling (mature, HSMWorks lineage)`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/boss-with-draft` },
  { group: 'Modeling', feature: 'History DAG / persistent naming',
    competitor: `${GOOD} Timeline + direct edit; persistent references`,
    kerf: `${GOOD} Feature DAG + persistent face naming (Phase 4)` },
  { group: 'Modeling', feature: 'Constraint sketcher',
    competitor: `${GOOD} Full parametric sketcher`,
    kerf: `${GOOD} Sketcher v2 — all major constraints` },
  { group: 'Modeling', feature: 'Direct modeling',
    competitor: `${GOOD} Direct + parametric history`,
    kerf: `${WEAK} Feature-tree primary; limited direct editing` },
  { group: 'Modeling', feature: 'Sheet metal',
    competitor: `${GOOD} Full sheet-metal workspace`,
    kerf: `${GOOD} Flange + unfold + flat-pattern DXF` },
  { group: 'Modeling', feature: 'Freeform / T-spline sculpt',
    competitor: `${GOOD} Sculpt workspace (T-spline), industry-quality`,
    kerf: `${WEAK} NURBS Phase 4 (early); no T-spline sculpt authoring` },

  // Assemblies
  { group: 'Assemblies', feature: 'Joints / mates',
    competitor: `${GOOD} Full joint system (rigid, revolute, slider, etc.)`,
    kerf: `${GOOD} Full joint system — rigid/revolute/slider/cam/gear/pin-slot` },
  { group: 'Assemblies', feature: 'Motion study',
    competitor: `${GOOD} Motion + contact sets + interference detection`,
    kerf: `${GAP} Not yet` },

  // CAM / fabrication
  { group: 'CAM / fabrication', feature: '2.5 / 3-axis CAM',
    competitor: `${GOOD} HSMWorks-lineage CAM + verified simulation (mature)`,
    kerf: `${GOOD} 3-axis CAM + tool DB` },
  { group: 'CAM / fabrication', feature: 'Multi-axis CAM',
    competitor: `${GOOD} 4/5-axis (paid extension; HSMWorks pedigree)`,
    kerf: `${GOOD} 5-axis CAM 3+2` },
  { group: 'CAM / fabrication', feature: 'Additive / slicing',
    competitor: `${GOOD} Additive workspace`,
    kerf: `${GOOD} Slicing Tier 1` },

  // Simulation — mechanical
  { group: 'Simulation — mechanical', feature: 'FEM (static / thermal)',
    competitor: `${GOOD} Built-in (extension / cloud-metered)`,
    kerf: `${WEAK} Linear static + thermal + nonlinear plasticity; not full multi-physics parity` },
  { group: 'Simulation — mechanical', feature: 'Generative design',
    competitor: `${GOOD} Cloud topology optimisation (flagship feature)`,
    kerf: `${GAP} Roadmap; not shipped` },

  // Simulation — pre-compliance (electronics)
  { group: 'Simulation — pre-compliance', feature: 'Signal integrity (SI)',
    competitor: `${WEAK} Via paid Fusion extension`,
    kerf: `${GOOD} In-box SI: transmission-line, via stub, differential pair` },
  { group: 'Simulation — pre-compliance', feature: 'EMC / EMI analysis',
    competitor: `${WEAK} Extension-gated; basic`,
    kerf: `${GOOD} EMC pre-compliance: common-mode, return-path gap, slot antenna` },
  { group: 'Simulation — pre-compliance', feature: 'PDN analysis',
    competitor: `${WEAK} Extension-gated`,
    kerf: `${GOOD} PDN: decap placement, target impedance, plane resonance` },
  { group: 'Simulation — pre-compliance', feature: 'Thermal (PCB)',
    competitor: `${WEAK} Extension-gated cooling analysis`,
    kerf: `${GOOD} PCB thermal: copper pour, via thermal relief, hot-spot` },

  // Drawings
  { group: 'Drawings & docs', feature: '2D drawings',
    competitor: `${GOOD} Full drawing + annotations`,
    kerf: `${GOOD} Multi-sheet drawings` },
  { group: 'Drawings & docs', feature: 'GD&T',
    competitor: `${GOOD} ASME / ISO GD&T`,
    kerf: `${GOOD} ASME Y14.5 datum + tolerance framework` },

  // Electronics
  { group: 'Electronics', feature: 'Schematic + PCB',
    competitor: `${GOOD} Fusion Electronics (EAGLE-derived; EAGLE EOL 2026-06)`,
    kerf: `${GOOD} Hierarchical schematic + PCB layout` },
  { group: 'Electronics', feature: 'Routing',
    competitor: `${GOOD} Push & shove routing`,
    kerf: `${GOOD} Shove router + FreeRouting` },
  { group: 'Electronics', feature: 'SPICE / RF',
    competitor: `${WEAK} Base SPICE; RF / SI via paid extension`,
    kerf: `${GOOD} SPICE + model lib + scikit-rf RF` },
  { group: 'Electronics', feature: 'Fab output',
    competitor: `${GOOD} Gerber / NC / IPC outputs`,
    kerf: `${GOOD} Gerber / Excellon / IPC-2581 / ODB++ / IPC-D-356A` },
  { group: 'Electronics', feature: 'MCAD/ECAD bridge',
    competitor: `${GOOD} Native ECAD⇔MCAD live link`,
    kerf: `${GOOD} Co-resident; IDF + board STEP export` },
  { group: 'Electronics', feature: 'DRC + IPC-2221B presets',
    competitor: `${GOOD} DRC with design rules`,
    kerf: `${GOOD} DRC + manufacturing presets (IPC-2221B A/B/C)` },

  // Domain breadth
  { group: 'Domain breadth', feature: 'Jewelry tooling',
    competitor: `${GAP} Generic CAD only — no jewelry modules`,
    kerf: `${GOOD} 40-module jewelry suite: ring v4, gemstones v2 (30 cuts), settings, chain v2, findings, casting export` },
  { group: 'Domain breadth', feature: 'Architecture / IFC',
    competitor: `${GAP} Not an AEC tool`,
    kerf: `${WEAK} IFC Tier 2 import + structural grid` },

  // Kernel quality
  { group: 'Kernel quality', feature: 'Test coverage',
    competitor: `${GOOD} Mature, field-tested across millions of files`,
    kerf: `${GOOD} 620 analytic-oracle kernel tests (exact closed-form references)` },

  // Collaboration
  { group: 'Collaboration', feature: 'Multi-user cloud edit',
    competitor: `${GOOD} Cloud storage + collab baked in`,
    kerf: `${GOOD} Cloud hosted multi-user + cloud-git project sync` },

  // Ecosystem & SDK
  { group: 'Ecosystem & SDK', feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits feature source per turn, doc-search backed` },
  { group: 'Ecosystem & SDK', feature: 'Scripting / API',
    competitor: `${GOOD} Fusion API (Python / C++)`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC; same interface LLM uses` },
  { group: 'Ecosystem & SDK', feature: 'File format support',
    competitor: `${GOOD} STEP / IGES / DXF / F3D / DWG / SVG`,
    kerf: `${GOOD} STEP / IGES / IFC / DXF / FreeCAD import; Gerber / IPC-2581 / ODB++` },
  { group: 'Ecosystem & SDK', feature: 'Community & training',
    competitor: `${GOOD} Millions of users, vast official + third-party tutorials`,
    kerf: `${WEAK} Early-stage, growing` },
]

/* -------------------------------------------------------------------------- */
/* Page                                                                         */
/* -------------------------------------------------------------------------- */

export default function FusionPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
        aria-label="Kerf vs Fusion 360 comparison"
      >
        <Breadcrumb />

        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <header className="mb-10">
          <p
            className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2"
            aria-hidden="true"
          >
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs Fusion 360
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Fusion 360 pioneered the idea of integrated CAD / CAM / CAE / PCB
            in a single cloud-connected workspace and has millions of users
            behind it. Kerf is the tool most similar to Fusion in shape — both
            cover multi-discipline engineering in one environment with cloud
            collaboration. The differences are in philosophy: Fusion is a
            closed subscription product with a polished decade-long track
            record; Kerf is MIT open-core, chat-native, and subscription-free.
            Below is an honest look at both.
          </p>
        </header>

        {/* ── Closest-peer callout ─────────────────────────────────────── */}
        <aside
          aria-label="Why Fusion is Kerf's closest peer"
          className="mb-10 rounded-xl border border-kerf-300/30 bg-kerf-300/5 px-5 py-4"
        >
          <h2 className="font-display text-base font-semibold text-kerf-200 mb-2">
            Closest peer in shape
          </h2>
          <p className="text-sm text-ink-300 leading-relaxed">
            Of all tools Kerf is compared against, Fusion 360 is the closest
            peer in <em>scope</em>: both combine parametric B-rep, CAM,
            simulation, PCB design, cloud collaboration, and a scripting API in
            one product. That makes this comparison meaningful — the overlap is
            substantial, and the gaps are real. Fusion&#8217;s advantages
            centre on CAM fidelity (HSMWorks lineage), generative design,
            T-spline sculpting, and a vastly larger ecosystem. Kerf&#8217;s
            advantages centre on MIT licensing, a chat-driven workflow, no
            subscription, BYO LLM, a 40-module jewelry vertical, and
            electronics simulation (SI/EMC/PDN/thermal) without extension
            gating.
          </p>
        </aside>

        {/* ── Where Fusion is strong ───────────────────────────────────── */}
        <Section title="Where Fusion 360 is strong">
          <ul
            className="flex flex-col gap-3"
            aria-label="Fusion 360 strengths"
          >
            <Li>
              <strong className="text-ink-100">Cloud-native + desktop in one.</strong>{' '}
              Fusion is designed cloud-first — every project auto-saves to
              Autodesk&#8217;s cloud, multi-user collaboration is baked in, and
              the same tool runs on Windows and macOS as a native desktop app.
            </Li>
            <Li>
              <strong className="text-ink-100">HSMWorks-lineage CAM.</strong>{' '}
              The CAM workspace inherits HSMWorks&#8217; industry-tested
              toolpath engine with verified simulation, a broad post-processor
              library, and years of in-the-field machining validation.
              Kerf&#8217;s CAM is younger.
            </Li>
            <Li>
              <strong className="text-ink-100">Cloud generative design.</strong>{' '}
              Automated topology exploration across load cases using cloud
              compute — a flagship capability for lightweighting and lattice
              design. Kerf has nothing equivalent today.
            </Li>
            <Li>
              <strong className="text-ink-100">T-spline sculpt workflow.</strong>{' '}
              The Sculpt workspace gives direct freeform surface modelling with
              T-spline subdivision and crease support — a natural organic
              modelling layer that Kerf&#8217;s early NURBS Phase 4 does not
              match.
            </Li>
            <Li>
              <strong className="text-ink-100">Assembly motion study and interference detection.</strong>{' '}
              Fusion provides motion studies, contact sets, and interference
              detection on top of its joint system. Kerf now matches the joint
              type set (rigid, revolute, slider, cam, gear, pin-slot) but does
              not yet ship motion study.
            </Li>
            <Li>
              <strong className="text-ink-100">FEM multi-physics depth.</strong>{' '}
              Linear static and thermal FEM (extension / cloud-metered) with
              a mature solver validation record. Kerf now ships linear static,
              thermal, and nonlinear plasticity FEM but does not yet match
              Fusion's multi-physics coverage or cloud-compute scale.
            </Li>
            <Li>
              <strong className="text-ink-100">Eagle PCB integration.</strong>{' '}
              Fusion Electronics is the direct successor to Autodesk EAGLE,
              with a native ECAD&#x21d4;MCAD live link that tracks component
              placement between the PCB editor and the mechanical model.
            </Li>
            <Li>
              <strong className="text-ink-100">Hobbyist-tier free personal use.</strong>{' '}
              The free tier covers personal / non-commercial projects without a
              time limit — generous for hobbyists, though it converts on
              commercial use or revenue above US$1,000/yr.
            </Li>
            <Li>
              <strong className="text-ink-100">Decades of vendor polish and community.</strong>{' '}
              Millions of users, an extensive official learning platform, a
              deep third-party tutorial ecosystem, and integration with the
              wider Autodesk portfolio (Inventor, AutoCAD, Fusion Team).
            </Li>
          </ul>
        </Section>

        {/* ── Where Kerf differs ───────────────────────────────────────── */}
        <Section title="Where Kerf differs">
          <ul
            className="flex flex-col gap-3"
            aria-label="Kerf differentiators vs Fusion 360"
          >
            <Li>
              <strong className="text-ink-100">MIT open-core, no subscription.</strong>{' '}
              Fusion charges ~US$680/yr and its free tier is non-commercial
              only. Kerf&#8217;s full feature set is MIT-licensed — free
              locally with no revenue restriction, no seat fee, and no
              feature-gating for premium workflow.
            </Li>
            <Li>
              <strong className="text-ink-100">BYO LLM / BYO key.</strong>{' '}
              Bring your own Anthropic or OpenAI API key and zero billing flows
              through Kerf — the{' '}
              <code className="font-mono text-kerf-300">kerf_byo</code> tier
              routes all inference to your own account. Fusion has no
              configurable LLM.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a feature, constraint, routing rule, or simulation check
              in plain language; the LLM edits the feature-tree source or PCB
              source backed by live doc-search so it does not invent API
              surface. Fusion has no comparable LLM integration.
            </Li>
            <Li>
              <strong className="text-ink-100">True offline, fully open codebase.</strong>{' '}
              <code className="font-mono text-kerf-300">pip install 'kerf[server]'</code>{' '}
              + <code className="font-mono text-kerf-300">kerf serve</code>{' '}
              with BYO Postgres — no Autodesk account, no limited-offline caveat.
              The full codebase is on GitHub under MIT.
            </Li>
            <Li>
              <strong className="text-ink-100">Every project is a real git repo.</strong>{' '}
              Projects are cloneable git repositories with large-file auto-handling,
              near-free forks, and optional GitHub or GitLab mirrors. The CLI
              provides <code className="font-mono text-kerf-300">kerf sync</code>,{' '}
              <code className="font-mono text-kerf-300">kerf export</code>,{' '}
              <code className="font-mono text-kerf-300">kerf import</code>, and{' '}
              <code className="font-mono text-kerf-300">kerf hydrate</code> for
              folder-level two-way sync.
            </Li>
            <Li>
              <strong className="text-ink-100">Pre-compliance electronics simulation — in-box.</strong>{' '}
              Signal integrity (transmission-line, via stub, differential pair),
              EMC/EMI (common-mode, return-path gap, slot antenna), PDN (decap
              placement, target impedance, plane resonance), and PCB thermal
              (copper pour, via relief, hot-spot) are all included without
              extension or cloud-metering. Fusion gates these behind paid
              extensions.
            </Li>
            <Li>
              <strong className="text-ink-100">Richer in-box electronics fab output.</strong>{' '}
              Gerber / Excellon / IPC-2581 / ODB++ / IPC-D-356A netlist and
              DRC with IPC-2221B A/B/C manufacturing presets — beyond Fusion
              Electronics&#8217; base fab pack.
            </Li>
            <Li>
              <strong className="text-ink-100">40-module jewelry domain.</strong>{' '}
              Ring v4, gemstones v2 (30 cuts), settings v3/v4, gem-seat v2,
              chain v2, findings, casting export, a 31-template library, and
              PBR gem / metal viewport materials — a complete professional
              jewelry vertical that Fusion has no equivalent for at all.
            </Li>
            <Li>
              <strong className="text-ink-100">620 analytic-oracle kernel tests.</strong>{' '}
              Every core geometric operation is regression-tested against
              closed-form analytic references. This validates correctness
              independently of user-reported bugs.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk Python scripting.</strong>{' '}
              Automate over HTTP/JSON-RPC from your own machine — the same
              interface the LLM uses internally, so scripts and chat edits are
              first-class citizens of the same API surface.
            </Li>
          </ul>
        </Section>

        {/* ── Honest gaps ──────────────────────────────────────────────── */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul
            className="flex flex-col gap-3"
            aria-label="Areas where Kerf is behind Fusion 360"
          >
            <Li>
              <strong className="text-ink-100">CAM fidelity and validation.</strong>{' '}
              Fusion&#8217;s CAM has years of in-the-field toolpath validation
              and the HSMWorks pedigree. Kerf&#8217;s 3-axis and 5-axis 3+2
              CAM are younger and less hardened.
            </Li>
            <Li>
              <strong className="text-ink-100">Assembly motion study.</strong>{' '}
              Kerf now matches Fusion&#8217;s joint type set, but motion studies,
              contact sets, and interference detection are not yet shipped.
            </Li>
            <Li>
              <strong className="text-ink-100">FEM multi-physics coverage.</strong>{' '}
              Kerf ships linear static, thermal, and nonlinear plasticity FEM;
              Fusion&#8217;s multi-physics cloud solvers cover more boundary
              conditions and load types. CFD is not in Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">No generative design.</strong>{' '}
              Fusion&#8217;s cloud topology optimisation across load cases is a
              flagship that has no Kerf counterpart today; it remains roadmap.
            </Li>
            <Li>
              <strong className="text-ink-100">No T-spline freeform / Sculpt.</strong>{' '}
              Fusion&#8217;s Sculpt workspace for organic freeform modelling
              has no Kerf counterpart. NURBS Phase 4 is early and
              scope-limited.
            </Li>
            <Li>
              <strong className="text-ink-100">Direct modelling is limited.</strong>{' '}
              Fusion&#8217;s ability to intermix direct editing with the
              parametric timeline is more capable than Kerf&#8217;s current
              feature-tree-primary approach.
            </Li>
            <Li>
              <strong className="text-ink-100">Smaller community, fewer tutorials.</strong>{' '}
              Fusion has millions of users and a mature learning platform.
              Kerf is early-stage; community resources are limited today.
            </Li>
          </ul>
        </Section>

        {/* ── Migration notes ──────────────────────────────────────────── */}
        <Section title="Notes for Fusion users considering Kerf">
          <ul
            className="flex flex-col gap-3"
            aria-label="Migration notes for Fusion 360 users"
          >
            <Li>
              <strong className="text-ink-100">What feels familiar.</strong>{' '}
              Parametric feature tree, constraint-based sketcher, multi-sheet
              drawings with GD&amp;T, an integrated PCB workspace, cloud
              collaboration, and a Python scripting API — all of these exist in
              Kerf with comparable intent.
            </Li>
            <Li>
              <strong className="text-ink-100">The simulation depth shift.</strong>{' '}
              Fusion gates SI, EMC, PDN, and thermal analysis behind paid
              extensions. In Kerf these are in-box — if you have been living
              without those tools due to cost, they are available immediately.
            </Li>
            <Li>
              <strong className="text-ink-100">What is intentionally simpler.</strong>{' '}
              Kerf does not have Fusion&#8217;s HSMWorks-class CAM
              verification, its generative design solver, or its T-spline
              sculpt workspace. If your workflow is CAM-heavy for production
              machining or relies on topology optimisation, Fusion remains
              ahead.
            </Li>
            <Li>
              <strong className="text-ink-100">File migration.</strong>{' '}
              Kerf imports STEP, IGES, and DXF. Native Fusion (.f3d) files are
              not directly imported — export to STEP from Fusion first.
            </Li>
            <Li>
              <strong className="text-ink-100">Offline and cost change.</strong>{' '}
              Dropping a US$680/yr subscription to a free MIT binary is the
              most immediate practical difference for teams evaluating the
              switch.
            </Li>
          </ul>
        </Section>

        {/* ── Side-by-side table ───────────────────────────────────────── */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="Fusion 360" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
