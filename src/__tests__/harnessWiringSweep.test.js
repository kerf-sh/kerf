// harnessWiringSweep.test.js — T-153 source-level + pure-JS geometry checks.
//
// No WASM required.  Tests fall into four groups:
//
//   1. Pure-JS geometry math for harnessFirstTangent and harnessSegmentLengths
//      (logic inlined here — occtWorker.js is a Web Worker and cannot be
//      imported in the Node/vitest environment).
//
//   2. Circle-wire profile geometry — verifies the tangent-aligned frame math
//      used by harnessBuildCircleWire places profile points correctly.
//
//   3. Source-level wiring checks on occtWorker.js — verifies that
//      opHarnessTubeSweep is defined and wired into both dispatch tables.
//
//   4. Node schema round-trip (via parseFeature / serializeFeature) — verifies
//      a harness_tube_sweep node survives serialisation intact.
//
// Pattern: mirrors featureBossWithDraft.test.js and sheetMetalFlange.test.js.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

import { parseFeature, serializeFeature } from '../lib/occtRunner.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const workerSrc = readFileSync(
  path.resolve(__dirname, '../lib/occtWorker.js'),
  'utf8',
)

// Boundary markers for the two dispatch tables.
const ET_START  = workerSrc.indexOf('function evaluateTree(')
const ETF_START = workerSrc.indexOf('async function evaluateToFinalShape(')

if (ET_START  === -1) throw new Error('evaluateTree not found in occtWorker.js')
if (ETF_START === -1) throw new Error('evaluateToFinalShape not found in occtWorker.js')

const etBody  = workerSrc.slice(ET_START, ETF_START)
const etfBody = workerSrc.slice(ETF_START)

// ---------------------------------------------------------------------------
// Pure-JS reimplementation of the geometry helpers from occtWorker.js
// (same logic as harnessFirstTangent / harnessSegmentLengths / the frame
// computation inside harnessBuildCircleWire).
//
// We duplicate the math here because occtWorker.js is a Web Worker module
// that cannot be imported in the Node environment (it calls self.addEventListener
// at module scope).  The source-level checks in group 3 verify the originals.
// ---------------------------------------------------------------------------

/**
 * Compute the first-segment unit tangent from a waypoints array.
 * Walks forward until a non-degenerate segment is found.
 * Falls back to [0,0,1] if all segments are degenerate.
 */
function harnessFirstTangentJS(waypoints) {
  for (let i = 0; i + 1 < waypoints.length; i++) {
    const [x0, y0, z0] = waypoints[i]
    const [x1, y1, z1] = waypoints[i + 1]
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz)
    if (len > 1e-9) return [dx / len, dy / len, dz / len]
  }
  return [0, 0, 1]
}

/**
 * Compute per-segment arc lengths from a waypoints array.
 */
function harnessSegmentLengthsJS(waypoints) {
  const lengths = []
  for (let i = 0; i + 1 < waypoints.length; i++) {
    const [x0, y0, z0] = waypoints[i]
    const [x1, y1, z1] = waypoints[i + 1]
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0
    lengths.push(Math.sqrt(dx * dx + dy * dy + dz * dz))
  }
  return lengths
}

/**
 * Compute the tangent-aligned frame (u, v) perpendicular to `tangent`.
 * Mirrors the frame logic inside harnessBuildCircleWire in occtWorker.js.
 */
function circleFrame(tangent) {
  const [tx, ty, tz] = tangent
  const up = Math.abs(tz) < 0.9 ? [0, 0, 1] : [0, 1, 0]
  const ux0 = up[1] * tz - up[2] * ty
  const uy0 = up[2] * tx - up[0] * tz
  const uz0 = up[0] * ty - up[1] * tx
  const ulen = Math.sqrt(ux0 * ux0 + uy0 * uy0 + uz0 * uz0)
  const ux = ux0 / ulen, uy = uy0 / ulen, uz = uz0 / ulen
  const vx = ty * uz - tz * uy
  const vy = tz * ux - tx * uz
  const vz = tx * uy - ty * ux
  return { u: [ux, uy, uz], v: [vx, vy, vz] }
}

/**
 * Compute the N-gon vertices that harnessBuildCircleWire places at the
 * circle plane defined by (cx, cy, cz, r, tangent).
 */
function circlePoints(cx, cy, cz, r, tangent, nPts) {
  const { u: [ux, uy, uz], v: [vx, vy, vz] } = circleFrame(tangent)
  const pts = []
  for (let i = 0; i < nPts; i++) {
    const a = (2 * Math.PI * i) / nPts
    const c = Math.cos(a), s = Math.sin(a)
    pts.push([
      cx + r * (c * ux + s * vx),
      cy + r * (c * uy + s * vy),
      cz + r * (c * uz + s * vz),
    ])
  }
  return pts
}

// ---------------------------------------------------------------------------
// 1. harnessFirstTangent — unit tangent of first non-degenerate segment
// ---------------------------------------------------------------------------

describe('harnessFirstTangent — unit tangent of first non-degenerate segment', () => {
  it('returns +Z for a straight vertical path', () => {
    const t = harnessFirstTangentJS([[0, 0, 0], [0, 0, 10]])
    expect(t[0]).toBeCloseTo(0, 10)
    expect(t[1]).toBeCloseTo(0, 10)
    expect(t[2]).toBeCloseTo(1, 10)
  })

  it('returns +X for a horizontal X-axis path', () => {
    const t = harnessFirstTangentJS([[0, 0, 0], [5, 0, 0]])
    expect(t[0]).toBeCloseTo(1, 10)
    expect(t[1]).toBeCloseTo(0, 10)
    expect(t[2]).toBeCloseTo(0, 10)
  })

  it('returns a unit vector (length == 1) for a diagonal path', () => {
    const t = harnessFirstTangentJS([[1, 2, 3], [4, 6, 3]])
    const len = Math.sqrt(t[0] ** 2 + t[1] ** 2 + t[2] ** 2)
    expect(len).toBeCloseTo(1, 10)
  })

  it('skips a degenerate (zero-length) first segment and uses the next', () => {
    const t = harnessFirstTangentJS([
      [0, 0, 0],
      [0, 0, 0],  // duplicate — degenerate
      [0, 10, 0], // valid second segment: +Y
    ])
    expect(t[0]).toBeCloseTo(0, 10)
    expect(t[1]).toBeCloseTo(1, 10)
    expect(t[2]).toBeCloseTo(0, 10)
  })

  it('falls back to [0,0,1] when ALL segments are degenerate', () => {
    const t = harnessFirstTangentJS([[5, 5, 5], [5, 5, 5]])
    expect(t).toEqual([0, 0, 1])
  })

  it('handles a 3-point L-shaped path — uses the first valid segment', () => {
    const t = harnessFirstTangentJS([[0, 0, 0], [10, 0, 0], [10, 10, 0]])
    expect(t[0]).toBeCloseTo(1, 10)
    expect(t[1]).toBeCloseTo(0, 10)
    expect(t[2]).toBeCloseTo(0, 10)
  })

  it('handles negative coordinates', () => {
    const t = harnessFirstTangentJS([[10, 10, 10], [0, 10, 10]])
    expect(t[0]).toBeCloseTo(-1, 10)
    expect(t[1]).toBeCloseTo(0, 10)
    expect(t[2]).toBeCloseTo(0, 10)
  })
})

// ---------------------------------------------------------------------------
// 2. harnessSegmentLengths — per-segment arc lengths
// ---------------------------------------------------------------------------

describe('harnessSegmentLengths — per-segment arc lengths', () => {
  it('returns a single length for a 2-point path', () => {
    const segs = harnessSegmentLengthsJS([[0, 0, 0], [3, 4, 0]])
    expect(segs).toHaveLength(1)
    expect(segs[0]).toBeCloseTo(5, 10) // 3-4-5 triangle
  })

  it('returns n-1 lengths for n waypoints', () => {
    const pts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 1]]
    const segs = harnessSegmentLengthsJS(pts)
    expect(segs).toHaveLength(pts.length - 1)
  })

  it('sums to total arc length for an L-path', () => {
    const pts = [[0, 0, 0], [10, 0, 0], [10, 10, 0]]
    const segs = harnessSegmentLengthsJS(pts)
    const total = segs.reduce((a, b) => a + b, 0)
    expect(total).toBeCloseTo(20, 10)
  })

  it('assigns zero length to a degenerate (duplicate) segment', () => {
    const pts = [[0, 0, 0], [0, 0, 0], [0, 0, 5]]
    const segs = harnessSegmentLengthsJS(pts)
    expect(segs[0]).toBeCloseTo(0, 10)
    expect(segs[1]).toBeCloseTo(5, 10)
  })

  it('computes correct 3D diagonal lengths (sqrt(3) per unit step)', () => {
    const pts = [[0, 0, 0], [1, 1, 1], [2, 2, 2]]
    const segs = harnessSegmentLengthsJS(pts)
    const diag = Math.sqrt(3)
    expect(segs[0]).toBeCloseTo(diag, 10)
    expect(segs[1]).toBeCloseTo(diag, 10)
  })

  it('gives all equal lengths for a uniform path', () => {
    const n = 5
    const pts = Array.from({ length: n }, (_, i) => [i * 10, 0, 0])
    const segs = harnessSegmentLengthsJS(pts)
    expect(segs).toHaveLength(n - 1)
    for (const s of segs) expect(s).toBeCloseTo(10, 10)
  })
})

// ---------------------------------------------------------------------------
// 3. Circle-wire profile geometry
// ---------------------------------------------------------------------------

describe('harnessBuildCircleWire profile geometry — tangent-aligned frame', () => {
  it('all circle points are at distance r from the centre (+Z tangent)', () => {
    const tangent = [0, 0, 1]
    const pts = circlePoints(0, 0, 0, 3, tangent, 16)
    for (const [x, y, z] of pts) {
      const dist = Math.sqrt(x * x + y * y + z * z)
      expect(dist).toBeCloseTo(3, 6)
    }
  })

  it('circle points lie in the plane perpendicular to tangent (+X tangent)', () => {
    const tangent = [1, 0, 0]
    const pts = circlePoints(5, 0, 0, 2, tangent, 16)
    for (const [x, y, z] of pts) {
      // dot(point - centre, tangent) ≈ 0
      const dot = (x - 5) * tangent[0] + y * tangent[1] + z * tangent[2]
      expect(dot).toBeCloseTo(0, 6)
    }
  })

  it('generates nPts distinct vertices for a +Y tangent', () => {
    const tangent = [0, 1, 0]
    const pts = circlePoints(0, 0, 0, 5, tangent, 16)
    expect(pts).toHaveLength(16)
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const d = Math.sqrt(
          (pts[i][0] - pts[j][0]) ** 2 +
          (pts[i][1] - pts[j][1]) ** 2 +
          (pts[i][2] - pts[j][2]) ** 2,
        )
        expect(d).toBeGreaterThan(0.01)
      }
    }
  })

  it('frame vectors u and v are perpendicular to tangent (diagonal tangent)', () => {
    const rawT = [1, 1, 0]
    const tlen = Math.sqrt(2)
    const tangent = [rawT[0] / tlen, rawT[1] / tlen, rawT[2] / tlen]
    const { u, v } = circleFrame(tangent)
    // u ⊥ tangent
    expect(u[0] * tangent[0] + u[1] * tangent[1] + u[2] * tangent[2]).toBeCloseTo(0, 10)
    // v ⊥ tangent
    expect(v[0] * tangent[0] + v[1] * tangent[1] + v[2] * tangent[2]).toBeCloseTo(0, 10)
  })

  it('frame vectors u and v are unit vectors', () => {
    const tangent = harnessFirstTangentJS([[0, 0, 0], [3, 4, 0]])
    const { u, v } = circleFrame(tangent)
    expect(Math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)).toBeCloseTo(1, 10)
    expect(Math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)).toBeCloseTo(1, 10)
  })

  it('u ⊥ v (frame is orthogonal)', () => {
    const tangent = harnessFirstTangentJS([[0, 0, 0], [1, 2, 3]])
    const { u, v } = circleFrame(tangent)
    const dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    expect(dot).toBeCloseTo(0, 10)
  })

  it('frame switches reference vector when tangent is nearly +Z', () => {
    // When tangent ≈ +Z, the fallback reference is [0,1,0] (not [0,0,1]).
    // The frame must still produce valid perpendicular vectors.
    const tangent = [0, 0, 1]  // exactly +Z
    const { u, v } = circleFrame(tangent)
    expect(u[0] * tangent[0] + u[1] * tangent[1] + u[2] * tangent[2]).toBeCloseTo(0, 6)
    expect(v[0] * tangent[0] + v[1] * tangent[1] + v[2] * tangent[2]).toBeCloseTo(0, 6)
  })

  it('centroid of profile points equals the circle centre', () => {
    const tangent = [0, 0, 1]
    const pts = circlePoints(7, 3, -5, 4, tangent, 16)
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length
    const cz = pts.reduce((s, p) => s + p[2], 0) / pts.length
    expect(cx).toBeCloseTo(7, 6)
    expect(cy).toBeCloseTo(3, 6)
    expect(cz).toBeCloseTo(-5, 6)
  })
})

// ---------------------------------------------------------------------------
// 4. Source-level wiring checks on occtWorker.js
// ---------------------------------------------------------------------------

describe('opHarnessTubeSweep — function definition in occtWorker.js', () => {
  it('function opHarnessTubeSweep is defined', () => {
    expect(workerSrc).toContain('function opHarnessTubeSweep(')
  })

  it('reads waypoints from node', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('node.waypoints')
  })

  it('reads bundle_diameter_mm from node', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('bundle_diameter_mm')
  })

  it('builds a polyline path wire using BRepBuilderAPI_MakeWire_1', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('BRepBuilderAPI_MakeWire_1()')
  })

  it('builds path edges using BRepBuilderAPI_MakeEdge_3', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('BRepBuilderAPI_MakeEdge_3(')
  })

  it('calls harnessFirstTangent to orient the profile', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('harnessFirstTangent(')
  })

  it('calls harnessBuildCircleWire for the circular cross-section profile', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('harnessBuildCircleWire(')
  })

  it('sweeps via BRepOffsetAPI_MakePipeShell', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('BRepOffsetAPI_MakePipeShell(')
  })

  it('calls MakeSolid to cap both ends', () => {
    const fnStart = workerSrc.indexOf('function opHarnessTubeSweep(')
    const fnBlock = workerSrc.slice(fnStart, fnStart + 3000)
    expect(fnBlock).toContain('MakeSolid()')
  })

  it('harnessFirstTangent helper function is defined (source check)', () => {
    expect(workerSrc).toContain('function harnessFirstTangent(')
  })

  it('harnessSegmentLengths helper function is defined (source check)', () => {
    expect(workerSrc).toContain('function harnessSegmentLengths(')
  })

  it('harnessBuildCircleWire helper function is defined (source check)', () => {
    expect(workerSrc).toContain('function harnessBuildCircleWire(')
  })
})

describe("case 'harness_tube_sweep' — evaluateTree dispatch", () => {
  it("case 'harness_tube_sweep' is present in evaluateTree", () => {
    expect(etBody).toContain("case 'harness_tube_sweep'")
  })

  it('evaluateTree harness_tube_sweep calls opHarnessTubeSweep', () => {
    const idx = etBody.indexOf("case 'harness_tube_sweep'")
    expect(idx).not.toBe(-1)
    const block = etBody.slice(idx, idx + 400)
    expect(block).toContain('opHarnessTubeSweep(')
  })
})

describe("case 'harness_tube_sweep' — evaluateToFinalShape dispatch", () => {
  it("case 'harness_tube_sweep' is present in evaluateToFinalShape", () => {
    expect(etfBody).toContain("case 'harness_tube_sweep'")
  })

  it('evaluateToFinalShape harness_tube_sweep calls opHarnessTubeSweep', () => {
    const idx = etfBody.indexOf("case 'harness_tube_sweep'")
    expect(idx).not.toBe(-1)
    const block = etfBody.slice(idx, idx + 400)
    expect(block).toContain('opHarnessTubeSweep(')
  })
})

describe('harness_tube_sweep — both dispatch tables wired', () => {
  it("exactly 2 case 'harness_tube_sweep' entries (one per dispatch table)", () => {
    const matches = workerSrc.match(/case 'harness_tube_sweep'/g)
    expect(matches).not.toBeNull()
    expect(matches.length).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// 5. Node schema round-trip via parseFeature / serializeFeature
// ---------------------------------------------------------------------------

describe('harness_tube_sweep node round-trip via parseFeature', () => {
  const SAMPLE_NODE = {
    id: 'harness-1',
    op: 'harness_tube_sweep',
    waypoints: [[0, 0, 0], [100, 0, 0], [100, 50, 30]],
    bundle_diameter_mm: 12.5,
    length_mm: 161.4,
    segment_lengths_mm: [100, 61.4],
  }

  it('parses a harness_tube_sweep node without dropping fields', () => {
    const json = JSON.stringify({ version: 1, name: 'Harness', features: [SAMPLE_NODE] })
    const parsed = parseFeature(json)
    expect(parsed.features).toHaveLength(1)
    const node = parsed.features[0]
    expect(node.op).toBe('harness_tube_sweep')
    expect(node.bundle_diameter_mm).toBe(12.5)
    expect(node.waypoints).toHaveLength(3)
  })

  it('serializeFeature round-trips a harness_tube_sweep node', () => {
    const tree = {
      version: 1,
      name: 'Harness',
      features: [SAMPLE_NODE],
      default_config: '',
      configurations: [],
    }
    const serialised = serializeFeature(tree)
    const back = JSON.parse(serialised)
    expect(back.features[0]).toMatchObject(SAMPLE_NODE)
  })

  it('waypoints array survives serialisation intact', () => {
    const json = JSON.stringify({ version: 1, name: 'H', features: [SAMPLE_NODE] })
    const parsed = parseFeature(json)
    const wp = parsed.features[0].waypoints
    expect(wp[0]).toEqual([0, 0, 0])
    expect(wp[1]).toEqual([100, 0, 0])
    expect(wp[2]).toEqual([100, 50, 30])
  })

  it('bundle_diameter_mm survives serialisation as a number', () => {
    const tree = {
      version: 1, name: 'H',
      features: [SAMPLE_NODE],
      default_config: '', configurations: [],
    }
    const back = JSON.parse(serializeFeature(tree))
    expect(typeof back.features[0].bundle_diameter_mm).toBe('number')
    expect(back.features[0].bundle_diameter_mm).toBeCloseTo(12.5, 6)
  })
})
