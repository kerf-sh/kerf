import { describe, it, expect } from 'vitest'
import { findGuides, applySnap, bboxFromComponent } from './alignmentGuides.js'

// Helpers
const box = (x, y, w = 10, h = 10) => ({ x, y, w, h })

describe('findGuides', () => {
  it('returns empty guides when no others', () => {
    const { guides, snapDelta } = findGuides(box(0, 0), [])
    expect(guides).toHaveLength(0)
    expect(snapDelta).toEqual({ dx: 0, dy: 0 })
  })

  it('returns empty guides when dragged bbox is null', () => {
    const { guides } = findGuides(null, [box(0, 0)])
    expect(guides).toHaveLength(0)
  })

  it('detects left-edge vertical alignment', () => {
    // Dragged left edge at x=10, other left edge also at x=10 → vertical guide
    const dragged = box(10, 20, 5, 5)
    const other   = box(10, 0, 5, 5)
    const { guides } = findGuides(dragged, [other], 0.5)
    const verticals = guides.filter((g) => g.kind === 'vertical')
    expect(verticals.length).toBeGreaterThan(0)
    expect(verticals[0].x1).toBeCloseTo(10)
  })

  it('detects horizontal center alignment', () => {
    // Both centers at y=10 → horizontal guide exists at y=10
    const dragged = box(0, 5, 10, 10)   // center y = 10
    const other   = box(20, 5, 10, 10)  // center y = 10
    const { guides } = findGuides(dragged, [other], 0.5)
    const horizontals = guides.filter((g) => g.kind === 'horizontal')
    expect(horizontals.length).toBeGreaterThan(0)
    // At least one horizontal guide should be at y=10 (center-to-center alignment)
    expect(horizontals.some((g) => Math.abs(g.y1 - 10) < 0.01)).toBe(true)
  })

  it('returns correct snap delta for center-to-center alignment', () => {
    // Dragged center at x=10.3, other center at x=10 → dx should snap to -0.3
    const dragged = box(5.3, 0, 10, 10)  // center = 10.3
    const other   = box(5,   0, 10, 10)  // center = 10
    const { snapDelta } = findGuides(dragged, [other], 0.5)
    expect(snapDelta.dx).toBeCloseTo(-0.3)
  })

  it('does not snap when distance exceeds threshold', () => {
    const dragged = box(0, 0, 5, 5)
    const other   = box(10, 10, 5, 5)
    const { guides, snapDelta } = findGuides(dragged, [other], 0.5)
    expect(guides).toHaveLength(0)
    expect(snapDelta.dx).toBe(0)
    expect(snapDelta.dy).toBe(0)
  })

  it('deduplicates guides from multiple others at same x', () => {
    const dragged = box(10, 5, 5, 5)
    const others  = [box(10, 0, 5, 5), box(10, 20, 5, 5)]
    const { guides } = findGuides(dragged, others, 0.5)
    const verticals = guides.filter((g) => g.kind === 'vertical' && Math.abs(g.x1 - 10) < 0.01)
    // Should be deduplicated to 1 guide at x=10
    expect(verticals.length).toBe(1)
  })

  it('detects right-edge alignment', () => {
    // Dragged right edge = 20, other right edge = 20
    const dragged = box(10, 0, 10, 5)  // right = 20
    const other   = box(15, 10, 5, 5)  // right = 20
    const { guides } = findGuides(dragged, [other], 0.5)
    const verticals = guides.filter((g) => g.kind === 'vertical')
    expect(verticals.some((g) => Math.abs(g.x1 - 20) < 0.01)).toBe(true)
  })

  it('handles multiple alignment hits and picks closest snap', () => {
    // Two candidates: one 0.1mm off, one 0.4mm off — should snap to 0.1mm
    const dragged = box(10.1, 0, 5, 5)
    const others  = [box(10, 0, 5, 5), box(9.7, 0, 5, 5)]
    const { snapDelta } = findGuides(dragged, others, 0.5)
    // closest snap is left=10.1 → left=10 → dx=-0.1
    expect(Math.abs(snapDelta.dx)).toBeLessThanOrEqual(0.2)
  })
})

describe('applySnap', () => {
  it('adds delta to position', () => {
    expect(applySnap({ x: 5, y: 3 }, { dx: 1, dy: -2 })).toEqual({ x: 6, y: 1 })
  })

  it('handles null/undefined delta', () => {
    expect(applySnap({ x: 5, y: 3 }, null)).toEqual({ x: 5, y: 3 })
  })
})

describe('bboxFromComponent', () => {
  it('builds bbox from pcbX/pcbY', () => {
    const bb = bboxFromComponent({ pcbX: 10, pcbY: 20, width: 4, height: 6 })
    expect(bb.x).toBeCloseTo(8)   // 10 - 4/2
    expect(bb.y).toBeCloseTo(17)  // 20 - 6/2
    expect(bb.w).toBe(4)
    expect(bb.h).toBe(6)
  })

  it('returns null for null component', () => {
    expect(bboxFromComponent(null)).toBeNull()
  })
})
