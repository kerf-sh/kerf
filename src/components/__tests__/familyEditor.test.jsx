// familyEditor.test.jsx — Pure data-layer tests for FamilyEditor helpers.
//
// Tests operate directly on family.js exported functions — same pattern as
// graphEditor.test.jsx. No React rendering needed.

import { describe, it, expect } from 'vitest'
import {
  defaultFamily,
  validateFamily,
  addParam,
  removeParam,
  updateParam,
  addType,
  removeType,
  resolveParams,
  flexFamily,
} from '../../lib/family.js'

// ── 1. defaultFamily ──────────────────────────────────────────────────────────

describe('defaultFamily', () => {
  it('returns an object with the given category', () => {
    const f = defaultFamily('Door')
    expect(f.category).toBe('Door')
  })

  it('defaults to Generic when no category supplied', () => {
    const f = defaultFamily()
    expect(f.category).toBe('Generic')
  })

  it('has an empty params array', () => {
    const f = defaultFamily()
    expect(Array.isArray(f.params)).toBe(true)
    expect(f.params).toHaveLength(0)
  })

  it('has an empty types array', () => {
    const f = defaultFamily()
    expect(Array.isArray(f.types)).toBe(true)
    expect(f.types).toHaveLength(0)
  })

  it('passes validateFamily with no errors', () => {
    const { ok } = validateFamily(defaultFamily('Window'))
    expect(ok).toBe(true)
  })
})

// ── 2. validateFamily ─────────────────────────────────────────────────────────

describe('validateFamily', () => {
  it('rejects a non-object', () => {
    const { ok, errors } = validateFamily(null)
    expect(ok).toBe(false)
    expect(errors.length).toBeGreaterThan(0)
  })

  it('rejects an invalid category', () => {
    const f = { ...defaultFamily(), category: 'Spaceship' }
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => /category/.test(e))).toBe(true)
  })

  it('rejects duplicate param names', () => {
    const f = defaultFamily()
    f.params = [
      { name: 'width', type: 'number' },
      { name: 'width', type: 'number' },
    ]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => /duplicate/.test(e))).toBe(true)
  })

  it('rejects a number param where min > max', () => {
    const f = defaultFamily()
    f.params = [{ name: 'h', type: 'number', min: 100, max: 50 }]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => /min.*max/.test(e))).toBe(true)
  })
})

// ── 3. addParam / removeParam / updateParam ───────────────────────────────────

describe('addParam', () => {
  it('appends the param', () => {
    const f = defaultFamily()
    addParam(f, { name: 'width', type: 'number', default: 600 })
    expect(f.params).toHaveLength(1)
    expect(f.params[0].name).toBe('width')
  })

  it('throws on duplicate name', () => {
    const f = defaultFamily()
    addParam(f, { name: 'width', type: 'number' })
    expect(() => addParam(f, { name: 'width', type: 'number' })).toThrow()
  })
})

describe('removeParam', () => {
  it('removes the named param', () => {
    const f = defaultFamily()
    addParam(f, { name: 'height', type: 'number' })
    removeParam(f, 'height')
    expect(f.params).toHaveLength(0)
  })

  it('throws when the param does not exist', () => {
    const f = defaultFamily()
    expect(() => removeParam(f, 'ghost')).toThrow()
  })
})

describe('updateParam', () => {
  it('patches the param in place', () => {
    const f = defaultFamily()
    addParam(f, { name: 'depth', type: 'number', default: 200 })
    updateParam(f, 'depth', { default: 300 })
    expect(f.params[0].default).toBe(300)
  })
})

// ── 4. addType / removeType ───────────────────────────────────────────────────

describe('addType / removeType', () => {
  it('adds a named type preset', () => {
    const f = defaultFamily()
    addType(f, { id: 'single', name: 'Single', params: { width: 800 } })
    expect(f.types).toHaveLength(1)
    expect(f.types[0].id).toBe('single')
  })

  it('throws on duplicate type id', () => {
    const f = defaultFamily()
    addType(f, { id: 'double', name: 'Double', params: {} })
    expect(() => addType(f, { id: 'double', name: 'Double2', params: {} })).toThrow()
  })

  it('removes a type by id', () => {
    const f = defaultFamily()
    addType(f, { id: 'slim', name: 'Slim', params: {} })
    removeType(f, 'slim')
    expect(f.types).toHaveLength(0)
  })
})

// ── 5. resolveParams ──────────────────────────────────────────────────────────

describe('resolveParams', () => {
  it('resolves defaults', () => {
    const f = defaultFamily()
    addParam(f, { name: 'width', type: 'number', default: 900 })
    const resolved = resolveParams(f, {})
    expect(resolved.width).toBe(900)
  })

  it('instance overrides type which overrides default', () => {
    const f = defaultFamily()
    addParam(f, { name: 'height', type: 'number', default: 2100 })
    addType(f, { id: 'tall', name: 'Tall', params: { height: 2400 } })
    const resolved = resolveParams(f, { type_id: 'tall', params: { height: 2600 } })
    expect(resolved.height).toBe(2600)
  })

  it('type override wins over default when no instance override', () => {
    const f = defaultFamily()
    addParam(f, { name: 'width', type: 'number', default: 800 })
    addType(f, { id: 'narrow', name: 'Narrow', params: { width: 700 } })
    const resolved = resolveParams(f, { type_id: 'narrow' })
    expect(resolved.width).toBe(700)
  })
})

// ── 6. flexFamily — T-109 flex panel (column / window / door) ─────────────────

describe('flexFamily — T-109 DoD flex panel', () => {
  // Shared column family fixture
  const columnFamily = {
    version: 1,
    name: 'Concrete Column',
    category: 'Column',
    params: [
      { name: 'width',  type: 'number', default: 400, min: 150, max: 1200, unit: 'mm' },
      { name: 'depth',  type: 'number', default: 400, min: 150, max: 1200, unit: 'mm' },
      { name: 'height', type: 'number', default: 3600, min: 2000, max: 12000, unit: 'mm' },
      { name: 'grade',  type: 'enum',   default: 'C30/37', options: ['C25/30', 'C30/37', 'C40/50', 'C45/55'] },
    ],
    types: [
      { id: '300sq',  name: '300×300',  params: { width: 300,  depth: 300 } },
      { id: '400sq',  name: '400×400',  params: { width: 400,  depth: 400 } },
      { id: '600sq',  name: '600×600',  params: { width: 600,  depth: 600 } },
      { id: '400x600', name: '400×600', params: { width: 400,  depth: 600, grade: 'C40/50' } },
    ],
  }

  it('sweeps all column types with allOk=true', () => {
    const sets = columnFamily.types.map((t) => ({ type_id: t.id }))
    const { allOk, results } = flexFamily(columnFamily, sets)
    expect(allOk).toBe(true)
    expect(results).toHaveLength(4)
  })

  it('300sq type resolves correct width and depth', () => {
    const { results } = flexFamily(columnFamily, [{ type_id: '300sq' }])
    expect(results[0].resolved.width).toBe(300)
    expect(results[0].resolved.depth).toBe(300)
    expect(results[0].resolved.grade).toBe('C30/37') // falls through to default
  })

  it('400x600 type resolves with upgraded grade', () => {
    const { results } = flexFamily(columnFamily, [{ type_id: '400x600' }])
    expect(results[0].resolved.width).toBe(400)
    expect(results[0].resolved.depth).toBe(600)
    expect(results[0].resolved.grade).toBe('C40/50')
  })

  it('instance param overrides type grade', () => {
    const { results } = flexFamily(columnFamily, [
      { type_id: '400sq', params: { grade: 'C45/55' } },
    ])
    expect(results[0].resolved.grade).toBe('C45/55')
    expect(results[0].ok).toBe(true)
  })

  it('below-min width is flagged', () => {
    const { results, allOk } = flexFamily(columnFamily, [
      { params: { width: 50 } }, // below min 150
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /below min/.test(e))).toBe(true)
    expect(allOk).toBe(false)
  })

  it('above-max height is flagged', () => {
    const { results } = flexFamily(columnFamily, [
      { params: { height: 99999 } }, // above max 12000
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /above max/.test(e))).toBe(true)
  })

  it('invalid enum grade is flagged', () => {
    const { results } = flexFamily(columnFamily, [
      { params: { grade: 'C80/100' } }, // not in options
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /not a valid option/.test(e))).toBe(true)
  })

  it('result includes index, input, resolved, errors, ok', () => {
    const { results } = flexFamily(columnFamily, [{ type_id: '400sq' }])
    const r = results[0]
    expect(r).toHaveProperty('index', 0)
    expect(r).toHaveProperty('input')
    expect(r).toHaveProperty('resolved')
    expect(r).toHaveProperty('errors')
    expect(r).toHaveProperty('ok')
  })

  it('throws on empty parameter sets', () => {
    expect(() => flexFamily(columnFamily, [])).toThrow()
  })
})
