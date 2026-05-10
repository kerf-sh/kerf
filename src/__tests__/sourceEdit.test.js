// sourceEdit.test.js — coverage for the targeted JSCAD source mutators in
// src/lib/sourceEdit.js. These edit a JSCAD file's literal `{id, geom}` shape
// to wrap/replace a `colors.colorize(...)` or `transforms.translate(...)`
// call. The functions are pragmatic regex+brace-walking — not full AST
// parsing — so the tests cover the canonical happy paths plus the bail-out
// cases the contract documents.

import { describe, it, expect } from 'vitest'
import { withColorizedPart, withTranslatedPart } from '../lib/sourceEdit.js'

const SEED = `export default function ({ primitives, transforms }) {
  return [
    { id: 'cube', geom: primitives.cube({ size: 10 }) },
    { id: 'ball', geom: primitives.sphere({ radius: 5 }) },
  ]
}
`

describe('withColorizedPart', () => {
  it('wraps a bare geom expression in colors.colorize with rounded RGB', () => {
    const next = withColorizedPart(SEED, 'cube', [1, 0, 0.5])
    expect(next).not.toBeNull()
    expect(next).toContain("colors.colorize([1, 0, 0.5], primitives.cube({ size: 10 }))")
  })

  it('replaces an existing colorize wrap rather than nesting it', () => {
    const src = `export default function () {
  return [{ id: 'cube', geom: colors.colorize([0.1, 0.2, 0.3], primitives.cube({ size: 10 })) }]
}`
    const next = withColorizedPart(src, 'cube', [0.5, 0.5, 0.5])
    expect(next).not.toBeNull()
    // Old rgba is gone and only one colorize call remains.
    expect(next).not.toContain('[0.1, 0.2, 0.3]')
    expect(next).toContain("colors.colorize([0.5, 0.5, 0.5], primitives.cube({ size: 10 }))")
    expect(next.match(/colorize/g) || []).toHaveLength(1)
  })

  it('returns null when the part id is not found', () => {
    expect(withColorizedPart(SEED, 'nope', [1, 0, 0])).toBeNull()
  })

  it('returns null when the part id appears more than once (ambiguous)', () => {
    const dup = `[{ id: 'cube', geom: A }, { id: 'cube', geom: B }]`
    expect(withColorizedPart(dup, 'cube', [1, 0, 0])).toBeNull()
  })

  it('rounds RGB components to 4 decimal places', () => {
    const next = withColorizedPart(SEED, 'cube', [0.123456789, 0.5, 1])
    expect(next).toContain('[0.1235, 0.5, 1]')
  })

  it('handles double-quoted ids equally', () => {
    const dq = `[{ id: "cube", geom: primitives.cube({size: 1}) }]`
    const next = withColorizedPart(dq, 'cube', [1, 1, 1])
    expect(next).toContain('colors.colorize([1, 1, 1], primitives.cube({size: 1}))')
  })
})

describe('withTranslatedPart', () => {
  it('wraps a bare geom in transforms.translate with rounded XYZ', () => {
    const next = withTranslatedPart(SEED, 'cube', [10, 20, 30])
    expect(next).not.toBeNull()
    expect(next).toContain('transforms.translate([10, 20, 30], primitives.cube({ size: 10 }))')
  })

  it('accumulates with mode="add" by summing the new delta with the existing xyz', () => {
    const src = `[{ id: 'cube', geom: transforms.translate([1, 2, 3], primitives.cube({size:1})) }]`
    const next = withTranslatedPart(src, 'cube', [10, 0, -1], 'add')
    expect(next).toContain('transforms.translate([11, 2, 2], primitives.cube({size:1}))')
  })

  it('replaces with mode="set" rather than accumulating', () => {
    const src = `[{ id: 'cube', geom: transforms.translate([1, 2, 3], primitives.cube({size:1})) }]`
    const next = withTranslatedPart(src, 'cube', [99, 0, 0], 'set')
    expect(next).toContain('transforms.translate([99, 0, 0], primitives.cube({size:1}))')
    expect(next).not.toContain('[1, 2, 3]')
  })

  it('preserves an inner colorize wrap when adding a translate', () => {
    const src = `[{ id: 'cube', geom: colors.colorize([1,0,0], primitives.cube({size:1})) }]`
    const next = withTranslatedPart(src, 'cube', [5, 0, 0])
    expect(next).toContain('transforms.translate([5, 0, 0], colors.colorize([1,0,0], primitives.cube({size:1})))')
  })

  it('returns null for an unknown part id', () => {
    expect(withTranslatedPart(SEED, 'mystery', [1, 2, 3])).toBeNull()
  })

  it('rounds XYZ to 4 decimal places', () => {
    const next = withTranslatedPart(SEED, 'cube', [0.123456789, 1.000005, 2])
    // 0.123456789 → 0.1235, 1.000005 → 1.0000 = 1, 2 → 2
    expect(next).toContain('[0.1235, 1, 2]')
  })

  it('only matches a top-level translate wrap (does not unwrap nested ones)', () => {
    // Outer call is some other helper; inner translate is buried — should be
    // treated as a bare expr and wrapped fresh, leaving the inner one intact.
    const src = `[{ id: 'cube', geom: utils.tag(transforms.translate([1,1,1], primitives.cube({size:1})), 'x') }]`
    const next = withTranslatedPart(src, 'cube', [10, 0, 0])
    expect(next).toContain('transforms.translate([10, 0, 0], utils.tag(transforms.translate([1,1,1], primitives.cube({size:1})), \'x\'))')
  })
})
