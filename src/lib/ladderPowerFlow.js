/**
 * ladderPowerFlow.js — Pure-JS IEC 61131-3 power-flow engine for the ladder editor.
 *
 * This module mirrors the Python-side simulation logic so that the frontend can
 * shade a rung's contacts, coils, and wires in real time without a server round
 * trip. It is intentionally dependency-free (no React, no Three.js) so it can be
 * unit-tested in a plain vitest environment.
 *
 * Data model
 * ----------
 * A *rung* is the ladder diagram row being evaluated. It is represented as an
 * array of *elements*, each with at least:
 *
 *   { id, type, variable }      — for contact-class elements
 *   { id, type, variable }      — for coil-class elements
 *
 * The supported element types are:
 *
 *   Contact types  (input side, read variable state from variableState map)
 *   ─────────────────────────────────────────────────────────────────────
 *   'NO'      Normally-Open:  lit when variable === true
 *   'NC'      Normally-Closed: lit when variable === false
 *   'R_TRIG'  Rising-edge trigger: lit when variable is true (simplified; a real
 *             implementation needs scan-cycle state, but for display purposes we
 *             show the current variable value as the energy state)
 *   'F_TRIG'  Falling-edge trigger: lit when variable is false (same caveat)
 *
 *   Coil types  (output side, energised by the upstream logic)
 *   ─────────────────────────────────────────────────────────
 *   'COIL'    Normal output coil
 *   'COIL_NC' Negated coil (energised when power rail is *not* flowing)
 *   'SET'     Set coil
 *   'RESET'   Reset coil
 *
 * Parallel branches are expressed by nesting arrays inside the rung array.
 * A nested array represents a group of branches evaluated with OR semantics:
 *
 *   [
 *     { id: 'c1', type: 'NO', variable: 'start' },
 *     [                                          ← parallel branch group
 *       [ { id: 'c2', … }, { id: 'c3', … } ],   ← branch A (series)
 *       [ { id: 'c4', … } ],                     ← branch B (series)
 *     ],
 *     { id: 'q1', type: 'COIL', variable: 'motor' },
 *   ]
 *
 * A flat element at the top level is evaluated in series with its neighbours.
 *
 * Public API
 * ----------
 * computePowerFlow(rung, variableState) → { contactsLit, coilsLit, wiresLit }
 *   rung          — array described above
 *   variableState — plain object / Map mapping variable name → boolean
 *
 * colorForState(lit, elementType) → CSS hex string
 *   Returns the display colour for an element based on whether it is energised.
 */

// ---------------------------------------------------------------------------
// Contact evaluation helpers
// ---------------------------------------------------------------------------

/**
 * Return the boolean energy state for a single contact element given the
 * current variable state map.
 *
 * @param {{ type: string, variable?: string }} element
 * @param {Record<string,boolean>|Map<string,boolean>} varState
 * @returns {boolean}
 */
export function evaluateContact(element, varState) {
  const val = _readVar(varState, element.variable)
  switch (element.type) {
    case 'NO':
      return val === true
    case 'NC':
      return val !== true
    case 'R_TRIG':
      // Simplified: display the raw variable value as the "rising" state.
      return val === true
    case 'F_TRIG':
      // Simplified: display the inverse of the variable value.
      return val !== true
    default:
      return false
  }
}

/**
 * Read a variable value from either a plain object or a Map.
 * Returns false for undefined variables.
 *
 * @param {Record<string,boolean>|Map<string,boolean>} varState
 * @param {string|undefined} name
 * @returns {boolean}
 */
function _readVar(varState, name) {
  if (!name) return false
  if (varState instanceof Map) return varState.get(name) === true
  return varState[name] === true
}

// ---------------------------------------------------------------------------
// Rung evaluation — series + parallel
// ---------------------------------------------------------------------------

const CONTACT_TYPES = new Set(['NO', 'NC', 'R_TRIG', 'F_TRIG'])
const COIL_TYPES = new Set(['COIL', 'COIL_NC', 'SET', 'RESET'])

/**
 * Evaluate one rung and return the set of lit element IDs.
 *
 * The rung is walked left-to-right. Contacts are evaluated in series (AND)
 * until the first nested array, which is evaluated as a parallel group (OR).
 * After the parallel group evaluation resumes in series.
 *
 * Coils at the end of the rung are lit if the upstream power rail is flowing.
 * A COIL_NC is lit when power is *not* flowing.
 *
 * @param {Array} rung
 * @param {Record<string,boolean>|Map<string,boolean>} variableState
 * @returns {{ contactsLit: Set<string>, coilsLit: Set<string>, wiresLit: Set<string> }}
 */
export function computePowerFlow(rung, variableState) {
  // Normalise null / undefined variableState to an empty object.
  if (variableState == null) variableState = {}
  const contactsLit = new Set()
  const coilsLit = new Set()
  const wiresLit = new Set()

  if (!Array.isArray(rung) || rung.length === 0) {
    return { contactsLit, coilsLit, wiresLit }
  }

  // Walk rung elements left to right, accumulating series power.
  let power = true // left power rail starts energised

  for (let i = 0; i < rung.length; i++) {
    const elem = rung[i]

    if (Array.isArray(elem)) {
      // Parallel branch group — each sub-array is a series branch.
      // The group is lit if ANY branch is lit (OR).
      const branchResults = elem.map((branch) => {
        if (!Array.isArray(branch)) return false
        // Each branch is a series of contacts.
        let branchPower = power
        for (const bElem of branch) {
          if (!bElem || !bElem.type) continue
          if (CONTACT_TYPES.has(bElem.type)) {
            const lit = evaluateContact(bElem, variableState)
            if (lit) contactsLit.add(bElem.id)
            branchPower = branchPower && lit
          }
        }
        return branchPower
      })

      const parallelLit = branchResults.some(Boolean)
      if (parallelLit) wiresLit.add(`wire_parallel_${i}`)
      power = parallelLit
    } else if (elem && CONTACT_TYPES.has(elem.type)) {
      const lit = evaluateContact(elem, variableState)
      if (lit) contactsLit.add(elem.id)
      power = power && lit
      if (power) wiresLit.add(`wire_after_${elem.id}`)
    } else if (elem && COIL_TYPES.has(elem.type)) {
      // Coil — energised according to current power rail state.
      let coilLit
      if (elem.type === 'COIL_NC') {
        coilLit = !power
      } else {
        coilLit = power
      }
      if (coilLit) coilsLit.add(elem.id)
    }
  }

  // The right-hand wire back to the neutral rail is lit if any coil was
  // energised (power reached the coil section).
  if (power) wiresLit.add('wire_rung_complete')

  return { contactsLit, coilsLit, wiresLit }
}

// ---------------------------------------------------------------------------
// Colour helper
// ---------------------------------------------------------------------------

/**
 * Return a CSS hex colour string for an element based on its energy state.
 *
 * Energised contacts/wires → green  (#34d399, Tailwind emerald-400)
 * Energised coils          → green  (#34d399)
 * De-energised elements    → dim    (#6b7280, Tailwind gray-500)
 *
 * When a coil is expected but not energised (i.e. the wire is broken
 * upstream) the caller should pass lit=false with elementType='COIL' to
 * receive the red broken-wire colour.
 *
 * @param {boolean} lit            Whether the element is energised.
 * @param {string}  elementType    Element type string (e.g. 'NO', 'COIL').
 * @returns {string}               CSS hex colour string.
 */
export function colorForState(lit, elementType) {
  if (lit) return '#34d399'            // emerald-400 — energised
  if (COIL_TYPES.has(elementType)) return '#f87171' // red-400 — broken wire / de-energised coil
  return '#6b7280'                     // gray-500  — dim contact
}
