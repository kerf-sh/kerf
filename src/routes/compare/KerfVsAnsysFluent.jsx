/**
 * /compare/ansys-fluent — Kerf vs ANSYS Fluent / ANSYS Mechanical (aerospace CFD/FEM)
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-19).
 *
 * ANSYS Fluent is the industry-dominant commercial CFD solver; ANSYS Mechanical
 * is the equivalent for structural FEM. Together they cover the principal
 * aerospace simulation disciplines: aerodynamics, aeroelasticity, heat transfer,
 * thermal-structural coupling, and fatigue. Both are multi-thousand-dollar
 * annual licences, Windows/Linux only, closed source, and validated against
 * aerospace certifying authority standards (FAA, EASA, DO-178C / DO-160).
 *
 * Kerf does not ship a CFD solver or a structural FEM engine. The comparison
 * is honest about that gap. The focus is on where Kerf provides value in the
 * same aerospace project: parametric CAD (geometry for CFD pre-processing),
 * GD&T drawing packages, mechanical CAD for fixtures and brackets, PCB co-
 * design for avionics, and the LLM-native workflow that neither ANSYS tool
 * provides.
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
/* Inline meta                                                                 */
/* -------------------------------------------------------------------------- */

const meta = {
  title: 'Kerf vs ANSYS Fluent — aerospace CFD & FEM compared',
  description:
    'ANSYS Fluent and Mechanical lead aerospace CFD/FEM. See where Kerf fits ' +
    'for CAD geometry, avionics PCB design, and LLM-native engineering workflows.',
  canonical: 'https://kerf.sh/compare/ansys-fluent',
  ogImage: 'https://kerf.sh/og/compare-ansys-fluent.png',
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Kerf vs ANSYS Fluent — aerospace CFD & FEM compared',
    description:
      'ANSYS Fluent and Mechanical lead aerospace CFD/FEM. See where Kerf fits ' +
      'for CAD geometry, avionics PCB design, and LLM-native engineering workflows.',
    url: 'https://kerf.sh/compare/ansys-fluent',
    image: 'https://kerf.sh/og/compare-ansys-fluent.png',
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
    competitor: `${WEAK} Proprietary; annual licence + maintenance`,
    kerf: `${GOOD} MIT open-core (permissive)`,
  },
  {
    group: 'Licensing & cost',
    feature: 'Cost',
    competitor: `${WEAK} Tens of thousands USD/yr per seat`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted`,
  },
  {
    group: 'Licensing & cost',
    feature: 'OS / platform',
    competitor: `${WEAK} Windows + Linux (no browser, no macOS)`,
    kerf: `${GOOD} Browser + single-binary (Win/macOS/Linux)`,
  },

  /* ── CAD geometry ──────────────────────────────────────────────────────── */
  {
    group: 'CAD geometry',
    feature: 'Parametric B-rep CAD',
    competitor: `${WEAK} SpaceClaim / Discovery bundled — limited feature history`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/fillet/draft`,
  },
  {
    group: 'CAD geometry',
    feature: 'Constraint sketcher',
    competitor: `${WEAK} SpaceClaim direct modelling; limited parametric sketch`,
    kerf: `${GOOD} Sketcher v2 — full geom + dim constraints`,
  },
  {
    group: 'CAD geometry',
    feature: 'STEP / IGES import (for meshing)',
    competitor: `${GOOD} STEP / IGES / Parasolid / ACIS import for meshing`,
    kerf: `${GOOD} STEP / IGES / DXF / FreeCAD import (source geometry)`,
  },
  {
    group: 'CAD geometry',
    feature: 'Geometry clean-up / de-featuring',
    competitor: `${GOOD} SpaceClaim geometry prep — void-fill, de-feature, share-topology`,
    kerf: `${WEAK} Boolean operations; no dedicated geometry clean-up for meshing`,
  },

  /* ── CFD (aerodynamics / heat transfer) ───────────────────────────────── */
  {
    group: 'CFD (aerodynamics)',
    feature: 'Navier-Stokes CFD solver',
    competitor: `${GOOD} Fluent — industry-leading pressure-based + density-based solver`,
    kerf: `${GAP} No CFD solver`,
  },
  {
    group: 'CFD (aerodynamics)',
    feature: 'Turbulence models (RANS / LES / DES)',
    competitor: `${GOOD} k-ε, k-ω, SST, RSM, SAS-SST, DES, LES, …`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'CFD (aerodynamics)',
    feature: 'Conjugate heat transfer (CHT)',
    competitor: `${GOOD} Multi-region CHT; solid + fluid coupling`,
    kerf: `${GAP} Not applicable (board-level thermal only)`,
  },
  {
    group: 'CFD (aerodynamics)',
    feature: 'Combustion / reacting flows',
    competitor: `${GOOD} Premixed / non-premixed / partially premixed; PPDF`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'CFD (aerodynamics)',
    feature: 'FSI (fluid-structure interaction)',
    competitor: `${GOOD} Two-way FSI via Fluent + Mechanical coupling`,
    kerf: `${GAP} Not applicable`,
  },

  /* ── Structural FEM ────────────────────────────────────────────────────── */
  {
    group: 'Structural FEM',
    feature: 'Linear / nonlinear static FEM',
    competitor: `${GOOD} ANSYS Mechanical — static, modal, buckling, fatigue`,
    kerf: `${GAP} No structural FEM`,
  },
  {
    group: 'Structural FEM',
    feature: 'Fatigue / damage tolerance',
    competitor: `${GOOD} nCode DesignLife / ANSYS fatigue module; fracture mechanics`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Structural FEM',
    feature: 'Composite / laminate analysis',
    competitor: `${GOOD} ACP (ANSYS Composite PrepPost) — lay-up, failure criteria`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Structural FEM',
    feature: 'Board-level thermal (2-D FD)',
    competitor: `${GAP} Not the scope of ANSYS Mechanical`,
    kerf: `${GOOD} thermal_board — 2-D finite-difference steady-state heat map`,
  },

  /* ── Meshing ───────────────────────────────────────────────────────────── */
  {
    group: 'Meshing',
    feature: 'Meshing (volume / surface)',
    competitor: `${GOOD} ANSYS Meshing — patch-conforming, sweep, multi-zone, mosaic`,
    kerf: `${GAP} No volumetric meshing for FEA / CFD`,
  },

  /* ── Drawings & documentation ─────────────────────────────────────────── */
  {
    group: 'Drawings & documentation',
    feature: '2D technical drawings',
    competitor: `${WEAK} Not a primary ANSYS function; requires separate CAD tool`,
    kerf: `${GOOD} Multi-sheet drawings — views, sections, BOM`,
  },
  {
    group: 'Drawings & documentation',
    feature: 'GD&T (ASME Y14.5)',
    competitor: `${WEAK} Via the CAD tool (SpaceClaim / Discovery); not native in Fluent`,
    kerf: `${GOOD} ASME Y14.5 datum + tolerance framework`,
  },

  /* ── Avionics / electronics ───────────────────────────────────────────── */
  {
    group: 'Avionics & electronics',
    feature: 'PCB schematic + layout',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Full EDA — schematic, push-and-shove routing, DRC`,
  },
  {
    group: 'Avionics & electronics',
    feature: 'SI / PDN / EMC pre-compliance',
    competitor: `${GAP} Separate tool (ANSYS HFSS / SIwave); separate licence`,
    kerf: `${GOOD} si_eye_wizard / pdn_wizard / emc_wizard (analytical)`,
  },
  {
    group: 'Avionics & electronics',
    feature: 'STEP MCAD ↔ PCB bridge',
    competitor: `${GAP} Via ECAD tool in the flow; not native to Fluent`,
    kerf: `${GOOD} IDF MCAD bridge + board STEP in-box`,
  },

  /* ── Interop ───────────────────────────────────────────────────────────── */
  {
    group: 'Interoperability',
    feature: 'STEP / IGES B-rep',
    competitor: `${GOOD} STEP / IGES import as mesh source geometry`,
    kerf: `${GOOD} STEP / IGES round-trip (source CAD)`,
  },
  {
    group: 'Interoperability',
    feature: 'CFD mesh export (for external meshing)',
    competitor: `${GOOD} Fluent .msh, CGNS, Ensight, Tecplot output`,
    kerf: `${GAP} No CFD mesh output`,
  },

  /* ── Ecosystem & AI ───────────────────────────────────────────────────── */
  {
    group: 'Ecosystem & AI',
    feature: 'Chat / LLM editing',
    competitor: `${GAP} No LLM-native workflow (as of 2026)`,
    kerf: `${GOOD} Chat-native — edits design source per turn, doc-search backed`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Scripting / automation',
    competitor: `${GOOD} Fluent TUI / Python + Mechanical ACT scripting`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC from your machine`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Certification / DO-160 support',
    competitor: `${GOOD} Validated against aerospace authority requirements`,
    kerf: `${WEAK} Not validated for aerospace sign-off`,
  },
]

/* -------------------------------------------------------------------------- */
/* Interop callout                                                             */
/* -------------------------------------------------------------------------- */

function InteropCallout() {
  return (
    <aside
      aria-label="STEP geometry interoperability story for CFD workflows"
      className="mb-10 rounded-xl border border-kerf-300/30 bg-kerf-300/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-kerf-200 mb-1">
        Interop story — STEP geometry as the bridge to CFD
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        Kerf exports <strong className="text-ink-100">STEP (AP203/AP214)</strong>{' '}
        — the standard geometry interchange format that ANSYS Fluent and
        ANSYS Meshing import for CFD pre-processing. An aerospace component
        designed in Kerf (airfoil cross-section, bracket, avionics enclosure)
        can flow directly into the ANSYS meshing and simulation pipeline via
        a STEP hand-off, without geometry re-modelling. GD&T drawings from
        Kerf also accompany the STEP file for manufacturing review.
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
      aria-label="Scope disclaimer for aerospace simulation"
      className="mb-10 rounded-xl border border-amber-500/30 bg-amber-500/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-amber-200 mb-1">
        Scope — Kerf does not replace aerospace CFD or FEM
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        ANSYS Fluent and ANSYS Mechanical are mature, aerospace-validated
        multi-physics solvers. Kerf has no CFD solver, no structural FEM
        engine, and no volumetric meshing. Aerospace teams need these tools
        for aerodynamics, aeroelasticity, heat-transfer, fatigue, and
        DO-160 / DO-178C compliance. Where Kerf fits is at the design
        geometry stage (parametric CAD, STEP export for meshing), at the
        avionics board boundary (PCB + MCAD co-design, SI / PDN / EMC
        pre-compliance), and in the documentation layer (GD&T drawings,
        BOM). Kerf is a complement to the ANSYS simulation stack, not a
        replacement.
      </p>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* Page component                                                              */
/* -------------------------------------------------------------------------- */

export default function KerfVsAnsysFluentPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        aria-label="Kerf vs ANSYS Fluent comparison"
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
      >
        <Breadcrumb />

        {/* Hero */}
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs ANSYS Fluent
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            ANSYS Fluent is the industry-dominant commercial CFD solver; ANSYS
            Mechanical is the equivalent for structural FEM. Together they
            cover the core aerospace simulation disciplines — aerodynamics,
            conjugate heat transfer, aeroelasticity, fatigue, and composite
            analysis. Kerf is not a CFD or FEM tool. Where it fits in an
            aerospace programme is at the geometry and documentation stage
            (parametric CAD and GD&T drawings to feed CFD pre-processing), at
            the avionics hardware boundary (PCB + mechanical co-design), and
            as a chat-native workflow for early-stage design iteration before
            a full simulation run.
          </p>
        </header>

        <ScopeCallout />

        {/* Where ANSYS Fluent / Mechanical is strong */}
        <Section title="Where ANSYS Fluent and Mechanical are strong">
          <ul className="flex flex-col gap-3" aria-label="ANSYS Fluent and Mechanical strengths">
            <Li>
              <strong className="text-ink-100">Industry-standard CFD solver.</strong>{' '}
              Fluent's pressure-based and density-based Navier-Stokes solvers
              cover incompressible and compressible flow, turbulence (RANS,
              LES, DES, SAS), combustion, multiphase, and conjugate heat
              transfer. Every major aerospace OEM and research institution runs
              Fluent.
            </Li>
            <Li>
              <strong className="text-ink-100">Structural FEM depth.</strong>{' '}
              ANSYS Mechanical handles linear and nonlinear static, modal,
              buckling, fatigue, and fracture mechanics analysis — validated for
              aerospace structural certification workflows.
            </Li>
            <Li>
              <strong className="text-ink-100">Composites and aeroelasticity.</strong>{' '}
              ANSYS Composite PrepPost (ACP) covers lay-up and failure criteria
              for composite structures. Two-way FSI coupling between Fluent and
              Mechanical addresses aeroelasticity — wing flutter, panel buzz,
              thermal-structural cycling.
            </Li>
            <Li>
              <strong className="text-ink-100">Aerospace certification alignment.</strong>{' '}
              Both tools have been used in programmes subject to FAA, EASA, and
              RTCA DO-160 / DO-178C review processes. The solver validation
              documentation is deep and peer-reviewed.
            </Li>
            <Li>
              <strong className="text-ink-100">High-quality meshing.</strong>{' '}
              ANSYS Meshing's patch-conforming, sweep, multi-zone, and mosaic
              algorithms handle complex aerospace geometries with
              boundary-layer refinement suitable for wall-resolved LES and
              turbomachinery.
            </Li>
            <Li>
              <strong className="text-ink-100">Enterprise ecosystem.</strong>{' '}
              Parametric optimisation (ANSYS Workbench), adjoint-based shape
              optimisation, topology optimisation (ANSYS Mechanical), HPC
              licensing, and a dedicated FAE support programme.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf wins */}
        <Section title="Where Kerf wins">
          <ul className="flex flex-col gap-3" aria-label="Kerf differentiators">
            <Li>
              <strong className="text-ink-100">Parametric CAD that feeds CFD pre-processing.</strong>{' '}
              Kerf's OCCT feature tree produces clean STEP geometry that imports
              directly into ANSYS Meshing for CFD pre-processing. An airfoil,
              nacelle, bracket, or avionics box modelled in Kerf can flow into
              the ANSYS pipeline via a standard STEP hand-off.
            </Li>
            <Li>
              <strong className="text-ink-100">GD&T drawings for manufacturing review.</strong>{' '}
              Multi-sheet technical drawings with ASME Y14.5 datums, tolerance
              frameworks, section views, and BOM tables accompany the STEP file
              — covering the documentation a fabrication or review package
              requires. ANSYS Fluent does not produce engineering drawings.
            </Li>
            <Li>
              <strong className="text-ink-100">Avionics PCB and MCAD co-design.</strong>{' '}
              Integrated schematic capture, push-and-shove PCB routing, DRC,
              IDF MCAD bridge, and B-rep enclosure design are all in-box. The
              electronics hardware that ANSYS Mechanical addresses as a thermal
              load is designed in Kerf alongside the structure.
            </Li>
            <Li>
              <strong className="text-ink-100">Board-level SI / PDN / EMC pre-compliance.</strong>{' '}
              Kerf's analytical si_eye_wizard, pdn_wizard, and emc_wizard cover
              avionics board concerns (HIRF sensitivity, conducted emissions)
              before a full HFSS or SIwave run. ANSYS covers this domain with
              separate, additional-cost products.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native workflow for early-stage design.</strong>{' '}
              Describe a geometry change, tolerance update, or drawing annotation
              in plain language; the LLM edits the design source directly,
              backed by doc-search. Faster iteration before geometry is handed
              to the ANSYS pipeline.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, zero licence overhead.</strong>{' '}
              Free local install via brew or curl. No licence server, no annual
              contract, no HPC token consumption for design geometry work.
              Accessible to university research groups and small aerospace
              startups.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where ANSYS Fluent and Mechanical lead">
          <ul className="flex flex-col gap-3" aria-label="Areas where ANSYS Fluent and Mechanical lead">
            <Li>
              <strong className="text-ink-100">No CFD solver.</strong>{' '}
              Kerf has no Navier-Stokes CFD engine, no turbulence models, and
              no combustion solver. Aerodynamic loads, heat-transfer coefficients,
              and wake studies require ANSYS Fluent or an equivalent solver.
            </Li>
            <Li>
              <strong className="text-ink-100">No structural FEM.</strong>{' '}
              Modal analysis, static stress, fatigue, fracture mechanics, and
              composites analysis all require ANSYS Mechanical or an equivalent
              FEM package. Kerf has none of this.
            </Li>
            <Li>
              <strong className="text-ink-100">No volumetric meshing.</strong>{' '}
              CFD and FEM both require high-quality volumetric meshes. ANSYS
              Meshing's multi-zone and mosaic algorithms are purpose-built for
              this; Kerf exports B-rep geometry only.
            </Li>
            <Li>
              <strong className="text-ink-100">No aerospace certification validation.</strong>{' '}
              ANSYS tools carry solver validation reports accepted by FAA, EASA,
              and RTCA. Kerf has no equivalent certification basis.
            </Li>
            <Li>
              <strong className="text-ink-100">Geometry clean-up tooling is basic.</strong>{' '}
              ANSYS SpaceClaim has dedicated de-featuring, void-fill, and shared-
              topology preparation workflows for meshing. Kerf's boolean
              operations cover CAD authoring, not mesh-preparation geometry repair.
            </Li>
            <Li>
              <strong className="text-ink-100">No HPC / distributed solving.</strong>{' '}
              Fluent scales across hundreds of cores via MPI decomposition and
              ANSYS HPC licensing. Kerf has no parallel solver.
            </Li>
          </ul>
        </Section>

        <InteropCallout />

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="ANSYS Fluent / Mechanical" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
