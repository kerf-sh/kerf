// units.test.js — sanity coverage for the pure unit-conversion helpers.
//
// CAD layer always stores millimetres; the helpers go to/from the user's
// display unit. Round-trip through millimetres should preserve the input
// exactly for mm/cm and within ~1e-12 for inches (irrational scale).

import { describe, it, expect } from 'vitest'
import {
  toMM, fromMM, convert, formatLength, roundTrip, UNIT_SUFFIX, UNITS,
} from '../lib/units.js'

describe('UNITS contract', () => {
  it('exposes the three supported codes', () => {
    expect(UNITS).toEqual(['mm', 'cm', 'inches'])
  })
  it('maps each code to a glyph', () => {
    expect(UNIT_SUFFIX.mm).toBe('mm')
    expect(UNIT_SUFFIX.cm).toBe('cm')
    expect(UNIT_SUFFIX.inches).toBe('in')
  })
})

describe('mm <-> cm', () => {
  it('toMM scales centimetres by 10', () => {
    expect(toMM(1, 'cm')).toBe(10)
    expect(toMM(2.5, 'cm')).toBe(25)
  })
  it('fromMM divides by 10 for cm', () => {
    expect(fromMM(50, 'cm')).toBe(5)
    expect(fromMM(7.5, 'cm')).toBe(0.75)
  })
  it('round-trips exactly', () => {
    expect(roundTrip(123.45, 'cm')).toBe(123.45)
  })
})

describe('mm <-> inches', () => {
  it('toMM uses 25.4 mm/inch', () => {
    expect(toMM(1, 'inches')).toBe(25.4)
    expect(toMM(2, 'inches')).toBe(50.8)
  })
  it('fromMM divides by 25.4 for inches', () => {
    expect(fromMM(25.4, 'inches')).toBeCloseTo(1, 12)
    expect(fromMM(101.6, 'inches')).toBeCloseTo(4, 12)
  })
  it('inch round-trip is stable to ~1e-12', () => {
    const v = 7.123456
    const r = roundTrip(v, 'inches')
    expect(r).toBeCloseTo(v, 10)
  })
})

describe('mm identity', () => {
  it('toMM/fromMM are no-ops for mm', () => {
    expect(toMM(42, 'mm')).toBe(42)
    expect(fromMM(42, 'mm')).toBe(42)
  })
  it('unknown units fall back to mm (forgiving)', () => {
    expect(toMM(5, 'parsec')).toBe(5)
    expect(fromMM(5, undefined)).toBe(5)
  })
})

describe('convert across units', () => {
  it('cm -> inches via mm', () => {
    expect(convert(2.54, 'cm', 'inches')).toBeCloseTo(1, 12)
  })
  it('inches -> cm via mm', () => {
    expect(convert(1, 'inches', 'cm')).toBeCloseTo(2.54, 12)
  })
  it('same unit is a no-op', () => {
    expect(convert(3.14, 'mm', 'mm')).toBe(3.14)
  })
})

describe('formatLength', () => {
  it('mm with 2-decimal default, trimmed', () => {
    expect(formatLength(12.5, 'mm')).toBe('12.5 mm')
    expect(formatLength(10, 'mm')).toBe('10 mm')
  })
  it('inches with 3-decimal default, trimmed', () => {
    expect(formatLength(25.4, 'inches')).toBe('1 in')
    expect(formatLength(2, 'inches')).toBe('0.079 in')
  })
  it('honours custom precision', () => {
    // Value chosen to avoid banker's-rounding edge cases in toFixed.
    expect(formatLength(1.2349, 'mm', 3)).toBe('1.235 mm')
  })
  it('falls back to mm for unknown units', () => {
    expect(formatLength(7, 'qux')).toBe('7 mm')
  })
})
