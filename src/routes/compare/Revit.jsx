/**
 * /compare/revit — Kerf vs Revit
 *
 * Web-grounded (last reviewed 2026-05-15). Autodesk Revit 2026 is the
 * dominant BIM platform for architecture, engineering, and construction:
 * ~US$2,910/yr single-user (~$365/mo), a deep parametric family system,
 * full MEP (HVAC / electrical / plumbing / fabrication), Revit Structure,
 * mature IFC 2x3/4 plus STEP/3DM/SKP/OBJ interop, Navisworks clash
 * coordination, BIM 360 / Autodesk Docs cloud, and pyRevit + Dynamo.
 *
 * Kerf's arch/civil capabilities are real but fundamentally lighter — IFC
 * Tier 2 import (task #92, task #123), IFC export in progress, DXF, BIM
 * primitives, structural grid + steel framing, site grading, stairs,
 * drawings, BOM. It is not a full BIM platform today, and we say so plainly.
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

const meta = makeCompareMeta('revit')

const TABLE = [
  // Licensing & platform
  {
    group: 'Licensing & platform',
    feature: 'License',
    competitor: `${WEAK} Proprietary subscription`,
    kerf: `${GOOD} MIT open-core`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Cost',
    competitor: `${WEAK} ~US$2,910/yr single-user (~$365/mo)`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Platform',
    competitor: `${WEAK} Windows only`,
    kerf: `${GOOD} Browser (hosted) + single-binary local`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Cloud / collaboration',
    competitor: `${GOOD} BIM 360 / Autodesk Docs, worksharing`,
    kerf: `${WEAK} Workspace + member roles (not BIM-specific)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Maturity',
    competitor: `${GOOD} Industry-standard, decades`,
    kerf: `${WEAK} Early-stage, < 2 yr public`,
  },

  // BIM authoring
  {
    group: 'BIM authoring',
    feature: 'Parametric family system',
    competitor: `${GOOD} Deep family editor + types + shared parameters`,
    kerf: `${GAP} No native family authoring`,
  },
  {
    group: 'BIM authoring',
    feature: 'Family library',
    competitor: `${GOOD} Autodesk Content Library + vast third-party`,
    kerf: `${GAP} No BIM family library`,
  },
  {
    group: 'BIM authoring',
    feature: 'Walls / doors / windows / slabs',
    competitor: `${GOOD} Full parametric building elements`,
    kerf: `${WEAK} BIM primitives (basic walls/doors/windows/slabs)`,
  },
  {
    group: 'BIM authoring',
    feature: 'Stairs / ramps',
    competitor: `${GOOD} Full stair/ramp families`,
    kerf: `${WEAK} Stairs (basic)`,
  },
  {
    group: 'BIM authoring',
    feature: 'Structural grid / framing',
    competitor: `${GOOD} Revit Structure + Robot structural analysis`,
    kerf: `${WEAK} Structural grid + steel framing (early)`,
  },
  {
    group: 'BIM authoring',
    feature: 'Site / earthwork',
    competitor: `${GOOD} Toposolids, site tools`,
    kerf: `${WEAK} Site grading / earthwork (basic)`,
  },
  {
    group: 'BIM authoring',
    feature: 'Materials & finishes',
    competitor: `${GOOD} Material library with render appearance`,
    kerf: `${WEAK} PBR materials; no BIM material catalogue`,
  },

  // MEP & coordination
  {
    group: 'MEP & coordination',
    feature: 'HVAC / plumbing / electrical',
    competitor: `${GOOD} Full Revit MEP + fabrication detailing`,
    kerf: `${GAP} Not yet`,
  },
  {
    group: 'MEP & coordination',
    feature: 'Clash detection',
    competitor: `${GOOD} Navisworks federated multi-discipline coordination`,
    kerf: `${GAP} Not yet`,
  },
  {
    group: 'MEP & coordination',
    feature: 'Multi-user worksharing',
    competitor: `${GOOD} Worksets + BIM 360 concurrent editing`,
    kerf: `${WEAK} General workspace roles, not BIM worksharing`,
  },
  {
    group: 'MEP & coordination',
    feature: '4D / 5D (schedule + cost)',
    competitor: `${GOOD} Via Navisworks / Autodesk Construction Cloud`,
    kerf: `${GAP} Not yet`,
  },

  // Documentation
  {
    group: 'Drawings & docs',
    feature: 'Sheets / views',
    competitor: `${GOOD} Full sheet-set management`,
    kerf: `${GOOD} Multi-sheet drawings`,
  },
  {
    group: 'Drawings & docs',
    feature: 'Schedules / BOM',
    competitor: `${GOOD} Parameter-driven building schedules`,
    kerf: `${GOOD} BOM + distributors`,
  },
  {
    group: 'Drawings & docs',
    feature: 'GD&T / tolerancing',
    competitor: `${WEAK} Not a mechanical-tolerance tool`,
    kerf: `${GOOD} ASME Y14.5 GD&T (mechanical side)`,
  },

  // Interoperability
  {
    group: 'Interoperability',
    feature: 'IFC import',
    competitor: `${GOOD} Mature IFC 2x3 / 4 (certified)`,
    kerf: `${GOOD} IFC Tier 2 import`,
  },
  {
    group: 'Interoperability',
    feature: 'IFC export',
    competitor: `${GOOD} Certified IFC 2x3 / 4 export`,
    kerf: `${WEAK} IFC export in progress`,
  },
  {
    group: 'Interoperability',
    feature: 'DXF / STEP / 3DM / SKP / OBJ',
    competitor: `${GOOD} Broad import/link/export`,
    kerf: `${WEAK} DXF + STEP/IGES; narrower set`,
  },

  // Cross-domain
  {
    group: 'Cross-domain',
    feature: 'Electronics (same tool)',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Full EDA stack in same workspace`,
  },
  {
    group: 'Cross-domain',
    feature: 'Mechanical B-rep CAD',
    competitor: `${WEAK} Not a mechanical CAD tool`,
    kerf: `${GOOD} OCCT feature tree, sketcher, CAM`,
  },
  {
    group: 'Cross-domain',
    feature: 'Jewelry design',
    competitor: `${GAP} Not a jewelry tool`,
    kerf: `${GOOD} Ring v4, gemstones v2, settings, chain v2`,
  },

  // Ecosystem & SDK
  {
    group: 'Ecosystem & SDK',
    feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits source per turn`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'Scripting / automation',
    competitor: `${GOOD} pyRevit + Dynamo + Revit API`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'AEC plugin ecosystem',
    competitor: `${GOOD} Vast Autodesk App Store`,
    kerf: `${WEAK} Plugin API early-stage`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'Community & training',
    competitor: `${GOOD} Enormous, certified training worldwide`,
    kerf: `${WEAK} Early-stage, growing`,
  },
]

export default function RevitPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
        aria-label="Kerf vs Revit comparison"
      >
        <Breadcrumb />

        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs Revit
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Revit is the dominant BIM platform for architecture, engineering,
            and construction — a deep parametric family system, full MEP, Revit
            Structure, mature IFC interoperability, Navisworks clash coordination,
            and Autodesk Docs cloud worksharing, at roughly US$2,910/yr per seat
            on Windows. Kerf&rsquo;s arch/civil workflow (IFC Tier 2 import, BIM
            primitives, structural grid + steel framing, site grading, stairs,
            drawings, BOM) is real but fundamentally lighter.{' '}
            <strong className="text-ink-200">
              Kerf is not a full BIM platform today
            </strong>
            , and this page says so plainly.
          </p>
        </div>

        <Section title="Where Revit is strong">
          <ul
            className="flex flex-col gap-3"
            aria-label="Revit strengths"
          >
            <Li>
              <strong className="text-ink-100">
                Deep parametric BIM family system.
              </strong>{' '}
              Revit&rsquo;s family editor lets every building element carry
              parameters, types, formulas, shared parameters, and schedule
              metadata — the load-bearing foundation of real BIM. Kerf has no
              native family authoring today.
            </Li>
            <Li>
              <strong className="text-ink-100">Vast content library.</strong>{' '}
              The Autodesk Content Library plus a large third-party market
              supply parametric families for nearly every product category —
              doors, structural sections, MEP equipment, and fixtures. Kerf
              has no BIM family library.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Full MEP and structural disciplines.
              </strong>{' '}
              HVAC, electrical, plumbing, and MEP fabrication detailing, plus
              Revit Structure with Robot structural analysis — entire
              disciplines Kerf does not yet address.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Navisworks clash detection and coordination.
              </strong>{' '}
              Revit models feed directly into Navisworks for federated,
              multi-discipline clash detection and 4D/5D construction
              sequencing — a core AEC project-delivery workflow.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Mature, certified IFC round-trip.
              </strong>{' '}
              Years of IFC 2x3 / 4 import and export refinement backed by
              buildingSMART certification and broad openBIM interoperability
              with structural, MEP, and civil tools.
            </Li>
            <Li>
              <strong className="text-ink-100">
                BIM 360 / Autodesk Docs worksharing.
              </strong>{' '}
              Worksets enable concurrent BIM model editing by large project
              teams, with cloud-hosted model coordination through Autodesk
              Construction Cloud.
            </Li>
            <Li>
              <strong className="text-ink-100">
                pyRevit + Dynamo automation.
              </strong>{' '}
              The Revit API — accessible from pyRevit (Python) and Dynamo
              (visual programming) — covers virtually every internal BIM
              object for scripted workflows. A vast Autodesk App Store
              supplements it.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Industry-standard AEC ecosystem.
              </strong>{' '}
              Decades of vendor support, certified training, structural
              analysis integrations (Robot, ETABS, Tekla), and an established
              pipeline to cost estimation, scheduling, and facilities
              management platforms.
            </Li>
          </ul>
        </Section>

        <Section title="Where Kerf differs">
          <ul
            className="flex flex-col gap-3"
            aria-label="Kerf differentiators vs Revit"
          >
            <Li>
              <strong className="text-ink-100">
                MIT open-core, dramatically lower cost.
              </strong>{' '}
              Revit is ~US$2,910/yr per seat and Windows-only. Kerf is
              MIT-licensed with a free local install via brew or curl on
              macOS/Linux/Windows, and pay-as-you-go hosted cloud — no
              per-seat subscription, no Autodesk account.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Describe a building element, layout change, or parametric
              constraint in plain language; the LLM edits the model source
              directly, backed by live doc-search so it does not invent API
              surface.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Persistent face IDs and parametric history DAG.
              </strong>{' '}
              Kerf&rsquo;s validated B-rep carries stable face names across
              history replays, avoiding downstream reference breakage — a
              concern that crops up in Revit automation when families or
              phases change element identity.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Mechanical + electronics in the same workspace.
              </strong>{' '}
              Teams designing smart buildings, IoT devices, or electronic
              enclosures can work on PCB layout and mechanical B-rep without
              leaving Kerf — disciplines that require separate tools in a
              Revit-centred workflow.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Multi-discipline under one licence.
              </strong>{' '}
              Architectural, mechanical, electronics, and jewelry workflows
              share one workspace and one SDK interface — no per-discipline
              seat stacking.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Mechanical-grade documentation.
              </strong>{' '}
              ASME Y14.5 GD&T and multi-sheet drawings serve
              product-fabrication work alongside architectural output in the
              same tool.
            </Li>
            <Li>
              <strong className="text-ink-100">
                kerf-sdk Python scripting.
              </strong>{' '}
              Automate drawing generation, BOM export, and model manipulation
              from Python on your own machine via HTTP/JSON-RPC — the same
              interface the LLM uses internally.
            </Li>
          </ul>
        </Section>

        <Section title="Honest gaps — where Kerf is behind today">
          <ul
            className="flex flex-col gap-3"
            aria-label="Honest Kerf gaps vs Revit"
          >
            <Li>
              <strong className="text-ink-100">
                Not a BIM platform today.
              </strong>{' '}
              For multi-discipline AEC firms — structural, MEP, and
              architectural teams on one federated model — Revit&rsquo;s
              depth is the appropriate choice. Kerf handles lighter arch and
              design-exploration tasks well, but is BIM-curious rather than
              BIM-deep.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No MEP or building services.
              </strong>{' '}
              HVAC, plumbing, and electrical systems modelling are absent.
              Revit MEP is far ahead and is a hard requirement for most AEC
              deliverable workflows.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No parametric family authoring.
              </strong>{' '}
              Revit&rsquo;s family editor — with nested families,
              formula-driven types, and scheduling metadata — underpins real
              BIM. Kerf&rsquo;s BIM primitives are fixed components, not
              author-your-own parametric building families.
            </Li>
            <Li>
              <strong className="text-ink-100">No clash detection.</strong>{' '}
              Federated multi-discipline coordination (Navisworks-style) is
              not in Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">
                IFC export is in progress.
              </strong>{' '}
              Kerf imports IFC at Tier 2 (tasks{' '}
              <span className="font-mono text-ink-200">#92</span>,{' '}
              <span className="font-mono text-ink-200">#123</span>) but full
              certified IFC export for round-trip openBIM interoperability is
              not yet complete.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No 4D/5D construction sequencing.
              </strong>{' '}
              Revit feeds Navisworks and Autodesk Construction Cloud for
              schedule-linked 4D walkthroughs and cost-linked 5D models.
              Kerf has no equivalent today.
            </Li>
            <Li>
              <strong className="text-ink-100">
                No BIM-grade worksharing.
              </strong>{' '}
              Kerf has general workspace member roles, not concurrent BIM
              model worksharing at the scale of a large AEC project team.
            </Li>
          </ul>
        </Section>

        <Section title="Migration notes for Revit users">
          <ul
            className="flex flex-col gap-3"
            aria-label="Migration notes for Revit users considering Kerf"
          >
            <Li>
              <strong className="text-ink-100">What will feel familiar.</strong>{' '}
              Kerf&rsquo;s parametric history DAG shares conceptual DNA with
              Revit&rsquo;s family-instance model: each feature in the tree is
              parametric, replayable, and dependent on earlier steps — much
              like a Revit family type is driven by its parameter table.
              Multi-sheet drawings, BOM schedules, and the notion of a
              persistent model that drives documentation all carry over. If
              you have written pyRevit scripts against the Revit API,
              kerf-sdk&rsquo;s HTTP/JSON-RPC interface will feel structurally
              similar.
            </Li>
            <Li>
              <strong className="text-ink-100">
                What is structurally different.
              </strong>{' '}
              Kerf&rsquo;s DAG is a general feature tree (pad, pocket,
              revolve, loft, boolean) rather than a building-element
              ontology. There are no wall types, floor assemblies,
              level-based hosting, or parametric families in the Revit sense
              — the BIM primitives are simpler fixed shapes. Think of it as
              closer to a parametric solid modeller with BIM-adjacent output
              than a full BIM authoring environment.
            </Li>
            <Li>
              <strong className="text-ink-100">
                What is missing for production AEC work.
              </strong>{' '}
              A Revit user moving to Kerf for architecture will immediately
              miss: the family editor with nested families and formula-driven
              types, level/grid-based element hosting, MEP routing tools,
              Navisworks-style federated coordination, 4D sequencing, and the
              Autodesk Content Library. These are not near-term roadmap items
              — they would require building a second, deep BIM stack alongside
              Kerf&rsquo;s current multi-domain approach.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Where the crossover works best.
              </strong>{' '}
              Revit users doing early-stage massing, concept design, mixed
              architecture + electronics products (smart-building hardware,
              IoT enclosures), or needing a lighter cross-platform tool for
              design exploration without Windows or seat licensing constraints
              will find Kerf useful alongside Revit — not necessarily instead
              of it.
            </Li>
          </ul>
        </Section>

        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="Revit" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
