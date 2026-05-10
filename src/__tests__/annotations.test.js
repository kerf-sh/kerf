// annotations.test.js — coverage for the symbol/glyph builders and the
// pure validators in src/lib/annotations.js. The DrawingView and SVG
// exporter both consume these — locking down their shapes catches
// silent regressions in the rendered drawings.

import { describe, it, expect } from 'vitest'
import {
  hatchPatternId,
  hatchPatternDef,
  surfaceFinishGlyph,
  weldGlyph,
  gdtGlyph,
  symbolGlyph,
  balloonGlyph,
  zigzagPoints,
  validateAnnotation,
  validateSymbol,
  detectCenterlines,
  CENTER_DASH,
} from '../lib/annotations.js'

describe('hatchPatternId / hatchPatternDef', () => {
  it('produces a stable id from spacing + angle', () => {
    expect(hatchPatternId(2.5, 45)).toBe('kerf-hatch-2_5-45')
    expect(hatchPatternId(2.5, 45)).toBe(hatchPatternId(2.5, 45))
  })

  it('clamps spacing below 0.5mm and normalises angle into [0, 180)', () => {
    expect(hatchPatternId(0.1, 45)).toBe('kerf-hatch-0_5-45')
    // 225° → (225 % 180 + 180) % 180 = 45.
    expect(hatchPatternId(2.5, 225)).toBe('kerf-hatch-2_5-45')
    // -45° normalises to 135°.
    expect(hatchPatternId(2.5, -45)).toBe('kerf-hatch-2_5-135')
  })

  it('hatchPatternDef returns props matching its id and includes the line shape', () => {
    const def = hatchPatternDef(3, 30)
    expect(def.id).toBe(hatchPatternId(3, 30))
    expect(def.width).toBe(3)
    expect(def.height).toBe(3)
    expect(def.patternUnits).toBe('userSpaceOnUse')
    expect(def.patternTransform).toBe('rotate(30)')
    expect(def.line).toMatchObject({ x1: 0, y1: 0, x2: 0, y2: 3 })
  })
})

describe('symbol glyphs', () => {
  it('surfaceFinishGlyph emits the V wedge plus an Ra label when provided', () => {
    const g = surfaceFinishGlyph({ ra: '1.6' })
    expect(g.bbox.w).toBe(9)
    expect(g.bbox.h).toBe(12)
    const types = g.elements.map((e) => e.type)
    expect(types).toContain('polyline')
    expect(types).toContain('text')
    expect(g.elements.find((e) => e.type === 'text').text).toBe('1.6')
  })

  it('surfaceFinishGlyph drops the top "machined" line when machined === false', () => {
    const g = surfaceFinishGlyph({ machined: false })
    // Only the wedge polyline remains (no top line, no Ra text).
    expect(g.elements.filter((e) => e.type === 'line')).toHaveLength(0)
    expect(g.elements.some((e) => e.type === 'text')).toBe(false)
  })

  it('weldGlyph places the fillet triangle on the requested side', () => {
    const arrow = weldGlyph({ text: '5', side: 'arrow' })
    const other = weldGlyph({ text: '5', side: 'other' })
    // Arrow side puts triangle below the reference line (positive y in svg
    // coords); "other" side places it above. Just check we got distinct
    // polylines for the two side variants.
    const arrowTri = arrow.elements.find((e) => e.type === 'polyline')
    const otherTri = other.elements.find((e) => e.type === 'polyline')
    expect(arrowTri).toBeTruthy()
    expect(otherTri).toBeTruthy()
    expect(arrowTri.points[0][1]).toBeGreaterThan(0)
    expect(otherTri.points[0][1]).toBeLessThan(0)
  })

  it('gdtGlyph adds a third datum cell only when datums are non-empty', () => {
    const noDatum = gdtGlyph({ tolerance: '0.1' })
    const withDatum = gdtGlyph({ tolerance: '0.1', datums: 'A' })
    const rectsNo = noDatum.elements.filter((e) => e.type === 'rect')
    const rectsYes = withDatum.elements.filter((e) => e.type === 'rect')
    expect(rectsYes.length).toBe(rectsNo.length + 1)
    // bbox grows when the datum cell is appended.
    expect(withDatum.bbox.w).toBeGreaterThan(noDatum.bbox.w)
  })

  it('symbolGlyph dispatches by kind and returns an empty shape for unknowns', () => {
    expect(symbolGlyph('surface_finish', { ra: '1.6' }).bbox.w).toBeGreaterThan(0)
    expect(symbolGlyph('weld', { text: '5' }).bbox.w).toBeGreaterThan(0)
    expect(symbolGlyph('gdt', { tolerance: '0.1' }).bbox.w).toBeGreaterThan(0)
    const unknown = symbolGlyph('mystery', {})
    expect(unknown.elements).toEqual([])
    expect(unknown.bbox).toEqual({ w: 0, h: 0 })
  })
})

describe('balloonGlyph', () => {
  it('renders a circle + the number text and exposes the radius', () => {
    const g = balloonGlyph({ number: 7 })
    expect(g.radius).toBe(4.5)
    expect(g.number).toBe('7')
    expect(g.elements.find((e) => e.type === 'circle').r).toBe(4.5)
    expect(g.elements.find((e) => e.type === 'text').text).toBe('7')
    expect(g.bbox).toEqual({ w: 9, h: 9 })
  })

  it('coerces missing number to "?"', () => {
    const g = balloonGlyph({})
    expect(g.number).toBe('?')
  })
})

describe('zigzagPoints', () => {
  it('returns 2*peaks + 1 points starting at p1 and ending at p2', () => {
    const pts = zigzagPoints({ x: 0, y: 0 }, { x: 10, y: 0 }, { peaks: 4 })
    expect(pts).toHaveLength(2 * 4 + 1)
    expect(pts[0]).toEqual({ x: 0, y: 0 })
    expect(pts[pts.length - 1]).toEqual({ x: 10, y: 0 })
  })

  it('alternates the offset sign across peaks (each peak is on the opposite side)', () => {
    const pts = zigzagPoints({ x: 0, y: 0 }, { x: 10, y: 0 }, { peaks: 3, amplitude: 2 })
    // Index 1 has sign +1 → y is +amp; index 2 has sign -1 → y is -amp.
    expect(pts[1].y).toBeGreaterThan(0)
    expect(pts[2].y).toBeLessThan(0)
  })

  it('survives a degenerate (zero-length) span without dividing by zero', () => {
    const pts = zigzagPoints({ x: 5, y: 5 }, { x: 5, y: 5 }, { peaks: 2 })
    for (const p of pts) {
      expect(Number.isFinite(p.x)).toBe(true)
      expect(Number.isFinite(p.y)).toBe(true)
    }
  })
})

describe('validateAnnotation', () => {
  it('returns null for valid kinds and a string error otherwise', () => {
    expect(validateAnnotation({ kind: 'text', x: 0, y: 0, text: 'hi' })).toBeNull()
    expect(validateAnnotation({ kind: 'text', x: 0, y: 0 })).toMatch(/needs text/)
    expect(validateAnnotation({ kind: 'leader', from: { x: 0, y: 0 }, to: { x: 1, y: 1 } })).toBeNull()
    expect(validateAnnotation({ kind: 'leader' })).toMatch(/from,to/)
    expect(validateAnnotation({ kind: 'balloon', cx: 0, cy: 0 })).toBeNull()
    expect(validateAnnotation({ kind: 'polyline', points: [[0, 0]] })).toMatch(/≥2 points/)
    expect(validateAnnotation({ kind: 'rect', x: 0, y: 0, width: 0, height: 5 })).toMatch(/width,height/)
    expect(validateAnnotation({ kind: 'circle', cx: 0, cy: 0, r: 0 })).toMatch(/needs r/)
    expect(validateAnnotation({ kind: 'mystery' })).toMatch(/unknown annotation kind/)
    expect(validateAnnotation(null)).toBe('must be an object')
  })
})

describe('validateSymbol', () => {
  it('accepts known kinds with a position and rejects everything else', () => {
    expect(validateSymbol({ kind: 'surface_finish', position: { x: 1, y: 2 } })).toBeNull()
    expect(validateSymbol({ kind: 'weld', position: { x: 0, y: 0 } })).toBeNull()
    expect(validateSymbol({ kind: 'gdt', position: { x: 0, y: 0 } })).toBeNull()
    expect(validateSymbol({ kind: 'mystery', position: { x: 0, y: 0 } })).toMatch(/unknown symbol/)
    expect(validateSymbol({ kind: 'weld' })).toMatch(/needs position/)
    expect(validateSymbol(null)).toBe('must be an object')
  })
})

describe('detectCenterlines', () => {
  it('returns an empty array for a sub-threshold segment count', () => {
    expect(detectCenterlines([])).toEqual([])
    expect(detectCenterlines([[[0, 0], [1, 0]]])).toEqual([])
  })

  it('finds the centre + radius of a regular polygon approximating a circle', () => {
    // 16-sided polygon around (10, 20) with radius 5 — the chain walker picks
    // it up since chain length ≥ 6 and variance is well below 5%.
    const r = 5
    const cx = 10
    const cy = 20
    const segs = []
    const N = 16
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2
      const b = ((i + 1) / N) * Math.PI * 2
      segs.push([
        [cx + r * Math.cos(a), cy + r * Math.sin(a)],
        [cx + r * Math.cos(b), cy + r * Math.sin(b)],
      ])
    }
    const found = detectCenterlines(segs)
    expect(found.length).toBeGreaterThan(0)
    expect(found[0].cx).toBeCloseTo(cx, 1)
    expect(found[0].cy).toBeCloseTo(cy, 1)
    expect(found[0].r).toBeCloseTo(r, 1)
    expect(found[0].kind).toBe('circle')
  })
})

describe('CENTER_DASH constant', () => {
  it('is the long-short-long dash pattern used by all centerline strokes', () => {
    expect(CENTER_DASH).toBe('4,1.2,0.8,1.2')
  })
})
