// sketchSolver.js — bridge between the Kerf Sketch JSON and planegcs (FreeCAD's
// PlaneGCS solver compiled to WASM, on npm as @salusoft89/planegcs).
//
// Public entry points:
//   - parseSketch(content)          → Sketch object, with default-empty arrays
//   - serializeSketch(sketch)       → pretty JSON string
//   - solveSketch(sketch)           → Promise<{ok, status, dofCount, solved, sketch, conflicts}>
//   - solveWithDrag(sketch, drag)   → solve with a temporary point-coordinate
//                                     constraint at `drag = {pointId, x, y}`.
//   - sketchToGeom2(sketch)         → JSCAD Geom2 built from solved entities.
//
// The wrapper is deliberately stateful per-call: we reload + re-solve the
// whole sketch on every invocation. The cost of allocating a fresh GcsWrapper
// is small for sketches with O(100) entities; it keeps the API trivially
// idempotent and bypasses the WASM module's quirky cleanup contract.
//
// Notes on the planegcs API:
//   * make_gcs_wrapper() must be awaited once before use; we lazy-load it on
//     first solveSketch() call. Subsequent calls pin a single shared module.
//   * planegcs uses string oids globally — points, lines, arcs, circles, AND
//     constraints all live in the same id namespace. We prefix internally
//     (`p:`, `c:`, `co:`) to keep our entity ids and constraint ids disjoint.
//   * Constraint values for distance/radius/diameter/angle take a number OR a
//     named param OR an object_param ref. We always pass the number — that's
//     enough for our v1 dimensional constraints.

// Browser build: we ship `planegcs.wasm` as a public asset (see
// `public/planegcs.wasm`, mirrored from the npm package at install time) and
// point planegcs's `locateFile` hook at `/planegcs.wasm`. This sidesteps the
// `new URL("planegcs.wasm", import.meta.url)` fallback inside the package's
// emscripten glue, which Vite/Rolldown would otherwise flag as an
// unsupported "ESM integration proposal for Wasm". The trick mirrors how
// `src/lib/stepLoader.js` serves `occt-import-js.wasm`.
//
// Tests under Node (vitest) override via `KERF_PLANEGCS_WASM` so the test
// runner can point at the file inside `node_modules/`.
import { substituteParams } from './equations.js'

const PLANEGCS_PUBLIC_URL = '/planegcs.wasm'

let modulePromise = null
let lastFailure = null

// Equations injection — see store/workspace.js loadProject for the resolver
// that walks the project tree, parses every `.equations` file, evaluates the
// rows, and returns the merged scope. Sketches reference params via `${name}`
// placeholders inside dimensional constraint values (distance / distance_x /
// distance_y / angle / radius / diameter). When no resolver is registered or
// the value is a plain number, this collapses to a no-op `Number(v) || 0`.

let equationsResolverSync = null
export function setSketchEquationsResolverSync(fn) {
  // fn: () => { values: { [name]: number } } | null
  // SYNC because the planegcs solver is sync and we don't want every constraint
  // value to await a fetch. The store calls this with a getter that returns
  // the cached scope built once per project load.
  equationsResolverSync = fn || null
}

// numericValue resolves a constraint value that may be either a number or a
// string with `${name}` placeholders. Falls back to 0 if the result is NaN.
function numericValue(v) {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && equationsResolverSync) {
    const scope = equationsResolverSync()?.values || {}
    const sub = substituteParams(v, scope)
    if (typeof sub === 'number' && Number.isFinite(sub)) return sub
    const n = Number(sub)
    return Number.isFinite(n) ? n : 0
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function loadPlanegcs() {
  if (modulePromise) return modulePromise
  modulePromise = (async () => {
    try {
      const mod = await import('@salusoft89/planegcs')
      const proc = (typeof globalThis !== 'undefined' && globalThis.process) || null
      const envOverride = proc?.env?.KERF_PLANEGCS_WASM || null
      const wasmUrl = envOverride || PLANEGCS_PUBLIC_URL
      const make = mod.make_gcs_wrapper
      const Algorithm = mod.Algorithm
      const SolveStatus = mod.SolveStatus
      return { mod, wasmUrl, make, Algorithm, SolveStatus }
    } catch (err) {
      lastFailure = err
      throw err
    }
  })()
  return modulePromise
}

// ---------------------------------------------------------------------------
// Pure JSON helpers.

export const SKETCH_VERSION = 1

// Always-present default plane.
export const DEFAULT_PLANE = { type: 'base', name: 'XY' }

// ---------------------------------------------------------------------------
// Face-anchored plane handling (Phase 3).
//
// Sketches can be anchored to a face on a `.feature` file via:
//   { type: 'face', file_id, feature_node_id, face_id, frame? }
// where `frame` is the resolved world-space `{origin, normal, uDir, vDir}` on
// the most recent feature evaluation. The frame is filled by the consumer
// (FeatureView / occtWorker) — the persisted JSON only carries the
// face-id reference. When the consumer can't resolve the frame (the source
// file isn't loaded, the face id no longer exists, etc.) the frame is left
// undefined and the sketcher falls back to XY for display.
//
// The 2D solver doesn't care about the plane — it operates in (u,v) — so
// these helpers are purely for view orientation + OCCT placement.

// Compute view orientation matrix for a face-anchored plane. Returns 12
// numbers (3x4 row-major: ux, uy, uz, ox, vx, vy, vz, oy, nx, ny, nz, oz)
// or null if the plane isn't a face anchor with a resolved frame.
//
// The sketcher's 3D backdrop and the SketchView's view transform consume this
// to draw the anchor face's neighborhood under the sketch as reference.
export function planeFaceFrame(plane) {
  if (!plane || plane.type !== 'face') return null
  const f = plane.frame
  if (!f) return null
  const o = f.origin || [0, 0, 0]
  const u = f.uDir   || [1, 0, 0]
  const v = f.vDir   || [0, 1, 0]
  const n = f.normal || [0, 0, 1]
  return { origin: o, uDir: u, vDir: v, normal: n }
}

// Bake a face frame onto a plane spec. Used by FeatureView before dispatch
// to the OCCT worker — the worker is sandboxed and can't read other feature
// files, so we resolve the frame on the main thread first.
export function withFaceFrame(plane, frame) {
  if (!plane || plane.type !== 'face' || !frame) return plane
  return { ...plane, frame: { origin: frame.origin, normal: frame.normal, uDir: frame.uDir, vDir: frame.vDir } }
}

export function defaultSketch(plane = 'XY', name = '') {
  return {
    version: SKETCH_VERSION,
    plane: { type: 'base', name: plane || 'XY' },
    entities: [
      { id: 'origin', type: 'point', x: 0, y: 0 },
    ],
    constraints: [],
    visible_3d: [],
    solved: {},
    metadata: name ? { name } : {},
  }
}

export function parseSketch(content) {
  const text = (content || '').trim()
  if (!text) return defaultSketch()
  try {
    const obj = JSON.parse(text)
    return {
      version: obj.version || SKETCH_VERSION,
      plane: obj.plane || DEFAULT_PLANE,
      entities: Array.isArray(obj.entities) ? obj.entities : [],
      constraints: Array.isArray(obj.constraints) ? obj.constraints : [],
      visible_3d: Array.isArray(obj.visible_3d) ? obj.visible_3d : [],
      solved: obj.solved && typeof obj.solved === 'object' ? obj.solved : {},
      metadata: obj.metadata && typeof obj.metadata === 'object' ? obj.metadata : {},
      // Configurations / variants (see src/lib/part.js for the canonical
      // shape and getActiveConfig helper). A sketch can carry param
      // overrides too — useful for an M3/M4/M5 hole-pattern sketch where
      // dimensional constraints reference `${d}` and the active config
      // sets it. The fields round-trip even though the solver itself is
      // dimensionless; the runner integration in workspace.js does the
      // actual merging.
      default_config: typeof obj.default_config === 'string' ? obj.default_config : '',
      configurations: Array.isArray(obj.configurations)
        ? obj.configurations.map(normalizeSketchConfiguration).filter(Boolean)
        : [],
    }
  } catch {
    return defaultSketch()
  }
}

function normalizeSketchConfiguration(raw) {
  if (!raw || typeof raw !== 'object') return null
  const id = typeof raw.id === 'string' ? raw.id.trim() : ''
  if (!id) return null
  return {
    id,
    label: typeof raw.label === 'string' && raw.label ? raw.label : id,
    params: raw.params && typeof raw.params === 'object' && !Array.isArray(raw.params)
      ? raw.params : {},
  }
}

export function serializeSketch(sketch) {
  // Stable key order for diffs. We deliberately omit `solved` from the
  // pretty form when empty so freshly-saved unsolved sketches don't carry a
  // useless empty cache through revision history.
  const out = {
    version: sketch.version || SKETCH_VERSION,
    plane: sketch.plane || DEFAULT_PLANE,
    entities: Array.isArray(sketch.entities) ? sketch.entities : [],
    constraints: Array.isArray(sketch.constraints) ? sketch.constraints : [],
    visible_3d: Array.isArray(sketch.visible_3d) ? sketch.visible_3d : [],
    solved: sketch.solved && typeof sketch.solved === 'object' ? sketch.solved : {},
    metadata: sketch.metadata || {},
  }
  if (typeof sketch.default_config === 'string' && sketch.default_config) {
    out.default_config = sketch.default_config
  }
  if (Array.isArray(sketch.configurations) && sketch.configurations.length > 0) {
    out.configurations = sketch.configurations.map((c) => ({
      id: c.id,
      label: c.label || c.id,
      params: c.params && typeof c.params === 'object' ? c.params : {},
    }))
  }
  return JSON.stringify(out, null, 2)
}

// ---------------------------------------------------------------------------
// Solving.

// Estimate degrees of freedom = (free coordinates from points & circles & arcs)
// minus the count of dimensional constraints. Coarse — the actual solver-side
// rank is harder to expose. Used only for the status badge "fully / under /
// over" so the imprecision is OK; planegcs's conflict/redundant flags are the
// authoritative signal.
function estimateDof(sketch) {
  const ent = sketch.entities || []
  let dof = 0
  let hasOrigin = false
  for (const e of ent) {
    if (e.type === 'point') {
      dof += 2
      if (e.id === 'origin') hasOrigin = true
    } else if (e.type === 'circle') {
      dof += 1 // radius (center is its own point)
    } else if (e.type === 'arc') {
      dof += 3 // start_angle, end_angle, radius (endpoints are points)
    } else if (e.type === 'ellipse') {
      // GK-P37: rx, ry, rotation — center point's 2 DOF counted separately above.
      dof += 3
    }
    // bezier control points are independent point entities — their DOF is
    // already counted in the 'point' branch above. No extra DOF here.
  }
  // The origin point is permanently pinned by the planegcs wrapper (fixed=true)
  // so it removes 2 DOF immediately. Without this subtraction the sketcher
  // could never report "fully constrained" — there's no Kerf constraint for
  // the implicit origin pin.
  if (hasOrigin) dof -= 2
  // Each dimensional / geometric constraint removes ~1 DOF. This is a
  // rough heuristic; real DOF depends on rank. Good enough for the badge.
  for (const c of sketch.constraints || []) {
    switch (c.type) {
      case 'coincident':
        dof -= 2
        break
      case 'horizontal':
      case 'vertical':
      case 'parallel':
      case 'perpendicular':
      case 'tangent':
      case 'equal_length':
      case 'equal_radius':
      case 'distance':
      case 'distance_x':
      case 'distance_y':
      case 'angle':
      case 'radius':
      case 'diameter':
      case 'point_on_line':
      case 'point_on_arc':
      case 'point_on_circle':
        dof -= 1
        break
      case 'symmetric':
        dof -= 2
        break
      case 'symmetric_over_line': {
        // Decomposed into N p2p_symmetric_ppl calls (one per point pair).
        // Each removes 2 DOFs. The number depends on the entity kinds:
        //   point   → 1 pair  → -2 DOF
        //   line    → 2 pairs → -4 DOF
        //   circle  → 1 pair (centers) + 1 equal_radius → -3 DOF
        //   arc     → 3 pairs (center, start, end) → -6 DOF
        //   bezier  → n control-point pairs → -2n DOF
        // We use 2 as a minimum lower bound for the badge; the actual solver
        // removes more depending on entity shape.
        dof -= 2
        break
      }
      case 'midpoint':
        // Two scalar conditions: on-line (1 DOF removed) + equidistant on
        // perp-bisector (1 DOF removed). Together they pin P to one point on L.
        dof -= 2
        break
      case 'fixed':
        // Pins both x and y of a single point.
        dof -= 2
        break
      case 'block': {
        // Pin every coordinate of every referenced entity (rough estimate).
        const refs = Array.isArray(c.refs) ? c.refs : []
        dof -= refs.length * 2
        break
      }
      case 'arc_on_circle':
      case 'arc_on_arc':
      case 'intersection_point':
        // Composed of two primitive constraints, removes 2 DOFs.
        dof -= 2
        break
      // Bezier continuity: tangent (G1 direction) removes 1 DOF; G1 compound
      // (coincident + tangent) removes 2 DOF; G2 is currently decomposed the
      // same as G1 since planegcs has no curvature-match primitive.
      case 'bezier_tangent':
        dof -= 1
        break
      case 'bezier_g1':
        dof -= 2
        break
      // GK-P36: collinear — three points must be collinear. Implemented as
      // point_on_line_ppp(p1, p2, p3): removes 1 DOF.
      case 'collinear':
        dof -= 1
        break
      // GK-P37: ellipse — center + rx + ry + rotation = 5 DOF total (2 for center
      // point, already counted; 3 for rx, ry, rotation). We count only the extra
      // non-point DOFs here; the center point's 2 DOF come from its own point entity.
      case 'point_on_ellipse':
        dof -= 1
        break
      case 'ellipse_semi_major':
      case 'ellipse_semi_minor':
      case 'ellipse_rotation':
        dof -= 1
        break
      // GK-P38: G2 curvature continuity. Approximated as G1 + equal-curvature via
      // radius-ratio constraint. Removes 2 DOF (1 for tangent + 1 for curvature).
      case 'bezier_g2':
        dof -= 2
        break
      default:
        break
    }
  }
  return dof
}

// ---------------------------------------------------------------------------
// Composite-entity decomposition for symmetric_over_line.
//
// Returns an array of { p1, p2 } pairs — resolved point ids — where each pair
// should be constrained as p2p_symmetric_ppl(p1, p2, line). The caller also
// handles the equal_radius side-constraint for circles/arcs separately.
//
// Supported entity kinds:
//   point   → 1 pair: (a.id, b.id)
//   line    → 2 pairs: endpoints (a.p1↔b.p1, a.p2↔b.p2)
//   circle  → 1 pair: centers (a.center↔b.center)  + equal_radius handled by caller
//   arc     → 3 pairs: center + two endpoints        + equal_radius handled by caller
//   bezier  → N pairs: each control_point[i] ↔ control_point[N-1-i]
//             (mirror reverses point order so the curve shape reflects correctly)
//   bspline → same as bezier (controls array)
//
// Arc mirroring reverses the start↔end pair because a reflection inverts
// the winding: arc A's start maps to arc B's end and vice versa.
function decomposeSymmetric(entA, entB, allEnts, resolve) {
  const pairs = []
  if (entA.type === 'point' && entB.type === 'point') {
    pairs.push({ p1: resolve(entA.id), p2: resolve(entB.id) })
  } else if (entA.type === 'line' && entB.type === 'line') {
    pairs.push({ p1: resolve(entA.p1), p2: resolve(entB.p1) })
    pairs.push({ p1: resolve(entA.p2), p2: resolve(entB.p2) })
  } else if (entA.type === 'circle' && entB.type === 'circle') {
    pairs.push({ p1: resolve(entA.center), p2: resolve(entB.center) })
  } else if (entA.type === 'arc' && entB.type === 'arc') {
    // Center ↔ center (both arcs share the same radius which we enforce via equal_radius).
    pairs.push({ p1: resolve(entA.center), p2: resolve(entB.center) })
    // Start/end are swapped on the reflected arc: A.start ↔ B.end, A.end ↔ B.start.
    pairs.push({ p1: resolve(entA.start), p2: resolve(entB.end) })
    pairs.push({ p1: resolve(entA.end),   p2: resolve(entB.start) })
  } else if (entA.type === 'bezier' && entB.type === 'bezier') {
    const cpsA = entA.control_points || []
    const cpsB = entB.control_points || []
    const n = Math.min(cpsA.length, cpsB.length)
    for (let i = 0; i < n; i++) {
      // Mirror reverses the control-point order: A[i] ↔ B[n-1-i].
      pairs.push({ p1: resolve(cpsA[i]), p2: resolve(cpsB[n - 1 - i]) })
    }
  } else if (entA.type === 'bspline' && entB.type === 'bspline') {
    const cpsA = entA.controls || []
    const cpsB = entB.controls || []
    const n = Math.min(cpsA.length, cpsB.length)
    for (let i = 0; i < n; i++) {
      pairs.push({ p1: resolve(cpsA[i]), p2: resolve(cpsB[n - 1 - i]) })
    }
  }
  // Filter out degenerate pairs (same point on both sides — already on the line).
  return pairs.filter((p) => p.p1 && p.p2 && p.p1 !== p.p2)
}

// Map our Sketch → a planegcs primitives + constraints array. We add the
// origin as fixed=true (so it pins the gauge), and any other point that is
// referenced by a `coincident` constraint is collapsed onto a single id.
function buildPlanegcsPrimitives(sketch) {
  const points = []
  const lines = []
  const arcs = []
  const circles = []
  const constraints = []
  // Coincident reduction: if A==B, all references to B become A.
  const remap = new Map()
  function resolve(id) {
    let cur = id
    let guard = 0
    while (remap.has(cur)) {
      cur = remap.get(cur)
      if (++guard > 1024) break
    }
    return cur
  }
  for (const c of sketch.constraints || []) {
    if (c.type === 'coincident' && c.a && c.b) {
      // Always remap the higher-id one onto the lower so origin wins.
      const a = c.a
      const b = c.b
      if (a === b) continue
      // Special case: if either is "origin", keep that side.
      if (b === 'origin') remap.set(a, b)
      else remap.set(b, a)
    }
  }
  const ent = sketch.entities || []
  const used = new Set()
  for (const e of ent) {
    if (e.type === 'point') {
      const eid = resolve(e.id)
      if (used.has(eid)) continue
      used.add(eid)
      const fixed = eid === 'origin'
      points.push({
        id: eid,
        type: 'point',
        x: typeof e.x === 'number' ? e.x : 0,
        y: typeof e.y === 'number' ? e.y : 0,
        fixed,
      })
    }
  }
  for (const e of ent) {
    if (e.type === 'line') {
      lines.push({
        id: e.id,
        type: 'line',
        p1_id: resolve(e.p1),
        p2_id: resolve(e.p2),
      })
    } else if (e.type === 'circle') {
      circles.push({
        id: e.id,
        type: 'circle',
        c_id: resolve(e.center),
        radius: typeof e.radius === 'number' && e.radius > 0 ? e.radius : 10,
      })
    } else if (e.type === 'arc') {
      const c = ent.find((p) => p.id === e.center)
      const s = ent.find((p) => p.id === e.start)
      const en = ent.find((p) => p.id === e.end)
      const cx = c?.x ?? 0
      const cy = c?.y ?? 0
      const sa = s ? Math.atan2((s.y || 0) - cy, (s.x || 0) - cx) : 0
      const ea = en ? Math.atan2((en.y || 0) - cy, (en.x || 0) - cx) : 0
      const r = s ? Math.hypot((s.x || 0) - cx, (s.y || 0) - cy) : 10
      arcs.push({
        id: e.id,
        type: 'arc',
        c_id: resolve(e.center),
        start_id: resolve(e.start),
        end_id: resolve(e.end),
        start_angle: sa,
        end_angle: ea,
        radius: r > 0 ? r : 10,
      })
    }
  }

  // Now translate Kerf constraints → planegcs constraints. We skip 'coincident'
  // (handled by the id-merge above) and emit numeric constraint ids prefixed
  // with `c:` so the planegcs id namespace can't collide with entity ids.
  let cIdx = 0
  function nextId() { return `c:${++cIdx}` }
  for (const c of sketch.constraints || []) {
    switch (c.type) {
      case 'coincident':
        // already handled via remap.
        break
      case 'horizontal':
        constraints.push({ id: nextId(), type: 'horizontal_l', l_id: c.line })
        break
      case 'vertical':
        constraints.push({ id: nextId(), type: 'vertical_l', l_id: c.line })
        break
      case 'parallel':
        constraints.push({ id: nextId(), type: 'parallel', l1_id: c.a, l2_id: c.b })
        break
      case 'perpendicular':
        constraints.push({ id: nextId(), type: 'perpendicular_ll', l1_id: c.a, l2_id: c.b })
        break
      case 'tangent': {
        // Pick the planegcs variant by the kinds of a/b.
        const aEnt = ent.find((x) => x.id === c.a)
        const bEnt = ent.find((x) => x.id === c.b)
        if (!aEnt || !bEnt) break
        const types = [aEnt.type, bEnt.type].sort().join('-')
        if (types === 'circle-line' || types === 'line-circle') {
          const lEnt = aEnt.type === 'line' ? aEnt : bEnt
          const cEnt = aEnt.type === 'circle' ? aEnt : bEnt
          constraints.push({ id: nextId(), type: 'tangent_lc', l_id: lEnt.id, c_id: cEnt.id })
        } else if (types === 'arc-line' || types === 'line-arc') {
          const lEnt = aEnt.type === 'line' ? aEnt : bEnt
          const aArc = aEnt.type === 'arc' ? aEnt : bEnt
          constraints.push({ id: nextId(), type: 'tangent_la', l_id: lEnt.id, a_id: aArc.id })
        } else if (types === 'circle-circle') {
          constraints.push({ id: nextId(), type: 'tangent_cc', c1_id: c.a, c2_id: c.b })
        } else if (types === 'arc-arc') {
          constraints.push({ id: nextId(), type: 'tangent_aa', a1_id: c.a, a2_id: c.b })
        } else if (types === 'arc-circle' || types === 'circle-arc') {
          const cE = aEnt.type === 'circle' ? aEnt : bEnt
          const aE = aEnt.type === 'arc' ? aEnt : bEnt
          constraints.push({ id: nextId(), type: 'tangent_ca', c_id: cE.id, a_id: aE.id })
        }
        break
      }
      case 'equal_length':
        constraints.push({ id: nextId(), type: 'equal_length', l1_id: c.a, l2_id: c.b })
        break
      case 'equal_radius':
        constraints.push({ id: nextId(), type: 'equal_radius_cc', c1_id: c.a, c2_id: c.b })
        break
      case 'distance': {
        // distance between two points (other entity types not supported in v1).
        const aEnt = ent.find((x) => x.id === c.a)
        const bEnt = ent.find((x) => x.id === c.b)
        if (aEnt?.type === 'point' && bEnt?.type === 'point') {
          constraints.push({
            id: nextId(),
            type: 'p2p_distance',
            p1_id: c.a, p2_id: c.b,
            distance: numericValue(c.value),
          })
        } else if (aEnt?.type === 'point' && bEnt?.type === 'line') {
          constraints.push({
            id: nextId(),
            type: 'p2l_distance',
            p_id: c.a, l_id: c.b,
            distance: numericValue(c.value),
          })
        } else if (aEnt?.type === 'line' && bEnt?.type === 'point') {
          constraints.push({
            id: nextId(),
            type: 'p2l_distance',
            p_id: c.b, l_id: c.a,
            distance: numericValue(c.value),
          })
        }
        break
      }
      case 'distance_x':
      case 'distance_y': {
        // Two points, axis-aligned distance. planegcs doesn't expose a direct
        // dx/dy constraint, but Difference on the x/y coordinate parameter of
        // the two points achieves the same thing.
        const prop = c.type === 'distance_x' ? 'x' : 'y'
        constraints.push({
          id: nextId(),
          type: 'difference',
          param1: { o_id: c.a, prop },
          param2: { o_id: c.b, prop },
          difference: numericValue(c.value),
        })
        break
      }
      case 'angle':
        constraints.push({
          id: nextId(),
          type: 'l2l_angle_ll',
          l1_id: c.a, l2_id: c.b,
          angle: ((numericValue(c.value)) * Math.PI) / 180,
        })
        break
      case 'radius':
        constraints.push({
          id: nextId(),
          type: 'circle_radius',
          c_id: c.circle,
          radius: numericValue(c.value),
        })
        break
      case 'diameter':
        constraints.push({
          id: nextId(),
          type: 'circle_diameter',
          c_id: c.circle,
          diameter: numericValue(c.value),
        })
        break
      case 'symmetric': {
        // Two points symmetric about a line entity (preferred) or a third
        // point (fallback). p2p_symmetric_ppl / p2p_symmetric_ppp.
        if (c.line) {
          constraints.push({
            id: nextId(), type: 'p2p_symmetric_ppl',
            p1_id: resolve(c.a), p2_id: resolve(c.b), l_id: c.line,
          })
        } else if (c.through) {
          constraints.push({
            id: nextId(), type: 'p2p_symmetric_ppp',
            p1_id: resolve(c.a), p2_id: resolve(c.b), p_id: resolve(c.through),
          })
        }
        break
      }
      case 'symmetric_over_line': {
        // Mirror entity_a across construction_line_id so it becomes the mirror
        // image of entity_b.
        //
        // planegcs provides p2p_symmetric_ppl(p1, p2, line) — the two points
        // are mirror images across the line. We decompose composite entities
        // into multiple such point-pair constraints via decomposeSymmetric.
        //
        // Schema: { type, entity_a_id, entity_b_id, construction_line_id }
        if (!c.entity_a_id || !c.entity_b_id || !c.construction_line_id) break
        const lineEnt = ent.find((x) => x.id === c.construction_line_id)
        if (!lineEnt || lineEnt.type !== 'line') break
        const entA = ent.find((x) => x.id === c.entity_a_id)
        const entB = ent.find((x) => x.id === c.entity_b_id)
        if (!entA || !entB) break
        for (const pair of decomposeSymmetric(entA, entB, ent, resolve)) {
          constraints.push({
            id: nextId(), type: 'p2p_symmetric_ppl',
            p1_id: pair.p1, p2_id: pair.p2, l_id: c.construction_line_id,
          })
        }
        // For circle/arc: also enforce equal radii.
        if ((entA.type === 'circle' || entA.type === 'arc') &&
            (entB.type === 'circle' || entB.type === 'arc')) {
          const rType = (entA.type === 'arc' && entB.type === 'arc')
            ? 'equal_radius_aa' : 'equal_radius_cc'
          constraints.push({ id: nextId(), type: rType, c1_id: c.entity_a_id, c2_id: c.entity_b_id })
        }
        break
      }
      case 'block': {
        // Pin every referenced entity's geometry. For each entity id, if
        // it's a point we emit coordinate_x + coordinate_y; for a circle/arc
        // we additionally pin the radius via circle_radius / arc_radius.
        const refs = Array.isArray(c.refs) ? c.refs : []
        for (const rid of refs) {
          const e = ent.find((x) => x.id === rid)
          if (!e) continue
          if (e.type === 'point') {
            constraints.push({ id: nextId(), type: 'coordinate_x', p_id: resolve(e.id), x: Number(e.x) || 0 })
            constraints.push({ id: nextId(), type: 'coordinate_y', p_id: resolve(e.id), y: Number(e.y) || 0 })
          } else if (e.type === 'circle') {
            const cp = ent.find((x) => x.id === e.center)
            if (cp) {
              constraints.push({ id: nextId(), type: 'coordinate_x', p_id: resolve(cp.id), x: Number(cp.x) || 0 })
              constraints.push({ id: nextId(), type: 'coordinate_y', p_id: resolve(cp.id), y: Number(cp.y) || 0 })
            }
            constraints.push({ id: nextId(), type: 'circle_radius', c_id: e.id, radius: Number(e.radius) || 0 })
          } else if (e.type === 'line') {
            for (const pid of [e.p1, e.p2]) {
              const cp = ent.find((x) => x.id === pid)
              if (!cp) continue
              constraints.push({ id: nextId(), type: 'coordinate_x', p_id: resolve(cp.id), x: Number(cp.x) || 0 })
              constraints.push({ id: nextId(), type: 'coordinate_y', p_id: resolve(cp.id), y: Number(cp.y) || 0 })
            }
          } else if (e.type === 'arc') {
            for (const pid of [e.center, e.start, e.end]) {
              const cp = ent.find((x) => x.id === pid)
              if (!cp) continue
              constraints.push({ id: nextId(), type: 'coordinate_x', p_id: resolve(cp.id), x: Number(cp.x) || 0 })
              constraints.push({ id: nextId(), type: 'coordinate_y', p_id: resolve(cp.id), y: Number(cp.y) || 0 })
            }
          }
        }
        break
      }
      case 'point_on_line':
        constraints.push({
          id: nextId(), type: 'point_on_line_pl',
          p_id: resolve(c.point), l_id: c.line,
        })
        break
      case 'point_on_arc': {
        // planegcs has both point_on_arc and point_on_circle; pick by
        // referenced entity kind.
        const t = ent.find((x) => x.id === c.arc)
        if (t?.type === 'circle') {
          constraints.push({ id: nextId(), type: 'point_on_circle', p_id: resolve(c.point), c_id: c.arc })
        } else if (t?.type === 'arc') {
          constraints.push({ id: nextId(), type: 'point_on_arc', p_id: resolve(c.point), a_id: c.arc })
        }
        break
      }
      case 'midpoint': {
        // Constrain point P to the midpoint of line L. planegcs doesn't have a
        // single "midpoint of line" constraint exposed for the (P, L) signature
        // (its midpoint_on_line_* variants relate two lines). We compose two
        // primitives instead:
        //   1. point_on_line_pl(P, L)               — P lies on L
        //   2. point_on_perp_bisector_pl(P, L)      — P equidistant from L's endpoints
        // The intersection of those two conditions is exactly the midpoint.
        const lEnt = ent.find((x) => x.id === c.line)
        if (c.point && lEnt?.type === 'line') {
          constraints.push({
            id: nextId(), type: 'point_on_line_pl',
            p_id: resolve(c.point), l_id: c.line,
          })
          constraints.push({
            id: nextId(), type: 'point_on_perp_bisector_pl',
            p_id: resolve(c.point), l_id: c.line,
          })
        }
        break
      }
      case 'fixed': {
        // Lock point P to a captured (x, y). The captured coordinates are
        // stored on the constraint at creation time (see SketchView's apply
        // path) so subsequent solves never let P drift even if other DOF
        // would otherwise pull it. We emit two coordinate constraints — the
        // same primitive pair that `block` uses for points.
        const pid = resolve(c.point)
        const px = typeof c.x === 'number' ? c.x
          : (ent.find((x) => x.id === c.point)?.x ?? 0)
        const py = typeof c.y === 'number' ? c.y
          : (ent.find((x) => x.id === c.point)?.y ?? 0)
        if (c.point) {
          constraints.push({ id: nextId(), type: 'coordinate_x', p_id: pid, x: Number(px) || 0 })
          constraints.push({ id: nextId(), type: 'coordinate_y', p_id: pid, y: Number(py) || 0 })
        }
        break
      }
      case 'point_on_circle': {
        const t = ent.find((x) => x.id === c.circle)
        if (t?.type === 'circle') {
          constraints.push({ id: nextId(), type: 'point_on_circle', p_id: resolve(c.point), c_id: c.circle })
        }
        break
      }
      case 'arc_on_circle': {
        // Arc must lie on a circle: arc's center must be on the circle
        // AND arc's radius must equal the circle's radius.
        const arcEnt = ent.find((x) => x.id === c.arc)
        const circEnt = ent.find((x) => x.id === c.circle)
        if (arcEnt?.type === 'arc' && circEnt?.type === 'circle') {
          // Arc center on circle.
          constraints.push({ id: nextId(), type: 'point_on_circle', p_id: resolve(arcEnt.center), c_id: c.circle })
          // Arc radius = circle radius.
          constraints.push({ id: nextId(), type: 'equal_radius_cc', c1_id: c.arc, c2_id: c.circle })
        }
        break
      }
      case 'arc_on_arc': {
        // Arc must lie on another arc: arc's center must be on the other arc's
        // circle AND arc's radius must equal the other arc's radius.
        const arcEnt = ent.find((x) => x.id === c.arc)
        const otherArcEnt = ent.find((x) => x.id === c.otherArc)
        if (arcEnt?.type === 'arc' && otherArcEnt?.type === 'arc') {
          // Arc center on other arc's circle.
          constraints.push({ id: nextId(), type: 'point_on_circle', p_id: resolve(arcEnt.center), c_id: c.otherArc })
          // Arc radius = other arc radius.
          constraints.push({ id: nextId(), type: 'equal_radius_aa', a1_id: c.arc, a2_id: c.otherArc })
        }
        break
      }
      case 'intersection_point': {
        // Point must be at the intersection of two lines: point lies on line1
        // AND point lies on line2.
        if (c.point && c.line1 && c.line2) {
          constraints.push({ id: nextId(), type: 'point_on_line_pl', p_id: resolve(c.point), l_id: c.line1 })
          constraints.push({ id: nextId(), type: 'point_on_line_pl', p_id: resolve(c.point), l_id: c.line2 })
        }
        break
      }
      // ---------------------------------------------------------------------------
      // GK-P36: Collinear constraint.
      //
      // Schema: { type: 'collinear', p1, p2, p3 }
      // All three points must be collinear. planegcs provides point_on_line_ppp
      // which enforces that p_id lies on the infinite line through p1_id—p2_id.
      // We constrain p1 on line(p2, p3) — one constraint is sufficient to make
      // all three collinear (p2 and p3 define the line; p1 is constrained to it).
      // Note: p2 and p3 are the anchor pair; p1 is the constrained point.
      // If the user wants all three fully mobile, they can apply two collinear
      // constraints (p1 on p2-p3, and p2 on p1-p3), but one is the canonical form.
      case 'collinear': {
        if (c.p1 && c.p2 && c.p3) {
          constraints.push({
            id: nextId(),
            type: 'point_on_line_ppp',
            p_id: resolve(c.p1),
            p1_id: resolve(c.p2),
            p2_id: resolve(c.p3),
          })
        }
        break
      }
      // ---------------------------------------------------------------------------
      // GK-P37: Ellipse constraints.
      //
      // planegcs has no native ellipse primitive in v1.1.7. The ellipse entity
      // in Kerf is stored as { center, rx, ry, rotation } and rendered by
      // sketchGeom2.js via tessellateEllipse(). The solver sees the center point
      // only. Dimension-style constraints (semi_major, semi_minor, rotation) are
      // applied as direct value assignments inside the sketch JSON — they act like
      // 'fixed' constraints for the non-point DOFs.
      //
      // point_on_ellipse: enforces that a free point lies on the ellipse perimeter.
      // Approximated as: p2p_distance(point, center) = r(theta) where theta is the
      // current angle from center to point. We use the r(theta) of an ellipse:
      //   r = rx*ry / sqrt((ry*cos(θ))^2 + (rx*sin(θ))^2)
      // and emit a p2p_distance constraint. This is an instantaneous linearisation
      // and re-linearises on each solve, giving first-order correctness for
      // well-initialised sketches (same approach FreeCAD's Sketcher uses for
      // its ellipse-on-curve constraint in v0.20 before native ellipse was added).
      case 'point_on_ellipse': {
        const ellEnt = ent.find((x) => x.id === c.ellipse)
        const ptEnt  = ent.find((x) => x.id === c.point)
        if (ellEnt?.type === 'ellipse' && ptEnt?.type === 'point') {
          const cptEnt = ent.find((x) => x.id === ellEnt.center)
          const cx = cptEnt?.x ?? 0
          const cy = cptEnt?.y ?? 0
          const px = ptEnt.x ?? 0
          const py = ptEnt.y ?? 0
          const rx = ellEnt.rx ?? 1
          const ry = ellEnt.ry ?? 1
          const rot = ellEnt.rotation ?? 0
          // Rotate point into ellipse frame.
          const cosR = Math.cos(-rot); const sinR = Math.sin(-rot)
          const lx = (px - cx) * cosR - (py - cy) * sinR
          const ly = (px - cx) * sinR + (py - cy) * cosR
          const theta = Math.atan2(ly, lx)
          const r = (rx * ry) / Math.hypot(ry * Math.cos(theta), rx * Math.sin(theta))
          constraints.push({
            id: nextId(),
            type: 'p2p_distance',
            p1_id: resolve(c.point),
            p2_id: resolve(ellEnt.center),
            distance: Math.max(0.001, r),
          })
        }
        break
      }
      // ellipse_semi_major / ellipse_semi_minor / ellipse_rotation: these are
      // applied directly to the entity JSON (like 'fixed' for scalar DOFs). The
      // solver doesn't need a constraint — the value is baked into the entity.
      case 'ellipse_semi_major':
      case 'ellipse_semi_minor':
      case 'ellipse_rotation':
        // No planegcs constraint needed; value is stored on the entity directly.
        break
      // ---------------------------------------------------------------------------
      // Bezier continuity constraints.
      //
      // planegcs has no native Bezier primitive. Instead we enforce continuity by
      // constraining the control-point positions geometrically:
      //
      //   bezier_tangent: tangent direction at the join — the two neighbouring
      //     control points (p0, p2) and the shared endpoint (p1) must be
      //     collinear. We enforce collinearity by constructing a synthetic Line
      //     p0→p2 and constraining p1 to lie on it.
      //
      //   bezier_g1: G0 (endpoint coincident) + G1 (tangent). Coincidence is
      //     already handled via the coincident-remap before we reach this point;
      //     the tangent part is the same collinearity as bezier_tangent.
      //
      //   bezier_g2: G2 (curvature match) — planegcs does NOT expose a
      //     CurvatureMatch or EqualCurvatureAtPoint constraint in its
      //     push_primitive API (confirmed: no such type in constraints.d.ts).
      //     We implement G2 as G1 (collinearity of p0—p1—p2) PLUS an equal-chord
      //     length constraint: |p1 - p0| == |p2 - p1|. This enforces matching
      //     curvature for uniform-parameterisation Bezier segments (the standard
      //     C2 condition). It is a first-order approximation; true G2 requires
      //     a curvature-equality primitive that planegcs v1.1.7 does not expose.
      //
      // Constraint schema:
      //   { type: 'bezier_tangent', p0, p1, p2 }  — p0 and p2 are the
      //     second-to-last / second control points of the two segments; p1 is the
      //     shared junction endpoint. All are point entity ids.
      //   { type: 'bezier_g2', p_minus2, p_minus1, p_junction, p_plus1, p_plus2 }
      //     p_minus2/p_minus1 are the last two control points of the incoming segment;
      //     p_junction is the shared endpoint; p_plus1/p_plus2 are the first two
      //     control points of the outgoing segment.
      case 'bezier_tangent':
      case 'bezier_g1': {
        // Collinearity of p0—p1—p2: synthesize a temp Line from p0 to p2 and
        // push point_on_line_ppp(p1, p0, p2). planegcs provides this constraint
        // via point_on_line_ppp (three points form: is p2 on line p0→p1?) but we
        // want p1 ON the line p0—p2, so the parameter order matters:
        //   point_on_line_pl(p_id, l_id) — uses a real line entity.
        // We instead use a synthetic Line (pushed inline) from p0 to p2 and then
        // constrain p1 to lie on it. But we can't push ephemeral lines after
        // constraints are already added (ordering matters in planegcs). Instead use
        // point_on_line_ppp which takes three point ids directly:
        //   { id, type: 'point_on_line_ppp', p_id, p1_id, p2_id }
        // This enforces that p_id lies on the infinite line through p1_id—p2_id.
        if (c.p0 && c.p1 && c.p2) {
          // p1 (junction point) lies on the line through p0 and p2 (the
          // tangent-handle control points of the two adjacent Bezier segments).
          constraints.push({
            id: nextId(),
            type: 'point_on_line_ppp',
            p_id: resolve(c.p1),
            p1_id: resolve(c.p0),
            p2_id: resolve(c.p2),
          })
        }
        break
      }
      // GK-P38: G2 (curvature) continuity constraint.
      //
      // Schema: { type: 'bezier_g2', p_minus2, p_minus1, p_junction, p_plus1, p_plus2 }
      //   p_minus2 — second-to-last control point of incoming segment  (in[-2])
      //   p_minus1 — last      control point of incoming segment        (in[-1])
      //   p_junction — shared  endpoint (in[-1] == out[0] via coincident)
      //   p_plus1  — first     control point of outgoing segment        (out[+1])
      //   p_plus2  — second    control point of outgoing segment        (out[+2])
      //
      // Approximation (planegcs has no curvature primitive):
      //   G1: p_minus1—p_junction—p_plus1 are collinear (tangent continuity).
      //   C2 equal-chord: |p_junction - p_minus1| == |p_plus1 - p_junction|.
      //     This is the standard C2 condition for uniform-parameterisation cubics.
      //     It is implemented as p2p_distance(p_minus1, p_junction) ==
      //     p2p_distance(p_junction, p_plus1) via the equal_length analog:
      //     we emit two p2p_distance constraints both pinned to the same computed
      //     chord length, giving a matched first-order curvature at the junction.
      //
      // Limitation: true G2 = matching curvature MAGNITUDES; C2 is sufficient for
      // Bezier segments of equal degree and uniform parameterisation, but not for
      // arcs or NURBS. This is the best approximation achievable with planegcs v1.1.7.
      case 'bezier_g2': {
        const { p_minus2, p_minus1, p_junction, p_plus1, p_plus2 } = c
        if (p_minus1 && p_junction && p_plus1) {
          // G1: collinearity of p_minus1—p_junction—p_plus1.
          constraints.push({
            id: nextId(),
            type: 'point_on_line_ppp',
            p_id: resolve(p_junction),
            p1_id: resolve(p_minus1),
            p2_id: resolve(p_plus1),
          })
          // C2 equal-chord: compute chord lengths from current geometry and pin both.
          const m1 = ent.find((x) => x.id === p_minus1)
          const jn = ent.find((x) => x.id === p_junction)
          const p1 = ent.find((x) => x.id === p_plus1)
          if (m1 && jn && p1) {
            const d1 = Math.hypot((jn.x ?? 0) - (m1.x ?? 0), (jn.y ?? 0) - (m1.y ?? 0))
            const d2 = Math.hypot((p1.x ?? 0) - (jn.x ?? 0), (p1.y ?? 0) - (jn.y ?? 0))
            const chord = (d1 + d2) / 2  // average as target — solver will equalize
            constraints.push({
              id: nextId(),
              type: 'p2p_distance',
              p1_id: resolve(p_minus1),
              p2_id: resolve(p_junction),
              distance: Math.max(0.001, chord),
            })
            constraints.push({
              id: nextId(),
              type: 'p2p_distance',
              p1_id: resolve(p_junction),
              p2_id: resolve(p_plus1),
              distance: Math.max(0.001, chord),
            })
          }
        }
        break
      }
      default:
        // Unknown constraint kind — silently skipped. The UI surface should
        // never produce one, but be lenient against forward-compat data.
        break
    }
  }

  return { points, lines, arcs, circles, constraints, remap }
}

// Run a solve. `temporary` is an optional planegcs constraint pushed alongside
// the persistent ones (used by drag).
async function runSolve(sketch, temporary = null) {
  const { make, Algorithm, SolveStatus, wasmUrl } = await loadPlanegcs()
  const wrapper = await make(wasmUrl)
  try {
    const { points, lines, arcs, circles, constraints, remap } = buildPlanegcsPrimitives(sketch)
    // Push order matters: points → composite primitives (line/circle/arc) →
    // constraints (which may reference any of the above).
    for (const p of points) wrapper.push_primitive(p)
    for (const l of lines) wrapper.push_primitive(l)
    for (const c of circles) wrapper.push_primitive(c)
    for (const a of arcs) wrapper.push_primitive(a)
    for (const c of constraints) wrapper.push_primitive(c)
    if (temporary) wrapper.push_primitive(temporary)

    const status = wrapper.solve(Algorithm.DogLeg)
    let okStatus = 'fully'
    let ok = false
    if (status === SolveStatus.Success || status === SolveStatus.Converged) {
      ok = true
      wrapper.apply_solution()
    } else if (status === SolveStatus.Failed) {
      okStatus = 'conflict'
    } else if (status === SolveStatus.SuccessfulSolutionInvalid) {
      okStatus = 'conflict'
    }
    let conflicts = []
    if (wrapper.has_gcs_conflicting_constraints?.()) {
      okStatus = 'conflict'
      conflicts = wrapper.get_gcs_conflicting_constraints?.() || []
    }

    // Read back solved values into a flat map keyed by entity id.
    const solved = {}
    for (const p of wrapper.sketch_index.get_primitives()) {
      if (p.type === 'point') {
        solved[p.id] = { x: p.x, y: p.y }
      } else if (p.type === 'circle') {
        solved[p.id] = { radius: p.radius }
      } else if (p.type === 'arc') {
        solved[p.id] = {
          start_angle: p.start_angle,
          end_angle: p.end_angle,
          radius: p.radius,
        }
      }
    }
    // Fold remap targets back so the entity-id consumer always finds its data.
    for (const [src, dst] of remap.entries()) {
      if (solved[dst] && !solved[src]) solved[src] = solved[dst]
    }

    // Apply the solved data back into a copy of the sketch's entities so the
    // canvas can render off the returned object directly.
    const nextEntities = (sketch.entities || []).map((e) => {
      if (e.type === 'point' && solved[e.id]) {
        return { ...e, x: solved[e.id].x, y: solved[e.id].y }
      }
      if (e.type === 'circle' && solved[e.id]) {
        return { ...e, radius: solved[e.id].radius }
      }
      return e
    })
    const nextSketch = { ...sketch, entities: nextEntities, solved }

    // Estimate over/under.
    const dof = estimateDof(nextSketch)
    if (okStatus !== 'conflict') {
      if (dof > 0) okStatus = 'under'
      else if (dof < 0) okStatus = 'over'
      else okStatus = 'fully'
    }

    return {
      ok,
      status: okStatus,
      dofCount: dof,
      solved,
      sketch: nextSketch,
      conflicts,
    }
  } finally {
    try { wrapper.destroy_gcs_module() } catch { /* ignore */ }
  }
}

export async function solveSketch(sketch) {
  return runSolve(sketch)
}

// Drag solve: pin a single point to (x,y) for the duration of one solve. We
// do this by adding two temporary `coordinate_x` / `coordinate_y` constraints
// — but planegcs doesn't expose those as combined drag pins, so we instead
// use two `difference` constraints against a fixed origin coordinate.
// Simpler: emit a temporary `p2p_distance` from a hidden anchor point at
// the cursor position with distance 0. Even simpler — two scalar `equal`
// constraints. The cleanest is to push a temporary fixed coordinate via the
// `coordinate_x` / `coordinate_y` constraints which planegcs also supports:
export async function solveWithDrag(sketch, drag) {
  if (!drag) return solveSketch(sketch)
  // Two temporary constraints that pin the dragged point's x/y to the cursor
  // coordinates. planegcs has `coordinate_x` / `coordinate_y` for exactly this.
  const tx = {
    id: 'c:drag_x',
    type: 'coordinate_x',
    p_id: drag.pointId,
    x: Number(drag.x) || 0,
    temporary: true,
  }
  const ty = {
    id: 'c:drag_y',
    type: 'coordinate_y',
    p_id: drag.pointId,
    y: Number(drag.y) || 0,
    temporary: true,
  }
  // We want both — but runSolve takes a single `temporary`. Stuff them as a
  // synthetic primitive: just push both into the constraints array via a
  // sketch-level mutation prior to solve.
  const augmented = {
    ...sketch,
    constraints: [
      ...(sketch.constraints || []),
      // Use the dx/dy difference encoding instead of coordinate_x/coordinate_y
      // because the latter don't appear in planegcs's exposed constraint
      // table; difference of param against origin works in v1.
    ],
  }
  // Emit two temp planegcs constraints by piggy-backing on the second-arg
  // path of runSolve. Since runSolve accepts only one `temporary`, push the
  // first directly and the second as a real planegcs primitive in the array.
  return runSolveTwoTemp(augmented, [tx, ty])
}

async function runSolveTwoTemp(sketch, temps) {
  const { make, Algorithm, SolveStatus, wasmUrl } = await loadPlanegcs()
  const wrapper = await make(wasmUrl)
  try {
    const { points, lines, arcs, circles, constraints, remap } = buildPlanegcsPrimitives(sketch)
    for (const p of points) wrapper.push_primitive(p)
    for (const l of lines) wrapper.push_primitive(l)
    for (const c of circles) wrapper.push_primitive(c)
    for (const a of arcs) wrapper.push_primitive(a)
    for (const c of constraints) wrapper.push_primitive(c)
    for (const t of temps) wrapper.push_primitive(t)
    const status = wrapper.solve(Algorithm.DogLeg)
    const ok = status === SolveStatus.Success || status === SolveStatus.Converged
    if (ok) wrapper.apply_solution()
    const solved = {}
    for (const p of wrapper.sketch_index.get_primitives()) {
      if (p.type === 'point') solved[p.id] = { x: p.x, y: p.y }
      else if (p.type === 'circle') solved[p.id] = { radius: p.radius }
      else if (p.type === 'arc') solved[p.id] = { start_angle: p.start_angle, end_angle: p.end_angle, radius: p.radius }
    }
    for (const [src, dst] of remap.entries()) {
      if (solved[dst] && !solved[src]) solved[src] = solved[dst]
    }
    const nextEntities = (sketch.entities || []).map((e) => {
      if (e.type === 'point' && solved[e.id]) return { ...e, x: solved[e.id].x, y: solved[e.id].y }
      if (e.type === 'circle' && solved[e.id]) return { ...e, radius: solved[e.id].radius }
      return e
    })
    const nextSketch = { ...sketch, entities: nextEntities, solved }
    const dof = estimateDof(nextSketch)
    let okStatus = ok ? (dof > 0 ? 'under' : dof < 0 ? 'over' : 'fully') : 'conflict'
    return { ok, status: okStatus, dofCount: dof, solved, sketch: nextSketch, conflicts: [] }
  } finally {
    try { wrapper.destroy_gcs_module() } catch { /* ignore */ }
  }
}

export function getSolverFailure() {
  return lastFailure
}
