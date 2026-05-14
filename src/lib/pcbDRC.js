// pcbDRC.js — Frontend design-rule check for CircuitJSON boards.
//
// Usage:
//   import { runDRC } from './pcbDRC.js'
//   const { errors, warnings } = runDRC(circuitJson)
//
// circuitJson: AnyCircuitElement[] (flat array from tscircuit)
// Returns:
//   errors   : Array<{ x, y, kind, message, trace_id? }>
//   warnings : Array<{ x, y, kind, message }>
//
// Default thresholds follow IPC-2221B Class B (consumer electronics) and can
// be overridden via the board's `drc_rules` key on the pcb_board element.

// -------------------------------------------------------------------
// Default DRC rules — mirrors IPC-2221B Class B + common fab minimums.
// -------------------------------------------------------------------
const DEFAULT_RULES = Object.freeze({
  min_trace_width_mm:      0.15,  // narrowest allowed trace
  min_via_clearance_mm:    0.10,  // via annular ring to adjacent copper
  min_drill_spacing_mm:    0.20,  // edge-to-edge between drill holes
  min_copper_to_edge_mm:   0.30,  // copper keepout from board edge
  silk_on_pad_tolerance:   0.05,  // how much silk can overlap pad (mm)
})

// -------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------

function dist2d(ax, ay, bx, by) {
  return Math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)
}

function segmentLength(points) {
  let len = 0
  for (let i = 1; i < points.length; i++) {
    len += dist2d(points[i - 1].x, points[i - 1].y, points[i].x, points[i].y)
  }
  return len
}

function segmentMidpoint(points) {
  if (!points.length) return { x: 0, y: 0 }
  if (points.length === 1) return { x: points[0].x, y: points[0].y }
  const mid = Math.floor(points.length / 2)
  return { x: (points[mid - 1].x + points[mid].x) / 2, y: (points[mid - 1].y + points[mid].y) / 2 }
}

function getRules(board) {
  if (!board) return { ...DEFAULT_RULES }
  const overrides = board.drc_rules || {}
  return { ...DEFAULT_RULES, ...overrides }
}

// -------------------------------------------------------------------
// Check: trace width minimum
// -------------------------------------------------------------------
function checkTraceWidth(traces, rules) {
  const errors = []
  const minW = rules.min_trace_width_mm
  for (const trace of traces) {
    const w = trace.route_thickness_mm ?? trace.width_mm ?? trace.stroke_width ?? null
    if (w !== null && w < minW) {
      const pts = trace.route ?? trace.points ?? []
      const pos = segmentMidpoint(pts.length ? pts : [{ x: trace.x ?? 0, y: trace.y ?? 0 }])
      errors.push({
        x: pos.x,
        y: pos.y,
        kind: 'trace_too_narrow',
        message: `Trace width ${w.toFixed(3)} mm is below minimum ${minW} mm`,
        trace_id: trace.pcb_trace_id ?? trace.id ?? null,
      })
    }
  }
  return errors
}

// -------------------------------------------------------------------
// Check: via clearance
// -------------------------------------------------------------------
function checkViaClearance(vias, rules) {
  const errors = []
  const minClear = rules.min_via_clearance_mm

  for (let i = 0; i < vias.length; i++) {
    for (let j = i + 1; j < vias.length; j++) {
      const a = vias[i]
      const b = vias[j]
      const ax = a.x ?? 0, ay = a.y ?? 0
      const bx = b.x ?? 0, by = b.y ?? 0
      const aOuter = (a.outer_diameter ?? a.pad_diameter ?? 0.6) / 2
      const bOuter = (b.outer_diameter ?? b.pad_diameter ?? 0.6) / 2
      const centerDist = dist2d(ax, ay, bx, by)
      const gap = centerDist - aOuter - bOuter
      if (gap < minClear) {
        errors.push({
          x: (ax + bx) / 2,
          y: (ay + by) / 2,
          kind: 'via_clearance',
          message: `Via clearance ${gap.toFixed(3)} mm is below minimum ${minClear} mm`,
        })
      }
    }
  }
  return errors
}

// -------------------------------------------------------------------
// Check: drill spacing (hole edge-to-edge)
// -------------------------------------------------------------------
function checkDrillSpacing(vias, rules) {
  const errors = []
  const minSpace = rules.min_drill_spacing_mm

  for (let i = 0; i < vias.length; i++) {
    for (let j = i + 1; j < vias.length; j++) {
      const a = vias[i]
      const b = vias[j]
      const ax = a.x ?? 0, ay = a.y ?? 0
      const bx = b.x ?? 0, by = b.y ?? 0
      const aDrill = (a.hole_diameter ?? a.drill_diameter ?? 0.3) / 2
      const bDrill = (b.hole_diameter ?? b.drill_diameter ?? 0.3) / 2
      const edgeToEdge = dist2d(ax, ay, bx, by) - aDrill - bDrill
      if (edgeToEdge < minSpace) {
        errors.push({
          x: (ax + bx) / 2,
          y: (ay + by) / 2,
          kind: 'drill_spacing',
          message: `Drill hole spacing ${edgeToEdge.toFixed(3)} mm is below minimum ${minSpace} mm`,
        })
      }
    }
  }
  return errors
}

// -------------------------------------------------------------------
// Check: silk-on-pad (silkscreen overlaps copper pad)
// -------------------------------------------------------------------
function checkSilkOnPad(silkTexts, pads, rules) {
  const warnings = []
  const tol = rules.silk_on_pad_tolerance

  for (const text of silkTexts) {
    const tx = text.anchor_x ?? text.x ?? 0
    const ty = text.anchor_y ?? text.y ?? 0

    for (const pad of pads) {
      const px = pad.x ?? 0
      const py = pad.y ?? 0
      const pr = (pad.width ?? pad.pad_diameter ?? 1.5) / 2

      const d = dist2d(tx, ty, px, py)
      if (d < pr - tol) {
        warnings.push({
          x: tx,
          y: ty,
          kind: 'silk_on_pad',
          message: `Silkscreen text may overlap pad at (${px.toFixed(2)}, ${py.toFixed(2)})`,
        })
        break  // one warning per silk element
      }
    }
  }
  return warnings
}

// -------------------------------------------------------------------
// Check: copper-to-edge clearance
// -------------------------------------------------------------------
function checkCopperToEdge(traces, pads, vias, board, rules) {
  const warnings = []
  const minEdge = rules.min_copper_to_edge_mm
  if (!board) return warnings

  const bw = board.width ?? 0
  const bh = board.height ?? 0
  if (bw <= 0 || bh <= 0) return warnings

  // Simple rectangular board check: distance from each copper element to the nearest edge.
  function check(x, y, label) {
    const dLeft   = x
    const dRight  = bw - x
    const dTop    = y
    const dBottom = bh - y
    const minD = Math.min(dLeft, dRight, dTop, dBottom)
    if (minD < minEdge) {
      warnings.push({
        x,
        y,
        kind: 'copper_to_edge',
        message: `${label} is ${minD.toFixed(3)} mm from board edge (min ${minEdge} mm)`,
      })
    }
  }

  for (const trace of traces) {
    const pts = trace.route ?? trace.points ?? []
    for (const pt of pts) check(pt.x ?? 0, pt.y ?? 0, 'Trace')
  }

  for (const pad of pads) check(pad.x ?? 0, pad.y ?? 0, 'Pad')
  for (const via of vias) check(via.x ?? 0, via.y ?? 0, 'Via')

  return warnings
}

// -------------------------------------------------------------------
// Check: dangling trace (endpoint not on any pad and not connected to
//        another trace endpoint)
// -------------------------------------------------------------------
function checkDanglingTraces(traces, pads) {
  const errors = []
  const EPS = 1e-4  // mm snap tolerance

  // Collect all pad positions
  const padPositions = pads.map((p) => ({ x: p.x ?? 0, y: p.y ?? 0 }))

  // Collect all trace endpoints
  const endpoints = []
  for (const trace of traces) {
    const pts = trace.route ?? trace.points ?? []
    if (pts.length < 2) continue
    endpoints.push({ x: pts[0].x, y: pts[0].y, trace })
    endpoints.push({ x: pts[pts.length - 1].x, y: pts[pts.length - 1].y, trace })
  }

  function onPad(x, y) {
    return padPositions.some(
      (p) => Math.abs(p.x - x) < EPS && Math.abs(p.y - y) < EPS,
    )
  }

  function connectedToOtherTrace(x, y, selfTrace) {
    return endpoints.some(
      (ep) =>
        ep.trace !== selfTrace &&
        Math.abs(ep.x - x) < EPS &&
        Math.abs(ep.y - y) < EPS,
    )
  }

  // Deduplicate: report each dangling endpoint once per trace
  for (const trace of traces) {
    const pts = trace.route ?? trace.points ?? []
    if (pts.length < 2) continue

    const checkEnd = (pt, label) => {
      const x = pt.x ?? 0
      const y = pt.y ?? 0
      if (!onPad(x, y) && !connectedToOtherTrace(x, y, trace)) {
        errors.push({
          x,
          y,
          kind: 'dangling_trace',
          severity: 'error',
          message: `Trace ${label} endpoint (${x.toFixed(3)}, ${y.toFixed(3)}) is not connected to a pad or another trace`,
          trace_id: trace.pcb_trace_id ?? trace.id ?? null,
        })
      }
    }

    checkEnd(pts[0], 'start')
    checkEnd(pts[pts.length - 1], 'end')
  }

  return errors
}

// -------------------------------------------------------------------
// Check: net short — two pads on different nets connected by copper.
//
// Algorithm: union-find over trace endpoints + pad positions.  Pads
// whose positions are < EPS apart (or connected through a chain of
// traces) get merged into the same cluster.  If a cluster contains
// pads from more than one distinct net_id, it is a net short.
// -------------------------------------------------------------------
function checkNetShorts(traces, pads) {
  const errors = []
  const EPS = 1e-4

  // Only care about pads that have a net_id
  const nettedPads = pads.filter((p) => p.net_id || p.net)

  if (nettedPads.length < 2) return errors

  // Nodes: each pad is a node; we also create transient nodes for trace
  // endpoints that are coincident with pads.
  const nodes = nettedPads.map((p, i) => ({
    id: i,
    x: p.x ?? 0,
    y: p.y ?? 0,
    net: p.net_id ?? p.net,
    parent: i,
  }))

  function find(id) {
    while (nodes[id].parent !== id) {
      nodes[id].parent = nodes[nodes[id].parent].parent
      id = nodes[id].parent
    }
    return id
  }

  function unite(a, b) {
    const ra = find(a), rb = find(b)
    if (ra !== rb) nodes[ra].parent = rb
  }

  // Two pads at the same location → same cluster (plated holes can share pos)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      if (
        Math.abs(nodes[i].x - nodes[j].x) < EPS &&
        Math.abs(nodes[i].y - nodes[j].y) < EPS
      ) {
        unite(i, j)
      }
    }
  }

  // Walk each trace: if both endpoints land on pads, union those pads
  for (const trace of traces) {
    const pts = trace.route ?? trace.points ?? []
    if (pts.length < 2) continue
    const startX = pts[0].x ?? 0, startY = pts[0].y ?? 0
    const endX = pts[pts.length - 1].x ?? 0, endY = pts[pts.length - 1].y ?? 0

    const startHits = nodes
      .map((n, i) => ({ i, n }))
      .filter(({ n }) => Math.abs(n.x - startX) < EPS && Math.abs(n.y - startY) < EPS)

    const endHits = nodes
      .map((n, i) => ({ i, n }))
      .filter(({ n }) => Math.abs(n.x - endX) < EPS && Math.abs(n.y - endY) < EPS)

    for (const s of startHits) {
      for (const e of endHits) {
        unite(s.i, e.i)
      }
    }
  }

  // Check each cluster for mixed nets
  const reported = new Set()
  const clusters = new Map()
  for (let i = 0; i < nodes.length; i++) {
    const root = find(i)
    if (!clusters.has(root)) clusters.set(root, [])
    clusters.get(root).push(nodes[i])
  }

  for (const [, members] of clusters) {
    const nets = [...new Set(members.map((m) => m.net))]
    if (nets.length > 1) {
      const key = nets.sort().join('|')
      if (!reported.has(key)) {
        reported.add(key)
        const cx = members.reduce((s, m) => s + m.x, 0) / members.length
        const cy = members.reduce((s, m) => s + m.y, 0) / members.length
        errors.push({
          x: cx,
          y: cy,
          kind: 'net_short',
          severity: 'error',
          message: `Net short: copper connects nets ${nets.join(', ')}`,
        })
      }
    }
  }

  return errors
}

// -------------------------------------------------------------------
// Main export: runDRC
// -------------------------------------------------------------------

/**
 * runDRC — run all DRC checks on a flat CircuitJSON array.
 *
 * @param {Array} circuitJson  AnyCircuitElement[]
 * @returns {{ errors: Array, warnings: Array }}
 */
export function runDRC(circuitJson) {
  if (!Array.isArray(circuitJson) || circuitJson.length === 0) {
    return { errors: [], warnings: [] }
  }

  const board      = circuitJson.find((e) => e?.type === 'pcb_board') ?? null
  const traces     = circuitJson.filter((e) => e?.type === 'pcb_trace')
  const vias       = circuitJson.filter((e) => e?.type === 'pcb_via' || e?.type === 'pcb_hole')
  const pads       = circuitJson.filter((e) => e?.type === 'pcb_smtpad' || e?.type === 'pcb_plated_hole')
  const silkTexts  = circuitJson.filter((e) => e?.type === 'pcb_silkscreen_text' || e?.type === 'pcb_text')

  const rules = getRules(board)

  const errors = [
    ...checkTraceWidth(traces, rules),
    ...checkViaClearance(vias, rules),
    ...checkDrillSpacing(vias, rules),
    ...checkDanglingTraces(traces, pads),
    ...checkNetShorts(traces, pads),
  ]

  const warnings = [
    ...checkSilkOnPad(silkTexts, pads, rules),
    ...checkCopperToEdge(traces, pads, vias, board, rules),
  ]

  return { errors, warnings }
}

// Also export the DEFAULT_RULES for use in settings UIs / tests.
export { DEFAULT_RULES }
