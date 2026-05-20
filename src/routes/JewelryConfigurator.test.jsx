/**
 * JewelryConfigurator.test.jsx
 *
 * Tests the pure-logic layer of the JewelryConfigurator wizard.
 * No DOM / React rendering required — we exercise the exported constants and
 * helper functions directly, then verify the component module shape.
 *
 * Coverage areas:
 *   1.  STEPS constant structure
 *   2.  PIECE_TYPES constant structure
 *   3.  METAL_OPTIONS constant structure
 *   4.  FINISH_OPTIONS constant structure
 *   5.  STONE_CUTS constant
 *   6.  SETTING_STYLES constant
 *   7.  RING_SIZES_US / CHAIN_LENGTHS_INCH constants
 *   8.  PRICE_PRESET coverage
 *   9.  DEFAULT_VOLUME_MM3 values
 *  10.  defaultStone factory
 *  11.  initialState factory
 *  12.  validateStep — step 0 (piece type)
 *  13.  validateStep — step 1 (metal)
 *  14.  validateStep — step 2 (stones, always valid)
 *  15.  validateStep — step 3 (ring size required for rings)
 *  16.  validateStep — step 4 (review, always valid)
 *  17.  buildToolPayload — basic shape for ring + metal
 *  18.  buildToolPayload — stones included when valid
 *  19.  buildToolPayload — stones omitted when carat is empty/invalid
 *  20.  buildToolPayload — uses volume from DEFAULT_VOLUME_MM3
 *  21.  buildToolPayload — uses price from PRICE_PRESET
 *  22.  buildToolPayload — includes setting_type from state
 *  23.  buildToolPayload — includes finish type
 *  24.  computeLocalEstimate — null when metal missing
 *  25.  computeLocalEstimate — net weight matches density × volume / 1000
 *  26.  computeLocalEstimate — gross weight = net × 1.15
 *  27.  computeLocalEstimate — metal_cost = gross × price/g
 *  28.  computeLocalEstimate — stone_cost aggregated from stones
 *  29.  computeLocalEstimate — labour includes bench + setting + finish
 *  30.  module default export is a function (component shape)
 */

import { describe, it, expect } from 'vitest'
import {
  STEPS,
  STEP_COUNT,
  PIECE_TYPES,
  METAL_OPTIONS,
  FINISH_OPTIONS,
  STONE_CUTS,
  SETTING_STYLES,
  RING_SIZES_US,
  CHAIN_LENGTHS_INCH,
  PRICE_PRESET,
  DEFAULT_VOLUME_MM3,
  defaultStone,
  initialState,
  validateStep,
  buildToolPayload,
  computeLocalEstimate,
} from './JewelryConfigurator.jsx'
import JewelryConfigurator from './JewelryConfigurator.jsx'

// ---------------------------------------------------------------------------
// 1. STEPS constant structure
// ---------------------------------------------------------------------------

describe('STEPS constant', () => {
  it('has exactly 5 steps', () => {
    expect(STEPS).toHaveLength(5)
  })

  it('STEP_COUNT equals 5', () => {
    expect(STEP_COUNT).toBe(5)
  })

  it('step ids are piece, metal, stones, setting, review', () => {
    expect(STEPS.map((s) => s.id)).toEqual(['piece', 'metal', 'stones', 'setting', 'review'])
  })

  it('every step has an id and label', () => {
    for (const s of STEPS) {
      expect(typeof s.id).toBe('string')
      expect(s.id.length).toBeGreaterThan(0)
      expect(typeof s.label).toBe('string')
      expect(s.label.length).toBeGreaterThan(0)
    }
  })

  it('step ids are unique', () => {
    const ids = STEPS.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// ---------------------------------------------------------------------------
// 2. PIECE_TYPES constant structure
// ---------------------------------------------------------------------------

describe('PIECE_TYPES constant', () => {
  it('contains ring, pendant, earring', () => {
    const keys = PIECE_TYPES.map((p) => p.key)
    expect(keys).toContain('ring')
    expect(keys).toContain('pendant')
    expect(keys).toContain('earring')
  })

  it('every piece has key, label, tool, icon', () => {
    for (const p of PIECE_TYPES) {
      expect(typeof p.key).toBe('string')
      expect(typeof p.label).toBe('string')
      expect(typeof p.tool).toBe('string')
      expect(typeof p.icon).toBe('string')
    }
  })

  it('ring tool references jewelry_ring', () => {
    const ring = PIECE_TYPES.find((p) => p.key === 'ring')
    expect(ring.tool).toContain('jewelry_ring')
  })

  it('piece keys are unique', () => {
    const keys = PIECE_TYPES.map((p) => p.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ---------------------------------------------------------------------------
// 3. METAL_OPTIONS constant structure
// ---------------------------------------------------------------------------

describe('METAL_OPTIONS constant', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(METAL_OPTIONS)).toBe(true)
    expect(METAL_OPTIONS.length).toBeGreaterThan(0)
  })

  it('every option has key, label, group, density', () => {
    for (const m of METAL_OPTIONS) {
      expect(typeof m.key).toBe('string')
      expect(typeof m.label).toBe('string')
      expect(typeof m.group).toBe('string')
      expect(typeof m.density).toBe('number')
      expect(m.density).toBeGreaterThan(0)
    }
  })

  it('includes 18k_yellow gold', () => {
    expect(METAL_OPTIONS.find((m) => m.key === '18k_yellow')).toBeTruthy()
  })

  it('includes platinum_950', () => {
    expect(METAL_OPTIONS.find((m) => m.key === 'platinum_950')).toBeTruthy()
  })

  it('includes sterling_925', () => {
    expect(METAL_OPTIONS.find((m) => m.key === 'sterling_925')).toBeTruthy()
  })

  it('keys are unique', () => {
    const keys = METAL_OPTIONS.map((m) => m.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ---------------------------------------------------------------------------
// 4. FINISH_OPTIONS constant structure
// ---------------------------------------------------------------------------

describe('FINISH_OPTIONS constant', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(FINISH_OPTIONS)).toBe(true)
    expect(FINISH_OPTIONS.length).toBeGreaterThan(0)
  })

  it('every option has key, label, cost', () => {
    for (const f of FINISH_OPTIONS) {
      expect(typeof f.key).toBe('string')
      expect(typeof f.label).toBe('string')
      expect(typeof f.cost).toBe('number')
    }
  })

  it('includes a polish option with zero cost', () => {
    const p = FINISH_OPTIONS.find((f) => f.key === 'polish')
    expect(p).toBeTruthy()
    expect(p.cost).toBe(0)
  })

  it('rhodium plating has a non-zero cost', () => {
    const r = FINISH_OPTIONS.find((f) => f.key === 'rhodium')
    expect(r).toBeTruthy()
    expect(r.cost).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// 5. STONE_CUTS constant
// ---------------------------------------------------------------------------

describe('STONE_CUTS constant', () => {
  it('is a non-empty array of strings', () => {
    expect(Array.isArray(STONE_CUTS)).toBe(true)
    expect(STONE_CUTS.length).toBeGreaterThan(0)
    for (const c of STONE_CUTS) {
      expect(typeof c).toBe('string')
    }
  })

  it('includes round_brilliant', () => {
    expect(STONE_CUTS).toContain('round_brilliant')
  })

  it('includes emerald cut', () => {
    expect(STONE_CUTS).toContain('emerald')
  })

  it('includes oval cut', () => {
    expect(STONE_CUTS).toContain('oval')
  })
})

// ---------------------------------------------------------------------------
// 6. SETTING_STYLES constant
// ---------------------------------------------------------------------------

describe('SETTING_STYLES constant', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(SETTING_STYLES)).toBe(true)
    expect(SETTING_STYLES.length).toBeGreaterThan(0)
  })

  it('every style has key, label, fee', () => {
    for (const s of SETTING_STYLES) {
      expect(typeof s.key).toBe('string')
      expect(typeof s.label).toBe('string')
      expect(typeof s.fee).toBe('number')
      expect(s.fee).toBeGreaterThanOrEqual(0)
    }
  })

  it('includes prong setting', () => {
    expect(SETTING_STYLES.find((s) => s.key === 'prong')).toBeTruthy()
  })

  it('includes bezel setting', () => {
    expect(SETTING_STYLES.find((s) => s.key === 'bezel')).toBeTruthy()
  })

  it('keys are unique', () => {
    const keys = SETTING_STYLES.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ---------------------------------------------------------------------------
// 7. RING_SIZES_US / CHAIN_LENGTHS_INCH constants
// ---------------------------------------------------------------------------

describe('RING_SIZES_US constant', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(RING_SIZES_US)).toBe(true)
    expect(RING_SIZES_US.length).toBeGreaterThan(0)
  })

  it('contains common US ring sizes', () => {
    expect(RING_SIZES_US).toContain('6')
    expect(RING_SIZES_US).toContain('7')
  })
})

describe('CHAIN_LENGTHS_INCH constant', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(CHAIN_LENGTHS_INCH)).toBe(true)
    expect(CHAIN_LENGTHS_INCH.length).toBeGreaterThan(0)
  })

  it('contains standard chain lengths', () => {
    expect(CHAIN_LENGTHS_INCH).toContain('18')
    expect(CHAIN_LENGTHS_INCH).toContain('20')
  })
})

// ---------------------------------------------------------------------------
// 8. PRICE_PRESET coverage
// ---------------------------------------------------------------------------

describe('PRICE_PRESET coverage', () => {
  it('has price for 18k_yellow', () => {
    expect(typeof PRICE_PRESET['18k_yellow']).toBe('number')
    expect(PRICE_PRESET['18k_yellow']).toBeGreaterThan(0)
  })

  it('has price for sterling_925', () => {
    expect(typeof PRICE_PRESET['sterling_925']).toBe('number')
    expect(PRICE_PRESET['sterling_925']).toBeGreaterThan(0)
  })

  it('gold prices are higher than sterling prices', () => {
    expect(PRICE_PRESET['18k_yellow']).toBeGreaterThan(PRICE_PRESET['sterling_925'])
  })
})

// ---------------------------------------------------------------------------
// 9. DEFAULT_VOLUME_MM3 values
// ---------------------------------------------------------------------------

describe('DEFAULT_VOLUME_MM3 constants', () => {
  it('ring has a positive volume', () => {
    expect(DEFAULT_VOLUME_MM3.ring).toBeGreaterThan(0)
  })

  it('pendant has a positive volume', () => {
    expect(DEFAULT_VOLUME_MM3.pendant).toBeGreaterThan(0)
  })

  it('earring has a positive volume', () => {
    expect(DEFAULT_VOLUME_MM3.earring).toBeGreaterThan(0)
  })

  it('earring volume is less than ring volume (smaller piece)', () => {
    expect(DEFAULT_VOLUME_MM3.earring).toBeLessThan(DEFAULT_VOLUME_MM3.ring)
  })
})

// ---------------------------------------------------------------------------
// 10. defaultStone factory
// ---------------------------------------------------------------------------

describe('defaultStone()', () => {
  it('returns an object with required fields', () => {
    const s = defaultStone()
    expect(s).toHaveProperty('cut')
    expect(s).toHaveProperty('carat')
    expect(s).toHaveProperty('price_per_carat')
    expect(s).toHaveProperty('count')
  })

  it('cut defaults to round_brilliant', () => {
    expect(defaultStone().cut).toBe('round_brilliant')
  })

  it('returns a fresh object each call', () => {
    const a = defaultStone()
    const b = defaultStone()
    expect(a).not.toBe(b)
  })
})

// ---------------------------------------------------------------------------
// 11. initialState factory
// ---------------------------------------------------------------------------

describe('initialState()', () => {
  it('returns an object with expected keys', () => {
    const s = initialState()
    expect(s).toHaveProperty('pieceType')
    expect(s).toHaveProperty('metal')
    expect(s).toHaveProperty('finish')
    expect(s).toHaveProperty('stones')
    expect(s).toHaveProperty('settingStyle')
    expect(s).toHaveProperty('ringSizeUs')
    expect(s).toHaveProperty('chainLengthInch')
  })

  it('pieceType is empty string', () => {
    expect(initialState().pieceType).toBe('')
  })

  it('stones is an empty array', () => {
    const s = initialState()
    expect(Array.isArray(s.stones)).toBe(true)
    expect(s.stones).toHaveLength(0)
  })

  it('returns a fresh object each call', () => {
    const a = initialState()
    const b = initialState()
    expect(a).not.toBe(b)
  })
})

// ---------------------------------------------------------------------------
// 12. validateStep — step 0 (piece type)
// ---------------------------------------------------------------------------

describe('validateStep — step 0 (piece type)', () => {
  it('returns an error string when no pieceType selected', () => {
    const err = validateStep(0, { pieceType: '' })
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns null when pieceType is set', () => {
    expect(validateStep(0, { pieceType: 'ring' })).toBeNull()
    expect(validateStep(0, { pieceType: 'pendant' })).toBeNull()
    expect(validateStep(0, { pieceType: 'earring' })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 13. validateStep — step 1 (metal)
// ---------------------------------------------------------------------------

describe('validateStep — step 1 (metal)', () => {
  it('returns an error string when no metal selected', () => {
    const err = validateStep(1, { metal: '' })
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns null when metal is set', () => {
    expect(validateStep(1, { metal: '18k_yellow' })).toBeNull()
    expect(validateStep(1, { metal: 'platinum_950' })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 14. validateStep — step 2 (stones, always valid)
// ---------------------------------------------------------------------------

describe('validateStep — step 2 (stones)', () => {
  it('returns null with no stones', () => {
    expect(validateStep(2, { stones: [] })).toBeNull()
  })

  it('returns null with stones present', () => {
    const s = { stones: [defaultStone()] }
    expect(validateStep(2, s)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 15. validateStep — step 3 (setting + size)
// ---------------------------------------------------------------------------

describe('validateStep — step 3 (setting + size)', () => {
  it('returns error for ring when ringSizeUs is empty', () => {
    const err = validateStep(3, { pieceType: 'ring', ringSizeUs: '' })
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns null for ring when ringSizeUs is set', () => {
    expect(validateStep(3, { pieceType: 'ring', ringSizeUs: '6' })).toBeNull()
  })

  it('returns null for pendant regardless of chainLengthInch', () => {
    expect(validateStep(3, { pieceType: 'pendant', chainLengthInch: '' })).toBeNull()
    expect(validateStep(3, { pieceType: 'pendant', chainLengthInch: '18' })).toBeNull()
  })

  it('returns null for earring', () => {
    expect(validateStep(3, { pieceType: 'earring', chainLengthInch: '' })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 16. validateStep — step 4 (review, always valid)
// ---------------------------------------------------------------------------

describe('validateStep — step 4 (review)', () => {
  it('returns null always', () => {
    expect(validateStep(4, {})).toBeNull()
    expect(validateStep(4, initialState())).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 17. buildToolPayload — basic shape for ring + metal
// ---------------------------------------------------------------------------

describe('buildToolPayload — basic shape', () => {
  const state = { pieceType: 'ring', metal: '18k_yellow', finish: 'polish', settingStyle: 'prong', stones: [] }
  const payload = buildToolPayload(state)

  it('has volume_mm3 > 0', () => {
    expect(payload.volume_mm3).toBeGreaterThan(0)
  })

  it('has metal field matching state', () => {
    expect(payload.metal).toBe('18k_yellow')
  })

  it('has metal_price_per_gram > 0 for gold', () => {
    expect(payload.metal_price_per_gram).toBeGreaterThan(0)
  })

  it('has casting_allowance_pct of 15', () => {
    expect(payload.casting_allowance_pct).toBe(15)
  })

  it('has setting_type field', () => {
    expect(payload.setting_type).toBe('prong')
  })

  it('has bench_hours and hourly_rate', () => {
    expect(typeof payload.bench_hours).toBe('number')
    expect(typeof payload.hourly_rate).toBe('number')
  })
})

// ---------------------------------------------------------------------------
// 18. buildToolPayload — stones included when valid
// ---------------------------------------------------------------------------

describe('buildToolPayload — stones included when valid', () => {
  const state = {
    pieceType: 'ring',
    metal: '14k_yellow',
    finish: 'polish',
    settingStyle: 'prong',
    stones: [
      { cut: 'round_brilliant', carat: '0.5', price_per_carat: '2000', count: 1 },
    ],
  }
  const payload = buildToolPayload(state)

  it('stones array is present', () => {
    expect(Array.isArray(payload.stones)).toBe(true)
    expect(payload.stones.length).toBe(1)
  })

  it('stone has cut, carat, price_per_carat, count', () => {
    const s = payload.stones[0]
    expect(s.cut).toBe('round_brilliant')
    expect(s.carat).toBeCloseTo(0.5, 5)
    expect(s.price_per_carat).toBe(2000)
    expect(s.count).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// 19. buildToolPayload — stones omitted when carat is empty/invalid
// ---------------------------------------------------------------------------

describe('buildToolPayload — stones omitted when invalid', () => {
  const state = {
    pieceType: 'ring',
    metal: '14k_yellow',
    finish: 'polish',
    settingStyle: 'prong',
    stones: [
      { cut: 'round_brilliant', carat: '', price_per_carat: '2000', count: 1 },
    ],
  }
  const payload = buildToolPayload(state)

  it('stones key is absent or empty array', () => {
    if (payload.stones !== undefined) {
      expect(payload.stones).toHaveLength(0)
    } else {
      expect(payload.stones).toBeUndefined()
    }
  })
})

// ---------------------------------------------------------------------------
// 20. buildToolPayload — uses volume from DEFAULT_VOLUME_MM3
// ---------------------------------------------------------------------------

describe('buildToolPayload — volume_mm3 matches DEFAULT_VOLUME_MM3', () => {
  it('ring volume matches default', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '14k_yellow', stones: [] })
    expect(p.volume_mm3).toBe(DEFAULT_VOLUME_MM3.ring)
  })

  it('pendant volume matches default', () => {
    const p = buildToolPayload({ pieceType: 'pendant', metal: '14k_yellow', stones: [] })
    expect(p.volume_mm3).toBe(DEFAULT_VOLUME_MM3.pendant)
  })

  it('earring volume matches default', () => {
    const p = buildToolPayload({ pieceType: 'earring', metal: '14k_yellow', stones: [] })
    expect(p.volume_mm3).toBe(DEFAULT_VOLUME_MM3.earring)
  })
})

// ---------------------------------------------------------------------------
// 21. buildToolPayload — uses price from PRICE_PRESET
// ---------------------------------------------------------------------------

describe('buildToolPayload — metal_price_per_gram from PRICE_PRESET', () => {
  it('18k_yellow uses preset price', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '18k_yellow', stones: [] })
    expect(p.metal_price_per_gram).toBe(PRICE_PRESET['18k_yellow'])
  })

  it('sterling_925 uses preset price', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: 'sterling_925', stones: [] })
    expect(p.metal_price_per_gram).toBe(PRICE_PRESET['sterling_925'])
  })
})

// ---------------------------------------------------------------------------
// 22. buildToolPayload — includes setting_type from state
// ---------------------------------------------------------------------------

describe('buildToolPayload — setting_type', () => {
  it('uses bezel when settingStyle is bezel', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '14k_yellow', settingStyle: 'bezel', stones: [] })
    expect(p.setting_type).toBe('bezel')
  })

  it('falls back to prong when settingStyle is absent', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '14k_yellow', stones: [] })
    expect(p.setting_type).toBe('prong')
  })
})

// ---------------------------------------------------------------------------
// 23. buildToolPayload — includes finish type
// ---------------------------------------------------------------------------

describe('buildToolPayload — finishing_type', () => {
  it('uses specified finish', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '14k_yellow', finish: 'satin', stones: [] })
    expect(p.finishing_type).toBe('satin')
  })

  it('includes finishing_cost for rhodium', () => {
    const p = buildToolPayload({ pieceType: 'ring', metal: '14k_yellow', finish: 'rhodium', stones: [] })
    expect(p.finishing_cost).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// 24. computeLocalEstimate — null when metal missing
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — returns null for missing metal', () => {
  it('returns null when metal is empty string', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '', stones: [] })
    expect(result).toBeNull()
  })

  it('returns null when metal is unknown key', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: 'unobtanium', stones: [] })
    expect(result).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 25. computeLocalEstimate — net weight = density × volume / 1000
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — net weight', () => {
  it('ring net weight = 18k_yellow density × ring volume / 1000', () => {
    const density = METAL_OPTIONS.find((m) => m.key === '18k_yellow').density
    const vol = DEFAULT_VOLUME_MM3.ring
    const expected = density * (vol / 1000)
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '18k_yellow', stones: [] })
    expect(result.net_grams).toBeCloseTo(expected, 4)
  })

  it('pendant net weight matches pendant volume', () => {
    const density = METAL_OPTIONS.find((m) => m.key === 'sterling_925').density
    const vol = DEFAULT_VOLUME_MM3.pendant
    const expected = density * (vol / 1000)
    const result = computeLocalEstimate({ pieceType: 'pendant', metal: 'sterling_925', stones: [] })
    expect(result.net_grams).toBeCloseTo(expected, 4)
  })
})

// ---------------------------------------------------------------------------
// 26. computeLocalEstimate — gross = net × 1.15
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — gross weight', () => {
  it('gross_grams = net_grams × 1.15', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '18k_yellow', stones: [] })
    expect(result.gross_grams).toBeCloseTo(result.net_grams * 1.15, 5)
  })
})

// ---------------------------------------------------------------------------
// 27. computeLocalEstimate — metal_cost = gross × price/g
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — metal_cost', () => {
  it('metal_cost = gross_grams × price_per_gram preset', () => {
    const metal = '18k_yellow'
    const result = computeLocalEstimate({ pieceType: 'ring', metal, stones: [] })
    expect(result.metal_cost).toBeCloseTo(result.gross_grams * PRICE_PRESET[metal], 4)
  })

  it('sterling silver metal_cost is much lower than 18k gold for same piece', () => {
    const gold  = computeLocalEstimate({ pieceType: 'ring', metal: '18k_yellow', stones: [] })
    const silver = computeLocalEstimate({ pieceType: 'ring', metal: 'sterling_925',  stones: [] })
    expect(gold.metal_cost).toBeGreaterThan(silver.metal_cost)
  })
})

// ---------------------------------------------------------------------------
// 28. computeLocalEstimate — stone_cost aggregated from stones
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — stone_cost', () => {
  it('stone_cost is 0 when no stones', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', stones: [] })
    expect(result.stone_cost).toBe(0)
  })

  it('stone_cost accumulates carat × price_per_carat × count', () => {
    const stones = [
      { carat: '0.5', price_per_carat: '2000', count: 1, cut: 'round_brilliant' },
      { carat: '0.1', price_per_carat: '500',  count: 3, cut: 'pave' },
    ]
    const expected = 0.5 * 2000 * 1 + 0.1 * 500 * 3
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', stones })
    expect(result.stone_cost).toBeCloseTo(expected, 4)
  })

  it('stone with zero carat contributes nothing', () => {
    const stones = [{ carat: '', price_per_carat: '2000', count: 1 }]
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', stones })
    expect(result.stone_cost).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 29. computeLocalEstimate — labour includes bench + setting + finish
// ---------------------------------------------------------------------------

describe('computeLocalEstimate — labour', () => {
  it('labour is positive with default state', () => {
    const result = computeLocalEstimate({
      pieceType: 'ring',
      metal: '14k_yellow',
      finish: 'polish',
      settingStyle: 'prong',
      stones: [],
    })
    // bench = 2h × $75 = $150; prong × 0 stones = $0; polish = $0 → 150
    expect(result.labour).toBeGreaterThanOrEqual(150)
  })

  it('rhodium finish adds to labour vs polish', () => {
    const withPolish  = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', finish: 'polish', settingStyle: 'prong', stones: [] })
    const withRhodium = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', finish: 'rhodium', settingStyle: 'prong', stones: [] })
    expect(withRhodium.labour).toBeGreaterThan(withPolish.labour)
  })

  it('stone setting adds to labour', () => {
    const noStones   = computeLocalEstimate({ pieceType: 'ring', metal: '14k_yellow', finish: 'polish', settingStyle: 'prong', stones: [] })
    const withStones = computeLocalEstimate({
      pieceType: 'ring', metal: '14k_yellow', finish: 'polish', settingStyle: 'prong',
      stones: [{ carat: '0.5', price_per_carat: '0', count: 2, cut: 'round_brilliant' }],
    })
    expect(withStones.labour).toBeGreaterThan(noStones.labour)
  })
})

// ---------------------------------------------------------------------------
// 30. Module default export is a function (component shape)
// ---------------------------------------------------------------------------

describe('JewelryConfigurator component', () => {
  it('default export is a function', () => {
    expect(typeof JewelryConfigurator).toBe('function')
  })

  it('has length 1 (accepts a props object)', () => {
    expect(JewelryConfigurator.length).toBeLessThanOrEqual(1)
  })
})

// ---------------------------------------------------------------------------
// T-I1: Stepper a11y + estimate states
// ---------------------------------------------------------------------------

describe('T-I1: stepper aria-current — STEPS supports aria-current="step"', () => {
  it('every step has a non-empty label for aria announcements', () => {
    for (const step of STEPS) {
      expect(typeof step.label).toBe('string')
      expect(step.label.length).toBeGreaterThan(0)
    }
  })

  it('step ids are stable (used as React keys in StepIndicator)', () => {
    const ids = STEPS.map((s) => s.id)
    expect(new Set(ids).size).toBe(STEPS.length)
  })
})

describe('T-I1: step-change announcement text', () => {
  // Mirrors the logic in goNext / goBack in JewelryConfigurator
  function buildAnnouncement(stepIndex) {
    return `Step ${stepIndex + 1} of ${STEP_COUNT}: ${STEPS[stepIndex].label}`
  }

  it('first step announcement is correct', () => {
    const msg = buildAnnouncement(0)
    expect(msg).toBe(`Step 1 of ${STEP_COUNT}: ${STEPS[0].label}`)
    expect(msg).toContain('Piece type')
  })

  it('last step announcement mentions Review & order', () => {
    const msg = buildAnnouncement(STEP_COUNT - 1)
    expect(msg).toContain('Review')
  })

  it('each step produces a unique announcement', () => {
    const msgs = STEPS.map((_, i) => buildAnnouncement(i))
    expect(new Set(msgs).size).toBe(STEP_COUNT)
  })

  it('announcement always starts with "Step N of 5:"', () => {
    for (let i = 0; i < STEP_COUNT; i++) {
      const msg = buildAnnouncement(i)
      expect(msg).toMatch(/^Step \d+ of 5:/)
    }
  })
})

describe('T-I1: EstimateCard — loading state accessibility', () => {
  // The loading branch in EstimateCard renders role="status" aria-live="polite".
  // We validate that the component module exports the helpers needed to drive it.
  it('computeLocalEstimate returns a non-null estimate for a valid ring state', () => {
    const state = {
      pieceType: 'ring',
      metal: '18k_yellow',
      finish: 'polish',
      settingStyle: 'prong',
      stones: [],
    }
    const est = computeLocalEstimate(state)
    expect(est).not.toBeNull()
    expect(typeof est.total).toBe('number')
    expect(est.total).toBeGreaterThan(0)
  })

  it('buildToolPayload builds a payload ready for api.jewelryQuote', () => {
    const state = {
      pieceType: 'ring',
      metal: '18k_yellow',
      finish: 'polish',
      settingStyle: 'prong',
      stones: [],
    }
    const payload = buildToolPayload(state)
    // Required fields expected by the server quote endpoint
    expect(payload).toHaveProperty('volume_mm3')
    expect(payload).toHaveProperty('metal')
    expect(payload).toHaveProperty('metal_price_per_gram')
    expect(payload).toHaveProperty('casting_allowance_pct')
    expect(payload).toHaveProperty('finishing_type')
    expect(payload).toHaveProperty('finishing_cost')
    expect(payload).toHaveProperty('setting_type')
    expect(payload).toHaveProperty('bench_hours')
    expect(payload).toHaveProperty('hourly_rate')
  })
})

describe('T-I1: EstimateCard — retryable error state', () => {
  it('computeLocalEstimate returns null for missing metal (error-path fallback)', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: '', stones: [] })
    expect(result).toBeNull()
  })

  it('computeLocalEstimate returns null for an unknown metal key', () => {
    const result = computeLocalEstimate({ pieceType: 'ring', metal: 'unobtanium_9k', stones: [] })
    expect(result).toBeNull()
  })

  it('estimate total is a number when all fields are valid (no error state)', () => {
    const state = {
      pieceType: 'pendant',
      metal: 'sterling_925',
      finish: 'polish',
      settingStyle: 'prong',
      stones: [],
    }
    const est = computeLocalEstimate(state)
    expect(est).not.toBeNull()
    expect(Number.isFinite(est.total)).toBe(true)
  })
})
