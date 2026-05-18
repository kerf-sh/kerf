// circuitJsonPatch.js — immutable helpers for editing Circuit JSON.
//
// Circuit JSON is the flat array format produced by tscircuit / @tscircuit/core.
// Each element is a plain object with a `type` field and type-specific fields.
// All mutations work on the PCB layer:
//   - pcb_component  { pcb_component_id, center:{x,y}, rotation?, … }
//   - pcb_smtpad     { pcb_smtpad_id, pcb_component_id?, x, y, … }
//   - pcb_plated_hole { pcb_plated_hole_id, pcb_component_id?, x, y, … }
//
// API — every function is pure: takes an array + args, returns a new array.
//
//   addFootprint(circuitJson, { footprintFn, refdes, x, y, rotation })
//     Insert a new component (pcb_component + its child pads) into the array.
//     `footprintFn` is one of the library strings ("res", "cap", "dip", …) or
//     a full tscircuit footprint specifier string. The raw pad/hole elements
//     returned by @tscircuit/footprinter are shifted to (x, y) and the
//     component rotation is applied before insertion.
//
//   rotateFootprint(circuitJson, { pcb_component_id, angleDeg })
//     Rotate a component and its child pads in-place (returns new array).
//     Rotation accumulates (adds to existing).
//
//   moveFootprint(circuitJson, { pcb_component_id, x, y })
//     Translate a component and its child pads (absolute position).
//
//   groupMove(circuitJson, { pcb_component_ids, dx, dy })
//     Translate a group of components by (dx, dy) — relative delta.
//
// Design decisions:
//   - Pure / immutable: never mutates the input array or any of its objects.
//   - Footprinter is used for pad geometry only. We never call the tscircuit
//     render pipeline — no React, no workers. Just geometry maths.
//   - IDs are generated as short random hex strings scoped to the session;
//     they're good enough for in-memory editing and don't need to be globally
//     stable until the user exports / commits circuit JSON.
//   - No Zod / schema validation — keep the dep surface minimal. Defensive
//     guards at each entry point.

import { fp, getFootprintNames, string as fpString } from '@tscircuit/footprinter'

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function uid() {
  return Math.random().toString(16).slice(2, 10)
}

// Rotate a 2-D point around the origin by `angleDeg` degrees.
function rotatePoint(x, y, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  return {
    x: x * cos - y * sin,
    y: x * sin + y * cos,
  }
}

// Translate a pad/hole element by (dx, dy).
function translatePad(el, dx, dy) {
  return { ...el, x: (el.x || 0) + dx, y: (el.y || 0) + dy }
}

// Rotate a pad/hole element around (cx, cy) by angleDeg.
function rotatePad(el, cx, cy, angleDeg) {
  const rel = rotatePoint((el.x || 0) - cx, (el.y || 0) - cy, angleDeg)
  return { ...el, x: rel.x + cx, y: rel.y + cy }
}

const PAD_TYPES = new Set(['pcb_smtpad', 'pcb_plated_hole'])

// Return true when `el` is a pad/hole that belongs to a given component.
function isPadOf(el, pcb_component_id) {
  return PAD_TYPES.has(el.type) && el.pcb_component_id === pcb_component_id
}

// ---------------------------------------------------------------------------
// addFootprint
// ---------------------------------------------------------------------------

// Passive footprint types that require a size argument to produce valid pads.
const PASSIVE_FNS = new Set(['res', 'cap', 'led', 'diode', 'electrolytic', 'melf', 'minimelf', 'micromelf'])

// Default imperial size used when a passive is requested without a size.
const DEFAULT_PASSIVE_SIZE = '0402'

/**
 * Insert a new footprint into circuitJson at position (x, y) with the given
 * rotation. Uses @tscircuit/footprinter to obtain pad geometry.
 *
 * @param {Array}  circuitJson   Existing Circuit JSON (not mutated).
 * @param {object} opts
 * @param {string} opts.footprintFn  Full specifier accepted by the footprinter
 *                                   string parser: "res0402", "cap0805",
 *                                   "dip8", "soic8", "qfn16", … OR a bare
 *                                   family name ("res", "cap", "dip") with
 *                                   sizing in opts.params. Bare passives
 *                                   without params default to 0402.
 * @param {string} [opts.refdes]     Reference designator ("R1", "C2", …).
 *                                   Auto-generated if omitted.
 * @param {number} [opts.x]          X centre in mm (default 0).
 * @param {number} [opts.y]          Y centre in mm (default 0).
 * @param {number} [opts.rotation]   Initial rotation in degrees (default 0).
 * @param {object} [opts.params]     Extra params for bare-name footprints.
 *                                   Passives: { imperial: '0402' } or
 *                                   { metric: '1005' }.
 *                                   Pin-count: { num_pins: 8 }.
 * @returns {Array} New Circuit JSON with the footprint appended.
 */
export function addFootprint(circuitJson, opts = {}) {
  if (!Array.isArray(circuitJson)) throw new TypeError('circuitJson must be an array')
  const {
    footprintFn = 'res0402',
    refdes,
    x = 0,
    y = 0,
    rotation = 0,
    params = {},
  } = opts

  const known = getFootprintNames()

  // Build the footprinter proxy.
  // We use `fpString(specifier)` which returns a fully configured proxy ready
  // for `.circuitJson()`. This is the canonical API for string specifiers like
  // "res0402", "dip8", "soic16", etc.
  //
  // For bare family names ("res", "dip", …) we construct the specifier from
  // the supplied params so they go through the same path.
  let specifier = String(footprintFn)

  if (typeof footprintFn === 'string' && known.includes(footprintFn)) {
    // Bare family name — build a full specifier.
    if (PASSIVE_FNS.has(footprintFn)) {
      // e.g. "res" → "res0402" (or "res0805" if params.imperial='0805')
      const size = params.imperial || params.metric
        ? (params.metric ? `${params.metric}_metric` : params.imperial)
        : DEFAULT_PASSIVE_SIZE
      specifier = `${footprintFn}${size}`
    } else if (params.num_pins != null) {
      // e.g. "dip" + { num_pins: 8 } → "dip8"
      specifier = `${footprintFn}${params.num_pins}`
    }
    // For all other bare names with no recognized params, pass through as-is
    // and let fpString / footprinter handle or reject.
  }

  let proxy
  try {
    proxy = fpString(specifier)
  } catch {
    return circuitJson.slice()
  }

  let rawPads
  try {
    rawPads = proxy.circuitJson()
  } catch {
    // Footprinter failed — return original array unchanged.
    return circuitJson.slice()
  }

  if (!Array.isArray(rawPads)) return circuitJson.slice()

  // Assign a fresh component id.
  const pcb_component_id = `pcb_component_${uid()}`
  const autoRefdes = refdes || `FP${uid().slice(0, 4).toUpperCase()}`

  // Shift pads from footprinter origin to (x, y) and apply rotation.
  const processedPads = rawPads
    .filter((el) => el && PAD_TYPES.has(el.type))
    .map((el) => {
      // Rotate first (around footprinter origin), then translate.
      const rotated = rotatePad(el, 0, 0, rotation)
      const translated = translatePad(rotated, x, y)
      const idField = el.type === 'pcb_smtpad' ? 'pcb_smtpad_id' : 'pcb_plated_hole_id'
      return {
        ...translated,
        [idField]: `${el.type}_${uid()}`,
        pcb_component_id,
      }
    })

  // Keep non-pad footprinter elements (silkscreen, courtyard, …) shifted too.
  const extraElements = rawPads
    .filter((el) => el && !PAD_TYPES.has(el.type))
    .map((el) => {
      // Silkscreen paths have a `route` array of {x,y} points.
      if (el.route && Array.isArray(el.route)) {
        const rotatedRoute = el.route.map((pt) => {
          const r = rotatePoint(pt.x || 0, pt.y || 0, rotation)
          return { ...pt, x: r.x + x, y: r.y + y }
        })
        return { ...el, route: rotatedRoute, pcb_component_id }
      }
      // Silkscreen text: shift center.
      if (el.anchor_position || (el.x != null && el.y != null)) {
        if (el.anchor_position) {
          const r = rotatePoint(el.anchor_position.x || 0, el.anchor_position.y || 0, rotation)
          return {
            ...el,
            anchor_position: { ...el.anchor_position, x: r.x + x, y: r.y + y },
            pcb_component_id,
          }
        }
        const rotated = rotatePad(el, 0, 0, rotation)
        return { ...translatePad(rotated, x, y), pcb_component_id }
      }
      return { ...el, pcb_component_id }
    })

  const pcbComponent = {
    type: 'pcb_component',
    pcb_component_id,
    center: { x, y },
    rotation,
    name: autoRefdes,
  }

  return [...circuitJson, pcbComponent, ...processedPads, ...extraElements]
}

// ---------------------------------------------------------------------------
// rotateFootprint
// ---------------------------------------------------------------------------

/**
 * Rotate a component (and its child pads) by `angleDeg` (accumulated).
 *
 * @param {Array}  circuitJson
 * @param {object} opts
 * @param {string} opts.pcb_component_id
 * @param {number} opts.angleDeg   Degrees to ADD to the current rotation.
 * @returns {Array}
 */
export function rotateFootprint(circuitJson, opts = {}) {
  if (!Array.isArray(circuitJson)) throw new TypeError('circuitJson must be an array')
  const { pcb_component_id, angleDeg = 0 } = opts
  if (!pcb_component_id) throw new Error('pcb_component_id is required')
  if (typeof angleDeg !== 'number' || !Number.isFinite(angleDeg)) {
    throw new TypeError('angleDeg must be a finite number')
  }

  // Find the component to get its current centre.
  const comp = circuitJson.find(
    (el) => el && el.type === 'pcb_component' && el.pcb_component_id === pcb_component_id
  )
  if (!comp) return circuitJson.slice()

  const cx = (comp.center && comp.center.x) || 0
  const cy = (comp.center && comp.center.y) || 0

  return circuitJson.map((el) => {
    if (!el) return el
    if (el.type === 'pcb_component' && el.pcb_component_id === pcb_component_id) {
      return { ...el, rotation: ((el.rotation || 0) + angleDeg) % 360 }
    }
    if (isPadOf(el, pcb_component_id)) {
      return rotatePad(el, cx, cy, angleDeg)
    }
    // Silkscreen/courtyard elements that belong to this component.
    if (el.pcb_component_id === pcb_component_id) {
      if (el.route && Array.isArray(el.route)) {
        return {
          ...el,
          route: el.route.map((pt) => {
            const r = rotatePoint((pt.x || 0) - cx, (pt.y || 0) - cy, angleDeg)
            return { ...pt, x: r.x + cx, y: r.y + cy }
          }),
        }
      }
      if (el.anchor_position) {
        const r = rotatePoint(
          (el.anchor_position.x || 0) - cx,
          (el.anchor_position.y || 0) - cy,
          angleDeg
        )
        return {
          ...el,
          anchor_position: { ...el.anchor_position, x: r.x + cx, y: r.y + cy },
        }
      }
      if (el.x != null && el.y != null) {
        return rotatePad(el, cx, cy, angleDeg)
      }
    }
    return el
  })
}

// ---------------------------------------------------------------------------
// moveFootprint
// ---------------------------------------------------------------------------

/**
 * Move a component to an absolute position (x, y).
 *
 * @param {Array}  circuitJson
 * @param {object} opts
 * @param {string} opts.pcb_component_id
 * @param {number} opts.x   New absolute X in mm.
 * @param {number} opts.y   New absolute Y in mm.
 * @returns {Array}
 */
export function moveFootprint(circuitJson, opts = {}) {
  if (!Array.isArray(circuitJson)) throw new TypeError('circuitJson must be an array')
  const { pcb_component_id, x = 0, y = 0 } = opts
  if (!pcb_component_id) throw new Error('pcb_component_id is required')
  if (typeof x !== 'number' || !Number.isFinite(x)) throw new TypeError('x must be a finite number')
  if (typeof y !== 'number' || !Number.isFinite(y)) throw new TypeError('y must be a finite number')

  const comp = circuitJson.find(
    (el) => el && el.type === 'pcb_component' && el.pcb_component_id === pcb_component_id
  )
  if (!comp) return circuitJson.slice()

  const oldCx = (comp.center && comp.center.x) || 0
  const oldCy = (comp.center && comp.center.y) || 0
  const dx = x - oldCx
  const dy = y - oldCy

  return circuitJson.map((el) => {
    if (!el) return el
    if (el.type === 'pcb_component' && el.pcb_component_id === pcb_component_id) {
      return { ...el, center: { x, y } }
    }
    if (isPadOf(el, pcb_component_id)) {
      return translatePad(el, dx, dy)
    }
    if (el.pcb_component_id === pcb_component_id) {
      if (el.route && Array.isArray(el.route)) {
        return {
          ...el,
          route: el.route.map((pt) => ({ ...pt, x: (pt.x || 0) + dx, y: (pt.y || 0) + dy })),
        }
      }
      if (el.anchor_position) {
        return {
          ...el,
          anchor_position: {
            ...el.anchor_position,
            x: (el.anchor_position.x || 0) + dx,
            y: (el.anchor_position.y || 0) + dy,
          },
        }
      }
      if (el.x != null && el.y != null) {
        return translatePad(el, dx, dy)
      }
    }
    return el
  })
}

// ---------------------------------------------------------------------------
// groupMove
// ---------------------------------------------------------------------------

/**
 * Move a group of components by a relative delta (dx, dy).
 *
 * @param {Array}  circuitJson
 * @param {object} opts
 * @param {string[]} opts.pcb_component_ids   IDs of components to move.
 * @param {number}   opts.dx                  Delta X in mm.
 * @param {number}   opts.dy                  Delta Y in mm.
 * @returns {Array}
 */
export function groupMove(circuitJson, opts = {}) {
  if (!Array.isArray(circuitJson)) throw new TypeError('circuitJson must be an array')
  const { pcb_component_ids = [], dx = 0, dy = 0 } = opts
  if (!Array.isArray(pcb_component_ids)) throw new TypeError('pcb_component_ids must be an array')
  if (typeof dx !== 'number' || !Number.isFinite(dx)) throw new TypeError('dx must be a finite number')
  if (typeof dy !== 'number' || !Number.isFinite(dy)) throw new TypeError('dy must be a finite number')

  if (pcb_component_ids.length === 0) return circuitJson.slice()

  const idSet = new Set(pcb_component_ids)

  return circuitJson.map((el) => {
    if (!el) return el
    if (el.type === 'pcb_component' && idSet.has(el.pcb_component_id)) {
      const cx = (el.center && el.center.x) || 0
      const cy = (el.center && el.center.y) || 0
      return { ...el, center: { x: cx + dx, y: cy + dy } }
    }
    if (PAD_TYPES.has(el.type) && idSet.has(el.pcb_component_id)) {
      return translatePad(el, dx, dy)
    }
    if (el.pcb_component_id && idSet.has(el.pcb_component_id)) {
      if (el.route && Array.isArray(el.route)) {
        return {
          ...el,
          route: el.route.map((pt) => ({ ...pt, x: (pt.x || 0) + dx, y: (pt.y || 0) + dy })),
        }
      }
      if (el.anchor_position) {
        return {
          ...el,
          anchor_position: {
            ...el.anchor_position,
            x: (el.anchor_position.x || 0) + dx,
            y: (el.anchor_position.y || 0) + dy,
          },
        }
      }
      if (el.x != null && el.y != null) {
        return translatePad(el, dx, dy)
      }
    }
    return el
  })
}
