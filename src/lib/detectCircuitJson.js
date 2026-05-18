// detectCircuitJson.js — heuristic to detect whether a JSON string / parsed
// value represents a tscircuit Circuit JSON payload.
//
// Two shapes are recognised:
//   1. An object with a top-level `circuit_json` key — the explicit wrapper
//      that many LLMs emit when they return circuit data.
//   2. A bare array of objects whose `.type` field matches the tscircuit
//      primitive prefixes (`source_`, `pcb_`, `schematic_`).
//
// Both shapes are valid circuit-json structures that the CircuitJsonPreview
// component can render via circuit-to-svg.

const CIRCUIT_TYPE_RE = /^(source_|pcb_|schematic_)/

/**
 * Return true when `jsonString` is (or parses as) a Circuit JSON payload.
 *
 * @param {string | unknown} jsonString - Raw JSON string OR already-parsed value.
 * @returns {boolean}
 */
export function detectCircuitJson(jsonString) {
  let value
  if (typeof jsonString === 'string') {
    try {
      value = JSON.parse(jsonString)
    } catch {
      return false
    }
  } else {
    value = jsonString
  }

  if (value === null || typeof value !== 'object') return false

  // Shape 1: explicit { circuit_json: [...] } wrapper
  if (!Array.isArray(value) && 'circuit_json' in value) {
    return true
  }

  // Shape 2: array of objects with tscircuit primitive .type values
  if (Array.isArray(value) && value.length > 0) {
    return value.some(
      (item) =>
        item !== null &&
        typeof item === 'object' &&
        typeof item.type === 'string' &&
        CIRCUIT_TYPE_RE.test(item.type),
    )
  }

  return false
}

/**
 * Normalise a detected Circuit JSON value to a plain array of primitives.
 * Returns null when the input is not a recognised circuit payload.
 *
 * @param {string | unknown} jsonString
 * @returns {Array | null}
 */
export function normaliseCircuitJson(jsonString) {
  if (!detectCircuitJson(jsonString)) return null

  let value
  if (typeof jsonString === 'string') {
    try {
      value = JSON.parse(jsonString)
    } catch {
      return null
    }
  } else {
    value = jsonString
  }

  if (Array.isArray(value)) return value
  if (value && 'circuit_json' in value) {
    const inner = value.circuit_json
    return Array.isArray(inner) ? inner : null
  }
  return null
}
