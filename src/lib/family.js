// family.js — Pure JS helpers for Kerf .family.json parametric component templates.
//
// A Family is a reusable parametric component template (window, door, column, …).
// Instances live inside .bim files and reference a family by id.
//
// Resolution precedence: instance params > type params > param defaults.

const VALID_CATEGORIES = [
  'Wall', 'Floor', 'Roof', 'Door', 'Window', 'Column', 'Beam',
  'Stair', 'Railing', 'Ceiling', 'Furniture', 'Generic',
]

const VALID_PARAM_TYPES = ['number', 'string', 'boolean', 'enum']
const VALID_REPRESENTATION_KINDS = ['geometry_ref', 'feature_tree', 'circuit_ref']

// ── defaultFamily ─────────────────────────────────────────────────────────────

/**
 * Returns a minimal valid family template for the given category.
 * @param {string} category
 * @returns {object}
 */
export function defaultFamily(category = 'Generic') {
  return {
    version: 1,
    name: '',
    category,
    params: [],
    types: [],
    host_rules: {
      allowed_hosts: [],
      host_alignment: 'centered_on_face',
    },
    representation: null,
  }
}

// ── validateFamily ────────────────────────────────────────────────────────────

/**
 * Validate a family object.
 * @param {object} family
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateFamily(family) {
  const errors = []

  if (!family || typeof family !== 'object') {
    return { ok: false, errors: ['family must be an object'] }
  }

  if (family.version !== 1) {
    errors.push('version must be 1')
  }

  if (typeof family.name !== 'string') {
    errors.push('name must be a string')
  }

  if (!VALID_CATEGORIES.includes(family.category)) {
    errors.push(`category must be one of: ${VALID_CATEGORIES.join(', ')}`)
  }

  if (!Array.isArray(family.params)) {
    errors.push('params must be an array')
  } else {
    const names = new Set()
    for (const [i, p] of family.params.entries()) {
      const prefix = `params[${i}]`
      if (typeof p.name !== 'string' || !p.name) {
        errors.push(`${prefix}: name is required`)
      } else if (names.has(p.name)) {
        errors.push(`${prefix}: duplicate param name "${p.name}"`)
      } else {
        names.add(p.name)
      }

      if (!VALID_PARAM_TYPES.includes(p.type)) {
        errors.push(`${prefix}: type must be one of: ${VALID_PARAM_TYPES.join(', ')}`)
      }

      if (p.type === 'enum') {
        if (!Array.isArray(p.options) || p.options.length === 0) {
          errors.push(`${prefix}: enum params require a non-empty options array`)
        }
        if (p.default !== undefined && Array.isArray(p.options) && !p.options.includes(p.default)) {
          errors.push(`${prefix}: default "${p.default}" is not in options`)
        }
      }

      if (p.type === 'number') {
        if (p.min !== undefined && p.max !== undefined && p.min > p.max) {
          errors.push(`${prefix}: min (${p.min}) must be <= max (${p.max})`)
        }
        if (p.default !== undefined && typeof p.default !== 'number') {
          errors.push(`${prefix}: default must be a number for number params`)
        }
        if (p.default !== undefined && p.min !== undefined && p.default < p.min) {
          errors.push(`${prefix}: default (${p.default}) is below min (${p.min})`)
        }
        if (p.default !== undefined && p.max !== undefined && p.default > p.max) {
          errors.push(`${prefix}: default (${p.default}) is above max (${p.max})`)
        }
      }
    }
  }

  if (family.types !== undefined && !Array.isArray(family.types)) {
    errors.push('types must be an array')
  } else if (Array.isArray(family.types)) {
    const typeIds = new Set()
    for (const [i, t] of family.types.entries()) {
      if (typeof t.id !== 'string' || !t.id) {
        errors.push(`types[${i}]: id is required`)
      } else if (typeIds.has(t.id)) {
        errors.push(`types[${i}]: duplicate type id "${t.id}"`)
      } else {
        typeIds.add(t.id)
      }
      if (typeof t.name !== 'string') {
        errors.push(`types[${i}]: name must be a string`)
      }
      if (t.params !== undefined && (typeof t.params !== 'object' || Array.isArray(t.params))) {
        errors.push(`types[${i}]: params must be an object`)
      }
    }
  }

  if (family.representation !== null && family.representation !== undefined) {
    const r = family.representation
    if (!VALID_REPRESENTATION_KINDS.includes(r.kind)) {
      errors.push(`representation.kind must be one of: ${VALID_REPRESENTATION_KINDS.join(', ')}`)
    }
  }

  return { ok: errors.length === 0, errors }
}

// ── resolveParams ─────────────────────────────────────────────────────────────

/**
 * Merge param values: defaults → type params → instance params.
 * Returns a plain object of resolved { paramName: value }.
 * @param {object} family
 * @param {object} instance  — { type_id?, params? }
 * @returns {object}
 */
export function resolveParams(family, instance = {}) {
  // 1. defaults from family param definitions
  const resolved = {}
  for (const p of family.params ?? []) {
    if (p.default !== undefined) {
      resolved[p.name] = p.default
    }
  }

  // 2. type params (if type_id is set)
  if (instance.type_id && Array.isArray(family.types)) {
    const type = family.types.find((t) => t.id === instance.type_id)
    if (type?.params) {
      Object.assign(resolved, type.params)
    }
  }

  // 3. per-instance overrides
  if (instance.params && typeof instance.params === 'object') {
    Object.assign(resolved, instance.params)
  }

  return resolved
}

// ── validateInstance ──────────────────────────────────────────────────────────

/**
 * Validate an instance against its family definition.
 * Checks types, enum membership, min/max bounds for the fully resolved params.
 * @param {object} family
 * @param {object} instance  — { type_id?, params? }
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateInstance(family, instance = {}) {
  const errors = []

  if (!family || typeof family !== 'object') {
    return { ok: false, errors: ['family must be an object'] }
  }

  if (!instance || typeof instance !== 'object') {
    return { ok: false, errors: ['instance must be an object'] }
  }

  // Check type_id exists in family, if provided
  if (instance.type_id !== undefined) {
    const typeExists = Array.isArray(family.types) && family.types.some((t) => t.id === instance.type_id)
    if (!typeExists) {
      errors.push(`type_id "${instance.type_id}" not found in family types`)
    }
  }

  const resolved = resolveParams(family, instance)
  const paramDefs = {}
  for (const p of family.params ?? []) {
    paramDefs[p.name] = p
  }

  for (const [name, value] of Object.entries(resolved)) {
    const def = paramDefs[name]
    if (!def) continue // unknown params are allowed (forward compat)

    if (def.type === 'number') {
      if (typeof value !== 'number') {
        errors.push(`param "${name}": expected number, got ${typeof value}`)
        continue
      }
      if (def.min !== undefined && value < def.min) {
        errors.push(`param "${name}": value ${value} is below min ${def.min}`)
      }
      if (def.max !== undefined && value > def.max) {
        errors.push(`param "${name}": value ${value} is above max ${def.max}`)
      }
    }

    if (def.type === 'enum') {
      if (!def.options.includes(value)) {
        errors.push(`param "${name}": "${value}" is not a valid option (${def.options.join(', ')})`)
      }
    }

    if (def.type === 'string' && typeof value !== 'string') {
      errors.push(`param "${name}": expected string, got ${typeof value}`)
    }

    if (def.type === 'boolean' && typeof value !== 'boolean') {
      errors.push(`param "${name}": expected boolean, got ${typeof value}`)
    }
  }

  return { ok: errors.length === 0, errors }
}

// ── addParam / removeParam / updateParam ──────────────────────────────────────

/**
 * Add a new param definition to a family (mutates and returns the family).
 * @param {object} family
 * @param {object} param
 * @returns {object}
 */
export function addParam(family, param) {
  if (!Array.isArray(family.params)) family.params = []
  if (family.params.some((p) => p.name === param.name)) {
    throw new Error(`param "${param.name}" already exists`)
  }
  family.params.push({ ...param })
  return family
}

/**
 * Remove a param by name (mutates and returns the family).
 * @param {object} family
 * @param {string} name
 * @returns {object}
 */
export function removeParam(family, name) {
  if (!Array.isArray(family.params)) return family
  const idx = family.params.findIndex((p) => p.name === name)
  if (idx === -1) throw new Error(`param "${name}" not found`)
  family.params.splice(idx, 1)
  return family
}

/**
 * Patch an existing param definition (mutates and returns the family).
 * @param {object} family
 * @param {string} name
 * @param {object} patch
 * @returns {object}
 */
export function updateParam(family, name, patch) {
  if (!Array.isArray(family.params)) throw new Error(`param "${name}" not found`)
  const p = family.params.find((p) => p.name === name)
  if (!p) throw new Error(`param "${name}" not found`)
  Object.assign(p, patch)
  return family
}

// ── addType / removeType ──────────────────────────────────────────────────────

/**
 * Add a named type (param preset) to the family (mutates and returns family).
 * @param {object} family
 * @param {{ id: string, name: string, params: object }} type
 * @returns {object}
 */
export function addType(family, type) {
  if (!Array.isArray(family.types)) family.types = []
  if (family.types.some((t) => t.id === type.id)) {
    throw new Error(`type "${type.id}" already exists`)
  }
  family.types.push({ ...type })
  return family
}

/**
 * Remove a type by id (mutates and returns the family).
 * @param {object} family
 * @param {string} type_id
 * @returns {object}
 */
export function removeType(family, type_id) {
  if (!Array.isArray(family.types)) return family
  const idx = family.types.findIndex((t) => t.id === type_id)
  if (idx === -1) throw new Error(`type "${type_id}" not found`)
  family.types.splice(idx, 1)
  return family
}

// ── flexFamily ────────────────────────────────────────────────────────────────

/**
 * Exercise a family across multiple parameter sets and return each resolved
 * result with validation. This mirrors the backend flex_family tool and is
 * the "flex panel" for the authoring UX.
 *
 * @param {object} family  — The .family.json object
 * @param {Array<object>} parameterSets  — Array of instance dicts {type_id?, params?}
 * @returns {{ results: Array<{index, input, resolved, errors, ok}>, allOk: boolean }}
 */
export function flexFamily(family, parameterSets) {
  if (!Array.isArray(parameterSets) || parameterSets.length === 0) {
    throw new Error('parameterSets must be a non-empty array')
  }

  const paramDefs = {}
  for (const p of family.params ?? []) {
    paramDefs[p.name] = p
  }

  const results = parameterSets.map((instance, idx) => {
    const resolved = resolveParams(family, instance)
    const errors = []

    for (const [name, value] of Object.entries(resolved)) {
      const def = paramDefs[name]
      if (!def) continue

      if (def.type === 'number') {
        if (typeof value !== 'number') {
          errors.push(`param "${name}": expected number, got ${typeof value}`)
          continue
        }
        if (def.min !== undefined && value < def.min) {
          errors.push(`param "${name}": value ${value} is below min ${def.min}`)
        }
        if (def.max !== undefined && value > def.max) {
          errors.push(`param "${name}": value ${value} is above max ${def.max}`)
        }
      }

      if (def.type === 'enum' && !def.options.includes(value)) {
        errors.push(`param "${name}": "${value}" is not a valid option (${def.options.join(', ')})`)
      }

      if (def.type === 'string' && typeof value !== 'string') {
        errors.push(`param "${name}": expected string, got ${typeof value}`)
      }

      if (def.type === 'boolean' && typeof value !== 'boolean') {
        errors.push(`param "${name}": expected boolean, got ${typeof value}`)
      }
    }

    return { index: idx, input: instance, resolved, errors, ok: errors.length === 0 }
  })

  return { results, allOk: results.every((r) => r.ok) }
}
