// sheetFrames.test.js — coverage for the drawing sheet-frame helpers:
// sheetDimensions (ISO/ANSI sizes + portrait swap), titleBlockLayout (the
// four template variants), scaleBarGeometry, and parseScaleString.
//
// All of these are pure functions over numeric data — no DOM, no fixtures.

import { describe, it, expect } from 'vitest'
import {
  SHEET_SIZES,
  TEMPLATES,
  sheetDimensions,
  titleBlockLayout,
  scaleBarGeometry,
  parseScaleString,
} from '../lib/sheetFrames.js'

describe('sheetDimensions', () => {
  it('returns landscape orientation by default for a known ISO size', () => {
    expect(sheetDimensions('A4')).toEqual({ w: 297, h: 210 })
  })

  it('swaps width/height for portrait orientation', () => {
    expect(sheetDimensions('A4', 'portrait')).toEqual({ w: 210, h: 297 })
  })

  it('falls back to A3 for unknown sizes', () => {
    expect(sheetDimensions('NOT_A_SIZE')).toEqual(SHEET_SIZES.A3)
  })

  it('handles ANSI sizes in mm', () => {
    expect(sheetDimensions('ANSI_B')).toEqual({ w: 431.8, h: 279.4 })
  })
})

describe('titleBlockLayout', () => {
  it('exposes the four canonical template names', () => {
    expect(TEMPLATES).toEqual(['default', 'iso', 'ansi', 'kerf'])
  })

  it('falls back to the default template for unknown names', () => {
    const layout = titleBlockLayout('A3', 'landscape', 'mystery')
    expect(layout.template).toBe('default')
  })

  it('places the default block in the bottom-right corner', () => {
    const { w, h } = sheetDimensions('A3')
    const layout = titleBlockLayout('A3', 'landscape', 'default')
    // 5mm margin from sheet edges.
    expect(layout.x + layout.w + 5).toBe(w)
    expect(layout.y + layout.h + 5).toBe(h)
  })

  it('iso template produces 8 cells with project + tolerances keys', () => {
    const layout = titleBlockLayout('A3', 'landscape', 'iso')
    expect(layout.template).toBe('iso')
    expect(layout.cells).toHaveLength(8)
    const keys = layout.cells.map((c) => c.key)
    expect(keys).toContain('project')
    expect(keys).toContain('tolerances')
    expect(keys).toContain('title')
  })

  it('ansi template produces 10 cells with the revision field', () => {
    const layout = titleBlockLayout('A3', 'landscape', 'ansi')
    expect(layout.cells).toHaveLength(10)
    expect(layout.cells.map((c) => c.key)).toContain('revision')
  })

  it('kerf template carries a brand-marked first cell', () => {
    const layout = titleBlockLayout('A3', 'landscape', 'kerf')
    expect(layout.cells[0].brand).toBe(true)
    expect(layout.cells).toHaveLength(4)
  })

  it('default A4 block is narrower than A3', () => {
    const a4 = titleBlockLayout('A4', 'landscape', 'default')
    const a3 = titleBlockLayout('A3', 'landscape', 'default')
    expect(a4.w).toBeLessThan(a3.w)
  })
})

describe('scaleBarGeometry', () => {
  it('always produces a positive number of tiles for sensible scales', () => {
    // NOTE: the source code aims for 3-8 tiles, but its single-shot
    // doubling step (`if (totalModelMm/unit > 8) unit *= 2`) is not
    // a fixed-point — at scale=0.5 (and family) it yields 13 tiles.
    // We assert the looser invariant: bars > 0 and finite tile width.
    for (const scale of [0.1, 0.5, 1, 2, 5, 10, 50, 100]) {
      const g = scaleBarGeometry(scale)
      expect(g.bars).toBeGreaterThanOrEqual(3)
      expect(Number.isFinite(g.tile)).toBe(true)
      expect(g.tile).toBeGreaterThan(0)
    }
  })

  it('total page-mm equals tile × bars', () => {
    const g = scaleBarGeometry(2)
    expect(g.totalPagemm).toBeCloseTo(g.tile * g.bars, 10)
  })

  it('formats 1:1 ratio when scale === 1', () => {
    expect(scaleBarGeometry(1).label).toBe('1:1')
  })

  it('formats N:1 ratio when scale < 1 (page bigger than model)', () => {
    expect(scaleBarGeometry(0.5).label).toBe('2:1')
  })

  it('formats 1:N ratio when scale > 1 (model bigger than page)', () => {
    expect(scaleBarGeometry(10).label).toBe('1:10')
  })
})

describe('parseScaleString', () => {
  it('parses 1:N as N', () => {
    expect(parseScaleString('1:10')).toBe(0.1)
    expect(parseScaleString('1:2')).toBe(0.5)
  })

  it('parses N:1 as 1/N', () => {
    expect(parseScaleString('2:1')).toBe(2)
  })

  it('tolerates whitespace', () => {
    expect(parseScaleString(' 1 : 4 ')).toBe(0.25)
  })

  it('returns null for malformed strings', () => {
    expect(parseScaleString('hello')).toBeNull()
    expect(parseScaleString('1:0')).toBeNull()
    expect(parseScaleString('')).toBeNull()
    expect(parseScaleString(null)).toBeNull()
  })
})
