/**
 * BimFamilyEditor.test.jsx — vitest tests for the BIM parametric family-
 * authoring panel (T-109).
 *
 * Tests cover two layers:
 *   A) Pure logic in bimFamilyOps.js (no DOM required)
 *   B) Static markup produced by BimFamilyEditor via react-dom/server
 *
 * The project pattern (see Loader.test.jsx) avoids @testing-library/react
 * and uses renderToStaticMarkup instead, so no new npm deps are needed.
 */

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import BimFamilyEditor from './BimFamilyEditor.jsx'
import {
  defaultColumnTemplate,
  validateTemplate,
  resolveParamValues,
  previewGeometry,
  clampParam,
  MATERIAL_CATALOGUE,
  materialCategories,
  materialsByCategory,
  NUMERIC_KINDS,
} from '../lib/bimFamilyOps.js'

// ── A. bimFamilyOps.js pure-logic tests ─────────────────────────────────────

describe('defaultColumnTemplate', () => {
  it('has name, category, geometry_type and parameters', () => {
    const t = defaultColumnTemplate()
    expect(t.name).toBeTruthy()
    expect(t.category).toBe('Column')
    expect(t.geometry_type).toBe('circular_column')
    expect(Array.isArray(t.parameters)).toBe(true)
  })

  it('includes D, H and material params', () => {
    const t = defaultColumnTemplate()
    const names = t.parameters.map((p) => p.name)
    expect(names).toContain('D')
    expect(names).toContain('H')
    expect(names).toContain('material')
  })

  it('D and H are numeric kinds', () => {
    const t = defaultColumnTemplate()
    const D = t.parameters.find((p) => p.name === 'D')
    const H = t.parameters.find((p) => p.name === 'H')
    expect(NUMERIC_KINDS.has(D.kind)).toBe(true)
    expect(NUMERIC_KINDS.has(H.kind)).toBe(true)
  })

  it('material is kind "material"', () => {
    const t = defaultColumnTemplate()
    const mat = t.parameters.find((p) => p.name === 'material')
    expect(mat.kind).toBe('material')
  })
})

describe('validateTemplate', () => {
  it('returns ok:true for the default column template', () => {
    const { ok, errors } = validateTemplate(defaultColumnTemplate())
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('returns ok:false when name is empty', () => {
    const t = { ...defaultColumnTemplate(), name: '' }
    const { ok, errors } = validateTemplate(t)
    expect(ok).toBe(false)
    expect(errors.some((e) => /name/i.test(e))).toBe(true)
  })

  it('returns ok:false when category is empty', () => {
    const t = { ...defaultColumnTemplate(), category: '' }
    const { ok } = validateTemplate(t)
    expect(ok).toBe(false)
  })

  it('reports duplicate parameter names', () => {
    const t = {
      ...defaultColumnTemplate(),
      parameters: [
        { name: 'X', kind: 'length', default: 1.0 },
        { name: 'X', kind: 'length', default: 2.0 },
      ],
    }
    const { ok, errors } = validateTemplate(t)
    expect(ok).toBe(false)
    expect(errors.some((e) => /duplicate/i.test(e))).toBe(true)
  })

  it('reports when default is below min_val', () => {
    const t = {
      ...defaultColumnTemplate(),
      parameters: [
        { name: 'D', kind: 'length', default: 0.01, min_val: 0.05, max_val: 5.0 },
      ],
    }
    const { ok, errors } = validateTemplate(t)
    expect(ok).toBe(false)
    expect(errors.some((e) => /min_val/i.test(e))).toBe(true)
  })

  it('returns ok:false for a non-object input', () => {
    const { ok } = validateTemplate(null)
    expect(ok).toBe(false)
  })
})

describe('clampParam', () => {
  const param = { kind: 'length', min_val: 0.05, max_val: 5.0 }

  it('clamps below min to min', () => {
    expect(clampParam(param, 0.01)).toBe(0.05)
  })

  it('clamps above max to max', () => {
    expect(clampParam(param, 100)).toBe(5.0)
  })

  it('passes through a value within range', () => {
    expect(clampParam(param, 1.5)).toBe(1.5)
  })

  it('handles null min/max (no clamping)', () => {
    const free = { kind: 'length', min_val: null, max_val: null }
    expect(clampParam(free, 999)).toBe(999)
  })
})

describe('resolveParamValues', () => {
  it('uses default values when no overrides', () => {
    const t = defaultColumnTemplate()
    const r = resolveParamValues(t, {})
    expect(r.D).toBe(0.3)
    expect(r.H).toBe(3.0)
  })

  it('applies overrides', () => {
    const t = defaultColumnTemplate()
    const r = resolveParamValues(t, { D: 0.6, H: 6.0 })
    expect(r.D).toBe(0.6)
    expect(r.H).toBe(6.0)
  })

  it('clamps override to min_val', () => {
    const t = defaultColumnTemplate()
    const r = resolveParamValues(t, { D: 0.001 }) // below min 0.05
    expect(r.D).toBeGreaterThanOrEqual(0.05)
  })

  it('propagates material override', () => {
    const t = defaultColumnTemplate()
    const r = resolveParamValues(t, { material: 'steel_a36' })
    expect(r.material).toBe('steel_a36')
  })
})

describe('previewGeometry — circular_column (analytic volume oracle)', () => {
  it('computes volume = π·D²·H/4 for default params', () => {
    const t = defaultColumnTemplate()
    const resolved = resolveParamValues(t, {})
    const preview = previewGeometry(t, resolved)
    const expected = Math.PI * 0.3 * 0.3 * 3.0 / 4
    expect(preview.volume).toBeCloseTo(expected, 9)
  })

  it('doubling D quadruples volume', () => {
    const t = defaultColumnTemplate()
    const base = previewGeometry(t, resolveParamValues(t, { D: 0.3, H: 3.0 }))
    const dbl = previewGeometry(t, resolveParamValues(t, { D: 0.6, H: 3.0 }))
    expect(dbl.volume / base.volume).toBeCloseTo(4.0, 9)
  })

  it('doubling H doubles volume', () => {
    const t = defaultColumnTemplate()
    const base = previewGeometry(t, resolveParamValues(t, { D: 0.3, H: 3.0 }))
    const dbl = previewGeometry(t, resolveParamValues(t, { D: 0.3, H: 6.0 }))
    expect(dbl.volume / base.volume).toBeCloseTo(2.0, 9)
  })

  it('returns null for unknown geometry_type', () => {
    const t = { ...defaultColumnTemplate(), geometry_type: 'nurbs_surface' }
    const resolved = resolveParamValues(t, {})
    expect(previewGeometry(t, resolved)).toBeNull()
  })

  it('returns diameter, height fields', () => {
    const t = defaultColumnTemplate()
    const preview = previewGeometry(t, resolveParamValues(t, {}))
    expect(preview).toHaveProperty('diameter')
    expect(preview).toHaveProperty('height')
  })
})

describe('previewGeometry — rectangular_column', () => {
  const rectTemplate = {
    name: 'Rect Column',
    category: 'Column',
    geometry_type: 'rectangular_column',
    parameters: [
      { name: 'W', kind: 'length', default: 0.4, min_val: 0.1 },
      { name: 'depth', kind: 'length', default: 0.4, min_val: 0.1 },
      { name: 'H', kind: 'length', default: 3.0, min_val: 0.5 },
    ],
  }

  it('computes volume = W * depth * H', () => {
    const resolved = resolveParamValues(rectTemplate, {})
    const preview = previewGeometry(rectTemplate, resolved)
    expect(preview.volume).toBeCloseTo(0.4 * 0.4 * 3.0, 9)
  })
})

describe('MATERIAL_CATALOGUE', () => {
  it('has at least one entry per structural category', () => {
    const cats = new Set(MATERIAL_CATALOGUE.map((m) => m.category))
    expect(cats.has('concrete')).toBe(true)
    expect(cats.has('steel')).toBe(true)
    expect(cats.has('timber')).toBe(true)
  })

  it('every entry has id, label, category', () => {
    for (const m of MATERIAL_CATALOGUE) {
      expect(typeof m.id).toBe('string')
      expect(typeof m.label).toBe('string')
      expect(typeof m.category).toBe('string')
    }
  })

  it('concrete_m30 is present (default material)', () => {
    expect(MATERIAL_CATALOGUE.some((m) => m.id === 'concrete_m30')).toBe(true)
  })
})

describe('materialCategories / materialsByCategory', () => {
  it('returns sorted unique categories', () => {
    const cats = materialCategories()
    expect(Array.isArray(cats)).toBe(true)
    expect(cats.length).toBeGreaterThan(0)
    // sorted
    expect([...cats].sort()).toEqual(cats)
  })

  it('materialsByCategory filters correctly', () => {
    const steel = materialsByCategory('steel')
    expect(steel.length).toBeGreaterThan(0)
    expect(steel.every((m) => m.category === 'steel')).toBe(true)
  })
})

// ── B. BimFamilyEditor static markup tests ───────────────────────────────────

describe('BimFamilyEditor (renderToStaticMarkup)', () => {
  it('renders without crashing', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(typeof html).toBe('string')
    expect(html.length).toBeGreaterThan(0)
  })

  it('renders the data-testid root element', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/data-testid="bim-family-editor"/)
  })

  it('renders a "Family Editor" heading', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toContain('Family Editor')
  })

  it('renders a "Parameters" section', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/Parameters/i)
  })

  it('renders a "Preview" section', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/Preview/i)
  })

  it('includes input[type=range] sliders for numeric params', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/type="range"/)
  })

  it('includes a material select dropdown', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/<select/)
  })

  it('includes Volume in the preview panel', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/Volume/)
  })

  it('renders geometry_type badge', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toContain('circular_column')
  })

  it('accepts a custom template prop', () => {
    const t = {
      ...defaultColumnTemplate(),
      name: 'Test Pillar',
    }
    const html = renderToStaticMarkup(<BimFamilyEditor template={t} />)
    expect(html).toContain('Test Pillar')
  })

  it('renders family-name input with aria-label', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/aria-label="Family name"/)
  })

  it('renders family-category input with aria-label', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor />)
    expect(html).toMatch(/aria-label="Family category"/)
  })

  it('marks inputs readonly when readOnly prop is true', () => {
    const html = renderToStaticMarkup(<BimFamilyEditor readOnly />)
    // React serialises the readOnly prop as readOnly="" in SSR markup.
    expect(html).toMatch(/readOnly=""/)
  })
})
