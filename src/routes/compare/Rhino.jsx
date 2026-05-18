/**
 * /compare/rhino — Kerf vs Rhino (RhinoGold / Matrix / MatrixGold)
 *
 * Web-grounded (last reviewed 2026-05-18). Rhino 8 is a perpetual,
 * one-time-purchase licence (~US$995 full / ~$595 upgrade — not a
 * subscription), Windows/macOS, with the industry-reference NURBS kernel,
 * SubD, ShrinkWrap, and Grasshopper visual scripting. For jewelry, the
 * RhinoGold / Matrix lineage has consolidated into MatrixGold / CrossGems —
 * deeply refined goldsmith tooling (ring builders, stone setting, pavé,
 * wax-mill paths, supplier catalogs).
 *
 * Kerf has a strong, free jewelry foundation (gemstones v2, settings v3/v4,
 * ring v4, chain v2, 31 templates) plus integrated B-rep, electronics, and
 * CAM — but Rhino's NURBS depth, Grasshopper ecosystem, and goldsmith-proven
 * jewelry plugins are well ahead today.
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

const meta = makeCompareMeta('rhino')

const TABLE = [
  // Licensing & platform
  { group: 'Licensing & platform', feature: 'License',
    competitor: `${WEAK} Proprietary; perpetual one-time buy`,
    kerf: `${GOOD} MIT open-core` },
  { group: 'Licensing & platform', feature: 'Cost',
    competitor: `${WEAK} ~US$995 full / ~$595 upgrade; +plugin cost`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted` },
  { group: 'Licensing & platform', feature: 'No subscription',
    competitor: `${GOOD} Perpetual licence, no renewal`,
    kerf: `${GOOD} No seat subscription` },
  { group: 'Licensing & platform', feature: 'Platform',
    competitor: `${WEAK} Windows + macOS desktop`,
    kerf: `${GOOD} Browser (hosted) + single-binary local` },
  { group: 'Licensing & platform', feature: 'Maturity',
    competitor: `${GOOD} Decades; Rhino 8`,
    kerf: `${WEAK} Early-stage, < 2 yr public` },

  // Modeling
  { group: 'Modeling', feature: 'NURBS surfacing',
    competitor: `${GOOD} Class-leading kernel (G0–G3)`,
    kerf: `${WEAK} NURBS Phase 4 — trim-by-curve, G3 combs (early)` },
  { group: 'Modeling', feature: 'SubD modelling',
    competitor: `${GOOD} SubD with creases (Rhino 8)`,
    kerf: `${GOOD} SubD authoring with creases; quad remesh + surfacing` },
  { group: 'Modeling', feature: 'Parametric solids (B-rep)',
    competitor: `${WEAK} Via Grasshopper / plugins`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/etc.` },
  { group: 'Modeling', feature: 'Mesh repair / ShrinkWrap',
    competitor: `${GOOD} ShrinkWrap, mesh tools`,
    kerf: `${WEAK} Quad remesh; no ShrinkWrap equivalent` },

  // Visual / parametric scripting
  { group: 'Parametric scripting', feature: 'Visual node scripting',
    competitor: `${GOOD} Grasshopper — industry standard`,
    kerf: `${GAP} No visual node environment` },
  { group: 'Parametric scripting', feature: 'Plugin marketplace',
    competitor: `${GOOD} Thousands of GH components / Food4Rhino`,
    kerf: `${WEAK} Plugin API early-stage` },
  { group: 'Parametric scripting', feature: 'Python / scripting',
    competitor: `${GOOD} rhinoscriptsyntax / RhinoCommon`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC` },

  // Jewelry
  { group: 'Jewelry', feature: 'Ring design',
    competitor: `${GOOD} MatrixGold / RhinoGold ring builders`,
    kerf: `${GOOD} Ring v4 + 31-template library` },
  { group: 'Jewelry', feature: 'Gemstones / cuts',
    competitor: `${GOOD} Extensive gem libraries`,
    kerf: `${GOOD} Gemstones v2 — 30 cuts` },
  { group: 'Jewelry', feature: 'Settings / pavé / channel',
    competitor: `${GOOD} Mature stone-setting wizards`,
    kerf: `${GOOD} Settings v3/v4 + gem-seat v2` },
  { group: 'Jewelry', feature: 'Chain / findings',
    competitor: `${GOOD} Dedicated chain + findings tools`,
    kerf: `${GOOD} Chain v2 + findings + decorative` },
  { group: 'Jewelry', feature: 'Casting / wax-mill export',
    competitor: `${GOOD} STL + wax-mill paths, supplier catalogs`,
    kerf: `${WEAK} Casting export; no supplier catalogs / wax paths` },
  { group: 'Jewelry', feature: 'Goldsmith UX depth',
    competitor: `${GOOD} Years of workshop-driven refinement`,
    kerf: `${WEAK} Functional but younger` },

  // Rendering
  { group: 'Rendering', feature: 'Photoreal rendering',
    competitor: `${GOOD} Cycles + V-Ray/Enscape/KeyShot; caustics + dispersion`,
    kerf: `${WEAK} Cycles backend + browser path tracer (no caustics/dispersion)` },

  // Documentation
  { group: 'Drawings & docs', feature: '2D drawings / GD&T',
    competitor: `${WEAK} Layout + annotation plugins`,
    kerf: `${GOOD} Multi-sheet drawings + ASME Y14.5 GD&T` },

  // CAM / cross-domain
  { group: 'CAM & cross-domain', feature: 'CNC CAM',
    competitor: `${WEAK} Via RhinoCAM plugin`,
    kerf: `${GOOD} 3-axis CAM + tool DB; 5-axis 3+2` },
  { group: 'CAM & cross-domain', feature: 'Electronics',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Full EDA stack in same workspace` },
  { group: 'CAM & cross-domain', feature: 'Architecture / IFC',
    competitor: `${WEAK} Via VisualARQ plugin`,
    kerf: `${WEAK} IFC Tier 2 import + structural grid` },

  // Ecosystem
  { group: 'Ecosystem & SDK', feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits source per turn` },
  { group: 'Ecosystem & SDK', feature: 'Hosted / cloud',
    competitor: `${GAP} Desktop only`,
    kerf: `${GOOD} Hosted SaaS + local install` },
  { group: 'Ecosystem & SDK', feature: 'Community & training',
    competitor: `${GOOD} Very large, mature, well-resourced`,
    kerf: `${WEAK} Early-stage, growing` },
]

export default function RhinoPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main className="mx-auto max-w-4xl px-6 pt-12 pb-20">
        <Breadcrumb />

        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs Rhino
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Rhino 8 — with the RhinoGold / Matrix lineage now consolidated into
            MatrixGold / CrossGems — is the professional reference for jewelry
            CAD and freeform NURBS design. It is a perpetual one-time licence
            (about US$995, not a subscription) with the industry-standard NURBS
            kernel and Grasshopper. Kerf has a strong, free jewelry foundation
            and integrated B-rep, electronics, and CAM — but Rhino's NURBS
            depth, Grasshopper ecosystem, and goldsmith-proven plugins are well
            ahead today. An honest look at both.
          </p>
        </div>

        <Section title="Where Rhino is strong">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">Class-leading NURBS kernel.</strong>{' '}
              Rhino's surface engine is the industry reference for freeform work
              — jewelry, industrial design, naval architecture, aerospace — with
              production-proven G0–G3 continuity tools.
            </Li>
            <Li>
              <strong className="text-ink-100">Grasshopper visual scripting.</strong>{' '}
              The gold standard for parametric 3D, with thousands of components
              spanning structural optimisation, pattern generation, and more.
              Kerf has no equivalent.
            </Li>
            <Li>
              <strong className="text-ink-100">Deeply refined jewelry plugins.</strong>{' '}
              MatrixGold / RhinoGold bring years of goldsmith-driven UX: ring
              builders, stone-setting and pavé wizards, sizing, wax-mill paths,
              and supplier catalogs.
            </Li>
            <Li>
              <strong className="text-ink-100">Perpetual licence, no subscription.</strong>{' '}
              A one-time purchase that does not expire — a genuine ownership
              advantage over subscription CAD tools.
            </Li>
            <Li>
              <strong className="text-ink-100">SubD and ShrinkWrap.</strong>{' '}
              Rhino 8's SubD (with creases) and ShrinkWrap give fast organic
              modelling and mesh-recovery workflows Kerf does not match.
            </Li>
            <Li>
              <strong className="text-ink-100">Advanced rendering ecosystem.</strong>{' '}
              Built-in Cycles plus V-Ray, Enscape, and KeyShot for photoreal
              jewelry renders with accurate caustics and gem dispersion.
            </Li>
            <Li>
              <strong className="text-ink-100">RhinoCommon / Python automation.</strong>{' '}
              rhinoscriptsyntax and RhinoCommon expose essentially every kernel
              operation for scripting.
            </Li>
          </ul>
        </Section>

        <Section title="Where Kerf differs">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">MIT open-core, free to use.</strong>{' '}
              Rhino is ~US$995 per seat and the jewelry plugins add more. Kerf's
              full jewelry workflow — ring v4, settings v3/v4, gemstones v2,
              chain v2, 31 templates — is MIT-licensed and free locally.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a change in plain language and the LLM edits the feature
              tree / JSCAD source with doc-search backing — no visual
              programming required.
            </Li>
            <Li>
              <strong className="text-ink-100">Integrated B-rep, electronics, drawings.</strong>{' '}
              An OCCT parametric feature tree, a full EDA stack, multi-sheet
              drawings, and ASME Y14.5 GD&T are in the same workspace —
              disciplines Rhino needs separate plugins or tools for.
            </Li>
            <Li>
              <strong className="text-ink-100">Hosted option or local pip install.</strong>{' '}
              Sign up and design in the browser, or{' '}
              <code className="font-mono text-kerf-300">pip install kerf</code>{' '}
              locally — no platform-specific installer, no licence dongle, and
              no Homebrew formula.
            </Li>
            <Li>
              <strong className="text-ink-100">CAM built in.</strong>{' '}
              3-axis CAM with a tool database and 5-axis 3+2 ship in-box, where
              Rhino relies on the RhinoCAM plugin.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk Python scripting.</strong>{' '}
              Automate jewelry templates and feature trees from any Python
              script over HTTP/JSON-RPC on your own machine.
            </Li>
          </ul>
        </Section>

        <Section title="Honest gaps — where Kerf is behind today">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">NURBS surfacing is early.</strong>{' '}
              NURBS Phase 4 (trim-by-curve, G3 combs) is functional but nowhere
              near Rhino's depth. blendSrf / networkSrf / sweep2-class freeform
              tools are roadmap, not shipped.
            </Li>
            <Li>
              <strong className="text-ink-100">No Grasshopper equivalent.</strong>{' '}
              Kerf has no visual parametric environment; chat + the Python SDK
              fill part of that space but not all of it.
            </Li>
            <Li>
              <strong className="text-ink-100">SubD depth is newer.</strong>{' '}
              Kerf now ships SubD authoring with creases, but Rhino 8&rsquo;s
              SubD tools are more mature and deeply integrated with the NURBS
              surfacing workflow (SubD→NURBS conversion, ShrinkWrap).
            </Li>
            <Li>
              <strong className="text-ink-100">Render quality is narrower.</strong>{' '}
              Kerf&rsquo;s Cycles backend and in-browser path tracer provide
              photoreal output, but Rhino&rsquo;s plugin ecosystem (V-Ray, Enscape,
              KeyShot) provides caustics, accurate gem dispersion, and archviz
              lighting quality that Kerf&rsquo;s render path does not match today.
            </Li>
            <Li>
              <strong className="text-ink-100">Jewelry plugin depth.</strong>{' '}
              MatrixGold / RhinoGold have supplier catalogs, wax-path generation,
              and sizing refinements Kerf is still building toward.
            </Li>
            <Li>
              <strong className="text-ink-100">Smaller community.</strong>{' '}
              Rhino has decades of training, forums, and Food4Rhino plugins;
              Kerf's ecosystem is early-stage.
            </Li>
          </ul>
        </Section>

        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="Rhino" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
