import { describe, it, expect } from 'vitest'
import { orthogonalSnap, corner45, detectTJunction, pointToSegmentDist } from './pcbRouting.js'

describe('orthogonalSnap', () => {
  it('snaps to horizontal when dx > dy', () => {
    const r = orthogonalSnap({ x: 0, y: 0 }, { x: 5, y: 1 })
    expect(r.y).toBe(0)
    expect(r.x).toBe(5)
  })
  it('snaps to vertical when dy > dx', () => {
    const r = orthogonalSnap({ x: 0, y: 0 }, { x: 1, y: 5 })
    expect(r.x).toBe(0)
    expect(r.y).toBe(5)
  })
  it('snaps to horizontal when dx === dy (tiebreak horizontal)', () => {
    const r = orthogonalSnap({ x: 0, y: 0 }, { x: 3, y: 3 })
    expect(r.y).toBe(0)
  })
  it('works with negative offsets', () => {
    const r = orthogonalSnap({ x: 5, y: 5 }, { x: 2, y: 4 })
    // dy=1, dx=3 → horizontal snap
    expect(r.y).toBe(5)
    expect(r.x).toBe(2)
  })
  it('returns prev when cursor equals prev', () => {
    const r = orthogonalSnap({ x: 2, y: 2 }, { x: 2, y: 2 })
    expect(r.x).toBe(2)
    expect(r.y).toBe(2)
  })
})

describe('corner45', () => {
  it('returns two points for non-45 angle (dx > dy)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 4, y: 2 })
    expect(pts.length).toBeGreaterThanOrEqual(1)
    const last = pts[pts.length - 1]
    expect(last.x).toBe(4)
    expect(last.y).toBe(2)
  })
  it('returns two points for non-45 angle (dy > dx)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 2, y: 4 })
    expect(pts.length).toBeGreaterThanOrEqual(1)
    const last = pts[pts.length - 1]
    expect(last.x).toBe(2)
    expect(last.y).toBe(4)
  })
  it('returns single point for perfect 45° (dx === dy)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 3, y: 3 })
    expect(pts.length).toBe(1)
    expect(pts[0].x).toBe(3)
    expect(pts[0].y).toBe(3)
  })
  it('returns single point for pure horizontal (dy === 0)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 5, y: 0 })
    expect(pts.length).toBe(1)
  })
  it('intermediate point for dx > dy has 45° segment from prev', () => {
    // prev=(0,0) cursor=(6,2): min=2, so first point should be at 45° then straight
    const pts = corner45({ x: 0, y: 0 }, { x: 6, y: 2 })
    expect(pts.length).toBe(2)
    const mid = pts[0]
    // mid should lie on a 45° line from (0,0), so |mid.x| === |mid.y|
    expect(Math.abs(mid.x)).toBeCloseTo(Math.abs(mid.y), 5)
  })
})

describe('pointToSegmentDist', () => {
  it('returns 0 for a point on the segment midpoint', () => {
    const d = pointToSegmentDist({ x: 1, y: 0 }, { x: 0, y: 0 }, { x: 2, y: 0 })
    expect(d).toBeCloseTo(0, 5)
  })
  it('returns perpendicular distance for a point beside the segment', () => {
    const d = pointToSegmentDist({ x: 1, y: 1 }, { x: 0, y: 0 }, { x: 2, y: 0 })
    expect(d).toBeCloseTo(1, 5)
  })
  it('returns distance to endpoint when closest point is beyond segment end', () => {
    const d = pointToSegmentDist({ x: 3, y: 0 }, { x: 0, y: 0 }, { x: 2, y: 0 })
    expect(d).toBeCloseTo(1, 5)
  })
  it('returns distance to start when closest point is before segment start', () => {
    const d = pointToSegmentDist({ x: -1, y: 0 }, { x: 0, y: 0 }, { x: 2, y: 0 })
    expect(d).toBeCloseTo(1, 5)
  })
  it('works for diagonal segment', () => {
    // Segment from (0,0) to (4,4), point at (0,4) — perpendicular distance = 2*sqrt(2)
    const d = pointToSegmentDist({ x: 0, y: 4 }, { x: 0, y: 0 }, { x: 4, y: 4 })
    expect(d).toBeCloseTo(2 * Math.sqrt(2), 4)
  })
  it('handles zero-length segment (degenerate)', () => {
    const d = pointToSegmentDist({ x: 3, y: 4 }, { x: 0, y: 0 }, { x: 0, y: 0 })
    expect(d).toBeCloseTo(5, 5)
  })
})

describe('detectTJunction', () => {
  it('detects a point at the segment midpoint', () => {
    const r = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 2, y: 0 })
    expect(r.hit).toBe(true)
    expect(r.point.x).toBeCloseTo(2, 3)
  })
  it('does not hit for a point clearly off the segment', () => {
    const r = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 2, y: 5 })
    expect(r.hit).toBe(false)
  })
  it('does not hit at the start endpoint', () => {
    const r = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 0, y: 0 }, 0.01)
    expect(r.hit).toBe(false)
  })
  it('does not hit at the end endpoint', () => {
    const r = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 0 }, 0.01)
    expect(r.hit).toBe(false)
  })
  it('respects custom tolerance — near-miss at default tol but hit at larger tol', () => {
    // Point is 0.05 away from segment (just below default tol of 0.1)
    const r1 = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 2, y: 0.05 }, 0.1)
    expect(r1.hit).toBe(true)
    const r2 = detectTJunction({ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 2, y: 0.5 }, 0.1)
    expect(r2.hit).toBe(false)
  })
})
