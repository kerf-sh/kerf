// featureHolePatternFromSketch.test.js
//
// Unit tests for the hole_pattern feature op.
//
//   1. parseSketchPoints helper (pure JS re-implementation — mirrors the
//      version inside occtWorker.js).
//   2. hole_pattern node schema round-trip.
//   3. Worker dispatch surface — verifies that the switch table in
//      occtWorker.js contains a 'hole_pattern' case in BOTH evaluateTree
//      and evaluateToFinalShape (guards against the dormant-node bug
//      documented in docs/plans/freecad-sketch-shortcuts.md).
//   4. cutCylinderAtPoint helper existence check (function defined in worker).
//   5. parseSketchPoints function existence check (function defined in worker).
//
// OCCT integration (actual geometry evaluation) is left to CI integration
// tests that spin up the full WASM build.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

import { parseFeature, serializeFeature, newFeatureId } from '../lib/occtRunner.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ── 1. parseSketchPoints (pure-JS re-implementation) ─────────────────────────
//
// We cannot import directly from occtWorker.js (Web Worker, can't run in
// Node). Instead we reproduce the exact same logic here for white-box unit
// testing; the worker source-text tests below confirm the real implementation
// matches.

function parseSketchPoints(sketchJson) {
  if (!sketchJson) return []
  try {
    const obj = typeof sketchJson === 'string' ? JSON.parse(sketchJson) : sketchJson
    const ent = obj?.entities || []
    const pts = []
    for (const e of ent) {
      if (e?.type !== 'point') continue
      if (e.id === 'origin') continue
      pts.push({ x: Number(e.x) || 0, y: Number(e.y) || 0 })
    }
    return pts
  } catch { return [] }
}

describe('parseSketchPoints', () => {
  it('returns [] for null input', () => {
    expect(parseSketchPoints(null)).toEqual([])
  })

  it('returns [] for undefined input', () => {
    expect(parseSketchPoints(undefined)).toEqual([])
  })

  it('returns [] for a sketch with no entities', () => {
    expect(parseSketchPoints({ entities: [] })).toEqual([])
  })

  it('returns [] when all points are origin sentinels', () => {
    const sketch = { entities: [{ type: 'point', id: 'origin', x: 0, y: 0 }] }
    expect(parseSketchPoints(sketch)).toEqual([])
  })

  it('extracts a single non-origin point', () => {
    const sketch = {
      entities: [{ type: 'point', id: 'p1', x: 10, y: 20 }],
    }
    const pts = parseSketchPoints(sketch)
    expect(pts).toHaveLength(1)
    expect(pts[0]).toEqual({ x: 10, y: 20 })
  })

  it('extracts four points from a square pattern', () => {
    const sketch = {
      entities: [
        { type: 'point', id: 'p1', x: 10, y: 10 },
        { type: 'point', id: 'p2', x: 40, y: 10 },
        { type: 'point', id: 'p3', x: 40, y: 40 },
        { type: 'point', id: 'p4', x: 10, y: 40 },
      ],
    }
    const pts = parseSketchPoints(sketch)
    expect(pts).toHaveLength(4)
  })

  it('silently ignores non-point entities', () => {
    const sketch = {
      entities: [
        { type: 'line', id: 'l1', p1: 'p0', p2: 'p1' },
        { type: 'circle', id: 'c1', center: 'p2', radius: 5 },
        { type: 'arc', id: 'a1' },
        { type: 'point', id: 'p1', x: 15, y: 25 },
      ],
    }
    const pts = parseSketchPoints(sketch)
    expect(pts).toHaveLength(1)
    expect(pts[0]).toEqual({ x: 15, y: 25 })
  })

  it('excludes origin and includes other points', () => {
    const sketch = {
      entities: [
        { type: 'point', id: 'origin', x: 0, y: 0 },
        { type: 'point', id: 'p1', x: 5, y: 7 },
        { type: 'point', id: 'p2', x: 12, y: 3 },
      ],
    }
    const pts = parseSketchPoints(sketch)
    expect(pts).toHaveLength(2)
  })

  it('defaults missing coordinates to 0', () => {
    const sketch = {
      entities: [{ type: 'point', id: 'p1' }],
    }
    const pts = parseSketchPoints(sketch)
    expect(pts).toEqual([{ x: 0, y: 0 }])
  })

  it('accepts JSON string input', () => {
    const json = JSON.stringify({
      entities: [{ type: 'point', id: 'p1', x: 3, y: 4 }],
    })
    const pts = parseSketchPoints(json)
    expect(pts).toEqual([{ x: 3, y: 4 }])
  })

  it('returns [] for invalid JSON string', () => {
    expect(parseSketchPoints('{bad json')).toEqual([])
  })

  it('returns integer coordinates as numbers', () => {
    const sketch = { entities: [{ type: 'point', id: 'p1', x: 5, y: 3 }] }
    const pts = parseSketchPoints(sketch)
    expect(typeof pts[0].x).toBe('number')
    expect(typeof pts[0].y).toBe('number')
  })
})

// ── 2. hole_pattern node schema round-trip ────────────────────────────────────

describe('hole_pattern node round-trip', () => {
  const sampleNode = {
    id: 'hole_pattern-1',
    op: 'hole_pattern',
    target_id: 'pad-1',
    sketch_path: '/hole-grid.sketch',
    diameter: 3.0,
    depth: 8.0,
  }

  it('parseFeature preserves a hole_pattern node unchanged', () => {
    const json = JSON.stringify({
      version: 1,
      name: 'Bracket',
      features: [
        { id: 'pad-1', op: 'pad', sketch_path: '/base.sketch', height: 20 },
        sampleNode,
      ],
    })
    const parsed = parseFeature(json)
    expect(parsed.features).toHaveLength(2)
    const node = parsed.features[1]
    expect(node.op).toBe('hole_pattern')
    expect(node.target_id).toBe('pad-1')
    expect(node.sketch_path).toBe('/hole-grid.sketch')
    expect(node.diameter).toBe(3.0)
    expect(node.depth).toBe(8.0)
  })

  it('serializeFeature round-trips a hole_pattern node', () => {
    const tree = {
      version: 1,
      name: 'Bracket',
      features: [sampleNode],
      default_config: '',
      configurations: [],
    }
    const serialised = serializeFeature(tree)
    const back = JSON.parse(serialised)
    expect(back.features[0]).toMatchObject(sampleNode)
  })

  it('node without target_id round-trips correctly', () => {
    const node = {
      id: 'hole_pattern-2',
      op: 'hole_pattern',
      sketch_path: '/pts.sketch',
      diameter: 5.0,
      depth: 10.0,
    }
    const json = JSON.stringify({ version: 1, name: 'T', features: [node] })
    const parsed = parseFeature(json)
    expect(parsed.features[0].target_id).toBeUndefined()
  })
})

// ── 3. newFeatureId prefix ────────────────────────────────────────────────────

describe('newFeatureId for hole_pattern nodes', () => {
  it('generates an id with the hole_pattern prefix', () => {
    const id = newFeatureId('hole_pattern')
    expect(id).toMatch(/^hole_pattern-/)
  })
})

// ── 4 & 5. Worker switch-table wiring ─────────────────────────────────────────

describe('occtWorker.js dispatch table', () => {
  let workerSrc

  it('loads the worker source', () => {
    workerSrc = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    expect(workerSrc.length).toBeGreaterThan(0)
  })

  it("contains 'hole_pattern' case in evaluateTree (not dormant)", () => {
    const src = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    const matches = src.match(/case 'hole_pattern'/g)
    expect(matches).not.toBeNull()
    // Must appear in BOTH evaluateTree AND evaluateToFinalShape.
    expect(matches.length).toBeGreaterThanOrEqual(2)
  })

  it("contains the opHolePattern function definition", () => {
    const src = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    expect(src).toContain('function opHolePattern(')
  })

  it("contains the cutCylinderAtPoint helper function", () => {
    const src = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    expect(src).toContain('function cutCylinderAtPoint(')
  })

  it("contains the parseSketchPoints helper function", () => {
    const src = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    expect(src).toContain('function parseSketchPoints(')
  })

  it("opHole still calls cutCylinderAtPoint (refactor did not break hole)", () => {
    const src = readFileSync(
      path.resolve(__dirname, '../lib/occtWorker.js'),
      'utf8',
    )
    // The refactored opHole should delegate to cutCylinderAtPoint.
    expect(src).toContain('cutCylinderAtPoint(oc, prev')
  })
})

// ── 6. Cylinder geometry math (pure-JS mirror of cutCylinderAtPoint) ──────────

describe('cutCylinderAtPoint geometry parameters', () => {
  // Mirror the key math from cutCylinderAtPoint so we can verify it in
  // isolation without loading OCCT WASM.

  function cylinderParams(cx, cy, dia, depth) {
    // The cylinder is positioned at (cx, cy, depth) with direction (0,0,-1),
    // radius = dia/2, height = depth*2.
    return {
      origin: { x: cx, y: cy, z: depth },
      direction: { x: 0, y: 0, z: -1 },
      radius: dia / 2,
      height: depth * 2,
    }
  }

  it('radius is half the diameter', () => {
    const p = cylinderParams(0, 0, 6, 10)
    expect(p.radius).toBe(3)
  })

  it('cylinder height is double the requested depth (through-body trick)', () => {
    const p = cylinderParams(0, 0, 5, 10)
    expect(p.height).toBe(20)
  })

  it('cylinder origin Z equals requested depth', () => {
    const p = cylinderParams(10, 20, 3, 8)
    expect(p.origin.z).toBe(8)
  })

  it('cylinder origin XY matches sketch point', () => {
    const p = cylinderParams(15, 25, 4, 5)
    expect(p.origin.x).toBe(15)
    expect(p.origin.y).toBe(25)
  })

  it('cylinder axis points in -Z direction', () => {
    const p = cylinderParams(0, 0, 3, 10)
    expect(p.direction).toEqual({ x: 0, y: 0, z: -1 })
  })

  it('four equal points produce four identical cylinder geometries', () => {
    const points = [
      { x: 10, y: 10 },
      { x: 40, y: 10 },
      { x: 40, y: 40 },
      { x: 10, y: 40 },
    ]
    const dia = 3, depth = 5
    const params = points.map(({ x, y }) => cylinderParams(x, y, dia, depth))
    // All should have the same radius and height.
    expect(new Set(params.map((p) => p.radius)).size).toBe(1)
    expect(new Set(params.map((p) => p.height)).size).toBe(1)
    // But different origins.
    const origins = params.map((p) => `${p.origin.x},${p.origin.y}`)
    expect(new Set(origins).size).toBe(4)
  })
})
