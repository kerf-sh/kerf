/**
 * JewelryShare.test.jsx
 *
 * Tests the pure-logic helpers exported from JewelryShare.jsx.
 * No DOM rendering required — we exercise formatMetal, formatPiece,
 * formatFinish, buildSpecRows, validateComment, validateApproval,
 * and the default export component shape.
 *
 * Coverage areas:
 *   1.  formatMetal — known keys
 *   2.  formatMetal — unknown key fallback
 *   3.  formatMetal — empty/null returns '—'
 *   4.  formatPiece — known keys
 *   5.  formatPiece — unknown key fallback
 *   6.  formatPiece — empty/null returns '—'
 *   7.  formatFinish — known keys
 *   8.  formatFinish — unknown key fallback
 *   9.  buildSpecRows — empty/null metadata
 *  10.  buildSpecRows — piece_type row
 *  11.  buildSpecRows — metal row uses formatMetal
 *  12.  buildSpecRows — finish row
 *  13.  buildSpecRows — ring_size_us row
 *  14.  buildSpecRows — chain_length_inch row
 *  15.  buildSpecRows — stones_count row (plural)
 *  16.  buildSpecRows — stones_count row (singular)
 *  17.  buildSpecRows — total row formatted as $
 *  18.  buildSpecRows — stones_count=0 omitted
 *  19.  validateComment — missing name
 *  20.  validateComment — missing body
 *  21.  validateComment — whitespace-only name
 *  22.  validateComment — whitespace-only body
 *  23.  validateComment — valid returns null
 *  24.  validateApproval — missing name
 *  25.  validateApproval — whitespace-only name
 *  26.  validateApproval — valid returns null
 *  27.  JewelryShare default export is a function
 *  28.  buildSpecRows — full metadata all rows present
 *  29.  buildSpecRows — partial metadata only present rows
 *  30.  buildSpecRows — total zero formats as $0.00
 */

import { describe, it, expect } from 'vitest'
import {
  formatMetal,
  formatPiece,
  formatFinish,
  buildSpecRows,
  validateComment,
  validateApproval,
} from './JewelryShare.jsx'
import JewelryShare from './JewelryShare.jsx'

// ---------------------------------------------------------------------------
// 1–3. formatMetal
// ---------------------------------------------------------------------------

describe('formatMetal', () => {
  it('maps 18k_yellow to 18k Yellow Gold', () => {
    expect(formatMetal('18k_yellow')).toBe('18k Yellow Gold')
  })

  it('maps platinum_950 to Platinum 950', () => {
    expect(formatMetal('platinum_950')).toBe('Platinum 950')
  })

  it('maps sterling_925 to Sterling Silver 925', () => {
    expect(formatMetal('sterling_925')).toBe('Sterling Silver 925')
  })

  it('falls back for unknown key replacing underscores with spaces', () => {
    const result = formatMetal('custom_alloy')
    expect(result).toBe('custom alloy')
  })

  it('returns — for empty string', () => {
    expect(formatMetal('')).toBe('—')
  })

  it('returns — for null/undefined', () => {
    expect(formatMetal(null)).toBe('—')
    expect(formatMetal(undefined)).toBe('—')
  })
})

// ---------------------------------------------------------------------------
// 4–6. formatPiece
// ---------------------------------------------------------------------------

describe('formatPiece', () => {
  it('maps ring to Ring', () => {
    expect(formatPiece('ring')).toBe('Ring')
  })

  it('maps pendant to Pendant', () => {
    expect(formatPiece('pendant')).toBe('Pendant')
  })

  it('maps earring to Earring', () => {
    expect(formatPiece('earring')).toBe('Earring')
  })

  it('capitalises unknown key', () => {
    expect(formatPiece('bangle')).toBe('Bangle')
  })

  it('returns — for empty string', () => {
    expect(formatPiece('')).toBe('—')
  })

  it('returns — for null', () => {
    expect(formatPiece(null)).toBe('—')
  })
})

// ---------------------------------------------------------------------------
// 7–8. formatFinish
// ---------------------------------------------------------------------------

describe('formatFinish', () => {
  it('maps polish to High-polish', () => {
    expect(formatFinish('polish')).toBe('High-polish')
  })

  it('maps rhodium to Rhodium plating', () => {
    expect(formatFinish('rhodium')).toBe('Rhodium plating')
  })

  it('falls back for unknown key replacing underscores', () => {
    expect(formatFinish('hand_engraved')).toBe('hand engraved')
  })

  it('returns — for empty/null', () => {
    expect(formatFinish('')).toBe('—')
    expect(formatFinish(null)).toBe('—')
  })
})

// ---------------------------------------------------------------------------
// 9–18. buildSpecRows
// ---------------------------------------------------------------------------

describe('buildSpecRows — empty metadata', () => {
  it('returns empty array for null', () => {
    expect(buildSpecRows(null)).toEqual([])
  })

  it('returns empty array for empty object', () => {
    expect(buildSpecRows({})).toEqual([])
  })

  it('returns empty array for non-object', () => {
    expect(buildSpecRows('string')).toEqual([])
  })
})

describe('buildSpecRows — individual rows', () => {
  it('includes piece_type row with formatted label', () => {
    const rows = buildSpecRows({ piece_type: 'ring' })
    const row = rows.find((r) => r.label === 'Piece')
    expect(row).toBeTruthy()
    expect(row.value).toBe('Ring')
  })

  it('includes metal row using formatMetal', () => {
    const rows = buildSpecRows({ metal: '18k_yellow' })
    const row = rows.find((r) => r.label === 'Metal')
    expect(row).toBeTruthy()
    expect(row.value).toBe('18k Yellow Gold')
  })

  it('includes finish row', () => {
    const rows = buildSpecRows({ finish: 'satin' })
    const row = rows.find((r) => r.label === 'Finish')
    expect(row).toBeTruthy()
    expect(row.value).toContain('Satin')
  })

  it('includes ring_size_us row', () => {
    const rows = buildSpecRows({ ring_size_us: '7' })
    const row = rows.find((r) => r.label === 'Ring size')
    expect(row).toBeTruthy()
    expect(row.value).toBe('US 7')
  })

  it('includes chain_length_inch row', () => {
    const rows = buildSpecRows({ chain_length_inch: '18' })
    const row = rows.find((r) => r.label === 'Chain')
    expect(row).toBeTruthy()
    expect(row.value).toBe('18"')
  })

  it('includes stones_count row with plural', () => {
    const rows = buildSpecRows({ stones_count: 3 })
    const row = rows.find((r) => r.label === 'Stones')
    expect(row).toBeTruthy()
    expect(row.value).toBe('3 stones')
  })

  it('includes stones_count row with singular', () => {
    const rows = buildSpecRows({ stones_count: 1 })
    const row = rows.find((r) => r.label === 'Stones')
    expect(row).toBeTruthy()
    expect(row.value).toBe('1 stone')
  })

  it('includes total row formatted as currency', () => {
    const rows = buildSpecRows({ total: 1234.5 })
    const row = rows.find((r) => r.label === 'Estimate')
    expect(row).toBeTruthy()
    expect(row.value).toBe('$1234.50')
  })

  it('omits stones_count when 0', () => {
    const rows = buildSpecRows({ stones_count: 0 })
    expect(rows.find((r) => r.label === 'Stones')).toBeUndefined()
  })
})

describe('buildSpecRows — full metadata', () => {
  const meta = {
    piece_type: 'ring',
    metal: '14k_rose',
    finish: 'polish',
    ring_size_us: '6',
    stones_count: 2,
    total: 890,
  }
  const rows = buildSpecRows(meta)

  it('has 6 rows for full metadata', () => {
    expect(rows.length).toBe(6)
  })

  it('all rows have non-empty label and value', () => {
    for (const row of rows) {
      expect(typeof row.label).toBe('string')
      expect(row.label.length).toBeGreaterThan(0)
      expect(typeof row.value).toBe('string')
      expect(row.value.length).toBeGreaterThan(0)
    }
  })
})

describe('buildSpecRows — partial metadata', () => {
  it('only emits rows for present fields', () => {
    const rows = buildSpecRows({ piece_type: 'earring', total: 150 })
    expect(rows).toHaveLength(2)
    expect(rows[0].label).toBe('Piece')
    expect(rows[1].label).toBe('Estimate')
  })
})

describe('buildSpecRows — total zero', () => {
  it('formats zero as $0.00', () => {
    const rows = buildSpecRows({ total: 0 })
    const row = rows.find((r) => r.label === 'Estimate')
    expect(row).toBeTruthy()
    expect(row.value).toBe('$0.00')
  })
})

// ---------------------------------------------------------------------------
// 19–23. validateComment
// ---------------------------------------------------------------------------

describe('validateComment', () => {
  it('returns error string for missing name', () => {
    const err = validateComment('', 'Nice ring')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns error string for whitespace-only name', () => {
    const err = validateComment('   ', 'Nice ring')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns error string for missing body', () => {
    const err = validateComment('Alice', '')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns error string for whitespace-only body', () => {
    const err = validateComment('Alice', '   ')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns null for valid name and body', () => {
    expect(validateComment('Alice', 'Looks great!')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 24–26. validateApproval
// ---------------------------------------------------------------------------

describe('validateApproval', () => {
  it('returns error for empty name', () => {
    const err = validateApproval('')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns error for whitespace-only name', () => {
    const err = validateApproval('   ')
    expect(typeof err).toBe('string')
    expect(err.length).toBeGreaterThan(0)
  })

  it('returns null for a non-empty name', () => {
    expect(validateApproval('Alice Smith')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 27. JewelryShare default export is a function
// ---------------------------------------------------------------------------

describe('JewelryShare component', () => {
  it('default export is a function', () => {
    expect(typeof JewelryShare).toBe('function')
  })
})
