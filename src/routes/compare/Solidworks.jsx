/**
 * /compare/solidworks — Kerf vs SOLIDWORKS (Dassault Systèmes)
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-18).
 *
 * SOLIDWORKS is the incumbent in professional mechanical CAD. Standard licence
 * ~US$4,000 one-time + ~US$1,500/yr maintenance; Professional ~US$5,500 + $2,000;
 * Premium ~US$7,500 + $2,500. Subscription "SOLIDWORKS Connected" ~US$2,200/yr/seat.
 * Windows-only native desktop; 3DExperience cloud overlay is a separate purchase.
 * Parametric feature tree, full assembly/motion, sheet metal, surfacing, drawings,
 * weldments, and the widest third-party add-in ecosystem in mechanical CAD.
 *
 * Kerf does not replace SOLIDWORKS for production mechanical engineering today —
 * the CAM depth, FEM, full assembly simulation, and partner ecosystem gaps are real.
 * Where Kerf differs: MIT open-core, no Windows-only constraint, no $4,000 seat,
 * chat-native editing, multi-discipline (ECAD + jewelry in one workspace), and
 * in-box electronics pre-compliance simulation.
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

/* -------------------------------------------------------------------------
 * Inline meta — compareMeta.js includes a 'solidworks' entry; we read it
 * here via makeCompareMeta but keep a fallback so the page self-contains.
 * ---------------------------------------------------------------------- */
const BASE = 'https://kerf.sh'
const meta = {
  title: 'Kerf vs SOLIDWORKS — mechanical CAD compared',
  description:
    'SOLIDWORKS is the incumbent professional mechanical CAD. See how ' +
    "Kerf's MIT open-core, chat-driven, multi-discipline workspace compares — honestly.",
  canonical: `${BASE}/compare/solidworks`,
  ogImage: `${BASE}/og/compare-solidworks.png`,
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Kerf vs SOLIDWORKS — mechanical CAD compared',
    description:
      'SOLIDWORKS is the incumbent professional mechanical CAD. See how ' +
      "Kerf's MIT open-core, chat-driven, multi-discipline workspace compares — honestly.",
    url: `${BASE}/compare/solidworks`,
    image: `${BASE}/og/compare-solidworks.png`,
    publisher: { '@type': 'Organization', name: 'Kerf', url: BASE },
  }),
  product: 'SOLIDWORKS',
  slug: 'solidworks',
}

/* -------------------------------------------------------------------------
 * Feature-matrix rows
 * ---------------------------------------------------------------------- */
const TABLE = [
  // Licensing & platform
  {
    group: 'Licensing & platform',
    feature: 'License',
    competitor: `${WEAK} Proprietary perpetual + maintenance or subscription`,
    kerf: `${GOOD} MIT open-core (permissive)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Cost',
    competitor: `${WEAK} ~US$4,000 perpetual + ~$1,500/yr maint; or ~$2,200/yr Connected`,
    kerf: `${GOOD} Free local install; pay-as-you-go hosted credits at cost`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Platform',
    competitor: `${WEAK} Windows only (native desktop)`,
    kerf: `${GOOD} Browser (hosted) + single-binary local (Win / macOS / Linux)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Offline / self-host',
    competitor: `${GOOD} Full offline (perpetual licence)`,
    kerf: `${GOOD} Full offline: pip install 'kerf[server]' + kerf serve (BYO Postgres)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Open source',
    competitor: `${GAP} Proprietary`,
    kerf: `${GOOD} MIT — full codebase on GitHub`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Maturity',
    competitor: `${GOOD} 30+ yr; millions of seats; dominant market share`,
    kerf: `${WEAK} Early-stage, < 2 yr public`,
  },

  // Modeling
  {
    group: 'Modeling',
    feature: 'Parametric B-rep',
    competitor: `${GOOD} Feature-tree B-rep (Parasolid kernel); industry standard`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/boss-with-draft`,
  },
  {
    group: 'Modeling',
    feature: 'History DAG / persistent naming',
    competitor: `${GOOD} Full history rollback; persistent references; flex features`,
    kerf: `${GOOD} Feature DAG + persistent face naming (Phase 4)`,
  },
  {
    group: 'Modeling',
    feature: 'Constraint sketcher',
    competitor: `${GOOD} Full parametric sketcher with relations manager`,
    kerf: `${GOOD} Sketcher v2 — all major constraints`,
  },
  {
    group: 'Modeling',
    feature: 'Direct modeling',
    competitor: `${GOOD} Instant3D direct push/pull + feature-based history`,
    kerf: `${WEAK} Feature-tree primary; limited direct editing`,
  },
  {
    group: 'Modeling',
    feature: 'Surfacing (NURBS)',
    competitor: `${GOOD} SurfaceWorks-class NURBS surfacing (Premium)`,
    kerf: `${WEAK} NURBS Phase 4 (early); trim-by-curve, C2 continuity`,
  },
  {
    group: 'Modeling',
    feature: 'Sheet metal',
    competitor: `${GOOD} Full sheet-metal workspace — flange, mitre, flat pattern, DXF`,
    kerf: `${GOOD} Flange + unfold + flat-pattern DXF`,
  },
  {
    group: 'Modeling',
    feature: 'Weldments',
    competitor: `${GOOD} Weldment profiles, structural members, gussets`,
    kerf: `${WEAK} Structural analysis via kerf-cad-core; no weldment workspace`,
  },

  // Assemblies
  {
    group: 'Assemblies',
    feature: 'Mates / joints',
    competitor: `${GOOD} Full mate system — coincident / concentric / gear / cam / screw`,
    kerf: `${GOOD} Full joint system — rigid/revolute/slider/cam/gear/pin-slot`,
  },
  {
    group: 'Assemblies',
    feature: 'Motion study / simulation',
    competitor: `${GOOD} Motion analysis, interference detection, collision`,
    kerf: `${GAP} Not yet`,
  },
  {
    group: 'Assemblies',
    feature: 'Large assembly mode',
    competitor: `${GOOD} Lightweight components, SpeedPak, large assembly mode`,
    kerf: `${WEAK} LOD mesh swapping (configurable threshold); less mature than SpeedPak`,
  },

  // CAM / fabrication
  {
    group: 'CAM / fabrication',
    feature: '2.5 / 3-axis CAM',
    competitor: `${WEAK} Requires CAMWorks / HSMWorks add-in (extra cost)`,
    kerf: `${GOOD} 3-axis CAM + tool DB (in-box)`,
  },
  {
    group: 'CAM / fabrication',
    feature: 'Multi-axis CAM',
    competitor: `${WEAK} Add-in required; HSMWorks 4/5-axis (extra cost)`,
    kerf: `${GOOD} 5-axis CAM 3+2 (in-box)`,
  },
  {
    group: 'CAM / fabrication',
    feature: 'Additive / slicing',
    competitor: `${WEAK} 3D Print output via partner tools`,
    kerf: `${GOOD} Slicing Tier 1 (in-box)`,
  },

  // Simulation
  {
    group: 'Simulation — mechanical',
    feature: 'FEM (static / thermal)',
    competitor: `${GOOD} SOLIDWORKS Simulation (add-in): static, thermal, fatigue`,
    kerf: `${WEAK} Linear static + thermal + nonlinear plasticity; not full multi-physics parity`,
  },
  {
    group: 'Simulation — mechanical',
    feature: 'CFD',
    competitor: `${GOOD} SOLIDWORKS Flow Simulation (add-in)`,
    kerf: `${GAP} Not yet`,
  },

  // Drawings & docs
  {
    group: 'Drawings & docs',
    feature: '2D drawings',
    competitor: `${GOOD} Full drawing environment + sheet templates`,
    kerf: `${GOOD} Multi-sheet drawings`,
  },
  {
    group: 'Drawings & docs',
    feature: 'GD&T',
    competitor: `${GOOD} ASME / ISO GD&T with DimXpert`,
    kerf: `${GOOD} ASME Y14.5 datum + tolerance framework`,
  },

  // Electronics
  {
    group: 'Electronics',
    feature: 'ECAD integration',
    competitor: `${WEAK} SOLIDWORKS PCB (Altium-derived, add-in); limited by default`,
    kerf: `${GOOD} Full hierarchical schematic + PCB layout in-box`,
  },
  {
    group: 'Electronics',
    feature: 'MCAD/ECAD co-design',
    competitor: `${WEAK} SOLIDWORKS PCB push/pull; limited vs Altium CoDesigner`,
    kerf: `${GOOD} Co-resident ECAD/MCAD; IDF + board STEP export`,
  },
  {
    group: 'Electronics',
    feature: 'SI / EMC / PDN / thermal (PCB)',
    competitor: `${GAP} External tools required`,
    kerf: `${GOOD} si_eye_wizard + emc_wizard + pdn_wizard + thermal_board — all in-box`,
  },

  // Domain breadth
  {
    group: 'Domain breadth',
    feature: 'Jewelry tooling',
    competitor: `${GAP} Generic CAD only — no jewelry modules`,
    kerf: `${GOOD} 40-module jewelry suite: ring v4, gemstones v2, settings v3/v4, chain v2`,
  },
  {
    group: 'Domain breadth',
    feature: 'Architecture / IFC',
    competitor: `${GAP} Not an AEC tool`,
    kerf: `${WEAK} IFC Tier 2 import + structural grid`,
  },

  // Kernel quality
  {
    group: 'Kernel quality',
    feature: 'Kernel',
    competitor: `${GOOD} Parasolid — industry-standard, extremely mature`,
    kerf: `${GOOD} OpenCASCADE (OCCT) — widely used open-source B-rep kernel`,
  },
  {
    group: 'Kernel quality',
    feature: 'Test coverage',
    competitor: `${GOOD} Decades of field validation across millions of files`,
    kerf: `${GOOD} 620 analytic-oracle kernel tests (exact closed-form references)`,
  },

  // Collaboration
  {
    group: 'Collaboration',
    feature: 'Multi-user cloud edit',
    competitor: `${WEAK} 3DExperience (separate SaaS product)`,
    kerf: `${GOOD} Cloud hosted multi-user + cloud-git project sync`,
  },
  {
    group: 'Collaboration',
    feature: 'Version control',
    competitor: `${WEAK} PDM Standard (local server) or 3DEXPERIENCE (cloud)`,
    kerf: `${GOOD} file_revisions (fine-grained undo) + cloud git (GitHub sync)`,
  },

  // Ecosystem & SDK
  {
    group: 'Ecosystem & SDK',
    feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits feature source per turn, doc-search backed`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'BYO LLM',
    competitor: `${GAP} Not applicable`,
    kerf: `${GOOD} BYO API key (kerf_byo bucket); any Anthropic/OpenAI compatible model`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'Scripting / API',
    competitor: `${GOOD} SOLIDWORKS API (COM/VBA/C#); deep automation`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'Add-in ecosystem',
    competitor: `${GOOD} Thousands of add-ins (CAM, FEA, rendering, PDM, ERP)`,
    kerf: `${WEAK} Early-stage; plugin architecture (kerf-* packages)`,
  },
  {
    group: 'Ecosystem & SDK',
    feature: 'Community & training',
    competitor: `${GOOD} Millions of users; MySolidWorks; certified resellers; VAR network`,
    kerf: `${WEAK} Early-stage, growing`,
  },
]

/* -------------------------------------------------------------------------
 * Page component
 * ---------------------------------------------------------------------- */
export default function SolidworksPage() {
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
            aria-hidden="true"
          >
            Compare
          </p>
          <h1
            className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight"
            aria-label="Kerf versus SOLIDWORKS comparison"
          >
            Kerf vs SOLIDWORKS
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            SOLIDWORKS is the dominant professional mechanical CAD platform with
            30+ years of refinement, millions of seats, a deep partner ecosystem,
            and the Parasolid kernel under the hood. Kerf will not out-SOLIDWORKS
            SOLIDWORKS on assembly motion, FEM, or add-in breadth — that is an
            honest statement. Where Kerf differs is in MIT open-core licensing,
            no Windows-only constraint, chat-native editing, no per-seat fee, and
            a multi-discipline workspace that unifies mechanical, electronics, and
            jewelry design without additional add-ins or subscriptions.
          </p>
        </div>

        {/* Where SOLIDWORKS is strong */}
        <Section title="Where SOLIDWORKS is strong">
          <ul
            className="flex flex-col gap-3"
            aria-label="SOLIDWORKS strengths"
          >
            <Li>
              <strong className="text-ink-100">Parasolid kernel and modeling depth.</strong>{' '}
              SOLIDWORKS runs on the Parasolid B-rep kernel — the same engine
              used by Siemens NX and Solid Edge. Decades of production hardening
              across millions of real-world files give it a reliability track
              record that newer kernels have not yet accumulated.
            </Li>
            <Li>
              <strong className="text-ink-100">Full assembly and motion simulation.</strong>{' '}
              A complete mate system (coincident, concentric, gear, cam, screw,
              slot), interference detection, motion analysis with contacts,
              and mass-property roll-up across large assemblies — mature and
              production-proven.
            </Li>
            <Li>
              <strong className="text-ink-100">FEM and CFD via add-ins.</strong>{' '}
              SOLIDWORKS Simulation (static, thermal, fatigue, drop-test) and
              Flow Simulation (CFD) are integrated add-ins that have been tuned
              by real engineering teams for years. Kerf has no structural FEM
              today.
            </Li>
            <Li>
              <strong className="text-ink-100">Weldments and structural framework.</strong>{' '}
              Structural-member profiles, weldment cut lists, gussets, and end
              treatments give fabricators a workflow purpose-built for structural
              steel and tubing that Kerf does not replicate.
            </Li>
            <Li>
              <strong className="text-ink-100">NURBS surfacing (Premium / SurfaceWorks).</strong>{' '}
              Class-A surface modelling tools for consumer products and automotive
              styling are mature in SOLIDWORKS Premium. Kerf&#8217;s NURBS Phase 4
              is early and scope-limited.
            </Li>
            <Li>
              <strong className="text-ink-100">Large assembly handling.</strong>{' '}
              Lightweight component mode, SpeedPak, and large assembly performance
              settings are well-tested workflows that enterprise mechanical teams
              rely on for thousand-part assemblies.
            </Li>
            <Li>
              <strong className="text-ink-100">Vast add-in and VAR ecosystem.</strong>{' '}
              Thousands of third-party add-ins — CAM (CAMWorks, HSMWorks), PDM
              (SOLIDWORKS PDM), rendering (KeyShot), ERP connectors, FEA, CFD —
              and a global network of certified resellers and value-added
              resellers (VARs) provide deep specialisation for every sub-domain.
            </Li>
            <Li>
              <strong className="text-ink-100">Drawings and DimXpert.</strong>{' '}
              Full drawing environment with sheet templates, DimXpert automated
              GD&amp;T annotation, and ASME / ISO standard compliance — a
              mature, production-tested 2D output workflow.
            </Li>
            <Li>
              <strong className="text-ink-100">Market standard and hiring pool.</strong>{' '}
              SOLIDWORKS proficiency is a near-universal requirement on mechanical
              engineering job descriptions. The community, certification programme,
              and training resources are unmatched.
            </Li>
          </ul>
        </Section>

        {/* Common SOLIDWORKS pain points */}
        <Section title="Common SOLIDWORKS pain points">
          <ul
            className="flex flex-col gap-3"
            aria-label="Common SOLIDWORKS pain points"
          >
            <Li>
              <strong className="text-ink-100">Cost and add-in stacking.</strong>{' '}
              The base perpetual licence is ~US$4,000 + ~$1,500/yr maintenance,
              but professional workflows typically require Simulation, CAM, PDM,
              and rendering add-ins — each with its own fee. A fully configured
              SOLIDWORKS Premium seat with key add-ins can exceed $15,000/seat/yr.
            </Li>
            <Li>
              <strong className="text-ink-100">Windows only.</strong>{' '}
              The desktop application is Windows-native. macOS and Linux engineers
              must virtualise or use a dedicated Windows machine — a meaningful
              overhead for cross-platform teams.
            </Li>
            <Li>
              <strong className="text-ink-100">CAM is an extra-cost add-in.</strong>{' '}
              Unlike some competitors, SOLIDWORKS ships no CAM by default. CAMWorks,
              HSMWorks for SOLIDWORKS, and similar products are separate purchases
              on top of the base licence.
            </Li>
            <Li>
              <strong className="text-ink-100">Cloud collaboration sold separately.</strong>{' '}
              3DExperience (the Dassault cloud overlay) is a separate product with
              its own subscription. Sharing and collaborating on SOLIDWORKS files
              across a distributed team requires a meaningful additional investment.
            </Li>
            <Li>
              <strong className="text-ink-100">No multi-discipline breadth.</strong>{' '}
              Electronics design requires a separate ECAD tool (or the limited
              SOLIDWORKS PCB add-in). Jewelry tooling does not exist. Teams with
              cross-discipline workloads must manage multiple software ecosystems
              with separate licences and file-exchange workflows.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf differs */}
        <Section title="Where Kerf differs">
          <ul
            className="flex flex-col gap-3"
            aria-label="Where Kerf differs from SOLIDWORKS"
          >
            <Li>
              <strong className="text-ink-100">MIT open-core, no seat fee.</strong>{' '}
              The full feature set is MIT-licensed and free to install locally.
              There is no $4,000 seat, no annual maintenance contract, no add-in
              stacking, and no commercial-use restriction.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow and BYO LLM.</strong>{' '}
              Describe a feature, sketch constraint, or assembly change in plain
              English; the model edits the feature-tree source backed by live
              doc-search. Bring your own Anthropic or compatible API key with
              zero billing routed through Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">CAM included in-box.</strong>{' '}
              3-axis CAM with tool DB and 5-axis 3+2 ship as part of the core
              product — no CAMWorks or HSMWorks add-in required.
            </Li>
            <Li>
              <strong className="text-ink-100">Cross-platform, browser + local binary.</strong>{' '}
              Runs in the browser (hosted SaaS) or as a single local binary on
              Windows, macOS, and Linux. No Parallels, no dedicated Windows box.
            </Li>
            <Li>
              <strong className="text-ink-100">Full ECAD in one workspace — no add-in.</strong>{' '}
              Hierarchical schematic, PCB layout, shove router, SPICE, IPC fab
              output, and the full pre-compliance simulation suite (SI, EMC, PDN,
              thermal) are built into the same workspace as the B-rep modeller,
              with no separate ECAD licence.
            </Li>
            <Li>
              <strong className="text-ink-100">
                Electronics pre-compliance simulation — in-box.
              </strong>{' '}
              <code className="text-kerf-300 font-mono text-xs">si_eye_wizard</code>,{' '}
              <code className="text-kerf-300 font-mono text-xs">pdn_wizard</code>,{' '}
              <code className="text-kerf-300 font-mono text-xs">emc_wizard</code>{' '}
              (FCC §15.109 + CISPR 32), and{' '}
              <code className="text-kerf-300 font-mono text-xs">thermal_board</code>{' '}
              analysis ship without any add-in. SOLIDWORKS has no equivalent at
              all by default.
            </Li>
            <Li>
              <strong className="text-ink-100">40-module jewelry domain.</strong>{' '}
              Ring v4, gemstones v2 (30 cuts), settings v3/v4, gem-seat v2,
              chain v2, findings, casting export, full cost panel, and PBR
              gem/metal viewport materials — a professional jewelry vertical
              that has no SOLIDWORKS counterpart.
            </Li>
            <Li>
              <strong className="text-ink-100">Cloud git built in.</strong>{' '}
              Every project gets fine-grained file revision history (undo) plus
              deliberate cloud-git commits with GitHub sync — no PDM server
              setup, no extra subscription.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk Python scripting.</strong>{' '}
              Automate B-rep, PCB, and jewelry workflows from a Python script on
              your own machine over HTTP/JSON-RPC — the same interface the LLM
              uses internally.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul
            className="flex flex-col gap-3"
            aria-label="Areas where Kerf is behind SOLIDWORKS today"
          >
            <Li>
              <strong className="text-ink-100">Assembly motion study.</strong>{' '}
              Kerf now matches SOLIDWORKS&#8217; joint type set (including gear,
              cam, pin-slot), but motion analysis, contact sets, and interference
              detection are not yet shipped in Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">FEM multi-physics depth and CFD.</strong>{' '}
              Kerf ships linear static, thermal, and nonlinear plasticity FEM, but
              SOLIDWORKS Simulation (fatigue, frequency, buckling, nonlinear) and
              Flow Simulation (CFD) are significantly more mature. CFD is not in
              Kerf.
            </Li>
            <Li>
              <strong className="text-ink-100">NURBS surfacing depth.</strong>{' '}
              SOLIDWORKS Premium&#8217;s surfacing tools are significantly ahead
              of Kerf&#8217;s NURBS Phase 4, which is early and scope-limited.
              Class-A surface modelling workflows are not available in Kerf today.
            </Li>
            <Li>
              <strong className="text-ink-100">Weldments workspace.</strong>{' '}
              SOLIDWORKS&#8217; structural member profiles, weldment cut lists,
              and gussets are a fabrication workflow Kerf does not replicate.
            </Li>
            <Li>
              <strong className="text-ink-100">Large assembly tooling.</strong>{' '}
              Lightweight components, SpeedPak, and large-assembly performance
              settings are well-tested SOLIDWORKS workflows with no Kerf
              equivalent today.
            </Li>
            <Li>
              <strong className="text-ink-100">SOLIDWORKS API depth.</strong>{' '}
              The SOLIDWORKS COM API has 20+ years of depth covering every
              feature, mate, and drawing entity. Kerf&#8217;s kerf-sdk is younger
              and covers the major workflows but lacks the API surface breadth.
            </Li>
            <Li>
              <strong className="text-ink-100">Add-in and VAR ecosystem.</strong>{' '}
              Thousands of certified third-party add-ins, a global VAR network,
              and decades of training content are irreplaceable near-term. Kerf
              is early-stage.
            </Li>
            <Li>
              <strong className="text-ink-100">Market standard in hiring.</strong>{' '}
              SOLIDWORKS on a resume is a near-universal mechanical engineering
              signal. Kerf cannot replace that signal for teams where tooling
              credentials matter.
            </Li>
          </ul>
        </Section>

        {/* Migration notes */}
        <Section title="Notes for SOLIDWORKS users considering Kerf">
          <ul
            className="flex flex-col gap-3"
            aria-label="Migration notes for SOLIDWORKS users"
          >
            <Li>
              <strong className="text-ink-100">What feels familiar.</strong>{' '}
              Parametric feature tree, constraint-based sketcher, multi-sheet
              drawings with GD&amp;T, sheet metal with flat pattern, cloud
              collaboration, and a Python scripting API all exist in Kerf with
              comparable intent.
            </Li>
            <Li>
              <strong className="text-ink-100">STEP is the migration path.</strong>{' '}
              Kerf imports STEP and IGES. Export from SOLIDWORKS to STEP first;
              the B-rep geometry transfers cleanly even though the feature history
              does not.
            </Li>
            <Li>
              <strong className="text-ink-100">CAM is where cost changes most.</strong>{' '}
              If your SOLIDWORKS workflow includes an add-in CAM licence, Kerf&#8217;s
              in-box 3-axis and 5-axis 3+2 CAM may reduce that cost immediately.
              The fidelity and post-processor breadth are younger, so validate
              your toolpaths carefully.
            </Li>
            <Li>
              <strong className="text-ink-100">Assembly-heavy workflows: expect gaps.</strong>{' '}
              Teams whose primary work is multi-thousand-part assemblies with
              motion simulation or interference detection will notice the
              capability difference quickly. Factor in ramp-up time if assembly
              is the primary workload.
            </Li>
            <Li>
              <strong className="text-ink-100">The ECAD + MCAD shift is the Kerf differentiator.</strong>{' '}
              If your team currently maintains separate ECAD and MCAD tools with
              a manual IDF or STEP handoff workflow, Kerf&#8217;s co-resident
              workspace removes that handoff boundary and adds an in-box
              electronics pre-compliance suite.
            </Li>
          </ul>
        </Section>

        {/* Side by side */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="SOLIDWORKS" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
