// Annotation, symbol, centerline and break-line rendering helpers.
//
// The drawing renderer (DrawingView.jsx) imports the SVG-glyph builders from
// here so the rendering logic is shared across the live canvas, the SVG
// exporter and any future thumbnail renderer.
//
// All coordinates are PAGE MILLIMETRES.

// Default stroke + paint settings — kept in sync with DrawingView constants.
export const ANN_STROKE = '#d9a800'
export const ANN_SELECTED = '#ffd633'
export const ANN_DEFAULT_W = 0.3
export const SYMBOL_STROKE = '#0c1118'
export const CENTERLINE_STROKE = '#1a3680'

// ---------------------------------------------------------------------------
// Hatch pattern (section views).
//
// We use SVG <pattern> elements with diagonal lines. patternId is keyed by
// spacing+angle so multiple sections can each pick their own density.

// Build a stable id for a pattern with the given config.
export function hatchPatternId(spacing, angleDeg) {
  const s = Math.max(0.5, Number(spacing) || 2.5)
  const a = ((Number(angleDeg) || 45) % 180 + 180) % 180
  return `kerf-hatch-${s.toFixed(1).replace('.', '_')}-${a.toFixed(0)}`
}

// Returns props for an <pattern> element (no JSX deps, pure data).
export function hatchPatternDef(spacing, angleDeg) {
  const s = Math.max(0.5, Number(spacing) || 2.5)
  const a = ((Number(angleDeg) || 45) % 180 + 180) % 180
  return {
    id: hatchPatternId(s, a),
    width: s,
    height: s,
    patternUnits: 'userSpaceOnUse',
    patternTransform: `rotate(${a})`,
    line: {
      x1: 0, y1: 0, x2: 0, y2: s,
      stroke: SYMBOL_STROKE, strokeWidth: 0.18,
    },
  }
}

// ---------------------------------------------------------------------------
// Symbols.
//
// Each symbol returns an array of SVG primitive descriptors so the renderer
// can stamp them with a single <g transform> wrap. Coordinates are RELATIVE
// to the symbol anchor and in PAGE MM. Caller positions via translate().

// Surface-finish glyph: tick "V" with optional Ra/Rz value. The ANSI
// machined-finish symbol is a triangular wedge sitting on the surface line;
// we draw the wedge at the origin pointing down at the leader root.
export function surfaceFinishGlyph(params = {}) {
  const ra = params.ra || params.text || ''
  const w = 5    // mm
  const h = 7
  return {
    elements: [
      // The "V" wedge.
      { type: 'polyline', points: [[-w / 2, 0], [0, h], [w / 2, 0]], stroke: SYMBOL_STROKE, fill: 'none', width: 0.3 },
      // Optional horizontal line across the top (machining-required variant).
      params.machined !== false
        ? { type: 'line', x1: -w / 2, y1: 0, x2: w / 2, y2: 0, stroke: SYMBOL_STROKE, width: 0.3 }
        : null,
      // Ra value text above the V.
      ra
        ? { type: 'text', x: 0, y: h + 3.2, anchor: 'middle', text: String(ra), fontSize: 2.8 }
        : null,
    ].filter(Boolean),
    bbox: { w: w + 4, h: h + 5 },
  }
}

// Weld-symbol glyph: horizontal reference line + flag + side-of-arrow tail.
// Highly simplified — one fillet weld size value above OR below.
export function weldGlyph(params = {}) {
  const text = params.text || ''
  const side = params.side || 'arrow' // 'arrow' (below) | 'other' (above)
  const refLen = 18
  const tailLen = 5
  return {
    elements: [
      // Reference line.
      { type: 'line', x1: 0, y1: 0, x2: refLen, y2: 0, stroke: SYMBOL_STROKE, width: 0.35 },
      // Tail (right side, breaks down).
      { type: 'line', x1: refLen, y1: 0, x2: refLen + tailLen, y2: -2, stroke: SYMBOL_STROKE, width: 0.35 },
      { type: 'line', x1: refLen, y1: 0, x2: refLen + tailLen, y2: 2, stroke: SYMBOL_STROKE, width: 0.35 },
      // Fillet triangle on the requested side.
      side === 'arrow'
        ? { type: 'polyline', points: [[refLen / 2 - 1.8, 0.4], [refLen / 2 + 1.8, 0.4], [refLen / 2 + 1.8, 3]], stroke: SYMBOL_STROKE, fill: SYMBOL_STROKE, width: 0.25 }
        : { type: 'polyline', points: [[refLen / 2 - 1.8, -0.4], [refLen / 2 + 1.8, -0.4], [refLen / 2 + 1.8, -3]], stroke: SYMBOL_STROKE, fill: SYMBOL_STROKE, width: 0.25 },
      text
        ? { type: 'text', x: refLen / 2, y: side === 'arrow' ? -1.2 : 4.2, anchor: 'middle', text: String(text), fontSize: 2.4 }
        : null,
    ].filter(Boolean),
    bbox: { w: refLen + tailLen + 2, h: 8 },
  }
}

// GD&T frame: simple two-cell rectangle [characteristic | tolerance |
// datums?]. v1 supports up to three cells; no compound frames.
export function gdtGlyph(params = {}) {
  const characteristic = params.characteristic || params.symbol || '⊥' // perpendicularity by default
  const tol = params.tolerance || params.value || ''
  const datums = params.datums || params.datum || ''
  // Each cell is laid out left-to-right. Width = 6mm symbol, 16mm tolerance,
  // 6mm datum (if present). Height is fixed at 6mm.
  const cellH = 6
  const cells = [
    { w: 6, text: characteristic, mono: false, big: true },
    { w: tol ? 18 : 0, text: tol, mono: true, big: false },
    { w: datums ? 6 * Math.max(1, String(datums).split(/[\s|,]/).filter(Boolean).length) : 0, text: datums, mono: true, big: false },
  ].filter((c) => c.w > 0)
  const elems = []
  let x = 0
  for (const c of cells) {
    elems.push({
      type: 'rect', x, y: 0, w: c.w, h: cellH,
      stroke: SYMBOL_STROKE, fill: 'none', width: 0.3,
    })
    elems.push({
      type: 'text',
      x: x + c.w / 2, y: cellH / 2 + (c.big ? 1.3 : 1.1),
      anchor: 'middle',
      text: c.text,
      fontSize: c.big ? 4.2 : 2.8,
      mono: c.mono,
    })
    x += c.w
  }
  return { elements: elems, bbox: { w: x, h: cellH } }
}

// Dispatch a symbol kind → glyph object.
export function symbolGlyph(kind, params) {
  switch (kind) {
    case 'surface_finish': return surfaceFinishGlyph(params)
    case 'weld':           return weldGlyph(params)
    case 'gdt':            return gdtGlyph(params)
    default: return { elements: [], bbox: { w: 0, h: 0 } }
  }
}

// ---------------------------------------------------------------------------
// Balloons (numbered callouts).

// Returns the balloon glyph + leader endpoint info. The renderer draws a
// circle with a number, plus an optional leader from the circle to a point.
export function balloonGlyph(params = {}) {
  const number = params.number ?? params.text ?? '?'
  const r = params.radius || 4.5
  return {
    radius: r,
    number: String(number),
    elements: [
      { type: 'circle', cx: 0, cy: 0, r, stroke: SYMBOL_STROKE, fill: '#ffffff', width: 0.4 },
      { type: 'text', x: 0, y: 1.4, anchor: 'middle', text: String(number), fontSize: 4.5, mono: false },
    ],
    bbox: { w: r * 2, h: r * 2 },
  }
}

// ---------------------------------------------------------------------------
// Centerlines.

// Compose a center dash pattern — long-short-long. Stroke width is fixed at
// 0.25 mm; consumers wrap with `vector-effect="non-scaling-stroke"`.
export const CENTER_DASH = '4,1.2,0.8,1.2'

// Auto-detect candidate centerlines for a projected view. Looks at the
// view's projected segment list for circles (3+ collinear segments forming
// a closed loop) — coarsely, we recognize a circle by clustering segment
// midpoints around a common centre with similar radii. Returns
// [{cx, cy, r, kind: 'circle'}].
//
// This is intentionally approximate: the goal is "draw plausible centerlines
// for typical hole patterns." Users can always add explicit centerlines via
// the toolbar.
export function detectCenterlines(segments) {
  const out = []
  if (!segments || segments.length < 3) return out
  // Group segments by their midpoint into a coarse spatial bucket; segments
  // that share a bucket likely belong to the same circle approximation.
  const buckets = new Map()
  for (const [a, b] of segments) {
    const mx = (a[0] + b[0]) / 2
    const my = (a[1] + b[1]) / 2
    const key = `${Math.round(mx)}::${Math.round(my)}`
    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key).push([a, b])
  }
  // For each segment, the centre of a circle through its midpoint along the
  // perpendicular bisector at distance r is unknown without more info, so we
  // use a pairwise circle-fit pass: for every two close midpoints, fit a
  // circle through their midpoints + endpoints and check that other segments
  // sit on it. This is O(n^2) — acceptable for n ≤ ~200 circles.
  // Simpler heuristic: look for arcs (3+ segments whose endpoints chain
  // around a centre). Fit a circle to every triplet of consecutive segments
  // sharing endpoints.
  const epts = []
  for (const [a, b] of segments) {
    epts.push({ a: [a[0], a[1]], b: [b[0], b[1]] })
  }
  // Build adjacency by shared endpoint (within 0.01 mm).
  function eq(p, q) { return Math.abs(p[0] - q[0]) < 0.01 && Math.abs(p[1] - q[1]) < 0.01 }
  const visited = new Array(epts.length).fill(false)
  for (let i = 0; i < epts.length; i++) {
    if (visited[i]) continue
    // Walk a chain.
    const chain = [epts[i]]
    visited[i] = true
    let last = epts[i].b
    let didFind = true
    while (didFind && chain.length < 64) {
      didFind = false
      for (let j = 0; j < epts.length; j++) {
        if (visited[j]) continue
        if (eq(epts[j].a, last)) {
          chain.push(epts[j]); last = epts[j].b; visited[j] = true; didFind = true; break
        }
        if (eq(epts[j].b, last)) {
          chain.push({ a: epts[j].b, b: epts[j].a }); last = epts[j].a; visited[j] = true; didFind = true; break
        }
      }
    }
    if (chain.length >= 6) {
      // Fit circle to chain endpoints' midpoints.
      const xs = []
      const ys = []
      for (const c of chain) {
        xs.push(c.a[0]); ys.push(c.a[1])
        xs.push(c.b[0]); ys.push(c.b[1])
      }
      const cx = xs.reduce((s, v) => s + v, 0) / xs.length
      const cy = ys.reduce((s, v) => s + v, 0) / ys.length
      let rs = 0
      for (let k = 0; k < xs.length; k++) {
        rs += Math.hypot(xs[k] - cx, ys[k] - cy)
      }
      const r = rs / xs.length
      // Check tightness — discard if variance too high.
      let v = 0
      for (let k = 0; k < xs.length; k++) {
        const d = Math.hypot(xs[k] - cx, ys[k] - cy) - r
        v += d * d
      }
      v = Math.sqrt(v / xs.length)
      if (v < r * 0.05 && r > 0.5) {
        out.push({ cx, cy, r, kind: 'circle' })
      }
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// Break lines.

// Build a zigzag polyline between p1 and p2 with `n` peaks. Used by the
// break-view annotation; the renderer draws this as a thin yellow line.
export function zigzagPoints(p1, p2, opts = {}) {
  const n = opts.peaks || 4
  const amp = opts.amplitude || 1.4
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const L = Math.hypot(dx, dy) || 1
  const ux = dx / L, uy = dy / L
  const nx = -uy, ny = ux
  const pts = [{ x: p1.x, y: p1.y }]
  for (let i = 1; i < n * 2; i++) {
    const t = i / (n * 2)
    const sign = (i % 2 === 1) ? 1 : -1
    const x = p1.x + ux * L * t + nx * amp * sign
    const y = p1.y + uy * L * t + ny * amp * sign
    pts.push({ x, y })
  }
  pts.push({ x: p2.x, y: p2.y })
  return pts
}

// Validate an annotation/symbol/centerline/break entry.
export function validateAnnotation(ann) {
  if (!ann || typeof ann !== 'object') return 'must be an object'
  switch (ann.kind) {
    case 'text':
      if (typeof ann.x !== 'number' || typeof ann.y !== 'number') return 'text needs x,y'
      if (!ann.text) return 'text needs text'
      return null
    case 'leader':
      if (!ann.from || !ann.to) return 'leader needs from,to'
      return null
    case 'balloon':
      if (typeof ann.cx !== 'number' || typeof ann.cy !== 'number') return 'balloon needs cx,cy'
      return null
    case 'note':
      if (typeof ann.x !== 'number' || typeof ann.y !== 'number') return 'note needs x,y'
      if (!ann.text) return 'note needs text'
      return null
    case 'polyline':
      if (!Array.isArray(ann.points) || ann.points.length < 2) return 'polyline needs ≥2 points'
      return null
    case 'rect':
      if (typeof ann.x !== 'number' || typeof ann.y !== 'number') return 'rect needs x,y'
      if (!(ann.width > 0 && ann.height > 0)) return 'rect needs width,height > 0'
      return null
    case 'circle':
      if (typeof ann.cx !== 'number' || typeof ann.cy !== 'number') return 'circle needs cx,cy'
      if (!(ann.r > 0)) return 'circle needs r > 0'
      return null
    default:
      return `unknown annotation kind: ${ann.kind}`
  }
}

export function validateSymbol(sym) {
  if (!sym || typeof sym !== 'object') return 'must be an object'
  if (!['surface_finish', 'weld', 'gdt'].includes(sym.kind)) {
    return `unknown symbol kind: ${sym.kind}`
  }
  if (!sym.position || typeof sym.position.x !== 'number' || typeof sym.position.y !== 'number') {
    return 'symbol needs position {x,y}'
  }
  return null
}
