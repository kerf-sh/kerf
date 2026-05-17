/**
 * /compare/onshape — Kerf vs Onshape (PTC)
 *
 * Web-grounded (last reviewed 2026-05-17). Onshape is PTC's cloud-native
 * parametric CAD platform — browser-only by design, with real-time multi-user
 * collaboration as its defining differentiator. It introduced version-controlled
 * CAD branches (Documents) and FeatureScript, a proprietary DSL for custom
 * parametric features. Professional plan ~US$2,100/yr; Standard ~US$1,500/yr;
 * a Free plan exists for public documents only. No desktop install; all work
 * lives in the browser and PTC's cloud. Simulation and rendering require
 * paid third-party add-ons via the App Store.
 *
 * Kerf is the most natural Onshape comparison: cloud-friendly, browser-first,
 * parametric. Key differences: Kerf is MIT open-core with a full local install,
 * chat-native, multi-discipline (mechanical + electronics + jewelry), and open
 * kernel; Onshape wins on real-time collab maturity, FeatureScript ecosystem,
 * vendor polish, and mobile/tablet editing.
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
/* Inline meta — compareMeta.js is not modified per constraints                */
/* -------------------------------------------------------------------------- */

const BASE = 'https://kerf.sh'
const slug = 'onshape'
const product = 'Onshape'

const _meta = {
  title: 'Kerf vs Onshape — cloud CAD compared',
  description:
    "Onshape pioneered real-time collaborative cloud CAD. See how Kerf's " +
    'MIT open-core, chat-driven, multi-discipline stack compares.',
  slug,
  product,
}

const meta = {
  title: _meta.title,
  description: _meta.description,
  canonical: `${BASE}/compare/${slug}`,
  ogImage: `${BASE}/og/compare-${slug}.png`,
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: _meta.title,
    description: _meta.description,
    url: `${BASE}/compare/${slug}`,
    image: `${BASE}/og/compare-${slug}.png`,
    publisher: { '@type': 'Organization', name: 'Kerf', url: BASE },
  }),
  product,
  slug,
}

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                               */
/* -------------------------------------------------------------------------- */

const TABLE = [
  // Licensing & platform
  { group: 'Licensing & platform', feature: 'License',
    competitor: `${WEAK} Proprietary SaaS subscription`,
    kerf: `${GOOD} MIT open-core` },
  { group: 'Licensing & platform', feature: 'Cost',
    competitor: `${WEAK} Standard ~US$1,500/yr; Professional ~US$2,100/yr`,
    kerf: `${GOOD} Free local install; pay-as-you-go hosted` },
  { group: 'Licensing & platform', feature: 'Free tier',
    competitor: `${WEAK} Public documents only (no private work)`,
    kerf: `${GOOD} Full free local install, private projects included` },
  { group: 'Licensing & platform', feature: 'Offline / self-host',
    competitor: `${GAP} Browser-only; requires connectivity`,
    kerf: `${GOOD} Full offline single-binary install (brew/curl)` },
  { group: 'Licensing & platform', feature: 'Open source',
    competitor: `${GAP} Proprietary; data stored on PTC cloud`,
    kerf: `${GOOD} MIT — full codebase on GitHub` },
  { group: 'Licensing & platform', feature: 'Vendor lock-in',
    competitor: `${WEAK} PTC-hosted; export-only escape hatch`,
    kerf: `${GOOD} Open format; self-hostable` },
  { group: 'Licensing & platform', feature: 'Maturity',
    competitor: `${GOOD} ~10 yr cloud CAD history; professional-grade`,
    kerf: `${WEAK} Early-stage, < 2 yr public` },

  // Cloud & collaboration
  { group: 'Cloud & collaboration', feature: 'Cloud-native architecture',
    competitor: `${GOOD} Purpose-built cloud; no sync or save needed`,
    kerf: `${GOOD} Hosted SaaS + local install; cloud-friendly` },
  { group: 'Cloud & collaboration', feature: 'Real-time multi-user collab',
    competitor: `${GOOD} Industry-leading; concurrent editing, live cursors`,
    kerf: `${WEAK} Cloud collab less mature (in progress)` },
  { group: 'Cloud & collaboration', feature: 'Version control (branches)',
    competitor: `${GOOD} Built-in branching / tagging in Documents`,
    kerf: `${GOOD} file_revisions (fine-grained undo) + cloud git branches` },
  { group: 'Cloud & collaboration', feature: 'Mobile / tablet editing',
    competitor: `${GOOD} iOS / Android apps with editing`,
    kerf: `${WEAK} Responsive browser; no dedicated mobile app` },

  // Modeling
  { group: 'Modeling', feature: 'Parametric B-rep',
    competitor: `${GOOD} Mature history-based Part Studios (OCCT underneath)`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/etc.` },
  { group: 'Modeling', feature: 'Constraint sketcher',
    competitor: `${GOOD} Full parametric sketcher`,
    kerf: `${GOOD} Sketcher v2 — all major constraints, 620 kernel tests` },
  { group: 'Modeling', feature: 'Sheet metal',
    competitor: `${GOOD} Full sheet-metal workspace`,
    kerf: `${GOOD} Flange + unfold + flat-pattern DXF` },
  { group: 'Modeling', feature: 'Freeform / NURBS',
    competitor: `${WEAK} Limited surface tooling vs dedicated NURBS tools`,
    kerf: `${WEAK} NURBS Phase 4 (early); no freeform sculpt` },

  // Custom features & scripting
  { group: 'Custom features & scripting', feature: 'Custom parametric features',
    competitor: `${GOOD} FeatureScript (proprietary DSL) — rich App Store ecosystem`,
    kerf: `${GOOD} MIT kernel directly; DAG is open and extensible` },
  { group: 'Custom features & scripting', feature: 'Scripting / automation',
    competitor: `${WEAK} FeatureScript only (proprietary); REST API limited`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC, runs on your machine` },
  { group: 'Custom features & scripting', feature: 'BYO LLM / AI',
    competitor: `${GAP} None`,
    kerf: `${GOOD} BYO key or hosted models; any OpenAI-compatible endpoint` },
  { group: 'Custom features & scripting', feature: 'Chat / LLM editing',
    competitor: `${GAP} No LLM integration`,
    kerf: `${GOOD} Chat-native — edits source per turn, doc-search backed` },

  // Assemblies
  { group: 'Assemblies', feature: 'Mates / constraints',
    competitor: `${GOOD} Full mate system in Assemblies`,
    kerf: `${WEAK} Assembly mates (newer)` },
  { group: 'Assemblies', feature: 'Motion / interference',
    competitor: `${WEAK} Basic motion; full simulation requires add-on`,
    kerf: `${GAP} Not yet` },

  // Drawings & docs
  { group: 'Drawings & docs', feature: '2D technical drawings',
    competitor: `${GOOD} Drawings workspace (associative)`,
    kerf: `${GOOD} Multi-sheet drawings` },
  { group: 'Drawings & docs', feature: 'GD&T',
    competitor: `${GOOD} ASME / ISO GD&T in Drawings`,
    kerf: `${GOOD} ASME Y14.5 GD&T framework` },

  // Simulation
  { group: 'Simulation', feature: 'FEM / structural',
    competitor: `${WEAK} Via paid third-party App Store add-ons only`,
    kerf: `${GAP} Not yet` },
  { group: 'Simulation', feature: 'Simulation depth',
    competitor: `${WEAK} Requires additional subscription on top of Onshape`,
    kerf: `${GAP} Not yet` },

  // Domain breadth
  { group: 'Domain breadth', feature: 'Electronics / PCB',
    competitor: `${GAP} Mechanical CAD only; no ECAD`,
    kerf: `${GOOD} Full EDA — schematic, routing, DRC, Gerber/IPC-2581` },
  { group: 'Domain breadth', feature: 'Jewelry tooling',
    competitor: `${GAP} Generic CAD only`,
    kerf: `${GOOD} Ring v4, gemstones v2 (30 cuts), settings, chain v2` },
  { group: 'Domain breadth', feature: 'Architecture / IFC',
    competitor: `${GAP} Not an AEC tool`,
    kerf: `${WEAK} IFC Tier 2 import + structural grid` },

  // Ecosystem
  { group: 'Ecosystem', feature: 'App Store / add-ons',
    competitor: `${GOOD} PTC App Store — simulation, rendering, CAM add-ons`,
    kerf: `${WEAK} Early — open-core + plugin API in progress` },
  { group: 'Ecosystem', feature: 'Community & training',
    competitor: `${GOOD} Professional user base, official training, certifications`,
    kerf: `${WEAK} Early-stage, growing` },
  { group: 'Ecosystem', feature: 'Import / export formats',
    competitor: `${GOOD} STEP, IGES, Parasolid, ACIS, DXF, STL`,
    kerf: `${GOOD} STEP/IGES/DXF/IFC/FreeCAD import; Gerber/IPC-2581 fab pack` },
]

/* -------------------------------------------------------------------------- */
/* Page component                                                               */
/* -------------------------------------------------------------------------- */

export default function OnshapePage() {
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
            aria-label="Comparison title: Kerf versus Onshape"
          >
            Kerf vs Onshape
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Onshape (PTC) pioneered cloud-native parametric CAD and remains the
            benchmark for real-time multi-user collaboration in design — the
            ability for multiple engineers to edit the same model simultaneously
            in a browser is genuinely unmatched. It introduced version-controlled
            Documents, FeatureScript for custom parametric features, and a growing
            App Store for simulation and rendering. Subscriptions start at
            ~US$1,500/yr; the free tier allows public documents only. Kerf is the
            most natural peer comparison: cloud-friendly, browser-first,
            parametric. The honest picture is below.
          </p>
        </div>

        {/* Where Onshape is strong */}
        <Section title="Where Onshape is strong">
          <ul className="flex flex-col gap-3" aria-label="Onshape strengths">
            <Li>
              <strong className="text-ink-100">Real-time multi-user collaboration.</strong>{' '}
              Onshape's defining capability: concurrent editing with live
              cursors and instant conflict resolution, all in the browser.
              No file locking, no "check out". This is genuinely ahead of any
              current Kerf collab offering.
            </Li>
            <Li>
              <strong className="text-ink-100">True cloud-native architecture.</strong>{' '}
              Purpose-built for the cloud from day one — no sync client, no
              save button, no version-mismatch between team members. Connectivity
              is required, but the experience is seamless when online.
            </Li>
            <Li>
              <strong className="text-ink-100">Built-in version control (Documents).</strong>{' '}
              Branching, tagging, and history are first-class features baked
              into the platform — no separate Git integration needed.
            </Li>
            <Li>
              <strong className="text-ink-100">FeatureScript ecosystem.</strong>{' '}
              FeatureScript is a proprietary DSL, but it has produced a rich
              library of custom parametric features in the App Store, refined
              over years of community contribution.
            </Li>
            <Li>
              <strong className="text-ink-100">Mobile and tablet editing.</strong>{' '}
              Dedicated iOS and Android apps with full model editing — Kerf
              is a responsive browser experience without a native app.
            </Li>
            <Li>
              <strong className="text-ink-100">Mature parametric CAD.</strong>{' '}
              Part Studios with a decade of engineering behind them, a polished
              UI, and battle-tested reliability across complex industrial models.
            </Li>
            <Li>
              <strong className="text-ink-100">Professional training and certification.</strong>{' '}
              Onshape Learning Center, official certifications (CSWA-equivalent),
              and a large professional user base with extensive community content.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf differs */}
        <Section title="Where Kerf differs">
          <ul className="flex flex-col gap-3" aria-label="Kerf differentiators">
            <Li>
              <strong className="text-ink-100">MIT open-core — no subscription, full offline.</strong>{' '}
              Onshape requires a subscription starting at ~US$1,500/yr; the free
              tier allows public documents only. Kerf is MIT-licensed — install
              the binary locally (brew/curl) for free, no account required, no
              connectivity needed, no revenue cap.
            </Li>
            <Li>
              <strong className="text-ink-100">Open kernel, not a proprietary DSL.</strong>{' '}
              Onshape extends via FeatureScript, a language PTC controls.
              Kerf's parametric DAG is backed by the MIT-licensed kernel
              directly — the extensibility surface is open, and there is no
              vendor gate on custom features.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow with BYO LLM.</strong>{' '}
              Describe a feature, constraint, or routing rule in plain language;
              the model edits the source backed by live doc-search. You can use
              Kerf's hosted models or bring your own API key — any
              OpenAI-compatible endpoint. Onshape has no LLM integration.
            </Li>
            <Li>
              <strong className="text-ink-100">Multi-discipline: mechanical + electronics + jewelry.</strong>{' '}
              Onshape is mechanical CAD. Kerf adds a full EDA stack
              (hierarchical schematic, shove router, SPICE, DRC, Gerber /
              IPC-2581) and a jewelry domain (ring v4, gemstones v2 — 30 cuts,
              settings, chain v2) in the same workspace.
            </Li>
            <Li>
              <strong className="text-ink-100">620 analytic-oracle verified kernel tests.</strong>{' '}
              The parametric and sketcher kernel ships with a verified test
              suite — results are checked against OCCT analytic ground truth,
              not just regression snapshots.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk Python scripting (out-of-process).</strong>{' '}
              HTTP/JSON-RPC from your own machine — the same interface the LLM
              uses internally, so scripts are first-class and automation is
              straightforward.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul className="flex flex-col gap-3" aria-label="Kerf honest gaps versus Onshape">
            <Li>
              <strong className="text-ink-100">Real-time collab maturity.</strong>{' '}
              Onshape's concurrent multi-user editing is a decade in the making.
              Kerf's cloud collaboration feature is less mature. If live
              concurrent editing is critical, Onshape is ahead.
            </Li>
            <Li>
              <strong className="text-ink-100">FeatureScript ecosystem.</strong>{' '}
              Years of community-built FeatureScript features in Onshape's App
              Store have no Kerf equivalent today. The MIT-licensed kernel is
              open, but the community library has not yet developed.
            </Li>
            <Li>
              <strong className="text-ink-100">No mobile app.</strong>{' '}
              Onshape's iOS and Android apps support editing on the go; Kerf
              is a responsive browser only, with no dedicated native app.
            </Li>
            <Li>
              <strong className="text-ink-100">Simulation requires add-ons on both platforms,
              but Onshape's ecosystem is larger.</strong>{' '}
              Neither platform ships first-party FEM, but Onshape's App Store
              has more mature simulation partner integrations available today.
            </Li>
            <Li>
              <strong className="text-ink-100">Vendor polish and assembly depth.</strong>{' '}
              Onshape's UI, mating system, and overall product finish reflect
              ten years of professional refinement. Kerf is younger, and rough
              edges will surface.
            </Li>
            <Li>
              <strong className="text-ink-100">Smaller community.</strong>{' '}
              Onshape has a large, professionally-certified user base. Kerf's
              community is early-stage and growing.
            </Li>
          </ul>
        </Section>

        {/* Migration notes */}
        <Section title="Coming from Onshape?">
          <ul className="flex flex-col gap-3" aria-label="Migration notes for Onshape users">
            <Li>
              <strong className="text-ink-100">Parametric concepts map directly.</strong>{' '}
              Feature trees, sketches, constraints, mates, and assembly
              structure translate with minimal conceptual overhead. The
              modelling vocabulary is the same.
            </Li>
            <Li>
              <strong className="text-ink-100">Real-time collab gap is real — plan for it.</strong>{' '}
              If your team depends on live concurrent editing today, Kerf's
              collab feature is not yet a drop-in replacement. Factor this in
              before migrating a multi-user team.
            </Li>
            <Li>
              <strong className="text-ink-100">FeatureScript work does not port automatically.</strong>{' '}
              Custom features built in FeatureScript must be recreated using
              kerf-sdk or the open kernel API. The underlying parametric
              capability is there; the DSL is not.
            </Li>
            <Li>
              <strong className="text-ink-100">Multi-discipline breadth is the win.</strong>{' '}
              If you need electronics alongside mechanical, or jewelry tooling,
              the migration pays off immediately — those domains do not exist
              in Onshape at all.
            </Li>
            <Li>
              <strong className="text-ink-100">Open licensing removes the subscription risk.</strong>{' '}
              Onshape documents live on PTC servers; export is the only escape
              hatch. With Kerf's MIT core and local install, your design data
              and the tooling that reads it are under your control.
            </Li>
          </ul>
        </Section>

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="Onshape" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
