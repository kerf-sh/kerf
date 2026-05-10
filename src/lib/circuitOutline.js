// circuitOutline.js — extract a 2D board outline from compiled CircuitJSON
// and emit it as a `.sketch`-shape JSON object that flows through the
// existing sketch-import pipeline (parseSketch → sketchGeom2 → extrudeLinear).
//
// Why this lives in its own module:
//   The cross-project resolver (workspace store, ROADMAP row 67 Phase 2) was
//   shipping a degenerate ~0.1mm slab as the "board_outline_2d" payload —
//   useful as a placeholder, useless as a sketch the host assembly can
//   extrude / pattern. This helper turns the same `pcb_board` records that
//   `circuit-to-svg` and `CircuitEditor.buildBoardParts` already consume into
//   a closed Geom2 polygon expressed as point + line entities — the same
//   shape `parseSketch` returns. The resolver consumer can then forward the
//   result as if the user had hand-authored a `.sketch` file.
//
// API:
//   extractBoardOutline(circuitJson) → { entities, units, source, plane,
//                                        version, constraints, visible_3d,
//                                        solved, metadata }
//
//   `entities` is an alternating array of point + line entries forming a
//   closed loop (last line's `p2` === first line's `p1`). The other fields
//   match the canonical sketch shape so callers can serialize the result
//   straight through `serializeSketch` if they want — they're all defaulted
//   to empty here so the pipeline doesn't trip over missing keys.
//
//   `source` is a small breadcrumb ('outline' | 'rect' | 'fallback')
//   describing which path produced the polygon — handy for tests and the
//   "where did this come from?" debugger.
//
// Defensive on malformed input:
//   - circuitJson not an array            → fallback rectangle
//   - no pcb_board record                 → fallback rectangle
//   - pcb_board with explicit polygon
//     outline (≥3 points)                 → outline path
//   - pcb_board with width/height
//     (and optional center)               → rectangle path
//   - pcb_board with neither              → fallback rectangle
//
// Fallback rectangle is 10mm × 10mm centered on origin — small enough that a
// human notices something's off, big enough that downstream extrudes don't
// blow up the renderer.

const FALLBACK_W = 10
const FALLBACK_H = 10

// Mint a stable id given a counter. Stable-vs-random matters here because
// the resolver consumer caches by content-hash; randomly-generated ids would
// invalidate the cache on every call even when the source hasn't changed.
function pid(i) { return `bo_p${i}` }
function lid(i) { return `bo_ln${i}` }

// Build entities from a sequence of [x, y] vertices forming a closed ring
// (the closing edge is implicit — we don't repeat the first vertex). Returns
// `{entities}` shaped for `.sketch`. The closing line's `p2` references the
// first point's id, so the loop is unambiguously closed.
function entitiesFromRing(ring) {
  const entities = []
  const n = ring.length
  for (let i = 0; i < n; i++) {
    const [x, y] = ring[i]
    entities.push({ id: pid(i), type: 'point', x: Number(x) || 0, y: Number(y) || 0 })
  }
  for (let i = 0; i < n; i++) {
    const a = pid(i)
    const b = pid((i + 1) % n)
    entities.push({ id: lid(i), type: 'line', p1: a, p2: b })
  }
  return entities
}

// Synthesise a centered axis-aligned rectangle ring as [x,y] pairs in CCW
// order. (CCW = positive signed area = outer ring per JSCAD geom2 conv.)
function rectRing(width, height, cx = 0, cy = 0) {
  const w = Math.max(0.001, Number(width)  || FALLBACK_W)
  const h = Math.max(0.001, Number(height) || FALLBACK_H)
  const x0 = (Number(cx) || 0) - w / 2
  const y0 = (Number(cy) || 0) - h / 2
  const x1 = x0 + w
  const y1 = y0 + h
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
}

// Pull a polygon outline out of `pcb_board.outline` if present and well-shaped.
// Returns null when the field is missing, malformed, or has fewer than 3
// distinct vertices.
function readExplicitOutline(board) {
  if (!board || !Array.isArray(board.outline) || board.outline.length < 3) return null
  const pts = []
  for (const p of board.outline) {
    if (!p || typeof p !== 'object') continue
    const x = Number(p.x)
    const y = Number(p.y)
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    pts.push([x, y])
  }
  if (pts.length < 3) return null
  // Strip a trailing duplicate of the first point if the source authored an
  // explicitly closed ring — we close implicitly via the wrapping line.
  const first = pts[0]
  const last = pts[pts.length - 1]
  if (Math.abs(first[0] - last[0]) < 1e-9 && Math.abs(first[1] - last[1]) < 1e-9) {
    pts.pop()
  }
  return pts.length >= 3 ? pts : null
}

// Wrap a ring in the canonical `.sketch` envelope. We populate the empty
// arrays so callers (and `serializeSketch`) don't have to special-case
// missing keys; `metadata.derived_from` is a breadcrumb for the debugger.
function wrapAsSketch(ring, source) {
  return {
    version: 1,
    plane: 'xy',
    entities: entitiesFromRing(ring),
    constraints: [],
    visible_3d: [],
    solved: {},
    metadata: { derived_from: source },
    units: 'mm',
    source,
  }
}

/**
 * Extract a 2D board outline from compiled CircuitJSON and return it shaped
 * as a `.sketch` JSON object. See module docstring for behaviour matrix.
 */
export function extractBoardOutline(circuitJson) {
  if (!Array.isArray(circuitJson)) {
    console.debug('extractBoardOutline: circuitJson is not an array; using fallback rect')
    return wrapAsSketch(rectRing(FALLBACK_W, FALLBACK_H), 'fallback')
  }
  const board = circuitJson.find((e) => e && e.type === 'pcb_board')
  if (!board) {
    console.debug('extractBoardOutline: no pcb_board record; using fallback rect')
    return wrapAsSketch(rectRing(FALLBACK_W, FALLBACK_H), 'fallback')
  }

  // Path 1: explicit polygon outline. Preferred — preserves non-rectangular
  // boards (rounded corners get pre-tessellated by tscircuit; we just
  // forward those vertices).
  const explicit = readExplicitOutline(board)
  if (explicit) {
    return wrapAsSketch(explicit, 'outline')
  }

  // Path 2: width/height + optional center. The synthetic rectangle is
  // centered on `pcb_board.center` when supplied, else origin.
  const w = Number(board.width)
  const h = Number(board.height)
  if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
    const cx = Number(board.center?.x) || 0
    const cy = Number(board.center?.y) || 0
    return wrapAsSketch(rectRing(w, h, cx, cy), 'rect')
  }

  // Path 3: defensive fallback.
  console.debug('extractBoardOutline: pcb_board lacks outline / width / height; using fallback rect')
  return wrapAsSketch(rectRing(FALLBACK_W, FALLBACK_H), 'fallback')
}

// Re-exports for callers that want the building blocks separately (e.g. a
// test that wants to assert the rect path without going through the full
// dispatcher). Kept on the same module so the surface stays tight.
export const __test__ = { rectRing, entitiesFromRing, readExplicitOutline }
