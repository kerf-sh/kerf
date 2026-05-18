// sectorCommandIndex.js — searchable command index for the new sector tooling.
//
// Sectors: Silicon, Firmware, Aerospace, PLC, Atopile.
//
// Each entry:
//   { id, label, description, keywords, action_type, target, sector }
//
// action_type is one of:
//   'route'       — navigate to a URL / route path (target is a path string)
//   'create_file' — scaffold a new file of a given template (target is template name)
//   'open_docs'   — open a documentation page (target is a URL or docs path)
//
// fuzzyMatch(query, entries) — case-insensitive substring + keyword match,
// scored and ranked. Returns entries enriched with a `score` field, highest
// first, empty array when nothing matches.

// ---------------------------------------------------------------------------
// Index
// ---------------------------------------------------------------------------

/** @type {Array<import('./sectorCommandIndex').SectorCommand>} */
export const SECTOR_COMMANDS = [
  // ── Silicon ───────────────────────────────────────────────────────────────
  {
    id: 'silicon-new-vhdl',
    sector: 'silicon',
    label: 'New VHDL file',
    description: 'Scaffold a new VHDL hardware description file in this project',
    keywords: ['vhdl', 'hdl', 'hardware', 'silicon', 'fpga', 'asic', 'rtl', 'synthesis'],
    action_type: 'create_file',
    target: 'vhdl',
  },
  {
    id: 'silicon-new-verilog',
    sector: 'silicon',
    label: 'New Verilog file',
    description: 'Scaffold a new Verilog hardware description file in this project',
    keywords: ['verilog', 'sv', 'systemverilog', 'hdl', 'hardware', 'silicon', 'fpga', 'asic', 'rtl'],
    action_type: 'create_file',
    target: 'verilog',
  },
  {
    id: 'silicon-new-spice',
    sector: 'silicon',
    label: 'New SPICE deck',
    description: 'Create a new SPICE netlist for analog / mixed-signal simulation',
    keywords: ['spice', 'ngspice', 'ltspice', 'netlist', 'analog', 'simulation', 'circuit', 'silicon'],
    action_type: 'create_file',
    target: 'spice',
  },
  {
    id: 'silicon-layout-viewer',
    sector: 'silicon',
    label: 'Open layout viewer',
    description: 'Open the IC / PCB layout viewer for this project',
    keywords: ['layout', 'viewer', 'gds', 'gdsii', 'klayout', 'silicon', 'ic', 'chip', 'floorplan'],
    action_type: 'route',
    target: '/silicon/layout',
  },
  {
    id: 'silicon-sky130-layers',
    sector: 'silicon',
    label: 'View SKY130 PDK layers',
    description: 'Browse the SkyWater SKY130 process design kit layer definitions',
    keywords: ['sky130', 'skywater', 'pdk', 'process', 'layers', 'silicon', 'open', 'foundry', 'node', '130nm'],
    action_type: 'open_docs',
    target: '/docs/silicon/sky130-layers',
  },

  // ── Firmware ──────────────────────────────────────────────────────────────
  {
    id: 'firmware-new-arduino',
    sector: 'firmware',
    label: 'New Arduino sketch',
    description: 'Scaffold a new Arduino (.ino) sketch for embedded development',
    keywords: ['arduino', 'ino', 'sketch', 'firmware', 'embedded', 'microcontroller', 'avr', 'esp', 'c++'],
    action_type: 'create_file',
    target: 'arduino',
  },
  {
    id: 'firmware-new-fw-json',
    sector: 'firmware',
    label: 'New .fw.json project',
    description: 'Create a new firmware project manifest (.fw.json)',
    keywords: ['fw', 'json', 'firmware', 'manifest', 'project', 'embedded', 'build'],
    action_type: 'create_file',
    target: 'fw.json',
  },
  {
    id: 'firmware-build',
    sector: 'firmware',
    label: 'Build firmware',
    description: 'Compile and build the firmware binary for the current target',
    keywords: ['build', 'compile', 'firmware', 'embedded', 'binary', 'elf', 'hex', 'flash'],
    action_type: 'route',
    target: '/firmware/build',
  },
  {
    id: 'firmware-upload',
    sector: 'firmware',
    label: 'Upload firmware',
    description: 'Flash the built firmware binary to a connected device',
    keywords: ['upload', 'flash', 'program', 'firmware', 'device', 'embedded', 'jtag', 'swd', 'bootloader'],
    action_type: 'route',
    target: '/firmware/upload',
  },
  {
    id: 'firmware-serial-monitor',
    sector: 'firmware',
    label: 'Open serial monitor',
    description: 'Open the serial / UART monitor to communicate with a connected device',
    keywords: ['serial', 'monitor', 'uart', 'usb', 'console', 'terminal', 'firmware', 'debug', 'log'],
    action_type: 'route',
    target: '/firmware/serial',
  },

  // ── Aerospace ─────────────────────────────────────────────────────────────
  {
    id: 'aerospace-vlm',
    sector: 'aerospace',
    label: 'Run VLM (vortex-lattice)',
    description: 'Execute a vortex-lattice method aerodynamic analysis on the current geometry',
    keywords: ['vlm', 'vortex', 'lattice', 'aero', 'aerodynamic', 'aerospace', 'lift', 'drag', 'panel', 'avl'],
    action_type: 'route',
    target: '/aerospace/vlm',
  },
  {
    id: 'aerospace-flutter',
    sector: 'aerospace',
    label: 'Solve flutter',
    description: 'Run a flutter / aeroelastic stability analysis on the current model',
    keywords: ['flutter', 'aeroelastic', 'stability', 'aerospace', 'vibration', 'modal', 'frequency', 'nasaem'],
    action_type: 'route',
    target: '/aerospace/flutter',
  },
  {
    id: 'aerospace-orbital',
    sector: 'aerospace',
    label: 'Compute orbital transfer',
    description: 'Calculate a Hohmann or bi-elliptic orbital transfer delta-v budget',
    keywords: ['orbital', 'transfer', 'hohmann', 'delta-v', 'dv', 'spacecraft', 'orbit', 'maneuver', 'aerospace'],
    action_type: 'route',
    target: '/aerospace/orbital',
  },
  {
    id: 'aerospace-material-lookup',
    sector: 'aerospace',
    label: 'Look up aerospace material',
    description: 'Search the aerospace materials database (Al alloys, Ti, CFRP, Inconel …)',
    keywords: ['material', 'aluminum', 'titanium', 'cfrp', 'composite', 'inconel', 'aerospace', 'alloy', 'strength'],
    action_type: 'open_docs',
    target: '/docs/aerospace/materials',
  },

  // ── PLC ───────────────────────────────────────────────────────────────────
  {
    id: 'plc-new-ladder',
    sector: 'plc',
    label: 'New ladder program',
    description: 'Create a new IEC 61131-3 ladder logic (.plc.ld) program',
    keywords: ['ladder', 'ld', 'plc', 'iec', '61131', 'logic', 'rung', 'coil', 'contact', 'automation'],
    action_type: 'create_file',
    target: 'ladder',
  },
  {
    id: 'plc-new-st',
    sector: 'plc',
    label: 'New ST program',
    description: 'Create a new IEC 61131-3 Structured Text (.plc.st) program',
    keywords: ['st', 'structured', 'text', 'plc', 'iec', '61131', 'automation', 'program', 'function-block'],
    action_type: 'create_file',
    target: 'st',
  },
  {
    id: 'plc-hmi-tester',
    sector: 'plc',
    label: 'Open HMI tester',
    description: 'Launch the human-machine interface tester to simulate panel interactions',
    keywords: ['hmi', 'tester', 'human', 'machine', 'interface', 'plc', 'panel', 'simulate', 'scada'],
    action_type: 'route',
    target: '/plc/hmi',
  },
  {
    id: 'plc-load-example',
    sector: 'plc',
    label: 'Load PLC example',
    description: 'Load a starter PLC example program from the template library',
    keywords: ['example', 'template', 'starter', 'plc', 'sample', 'demo', 'ladder', 'st'],
    action_type: 'route',
    target: '/plc/examples',
  },

  // ── PLC (extra) ───────────────────────────────────────────────────────────
  {
    id: 'plc-simulate',
    sector: 'plc',
    label: 'Simulate PLC scan cycle',
    description: 'Run a software simulation of the PLC scan cycle without hardware',
    keywords: ['simulate', 'scan', 'cycle', 'plc', 'software', 'test', 'virtual', 'iec', '61131'],
    action_type: 'route',
    target: '/plc/simulate',
  },

  // ── Aerospace (extra) ─────────────────────────────────────────────────────
  {
    id: 'aerospace-cfd',
    sector: 'aerospace',
    label: 'Run CFD panel solve',
    description: 'Execute a computational fluid dynamics panel method solve for drag estimation',
    keywords: ['cfd', 'fluid', 'dynamics', 'panel', 'drag', 'aerospace', 'euler', 'navier-stokes'],
    action_type: 'route',
    target: '/aerospace/cfd',
  },

  // ── Silicon (extra) ───────────────────────────────────────────────────────
  {
    id: 'silicon-drc-check',
    sector: 'silicon',
    label: 'Run DRC check',
    description: 'Execute a design rule check on the current IC layout',
    keywords: ['drc', 'design', 'rule', 'check', 'layout', 'silicon', 'verification', 'gds', 'klayout'],
    action_type: 'route',
    target: '/silicon/drc',
  },

  // ── Firmware (extra) ──────────────────────────────────────────────────────
  {
    id: 'firmware-debug-session',
    sector: 'firmware',
    label: 'Start debug session',
    description: 'Launch a GDB / OpenOCD debug session connected to a target device',
    keywords: ['debug', 'gdb', 'openocd', 'jtag', 'swd', 'firmware', 'breakpoint', 'step', 'embedded'],
    action_type: 'route',
    target: '/firmware/debug',
  },

  // ── Atopile ───────────────────────────────────────────────────────────────
  {
    id: 'atopile-new-ato',
    sector: 'atopile',
    label: 'New .ato file',
    description: 'Scaffold a new atopile (.ato) hardware description file',
    keywords: ['ato', 'atopile', 'hardware', 'description', 'hdl', 'component', 'module', 'circuit'],
    action_type: 'create_file',
    target: 'ato',
  },
  {
    id: 'atopile-compile',
    sector: 'atopile',
    label: 'Compile .ato to Circuit JSON',
    description: 'Run the atopile compiler to produce a Circuit JSON netlist from the current .ato source',
    keywords: ['compile', 'ato', 'atopile', 'circuit', 'json', 'netlist', 'build', 'output'],
    action_type: 'route',
    target: '/atopile/compile',
  },
  {
    id: 'atopile-to-jsx',
    sector: 'atopile',
    label: 'Convert .ato to JSX',
    description: 'Transpile the current .ato module into a React JSX circuit component',
    keywords: ['convert', 'ato', 'atopile', 'jsx', 'react', 'component', 'transpile', 'circuit'],
    action_type: 'route',
    target: '/atopile/to-jsx',
  },
]

// ---------------------------------------------------------------------------
// fuzzyMatch
// ---------------------------------------------------------------------------

/**
 * Match a free-text query against the sector command index.
 *
 * Scoring rubric (additive):
 *   +10  exact whole-word match in label (case-insensitive)
 *   +6   substring match in label
 *   +4   substring match in description
 *   +5   exact keyword match in keywords array
 *   +3   partial keyword match (query token is prefix of a keyword)
 *
 * Multi-token queries: each token is scored independently; scores are summed.
 * Results with score === 0 are excluded.
 *
 * @param {string} query
 * @param {Array<object>} [entries=SECTOR_COMMANDS]
 * @returns {Array<object & { score: number }>} — entries enriched with `score`,
 *   sorted descending by score (best match first).
 */
export function fuzzyMatch(query, entries = SECTOR_COMMANDS) {
  if (!query || !query.trim()) return []

  const tokens = query
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 0)

  if (tokens.length === 0) return []

  const scored = entries.map((entry) => {
    const labelLower = entry.label.toLowerCase()
    const descLower = entry.description.toLowerCase()

    let score = 0

    for (const token of tokens) {
      // Exact whole-word match in label
      const wordRe = new RegExp(`\\b${escapeRe(token)}\\b`)
      if (wordRe.test(labelLower)) {
        score += 10
      } else if (labelLower.includes(token)) {
        // Substring match in label
        score += 6
      }

      // Substring match in description
      if (descLower.includes(token)) {
        score += 4
      }

      // Keyword matching
      for (const kw of entry.keywords) {
        if (kw === token) {
          score += 5
        } else if (kw.startsWith(token) || token.startsWith(kw)) {
          score += 3
        }
      }

      // Sector name match
      if (entry.sector === token) {
        score += 4
      } else if (entry.sector.includes(token)) {
        score += 2
      }
    }

    return { ...entry, score }
  })

  return scored
    .filter((e) => e.score > 0)
    .sort((a, b) => b.score - a.score)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Escape a string for use in a RegExp literal.
 * @param {string} s
 * @returns {string}
 */
function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Return all commands for a given sector slug.
 * @param {string} sector
 * @param {Array<object>} [entries=SECTOR_COMMANDS]
 * @returns {Array<object>}
 */
export function commandsBySector(sector, entries = SECTOR_COMMANDS) {
  return entries.filter((e) => e.sector === sector)
}

/**
 * Return the unique sector slugs present in the index.
 * @param {Array<object>} [entries=SECTOR_COMMANDS]
 * @returns {string[]}
 */
export function sectors(entries = SECTOR_COMMANDS) {
  return [...new Set(entries.map((e) => e.sector))]
}
