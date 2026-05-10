// sketchUI.test.js — coverage for the un-tested pure helpers in
// src/lib/sketchUI.js.
//
// sketcher.test.js already covers projectLineDraft, describeLineDraft, and the
// happy-path branches of formatConstraintValue + friendlyConstraintLabel. This
// file fills in the remaining gaps:
//
//   * constraintEntityRefs — the click-to-pulse highlight resolver. One assertion
//     per branch of its switch (coincident, horizontal, parallel, distance,
//     radius, symmetric, point_on_line/arc, block, default).
//   * formatConstraintValue — empty-string returns for null/missing/non-finite
//     values; mm formatting for non-angle types.
//   * friendlyConstraintLabel — every branch returns a string (no undefined).

import { describe, it, expect } from 'vitest'
import {
  constraintEntityRefs,
  formatConstraintValue,
  friendlyConstraintLabel,
} from '../lib/sketchUI.js'

describe('constraintEntityRefs', () => {
  it('returns [a, b] for two-entity constraints (coincident)', () => {
    expect(constraintEntityRefs({ type: 'coincident', a: 'p1', b: 'p2' }))
      .toEqual(['p1', 'p2'])
  })

  it('returns [line] for horizontal/vertical', () => {
    expect(constraintEntityRefs({ type: 'horizontal', line: 'L1' })).toEqual(['L1'])
    expect(constraintEntityRefs({ type: 'vertical', line: 'L9' })).toEqual(['L9'])
  })

  it('returns [a, b] for parallel/perpendicular/tangent/equal_*', () => {
    for (const type of ['parallel', 'perpendicular', 'tangent', 'equal_length', 'equal_radius']) {
      expect(constraintEntityRefs({ type, a: 'x', b: 'y' })).toEqual(['x', 'y'])
    }
  })

  it('returns [a, b] for dimensional distance/angle types', () => {
    for (const type of ['distance', 'distance_x', 'distance_y', 'angle']) {
      expect(constraintEntityRefs({ type, a: 'foo', b: 'bar' })).toEqual(['foo', 'bar'])
    }
  })

  it('returns [circle] for radius/diameter', () => {
    expect(constraintEntityRefs({ type: 'radius', circle: 'c1' })).toEqual(['c1'])
    expect(constraintEntityRefs({ type: 'diameter', circle: 'c2' })).toEqual(['c2'])
  })

  it('returns [a, b, line] for symmetric', () => {
    expect(constraintEntityRefs({ type: 'symmetric', a: 'p1', b: 'p2', line: 'L7' }))
      .toEqual(['p1', 'p2', 'L7'])
  })

  it('returns the refs array for block (or [] when missing)', () => {
    expect(constraintEntityRefs({ type: 'block', refs: ['a', 'b', 'c'] }))
      .toEqual(['a', 'b', 'c'])
    expect(constraintEntityRefs({ type: 'block' })).toEqual([])
  })

  it('returns [point, line/arc] for point_on_line / point_on_arc', () => {
    expect(constraintEntityRefs({ type: 'point_on_line', point: 'p', line: 'L' }))
      .toEqual(['p', 'L'])
    expect(constraintEntityRefs({ type: 'point_on_arc', point: 'p', arc: 'A' }))
      .toEqual(['p', 'A'])
  })

  it('returns [] for unknown / null / missing types', () => {
    expect(constraintEntityRefs({ type: 'made-up' })).toEqual([])
    expect(constraintEntityRefs(null)).toEqual([])
    expect(constraintEntityRefs(undefined)).toEqual([])
    expect(constraintEntityRefs({})).toEqual([])
  })
})

describe('formatConstraintValue edge cases', () => {
  it('returns empty string when value is null / undefined', () => {
    expect(formatConstraintValue({ type: 'distance' })).toBe('')
    expect(formatConstraintValue({ type: 'distance', value: null })).toBe('')
  })

  it('returns empty string when value is non-finite (NaN / Infinity)', () => {
    expect(formatConstraintValue({ type: 'distance', value: NaN })).toBe('')
    expect(formatConstraintValue({ type: 'distance', value: 'banana' })).toBe('')
    expect(formatConstraintValue({ type: 'distance', value: Infinity })).toBe('')
  })

  it('formats radius / diameter / distance_x / distance_y in millimetres', () => {
    expect(formatConstraintValue({ type: 'radius', value: 7.5 })).toBe('7.50 mm')
    expect(formatConstraintValue({ type: 'diameter', value: 15 })).toBe('15.00 mm')
    expect(formatConstraintValue({ type: 'distance_x', value: 3.14159 })).toBe('3.14 mm')
    expect(formatConstraintValue({ type: 'distance_y', value: 0 })).toBe('0.00 mm')
  })

  it('coerces numeric strings before formatting', () => {
    expect(formatConstraintValue({ type: 'distance', value: '12.5' })).toBe('12.50 mm')
    expect(formatConstraintValue({ type: 'angle', value: '45' })).toBe('45.0°')
  })
})

describe('friendlyConstraintLabel covers every known type', () => {
  it('returns a non-empty string for each known constraint type', () => {
    const types = [
      'coincident', 'horizontal', 'vertical', 'parallel', 'perpendicular',
      'tangent', 'equal_length', 'equal_radius', 'distance', 'distance_x',
      'distance_y', 'angle', 'radius', 'diameter', 'symmetric', 'block',
      'point_on_line', 'point_on_arc',
    ]
    for (const type of types) {
      const label = friendlyConstraintLabel({ type })
      expect(typeof label).toBe('string')
      expect(label.length).toBeGreaterThan(0)
    }
  })

  it('falls back to the raw type for unknown constraints', () => {
    expect(friendlyConstraintLabel({ type: 'something-new' })).toBe('something-new')
  })

  it('returns a generic label when type is missing entirely', () => {
    expect(friendlyConstraintLabel(null)).toBe('Constraint')
    expect(friendlyConstraintLabel({})).toBe('Constraint')
  })
})
