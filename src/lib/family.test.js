import { describe, it, expect } from 'vitest'
import {
  defaultFamily,
  validateFamily,
  resolveParams,
  validateInstance,
  addParam,
  removeParam,
  updateParam,
  addType,
  removeType,
  flexFamily,
} from './family.js'

// ── defaultFamily ─────────────────────────────────────────────────────────────

describe('defaultFamily', () => {
  it('returns a valid family for a known category', () => {
    const f = defaultFamily('Window')
    expect(f.version).toBe(1)
    expect(f.category).toBe('Window')
    expect(Array.isArray(f.params)).toBe(true)
    expect(Array.isArray(f.types)).toBe(true)
  })

  it('defaults to Generic when no category supplied', () => {
    const f = defaultFamily()
    expect(f.category).toBe('Generic')
  })
})

// ── validateFamily ────────────────────────────────────────────────────────────

describe('validateFamily', () => {
  it('accepts a well-formed window family', () => {
    const f = {
      version: 1,
      name: 'Standard Window',
      category: 'Window',
      params: [
        { name: 'width', type: 'number', unit: 'mm', default: 900, min: 300, max: 3000 },
        { name: 'glazing', type: 'enum', options: ['single', 'double', 'triple'], default: 'double' },
      ],
      types: [],
    }
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('rejects unknown category', () => {
    const f = { ...defaultFamily('Window'), category: 'Spaceship' }
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('category'))).toBe(true)
  })

  it('rejects wrong version', () => {
    const f = { ...defaultFamily('Door'), version: 2 }
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('version'))).toBe(true)
  })

  it('rejects duplicate param names', () => {
    const f = defaultFamily('Wall')
    f.params = [
      { name: 'width', type: 'number', default: 100 },
      { name: 'width', type: 'number', default: 200 },
    ]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('duplicate'))).toBe(true)
  })

  it('rejects enum param without options', () => {
    const f = defaultFamily('Door')
    f.params = [{ name: 'swing', type: 'enum', options: [], default: 'left' }]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('options'))).toBe(true)
  })

  it('rejects enum default not in options', () => {
    const f = defaultFamily('Door')
    f.params = [{ name: 'swing', type: 'enum', options: ['left', 'right'], default: 'both' }]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('not in options'))).toBe(true)
  })

  it('rejects number param where min > max', () => {
    const f = defaultFamily('Window')
    f.params = [{ name: 'width', type: 'number', min: 1000, max: 500 }]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('min') && e.includes('max'))).toBe(true)
  })

  it('rejects duplicate type ids', () => {
    const f = defaultFamily('Column')
    f.types = [
      { id: 't1', name: 'Type A', params: {} },
      { id: 't1', name: 'Type B', params: {} },
    ]
    const { ok, errors } = validateFamily(f)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('duplicate type'))).toBe(true)
  })
})

// ── resolveParams ─────────────────────────────────────────────────────────────

describe('resolveParams', () => {
  const family = {
    version: 1,
    name: 'Window',
    category: 'Window',
    params: [
      { name: 'width', type: 'number', default: 900 },
      { name: 'height', type: 'number', default: 1200 },
      { name: 'glazing', type: 'enum', options: ['single', 'double', 'triple'], default: 'double' },
      { name: 'sill_height', type: 'number', default: 900 },
    ],
    types: [
      { id: 'type-wide', name: 'Wide', params: { width: 1500, glazing: 'triple' } },
    ],
  }

  it('returns defaults when no instance overrides', () => {
    const r = resolveParams(family, {})
    expect(r.width).toBe(900)
    expect(r.height).toBe(1200)
    expect(r.glazing).toBe('double')
  })

  it('instance params override defaults', () => {
    const r = resolveParams(family, { params: { width: 800 } })
    expect(r.width).toBe(800)
    expect(r.height).toBe(1200)
  })

  it('type params override defaults', () => {
    const r = resolveParams(family, { type_id: 'type-wide' })
    expect(r.width).toBe(1500)
    expect(r.glazing).toBe('triple')
    expect(r.height).toBe(1200) // still from default
  })

  it('instance params override type params (full precedence chain)', () => {
    const r = resolveParams(family, { type_id: 'type-wide', params: { width: 600, sill_height: 850 } })
    expect(r.width).toBe(600)       // instance wins over type
    expect(r.glazing).toBe('triple') // type wins over default
    expect(r.height).toBe(1200)     // default
    expect(r.sill_height).toBe(850) // instance
  })

  it('unknown type_id yields only defaults', () => {
    const r = resolveParams(family, { type_id: 'does-not-exist' })
    expect(r.width).toBe(900)
  })
})

// ── validateInstance ──────────────────────────────────────────────────────────

describe('validateInstance', () => {
  const family = {
    version: 1,
    name: 'Door',
    category: 'Door',
    params: [
      { name: 'width', type: 'number', default: 900, min: 600, max: 2400 },
      { name: 'height', type: 'number', default: 2100, min: 1800, max: 3000 },
      { name: 'swing', type: 'enum', options: ['left', 'right', 'double'], default: 'right' },
    ],
    types: [{ id: 'type-a', name: 'Type A', params: { width: 1000 } }],
  }

  it('accepts valid resolved params', () => {
    const { ok } = validateInstance(family, { params: { width: 900, swing: 'left' } })
    expect(ok).toBe(true)
  })

  it('rejects value below min', () => {
    const { ok, errors } = validateInstance(family, { params: { width: 100 } })
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('below min'))).toBe(true)
  })

  it('rejects value above max', () => {
    const { ok, errors } = validateInstance(family, { params: { height: 5000 } })
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('above max'))).toBe(true)
  })

  it('rejects invalid enum value', () => {
    const { ok, errors } = validateInstance(family, { params: { swing: 'up' } })
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('not a valid option'))).toBe(true)
  })

  it('rejects unknown type_id', () => {
    const { ok, errors } = validateInstance(family, { type_id: 'no-such-type' })
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('type_id'))).toBe(true)
  })

  it('accepts valid type_id reference', () => {
    const { ok } = validateInstance(family, { type_id: 'type-a' })
    expect(ok).toBe(true)
  })
})

// ── addParam / removeParam / updateParam ──────────────────────────────────────

describe('addParam / removeParam / updateParam', () => {
  it('addParam appends a new param', () => {
    const f = defaultFamily('Beam')
    addParam(f, { name: 'span', type: 'number', default: 6000 })
    expect(f.params).toHaveLength(1)
    expect(f.params[0].name).toBe('span')
  })

  it('addParam throws on duplicate name', () => {
    const f = defaultFamily('Beam')
    addParam(f, { name: 'span', type: 'number' })
    expect(() => addParam(f, { name: 'span', type: 'number' })).toThrow()
  })

  it('removeParam removes by name', () => {
    const f = defaultFamily('Beam')
    addParam(f, { name: 'span', type: 'number' })
    addParam(f, { name: 'depth', type: 'number' })
    removeParam(f, 'span')
    expect(f.params).toHaveLength(1)
    expect(f.params[0].name).toBe('depth')
  })

  it('removeParam throws when name not found', () => {
    const f = defaultFamily('Beam')
    expect(() => removeParam(f, 'nonexistent')).toThrow()
  })

  it('updateParam patches a field', () => {
    const f = defaultFamily('Window')
    addParam(f, { name: 'width', type: 'number', default: 900 })
    updateParam(f, 'width', { default: 1200, max: 3000 })
    expect(f.params[0].default).toBe(1200)
    expect(f.params[0].max).toBe(3000)
  })
})

// ── addType / removeType ──────────────────────────────────────────────────────

describe('addType / removeType', () => {
  it('addType appends a named preset', () => {
    const f = defaultFamily('Column')
    addType(f, { id: 'ipe200', name: 'IPE 200', params: { depth: 200, width: 100 } })
    expect(f.types).toHaveLength(1)
    expect(f.types[0].id).toBe('ipe200')
  })

  it('addType throws on duplicate id', () => {
    const f = defaultFamily('Column')
    addType(f, { id: 'ipe200', name: 'IPE 200', params: {} })
    expect(() => addType(f, { id: 'ipe200', name: 'IPE 200 dup', params: {} })).toThrow()
  })

  it('removeType removes by id', () => {
    const f = defaultFamily('Column')
    addType(f, { id: 'ipe200', name: 'IPE 200', params: {} })
    addType(f, { id: 'ipe300', name: 'IPE 300', params: {} })
    removeType(f, 'ipe200')
    expect(f.types).toHaveLength(1)
    expect(f.types[0].id).toBe('ipe300')
  })

  it('removeType throws when id not found', () => {
    const f = defaultFamily('Column')
    expect(() => removeType(f, 'missing')).toThrow()
  })
})

// ── flexFamily — end-to-end parametric flex tests (T-109 DoD) ─────────────────

describe('flexFamily — column family end-to-end flex', () => {
  // Parametric Column family with multiple types
  const columnFamily = {
    version: 1,
    name: 'Structural Column',
    category: 'Column',
    params: [
      { name: 'width',    type: 'number', default: 400, min: 150, max: 1200, unit: 'mm' },
      { name: 'depth',    type: 'number', default: 400, min: 150, max: 1200, unit: 'mm' },
      { name: 'height',   type: 'number', default: 3600, min: 2000, max: 12000, unit: 'mm' },
      { name: 'material', type: 'enum',   default: 'concrete', options: ['concrete', 'steel', 'timber'] },
    ],
    types: [
      { id: '300sq',  name: '300×300',  params: { width: 300,  depth: 300 } },
      { id: '400sq',  name: '400×400',  params: { width: 400,  depth: 400 } },
      { id: '600sq',  name: '600×600',  params: { width: 600,  depth: 600 } },
      { id: '400x600', name: '400×600', params: { width: 400,  depth: 600, material: 'steel' } },
    ],
  }

  it('returns allOk when all parameter sets are valid', () => {
    const { results, allOk } = flexFamily(columnFamily, [
      {},                                          // all defaults
      { type_id: '300sq' },                        // smallest type
      { type_id: '600sq' },                        // largest type
      { type_id: '400x600', params: { height: 4000 } }, // type + instance override
    ])
    expect(results).toHaveLength(4)
    expect(allOk).toBe(true)
  })

  it('resolves defaults for empty instance', () => {
    const { results } = flexFamily(columnFamily, [{}])
    const r = results[0].resolved
    expect(r.width).toBe(400)
    expect(r.depth).toBe(400)
    expect(r.height).toBe(3600)
    expect(r.material).toBe('concrete')
  })

  it('resolves type param preset correctly', () => {
    const { results } = flexFamily(columnFamily, [{ type_id: '300sq' }])
    const r = results[0].resolved
    expect(r.width).toBe(300)
    expect(r.depth).toBe(300)
    expect(r.material).toBe('concrete') // falls through to default
  })

  it('instance param beats type param beats default', () => {
    const { results } = flexFamily(columnFamily, [
      { type_id: '400x600', params: { depth: 700 } },
    ])
    const r = results[0].resolved
    expect(r.width).toBe(400)    // from type
    expect(r.depth).toBe(700)    // instance overrides type (600)
    expect(r.material).toBe('steel') // from type
  })

  it('flags below-min violation and marks row not ok', () => {
    const { results, allOk } = flexFamily(columnFamily, [
      { params: { width: 50 } },  // 50 < min 150
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /below min/.test(e))).toBe(true)
    expect(allOk).toBe(false)
  })

  it('flags above-max violation', () => {
    const { results } = flexFamily(columnFamily, [
      { params: { height: 99999 } },  // > max 12000
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /above max/.test(e))).toBe(true)
  })

  it('flags invalid enum value', () => {
    const { results } = flexFamily(columnFamily, [
      { params: { material: 'aluminium' } },
    ])
    expect(results[0].ok).toBe(false)
    expect(results[0].errors.some((e) => /not a valid option/.test(e))).toBe(true)
  })

  it('throws when parameterSets is empty', () => {
    expect(() => flexFamily(columnFamily, [])).toThrow()
  })

  it('spans all 4 types correctly (full type sweep)', () => {
    const sets = columnFamily.types.map((t) => ({ type_id: t.id }))
    const { results, allOk } = flexFamily(columnFamily, sets)
    expect(allOk).toBe(true)
    expect(results[0].resolved.width).toBe(300)
    expect(results[1].resolved.width).toBe(400)
    expect(results[2].resolved.width).toBe(600)
    expect(results[3].resolved.depth).toBe(600)
  })
})

describe('flexFamily — window family end-to-end flex', () => {
  const windowFamily = {
    version: 1,
    name: 'Casement Window',
    category: 'Window',
    params: [
      { name: 'width',   type: 'number', default: 900,  min: 300, max: 3000, unit: 'mm' },
      { name: 'height',  type: 'number', default: 1200, min: 600, max: 2400, unit: 'mm' },
      { name: 'glazing', type: 'enum',   default: 'double', options: ['single', 'double', 'triple'] },
      { name: 'openable', type: 'boolean', default: true },
    ],
    types: [
      { id: 'narrow', name: 'Narrow', params: { width: 600 } },
      { id: 'wide',   name: 'Wide',   params: { width: 1500, glazing: 'triple' } },
      { id: 'fixed',  name: 'Fixed',  params: { openable: false } },
    ],
  }

  it('flexes all window types with valid params', () => {
    const sets = windowFamily.types.map((t) => ({ type_id: t.id }))
    const { allOk } = flexFamily(windowFamily, sets)
    expect(allOk).toBe(true)
  })

  it('wide type has correct glazing', () => {
    const { results } = flexFamily(windowFamily, [{ type_id: 'wide' }])
    expect(results[0].resolved.glazing).toBe('triple')
    expect(results[0].resolved.width).toBe(1500)
  })

  it('fixed type sets openable to false', () => {
    const { results } = flexFamily(windowFamily, [{ type_id: 'fixed' }])
    expect(results[0].resolved.openable).toBe(false)
  })
})

describe('flexFamily — door family end-to-end flex', () => {
  const doorFamily = {
    version: 1,
    name: 'Single Leaf Door',
    category: 'Door',
    params: [
      { name: 'width',   type: 'number', default: 900,  min: 600, max: 2400, unit: 'mm' },
      { name: 'height',  type: 'number', default: 2100, min: 1800, max: 3000, unit: 'mm' },
      { name: 'swing',   type: 'enum',   default: 'right', options: ['left', 'right', 'double', 'sliding'] },
      { name: 'fire_rated', type: 'boolean', default: false },
    ],
    types: [
      { id: '762x2032', name: '762×2032',  params: { width: 762,  height: 2032 } },
      { id: '838x2032', name: '838×2032',  params: { width: 838,  height: 2032 } },
      { id: '900x2100', name: '900×2100',  params: { width: 900,  height: 2100 } },
      { id: 'double',   name: 'Double',    params: { width: 1800, swing: 'double' } },
    ],
  }

  it('flexes all door types cleanly', () => {
    const sets = doorFamily.types.map((t) => ({ type_id: t.id }))
    const { allOk, results } = flexFamily(doorFamily, sets)
    expect(allOk).toBe(true)
    expect(results).toHaveLength(4)
  })

  it('double door type sets correct swing', () => {
    const { results } = flexFamily(doorFamily, [{ type_id: 'double' }])
    expect(results[0].resolved.swing).toBe('double')
    expect(results[0].resolved.width).toBe(1800)
  })

  it('authored instance overrides type', () => {
    const { results } = flexFamily(doorFamily, [
      { type_id: '900x2100', params: { swing: 'left', fire_rated: true } },
    ])
    const r = results[0].resolved
    expect(r.swing).toBe('left')
    expect(r.fire_rated).toBe(true)
    expect(r.width).toBe(900)
    expect(r.height).toBe(2100)
  })
})
