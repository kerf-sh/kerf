/**
 * /compare/platformio — Kerf vs PlatformIO (firmware / embedded)
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-19).
 *
 * PlatformIO is the leading open-source build system and IDE extension for
 * embedded / firmware development. It supports 50+ platforms (AVR, ESP32,
 * STM32, RP2040, RISC-V, …), 900+ boards, 10 000+ libraries, and integrates
 * with VS Code, CLion, and Atom. It handles toolchain management, library
 * dependency resolution, unit testing (Unity / GoogleTest / doctest), remote
 * debugging (OpenOCD, J-Link, pyOCD), and static analysis.
 *
 * Kerf does not ship a firmware build system. The comparison is honest about
 * that gap and focuses on where the tools are complementary: Kerf provides
 * the hardware design (PCB + mechanical) that the firmware runs on; PlatformIO
 * provides the firmware development workflow.
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
  title: 'Kerf vs PlatformIO — firmware & embedded development compared',
  description:
    'PlatformIO leads embedded firmware development. See where Kerf complements ' +
    'it for PCB design, mechanical co-design, and hardware-LLM workflows.',
  canonical: 'https://kerf.sh/compare/platformio',
  ogImage: 'https://kerf.sh/og/compare-platformio.png',
  jsonLd: JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Kerf vs PlatformIO — firmware & embedded development compared',
    description:
      'PlatformIO leads embedded firmware development. See where Kerf complements ' +
      'it for PCB design, mechanical co-design, and hardware-LLM workflows.',
    url: 'https://kerf.sh/compare/platformio',
    image: 'https://kerf.sh/og/compare-platformio.png',
    publisher: { '@type': 'Organization', name: 'Kerf', url: 'https://kerf.sh' },
  }),
}

/* -------------------------------------------------------------------------- */
/* Feature matrix                                                              */
/* -------------------------------------------------------------------------- */

const TABLE = [
  /* ── Licensing & platform ─────────────────────────────────────────────── */
  {
    group: 'Licensing & platform',
    feature: 'License',
    competitor: `${GOOD} Apache 2.0 open-source (PlatformIO Core)`,
    kerf: `${GOOD} MIT open-core (permissive)`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Cost',
    competitor: `${GOOD} Free Core; PlatformIO Plus from ~$15/mo`,
    kerf: `${GOOD} Free local; pay-as-you-go hosted`,
  },
  {
    group: 'Licensing & platform',
    feature: 'Platform',
    competitor: `${GOOD} VS Code / CLion extension; CLI; any OS`,
    kerf: `${GOOD} Browser + single-binary local (Win/macOS/Linux)`,
  },

  /* ── Firmware build & toolchain ───────────────────────────────────────── */
  {
    group: 'Firmware build & toolchain',
    feature: 'Build system / toolchain mgmt',
    competitor: `${GOOD} Unified build system — auto-downloads toolchains for 50+ platforms`,
    kerf: `${GAP} No firmware build system`,
  },
  {
    group: 'Firmware build & toolchain',
    feature: 'Platform / board support',
    competitor: `${GOOD} 50+ platforms, 900+ boards (AVR, STM32, ESP32, RP2040, RISC-V, …)`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Firmware build & toolchain',
    feature: 'Library management',
    competitor: `${GOOD} 10 000+ libraries; dependency resolver; LDF`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Firmware build & toolchain',
    feature: 'Framework support',
    competitor: `${GOOD} Arduino, ESP-IDF, Zephyr, Mbed, CMSIS, LibOpenCM3, …`,
    kerf: `${GAP} Not applicable`,
  },

  /* ── Testing & debug ───────────────────────────────────────────────────── */
  {
    group: 'Testing & debug',
    feature: 'Unit test framework integration',
    competitor: `${GOOD} Unity / GoogleTest / doctest — on-device + native`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Testing & debug',
    feature: 'Remote debugging',
    competitor: `${GOOD} OpenOCD / J-Link / pyOCD / ESP-Prog — breakpoints on-chip`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Testing & debug',
    feature: 'Static analysis',
    competitor: `${GOOD} cppcheck + PVS-Studio (Plus) integration`,
    kerf: `${GAP} Not applicable`,
  },
  {
    group: 'Testing & debug',
    feature: 'Serial monitor / device scanner',
    competitor: `${GOOD} Built-in serial monitor + device scanner`,
    kerf: `${GAP} Not applicable`,
  },

  /* ── Hardware design ───────────────────────────────────────────────────── */
  {
    group: 'Hardware design (PCB + mechanical)',
    feature: 'Schematic capture',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Hierarchical schematic + ERC + buses`,
  },
  {
    group: 'Hardware design (PCB + mechanical)',
    feature: 'PCB layout & routing',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} Push-and-shove router + DRC + IPC-2221B`,
  },
  {
    group: 'Hardware design (PCB + mechanical)',
    feature: 'Fabrication output (.hex / .bin / .uf2)',
    competitor: `${GOOD} Generates .hex / .bin / .uf2 / .elf firmware images`,
    kerf: `${GAP} Not applicable (hardware side: Gerber/IPC-2581/ODB++)`,
  },
  {
    group: 'Hardware design (PCB + mechanical)',
    feature: 'Fabrication output (Gerber / IPC-2581)',
    competitor: `${GAP} Not applicable`,
    kerf: `${GOOD} Gerber / Excellon / IPC-2581 / ODB++ fab pack`,
  },
  {
    group: 'Hardware design (PCB + mechanical)',
    feature: 'Mechanical CAD (enclosure / heatsink)',
    competitor: `${GAP} Separate tool required`,
    kerf: `${GOOD} OCCT B-rep, sketcher, sheet metal, GD&T drawings`,
  },

  /* ── Simulation ────────────────────────────────────────────────────────── */
  {
    group: 'Simulation',
    feature: 'SPICE / circuit simulation',
    competitor: `${GAP} Not included`,
    kerf: `${GOOD} SPICE + Monte-Carlo corners + model library`,
  },
  {
    group: 'Simulation',
    feature: 'Signal integrity / PDN / EMC',
    competitor: `${GAP} Not included`,
    kerf: `${GOOD} si_eye_wizard / pdn_wizard / emc_wizard (analytical)`,
  },
  {
    group: 'Simulation',
    feature: 'Thermal (board-level)',
    competitor: `${GAP} Not included`,
    kerf: `${GOOD} thermal_board — 2-D finite-difference steady-state`,
  },

  /* ── Interop ───────────────────────────────────────────────────────────── */
  {
    group: 'Interoperability',
    feature: 'Firmware hex / binary output',
    competitor: `${GOOD} .hex / .bin / .uf2 / .elf for every supported board`,
    kerf: `${GAP} No firmware toolchain`,
  },
  {
    group: 'Interoperability',
    feature: 'BOM / component data',
    competitor: `${WEAK} Library metadata; no distributor-linked BOM`,
    kerf: `${GOOD} BOM cost + distributor links + DFM checks`,
  },

  /* ── Ecosystem & AI ───────────────────────────────────────────────────── */
  {
    group: 'Ecosystem & AI',
    feature: 'Chat / LLM editing',
    competitor: `${WEAK} GitHub Copilot in VS Code (not PlatformIO-aware)`,
    kerf: `${GOOD} Chat-native — edits hardware source per turn, doc-search backed`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Scripting / automation',
    competitor: `${GOOD} Python scripting + CLI — CI-friendly`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC from your machine`,
  },
  {
    group: 'Ecosystem & AI',
    feature: 'Community / ecosystem',
    competitor: `${GOOD} Very large; active library/board contributions`,
    kerf: `${WEAK} Early-stage, growing`,
  },
]

/* -------------------------------------------------------------------------- */
/* Interop callout                                                             */
/* -------------------------------------------------------------------------- */

function InteropCallout() {
  return (
    <aside
      aria-label="Firmware hex and hardware interoperability story"
      className="mb-10 rounded-xl border border-kerf-300/30 bg-kerf-300/5 px-5 py-4"
    >
      <p className="text-sm font-semibold text-kerf-200 mb-1">
        Interop story — hardware + firmware as a single workflow
      </p>
      <p className="text-sm text-ink-300 leading-relaxed">
        Kerf produces the <strong className="text-ink-100">PCB fab pack</strong>{' '}
        (Gerber / IPC-2581 / ODB++) and the{' '}
        <strong className="text-ink-100">STEP / IDF mechanical bridge</strong>
        ; PlatformIO builds the{' '}
        <strong className="text-ink-100">.hex / .bin / .uf2</strong> firmware
        image that runs on the board. The two tools are complementary — a team
        designing an embedded product will use PlatformIO for firmware and Kerf
        (or KiCad) for hardware. The kerf-sdk lets you script BOM generation,
        schematic annotation, or DRC checks from the same CI pipeline that
        runs PlatformIO's unit tests.
      </p>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* Page component                                                              */
/* -------------------------------------------------------------------------- */

export default function KerfVsPlatformIOPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main
        aria-label="Kerf vs PlatformIO comparison"
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
      >
        <Breadcrumb />

        {/* Hero */}
        <header className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs PlatformIO
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            PlatformIO is the leading open-source firmware development platform:
            a unified build system, library manager, and debugging interface
            for 50+ embedded platforms and 900+ boards, tightly integrated
            with VS Code. Kerf is a hardware design tool — PCB schematic and
            layout, mechanical CAD, SPICE simulation, and pre-compliance
            analysis. The two tools do not compete; they are complementary
            halves of a full embedded product stack. This page documents each
            tool's domain honestly, and explains where they connect.
          </p>
        </header>

        {/* Where PlatformIO is strong */}
        <Section title="Where PlatformIO is strong">
          <ul className="flex flex-col gap-3" aria-label="PlatformIO strengths">
            <Li>
              <strong className="text-ink-100">Unified embedded build system.</strong>{' '}
              PlatformIO Core manages toolchain downloads, cross-compilation,
              and upload for 50+ platforms and 900+ boards. One{' '}
              <code className="text-kerf-200 text-xs bg-ink-800 px-1 rounded">
                platformio.ini
              </code>{' '}
              file replaces platform-specific IDE configuration for every
              target.
            </Li>
            <Li>
              <strong className="text-ink-100">10 000+ library ecosystem.</strong>{' '}
              The Library Dependency Finder (LDF) resolves transitive
              dependencies across Arduino, ESP-IDF, Zephyr, Mbed, and other
              frameworks — a mature, CI-friendly workflow.
            </Li>
            <Li>
              <strong className="text-ink-100">On-device unit testing.</strong>{' '}
              Unity, GoogleTest, and doctest run directly on target hardware or
              natively on the host, with a unified test runner and CI
              integration. This is a capability unique to firmware development.
            </Li>
            <Li>
              <strong className="text-ink-100">Hardware debugger integration.</strong>{' '}
              OpenOCD, J-Link, pyOCD, and ESP-Prog connect directly from the VS
              Code debug panel — breakpoints, watchpoints, and register
              inspection on chip, without external IDE tooling.
            </Li>
            <Li>
              <strong className="text-ink-100">Framework breadth.</strong>{' '}
              Arduino, ESP-IDF, Zephyr RTOS, Mbed, CMSIS, LibOpenCM3 — major
              embedded frameworks are first-class citizens with pre-configured
              build scripts and library scoping rules.
            </Li>
            <Li>
              <strong className="text-ink-100">CI-first design.</strong>{' '}
              PlatformIO Core is a Python CLI — trivially scriptable in GitHub
              Actions, GitLab CI, or Jenkins for build, test, and flash
              pipelines without a GUI.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf wins */}
        <Section title="Where Kerf wins">
          <ul className="flex flex-col gap-3" aria-label="Kerf differentiators">
            <Li>
              <strong className="text-ink-100">PCB design in the same tool as mechanical CAD.</strong>{' '}
              Schematic capture, push-and-shove routing, DRC, Gerber / IPC-2581
              fab pack, IDF MCAD bridge, and B-rep enclosure design are all
              co-resident — the workflow PlatformIO teams currently stitch
              together with KiCad plus a separate MCAD tool.
            </Li>
            <Li>
              <strong className="text-ink-100">SPICE + Monte-Carlo corner analysis.</strong>{' '}
              sim_corner sweeps min/typ/max and Monte-Carlo parameter variants;
              the SPICE engine handles AC, DC, and transient runs with a
              built-in model library. PlatformIO has no circuit simulation.
            </Li>
            <Li>
              <strong className="text-ink-100">Pre-compliance SI / PDN / EMC.</strong>{' '}
              si_eye_wizard, pdn_wizard, and emc_wizard give analytical
              pre-compliance estimates (FCC §15.109 / CISPR 32 Class B) at the
              board boundary — before a product goes to a test lab.
              PlatformIO does not address this.
            </Li>
            <Li>
              <strong className="text-ink-100">Chat-native hardware workflow.</strong>{' '}
              Describe a schematic change, routing constraint, or DRC rule in
              plain language; the LLM edits the hardware source directly,
              backed by live doc-search. This is hardware-aware LLM editing,
              not a generic Copilot autocomplete.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk CI integration.</strong>{' '}
              The kerf-sdk (PyPI) calls the same HTTP/JSON-RPC interface the
              LLM uses. Run BOM cost checks, schematic annotation, or DRC from
              the same CI pipeline that runs PlatformIO unit tests.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, browser + local.</strong>{' '}
              Free local install via brew or curl, hosted SaaS option,
              permissive MIT licence. No licence server.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where PlatformIO leads">
          <ul className="flex flex-col gap-3" aria-label="Areas where PlatformIO leads">
            <Li>
              <strong className="text-ink-100">Kerf has no firmware build system.</strong>{' '}
              PlatformIO's toolchain management, framework support, and upload
              pipeline have no equivalent in Kerf. Embedded teams will still
              need PlatformIO (or a comparable system) for firmware.
            </Li>
            <Li>
              <strong className="text-ink-100">No on-device testing.</strong>{' '}
              Unity/GoogleTest running on target hardware is unique to PlatformIO's
              scope. Kerf's test surface is for hardware design validation (DRC,
              ERC), not firmware correctness.
            </Li>
            <Li>
              <strong className="text-ink-100">No hardware debugger.</strong>{' '}
              OpenOCD / J-Link integration is core to PlatformIO. Kerf does not
              address JTAG/SWD debugging.
            </Li>
            <Li>
              <strong className="text-ink-100">Library ecosystem gap.</strong>{' '}
              PlatformIO's 10 000+ embedded library registry is a mature resource
              with active community curation. Kerf's component catalog is hardware
              parts (schematic symbols, footprints), not firmware libraries.
            </Li>
            <Li>
              <strong className="text-ink-100">PCB maturity vs KiCad.</strong>{' '}
              Embedded teams already using KiCad alongside PlatformIO have a
              deeply validated PCB workflow. Kerf's PCB tooling is newer and
              less battle-tested, particularly for advanced HDI and high-speed
              differential routing.
            </Li>
          </ul>
        </Section>

        <InteropCallout />

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="PlatformIO" />
          <TableFooter />
        </Section>

        <FairnessNote />
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}
