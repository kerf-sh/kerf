/**
 * bimFamilyOps.js — Pure client-side logic for the BIM parametric
 * family-authoring UX (T-109).
 *
 * This module is dependency-free (no React, no fetch) so it can be
 * exercised directly in vitest without a DOM.  The React component
 * BimFamilyEditor.jsx imports from here.
 *
 * Data model
 * ----------
 * A **FamilyTemplate** is a plain JS object:
 *   {
 *     name:          string,
 *     category:      string,          // e.g. "Column"
 *     geometry_type: string,          // e.g. "circular_column"
 *     parameters: [
 *       {
 *         name:        string,
 *         kind:        string,        // "length" | "float" | "material" | …
 *         default:     number|string,
 *         min_val?:    number,
 *         max_val?:    number,
 *         expression?: string,        // formula (overrides value)
 *         description: string,
 *       },
 *       …
 *     ],
 *     description:   string,
 *   }
 *
 * An **overrides** map is { paramName: value }.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const BIM_CATEGORIES = [
  'Column', 'Beam', 'Wall', 'Floor', 'Roof', 'Door', 'Window',
  'Stair', 'Railing', 'Ceiling', 'Furniture', 'Generic',
]

export const GEOMETRY_TYPES = [
  'circular_column',
  'rectangular_column',
]

export const NUMERIC_KINDS = new Set(['length', 'float', 'angle', 'integer'])
export const MATERIAL_KIND = 'material'

// ---------------------------------------------------------------------------
// Default template factory
// ---------------------------------------------------------------------------

/**
 * Return the built-in parametric column template as a plain JS object.
 * This mirrors COLUMN_TEMPLATE in family_authoring.py so the UI has a
 * sensible starting point without an API round-trip.
 *
 * @returns {object} FamilyTemplate
 */
export function defaultColumnTemplate() {
  return {
    name: 'Parametric Column',
    category: 'Column',
    geometry_type: 'circular_column',
    parameters: [
      {
        name: 'D',
        kind: 'length',
        default: 0.3,
        min_val: 0.05,
        max_val: 5.0,
        expression: null,
        description: 'Column diameter (m)',
      },
      {
        name: 'H',
        kind: 'length',
        default: 3.0,
        min_val: 0.5,
        max_val: 50.0,
        expression: null,
        description: 'Column height (m)',
      },
      {
        name: 'material',
        kind: 'material',
        default: 'concrete_m30',
        min_val: null,
        max_val: null,
        expression: null,
        description: 'Structural material from the T-115 catalogue',
      },
    ],
    description: 'Round column parameterised by diameter and height.',
  }
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Validate a FamilyTemplate object (client-side, offline).
 *
 * @param {object} template
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateTemplate(template) {
  const errors = []

  if (!template || typeof template !== 'object') {
    return { ok: false, errors: ['template must be an object'] }
  }

  if (!template.name || !template.name.trim()) {
    errors.push('template name must be a non-empty string')
  }

  if (!template.category || !template.category.trim()) {
    errors.push('template category must be a non-empty string')
  }

  if (!Array.isArray(template.parameters)) {
    errors.push('parameters must be an array')
    return { ok: false, errors }
  }

  const seenNames = new Set()

  for (const [i, p] of template.parameters.entries()) {
    const prefix = `parameters[${i}]`

    if (!p.name || !p.name.trim()) {
      errors.push(`${prefix}: name must be a non-empty string`)
      continue
    }

    if (seenNames.has(p.name)) {
      errors.push(`${prefix}: duplicate parameter name '${p.name}'`)
    } else {
      seenNames.add(p.name)
    }

    if (NUMERIC_KINDS.has(p.kind) && p.expression == null) {
      const val = Number(p.default)
      if (Number.isNaN(val)) {
        errors.push(`${prefix} '${p.name}': default is not numeric for kind '${p.kind}'`)
      } else {
        if (p.min_val != null && val < p.min_val) {
          errors.push(`${prefix} '${p.name}': default ${val} is below min_val ${p.min_val}`)
        }
        if (p.max_val != null && val > p.max_val) {
          errors.push(`${prefix} '${p.name}': default ${val} is above max_val ${p.max_val}`)
        }
      }
    }
  }

  return { ok: errors.length === 0, errors }
}

// ---------------------------------------------------------------------------
// Parameter resolution
// ---------------------------------------------------------------------------

/**
 * Clamp a numeric value to [min_val, max_val] as declared on the parameter.
 *
 * @param {object} param  — TemplateParameter
 * @param {number} value
 * @returns {number}
 */
export function clampParam(param, value) {
  let v = Number(value)
  if (param.min_val != null) v = Math.max(param.min_val, v)
  if (param.max_val != null) v = Math.min(param.max_val, v)
  return v
}

/**
 * Apply *overrides* on top of the template's parameter defaults.
 * Formula (expression) parameters are **not** evaluated here — that
 * requires the Python evaluator and happens server-side. Instead, this
 * function returns a partial resolution sufficient for the flex panel
 * preview (sliders + material picker).
 *
 * @param {object}  template   FamilyTemplate
 * @param {object}  overrides  { paramName: value }
 * @returns {object}  resolved map { paramName: resolvedValue }
 */
export function resolveParamValues(template, overrides = {}) {
  const resolved = {}
  for (const p of (template.parameters ?? [])) {
    if (p.expression) {
      // Expression params retain their default as a placeholder until the
      // server evaluates the formula.
      resolved[p.name] = p.default
    } else if (p.name in overrides) {
      const raw = overrides[p.name]
      resolved[p.name] = NUMERIC_KINDS.has(p.kind) ? clampParam(p, raw) : raw
    } else {
      resolved[p.name] = p.default
    }
  }
  return resolved
}

// ---------------------------------------------------------------------------
// Geometry preview (client-side analytic for circular_column)
// ---------------------------------------------------------------------------

/**
 * Compute a lightweight geometry preview from resolved params.
 * For ``circular_column`` this returns the analytic volume π·D²·H/4.
 * For other geometry types the preview is ``null`` (server handles it).
 *
 * @param {object} template  FamilyTemplate
 * @param {object} resolved  resolved param map from resolveParamValues()
 * @returns {{ volume?: number, diameter?: number, height?: number } | null}
 */
export function previewGeometry(template, resolved) {
  if (template.geometry_type === 'circular_column') {
    const D = Number(resolved.D ?? resolved.diameter ?? 0)
    const H = Number(resolved.H ?? resolved.height ?? 0)
    return {
      diameter: D,
      height: H,
      volume: Math.PI * D * D * H / 4,
    }
  }
  if (template.geometry_type === 'rectangular_column') {
    const W = Number(resolved.W ?? resolved.width ?? 0)
    const depth = Number(resolved.depth ?? resolved.D ?? 0)
    const H = Number(resolved.H ?? resolved.height ?? 0)
    return {
      width: W,
      depth,
      height: H,
      volume: W * depth * H,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Material catalogue subset (T-115 mirror — keeps the UI offline-capable)
// ---------------------------------------------------------------------------

/** Flat list of material ids from the T-115 catalogue, grouped by category. */
export const MATERIAL_CATALOGUE = [
  // concrete
  { id: 'concrete_m20', label: 'Concrete M20', category: 'concrete' },
  { id: 'concrete_m30', label: 'Concrete M30', category: 'concrete' },
  { id: 'concrete_m40', label: 'Concrete M40', category: 'concrete' },
  { id: 'concrete_m50', label: 'Concrete M50', category: 'concrete' },
  // steel
  { id: 'steel_a36',       label: 'Steel A36',       category: 'steel' },
  { id: 'steel_a572_50',   label: 'Steel A572-50',   category: 'steel' },
  { id: 'steel_s275',      label: 'Steel S275',      category: 'steel' },
  { id: 'steel_s355',      label: 'Steel S355',      category: 'steel' },
  { id: 'steel_stainless_304', label: 'Steel 304 SS', category: 'steel' },
  // aluminum
  { id: 'aluminum_6061_t6',  label: 'Aluminium 6061-T6',  category: 'aluminum' },
  { id: 'aluminum_5052_h32', label: 'Aluminium 5052-H32', category: 'aluminum' },
  // timber
  { id: 'timber_spf',          label: 'Timber SPF',          category: 'timber' },
  { id: 'timber_doug_fir',     label: 'Timber Douglas Fir',  category: 'timber' },
  { id: 'timber_oak',          label: 'Timber Oak',          category: 'timber' },
  { id: 'timber_southern_pine',label: 'Timber Southern Pine',category: 'timber' },
  // masonry / glass
  { id: 'brick_clay',          label: 'Clay Brick',          category: 'masonry' },
  { id: 'masonry_cmu_concrete',label: 'Concrete CMU',        category: 'masonry' },
  { id: 'glass_annealed_float',label: 'Glass (annealed)',    category: 'glass' },
  { id: 'glass_tempered',      label: 'Glass (tempered)',    category: 'glass' },
]

/**
 * Return a sorted, de-duped list of category strings present in MATERIAL_CATALOGUE.
 * @returns {string[]}
 */
export function materialCategories() {
  return [...new Set(MATERIAL_CATALOGUE.map((m) => m.category))].sort()
}

/**
 * Filter MATERIAL_CATALOGUE by category.
 * @param {string} category
 * @returns {Array<{id:string, label:string, category:string}>}
 */
export function materialsByCategory(category) {
  return MATERIAL_CATALOGUE.filter((m) => m.category === category)
}
