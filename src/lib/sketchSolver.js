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
    }
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
        dof -= 1
        break
      case 'symmetric':
        dof -= 2
        break
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
      default:
        break
    }
  }
  return dof
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
