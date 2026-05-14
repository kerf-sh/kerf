// netClasses.js — KiCad-style net class management for CircuitJSON boards.
//
// CircuitJSON extension (on the board element):
//   board.net_classes: [{ name, trace_width_mm, clearance_mm,
//                         via_diameter_mm, via_drill_mm, target_impedance_ohms? }]
//   board.net_class_assignments: { [net_id]: class_name }
//
// The "Default" class is always implicit and cannot be removed.
// Net-class rules are advisory — actual DRC enforcement is the DRC agent's job.

const BUILTIN_CLASSES = [
  {
    name: 'Default',
    trace_width_mm: 0.25,
    clearance_mm: 0.20,
    via_diameter_mm: 0.60,
    via_drill_mm: 0.30,
  },
  {
    name: 'Power',
    trace_width_mm: 0.50,
    clearance_mm: 0.25,
    via_diameter_mm: 0.80,
    via_drill_mm: 0.40,
  },
  {
    name: 'Signal',
    trace_width_mm: 0.25,
    clearance_mm: 0.20,
    via_diameter_mm: 0.60,
    via_drill_mm: 0.30,
  },
  {
    name: 'HighSpeed',
    trace_width_mm: 0.20,
    clearance_mm: 0.20,
    via_diameter_mm: 0.50,
    via_drill_mm: 0.25,
    target_impedance_ohms: 50,
  },
  {
    name: 'Differential',
    trace_width_mm: 0.20,
    clearance_mm: 0.20,
    via_diameter_mm: 0.50,
    via_drill_mm: 0.25,
    target_impedance_ohms: 100,
  },
]

/**
 * Returns the five predefined net classes (deep copy).
 * @returns {{ name: string, trace_width_mm: number, clearance_mm: number,
 *             via_diameter_mm: number, via_drill_mm: number,
 *             target_impedance_ohms?: number }[]}
 */
export function defaultNetClasses() {
  return BUILTIN_CLASSES.map(c => ({ ...c }))
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function getBoard(circuit_json) {
  if (!circuit_json || typeof circuit_json !== 'object') return null
  if (Array.isArray(circuit_json)) {
    return circuit_json.find(el => el && el.type === 'pcb_board') ?? null
  }
  // Single board object passed directly
  if (circuit_json.type === 'pcb_board') return circuit_json
  return null
}

function cloneCircuit(circuit_json) {
  return JSON.parse(JSON.stringify(circuit_json))
}

/**
 * Resolve the board element inside a (possibly cloned) circuit and ensure the
 * net_classes / net_class_assignments keys exist.
 */
function ensureBoardKeys(circuit_json) {
  const board = getBoard(circuit_json)
  if (!board) return null
  if (!Array.isArray(board.net_classes)) board.net_classes = []
  if (!board.net_class_assignments || typeof board.net_class_assignments !== 'object') {
    board.net_class_assignments = {}
  }
  return board
}

function resolveClass(board, name) {
  // Check user-defined classes first, then builtins
  const userDefined = (board.net_classes || []).find(c => c.name === name)
  if (userDefined) return userDefined
  return BUILTIN_CLASSES.find(c => c.name === name) ?? null
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Returns the class name assigned to a net, or "Default" if unassigned.
 * @param {any} circuit_json
 * @param {string} net_id
 * @returns {string}
 */
export function findNetClass(circuit_json, net_id) {
  const board = getBoard(circuit_json)
  if (!board || !board.net_class_assignments) return 'Default'
  return board.net_class_assignments[net_id] ?? 'Default'
}

/**
 * Returns a new circuit_json with net_id assigned to class_name.
 * Throws if class_name does not exist in the circuit or builtins.
 * @param {any} circuit_json
 * @param {string} net_id
 * @param {string} class_name
 * @returns {any}
 */
export function assignNetToClass(circuit_json, net_id, class_name) {
  if (!net_id) throw new Error('net_id is required')
  if (!class_name) throw new Error('class_name is required')

  const cloned = cloneCircuit(circuit_json)
  const board = ensureBoardKeys(cloned)
  if (!board) throw new Error('No pcb_board element found in circuit_json')

  // Validate the class exists
  const cls = resolveClass(board, class_name)
  if (!cls) throw new Error(`Net class "${class_name}" does not exist`)

  board.net_class_assignments[net_id] = class_name
  return cloned
}

/**
 * Returns a new circuit_json with the class definition added or updated.
 * "Default" may be updated (overriding defaults) but not removed.
 * @param {any} circuit_json
 * @param {{ name: string, trace_width_mm: number, clearance_mm: number,
 *           via_diameter_mm: number, via_drill_mm: number,
 *           target_impedance_ohms?: number }} classDef
 * @returns {any}
 */
export function defineNetClass(circuit_json, classDef) {
  if (!classDef || !classDef.name) throw new Error('classDef.name is required')
  const required = ['trace_width_mm', 'clearance_mm', 'via_diameter_mm', 'via_drill_mm']
  for (const key of required) {
    if (typeof classDef[key] !== 'number') {
      throw new Error(`classDef.${key} must be a number`)
    }
  }

  const cloned = cloneCircuit(circuit_json)
  const board = ensureBoardKeys(cloned)
  if (!board) throw new Error('No pcb_board element found in circuit_json')

  const idx = board.net_classes.findIndex(c => c.name === classDef.name)
  const entry = { ...classDef }
  if (idx >= 0) {
    board.net_classes[idx] = entry
  } else {
    board.net_classes.push(entry)
  }
  return cloned
}

/**
 * Returns a new circuit_json with the named class removed.
 * Any nets assigned to it are reassigned to "Default".
 * Throws if you try to remove "Default".
 * @param {any} circuit_json
 * @param {string} class_name
 * @returns {any}
 */
export function removeNetClass(circuit_json, class_name) {
  if (class_name === 'Default') throw new Error('Cannot remove the Default net class')

  const cloned = cloneCircuit(circuit_json)
  const board = ensureBoardKeys(cloned)
  if (!board) throw new Error('No pcb_board element found in circuit_json')

  board.net_classes = board.net_classes.filter(c => c.name !== class_name)

  // Reassign nets that used the removed class
  for (const net_id of Object.keys(board.net_class_assignments)) {
    if (board.net_class_assignments[net_id] === class_name) {
      board.net_class_assignments[net_id] = 'Default'
    }
  }
  return cloned
}

/**
 * Returns the merged rule set for a net: class defaults overridden by any
 * per-net `net_rules` entry stored in board.net_rules[net_id].
 * @param {any} circuit_json
 * @param {string} net_id
 * @returns {{ trace_width_mm: number, clearance_mm: number,
 *             via_diameter_mm: number, via_drill_mm: number,
 *             target_impedance_ohms?: number, net_class: string }}
 */
export function effectiveRulesForNet(circuit_json, net_id) {
  const board = getBoard(circuit_json)
  const className = findNetClass(circuit_json, net_id)

  // Resolve class: check board.net_classes first, then builtins
  const userDefined = board && Array.isArray(board.net_classes)
    ? board.net_classes.find(c => c.name === className)
    : null
  const builtinCls = BUILTIN_CLASSES.find(c => c.name === className)
  const classDef = userDefined ?? builtinCls ?? BUILTIN_CLASSES[0] // fallback to Default

  // Per-net overrides stored at board.net_rules[net_id]
  const netOverrides = (board && board.net_rules && board.net_rules[net_id]) ?? {}

  const { name: _n, ...classRules } = classDef
  return { ...classRules, ...netOverrides, net_class: className }
}
