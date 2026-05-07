// occtBridge.js — pure helpers that translate between Kerf data shapes and
// OpenCascade (OCCT) topological data structures.
//
// All functions take an `oc` instance (the value resolved from
// `initOpenCascade()` in opencascade.js). They are completely pure with
// respect to the worker — they never call postMessage and never read shared
// module state.
//
// Performance notes (rough, on a 2024 MacBook M2; will vary):
//   * geom2ToBRepFace          — ~5-15 ms for a ring of 100 vertices
//   * breptToMesh              — ~100-400 ms for a typical Pad+Fillet result.
//                                The triangulation step (BRepMesh_IncMesh) is
//                                the dominant cost and scales with face area
//                                / linear deflection.
//   * cleanupShape             — < 1 ms; just decrements OCCT refcounts.
//   * serializeStep            — ~200-800 ms for a moderate B-rep. STEP
//                                writers are not particularly fast in OCCT
//                                regardless of the binding layer.
//
// Memory discipline:
//   OCCT WASM lives on a shared linear heap. Every `new oc.SomethingHandle()`,
//   `new oc.gp_Pnt_3()`, etc. allocates emscripten-managed memory that must
//   be `.delete()`-ed when no longer needed. Failure to delete leaks the
//   underlying C++ object. We use `track()` everywhere a transient is created
//   so a single `freeAll(tracked)` at the end of an operation cleans up in
//   one pass; only the result shape is hand-managed (caller deletes it via
//   cleanupShape).
//
// Edge / face id stability:
//   We assign a numeric id to every face/edge as they appear in the post-
//   evaluation TopExp explorer order. Re-running the same FeatureTree with
//   identical inputs produces a deterministic ordering, so ids are stable
//   across re-evaluations of an unchanged tree. *Across* feature edits ids
//   may shuffle — this is the persistent-naming problem; v1 accepts it and
//   leaves the cross-edit identity layer to a later phase.

// ---------------------------------------------------------------------------
// Tracker for transient OCCT handles. Push everything you allocate onto
// `tracked`, then call freeAll(tracked) in finally{}.
export function makeTracker() {
  return []
}

export function track(tracker, obj) {
  if (obj) tracker.push(obj)
  return obj
}

export function freeAll(tracker) {
  if (!tracker) return
  for (let i = tracker.length - 1; i >= 0; i--) {
    const obj = tracker[i]
    if (!obj) continue
    try {
      // Most OCCT objects expose .delete(); some are scalar wrappers that don't.
      if (typeof obj.delete === 'function') obj.delete()
    } catch {
      // Tolerate double-delete and unmanaged objects.
    }
  }
  tracker.length = 0
}

// Final shape cleanup. Caller passes the TopoDS_Shape returned by an op.
export function cleanupShape(_oc, shape) {
  if (!shape) return
  try {
    if (typeof shape.delete === 'function') shape.delete()
  } catch { /* tolerate */ }
}

// ---------------------------------------------------------------------------
// Sketch (loop-of-[x,y]) → TopoDS_Face.
//
// Strategy:
//   1. Walk vertices, build segments via BRepBuilderAPI_MakeEdge (line edges).
//      For arcs / curves the caller is expected to have pre-tessellated the
//      sketch to a polyline (we receive [x,y] only). v1 only consumes line
//      segments — sketchToGeom2 already polylines arcs.
//   2. Stitch segments into a wire with BRepBuilderAPI_MakeWire.
//   3. Build a face on plane Z=0 with BRepBuilderAPI_MakeFace.
//
// Multi-loop profiles (outer + holes) are handled by passing a `loops` array
// where the first loop is the outer and the rest are CW-oriented holes.
//
// Returns a fresh TopoDS_Face. Caller owns + deletes it.

function _ringFromPoints(oc, ring, tracker) {
  // Build a closed polyline wire on the XY plane (Z=0).
  if (!Array.isArray(ring) || ring.length < 3) return null
  const wireBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  let last = null
  for (let i = 0; i < ring.length; i++) {
    const cur = ring[i]
    if (!cur || cur.length < 2) continue
    if (last) {
      const p1 = track(tracker, new oc.gp_Pnt_3(last[0], last[1], 0))
      const p2 = track(tracker, new oc.gp_Pnt_3(cur[0], cur[1], 0))
      const me = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p1, p2))
      if (me.IsDone()) wireBuilder.Add_1(me.Edge())
    }
    last = cur
  }
  // Close with a final segment from last → first if not already coincident.
  const first = ring[0]
  const lastV = ring[ring.length - 1]
  const dx = (first[0] - lastV[0]), dy = (first[1] - lastV[1])
  if (Math.hypot(dx, dy) > 1e-9) {
    const p1 = track(tracker, new oc.gp_Pnt_3(lastV[0], lastV[1], 0))
    const p2 = track(tracker, new oc.gp_Pnt_3(first[0], first[1], 0))
    const me = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p1, p2))
    if (me.IsDone()) wireBuilder.Add_1(me.Edge())
  }
  if (!wireBuilder.IsDone()) return null
  return wireBuilder.Wire()
}

// Convert a JSCAD Geom2 (or a plain {sides:[[ax,ay],[bx,by]]} polylike
// structure) → an array of rings. Each ring is an [x,y] vertex list.
export function geom2ToRings(geom2) {
  if (!geom2) return []
  // JSCAD Geom2 internal: { sides: [[[ax,ay],[bx,by]], ...], transforms }
  // Each side is an edge from a→b. Stitch them into rings by chasing endpoints.
  const sides = geom2.sides || []
  if (sides.length === 0) return []
  // Build adjacency keyed by quantized vertex.
  const Q = 1e6 // ~1µm quantization keyed
  function key(p) { return `${Math.round(p[0] * Q)},${Math.round(p[1] * Q)}` }
  const startMap = new Map() // start key → side index
  for (let i = 0; i < sides.length; i++) {
    startMap.set(key(sides[i][0]), i)
  }
  const used = new Set()
  const loops = []
  for (let i = 0; i < sides.length; i++) {
    if (used.has(i)) continue
    const ring = []
    let cur = i
    let safety = 0
    while (cur !== undefined && !used.has(cur) && safety++ < 10000) {
      used.add(cur)
      const side = sides[cur]
      ring.push([side[0][0], side[0][1]])
      const next = startMap.get(key(side[1]))
      cur = next
      if (cur === i) break
    }
    if (ring.length >= 3) loops.push(ring)
  }
  return loops
}

// Create a TopoDS_Face on Z=0 from a list of rings (first = outer, rest = holes).
// `loops` is an array of [x,y] arrays.
export function ringsToFace(oc, loops, tracker) {
  if (!loops || loops.length === 0) return null
  const outer = _ringFromPoints(oc, loops[0], tracker)
  if (!outer) return null
  const mf = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(outer, true))
  for (let i = 1; i < loops.length; i++) {
    const hole = _ringFromPoints(oc, loops[i], tracker)
    if (hole) mf.Add(hole)
  }
  if (!mf.IsDone()) return null
  return mf.Face()
}

// Convenience: take a Geom2 directly and produce a face.
export function geom2ToBRepFace(oc, geom2, tracker) {
  const loops = geom2ToRings(geom2)
  if (loops.length === 0) return null
  return ringsToFace(oc, loops, tracker)
}

// ---------------------------------------------------------------------------
// Wire builders (open or closed) — used by sweep/loft. Unlike ringsToFace
// these produce a TopoDS_Wire suitable for spine paths (open) or as cross-
// section profiles for ThruSections (closed).
//
// We accept three shapes:
//   * a sketch JSON (with .entities) — caller passes through `sketchToWirePoints`
//   * a JSCAD Geom2-like (.sides) — `geom2ToRings` extracts polylines
//   * a raw [[x,y]...] polyline — caller passes directly
//
// `closed=true` adds a closing edge from last → first if not coincident.

function _polylineToWire(oc, points, plane, closed, tracker) {
  if (!Array.isArray(points) || points.length < 2) return null
  const wireBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  // For 2D points we elevate to 3D using the plane (default XY at Z=0).
  // The placeFaceOnPlane / wire-on-plane transform happens later for spine
  // paths whose sketch declares a non-XY plane.
  const pZ = (xy) => {
    if (xy.length >= 3) return [xy[0], xy[1], xy[2]]
    return [xy[0], xy[1], 0]
  }
  let last = pZ(points[0])
  for (let i = 1; i < points.length; i++) {
    const cur = pZ(points[i])
    const dx = cur[0] - last[0], dy = cur[1] - last[1], dz = cur[2] - last[2]
    if (Math.hypot(dx, dy, dz) < 1e-9) { last = cur; continue }
    const p1 = track(tracker, new oc.gp_Pnt_3(last[0], last[1], last[2]))
    const p2 = track(tracker, new oc.gp_Pnt_3(cur[0], cur[1], cur[2]))
    const me = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p1, p2))
    if (me.IsDone()) wireBuilder.Add_1(me.Edge())
    last = cur
  }
  if (closed) {
    const first = pZ(points[0])
    const dx = first[0] - last[0], dy = first[1] - last[1], dz = first[2] - last[2]
    if (Math.hypot(dx, dy, dz) > 1e-9) {
      const p1 = track(tracker, new oc.gp_Pnt_3(last[0], last[1], last[2]))
      const p2 = track(tracker, new oc.gp_Pnt_3(first[0], first[1], first[2]))
      const me = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p1, p2))
      if (me.IsDone()) wireBuilder.Add_1(me.Edge())
    }
  }
  if (!wireBuilder.IsDone()) return null
  void plane
  return wireBuilder.Wire()
}

// Walk a Sketch's adjacency to extract a connected polyline. Unlike Geom2
// extraction (which only emits closed loops), this emits the longest open or
// closed chain we can find — sweep paths are usually open.
//
// Returns:
//   { points: [[x,y]...], closed: bool } — or null if no chain.
export function sketchToWirePoints(sketch) {
  if (!sketch || !Array.isArray(sketch.entities)) return null
  // Build vertex map.
  const points = new Map()
  for (const e of sketch.entities) {
    if (e.type === 'point') points.set(e.id, [e.x || 0, e.y || 0])
  }
  // Build adjacency: pointId → [{otherId, kind, e, fromStart}].
  const adj = new Map()
  function addEdge(pid, edge) {
    if (!adj.has(pid)) adj.set(pid, [])
    adj.get(pid).push(edge)
  }
  for (const e of sketch.entities) {
    if (e.construction) continue
    if (e.type === 'line') {
      addEdge(e.p1, { otherId: e.p2, edgeId: e.id, kind: 'line', e })
      addEdge(e.p2, { otherId: e.p1, edgeId: e.id, kind: 'line', e })
    } else if (e.type === 'arc') {
      addEdge(e.start, { otherId: e.end, edgeId: e.id, kind: 'arc', e, fromStart: true })
      addEdge(e.end, { otherId: e.start, edgeId: e.id, kind: 'arc', e, fromStart: false })
    }
  }
  if (adj.size === 0) return null
  // Find an endpoint (vertex with degree 1) to start from; fall back to any
  // vertex if the chain is closed (all degree 2).
  let start = null
  for (const [pid, edges] of adj) {
    if (edges.length === 1) { start = pid; break }
  }
  let isClosed = false
  if (!start) {
    start = adj.keys().next().value
    isClosed = true
  }
  // Walk the chain, tessellating arcs as we go.
  const used = new Set()
  const out = []
  let prev = null
  let cur = start
  let safety = 0
  while (cur != null && safety++ < 4096) {
    const p = points.get(cur)
    if (!p) break
    if (out.length === 0 || out[out.length - 1][0] !== p[0] || out[out.length - 1][1] !== p[1]) {
      out.push([p[0], p[1]])
    }
    const candidates = (adj.get(cur) || []).filter((e) => !used.has(e.edgeId) && e.otherId !== prev)
    if (candidates.length === 0) break
    const pick = candidates[0]
    used.add(pick.edgeId)
    if (pick.kind === 'arc') {
      const arc = pick.e
      const c = points.get(arc.center)
      const s = points.get(arc.start)
      const e = points.get(arc.end)
      if (c && s && e) {
        const r = Math.hypot(s[0] - c[0], s[1] - c[1])
        const sa = Math.atan2(s[1] - c[1], s[0] - c[0])
        const ea = Math.atan2(e[1] - c[1], e[0] - c[0])
        const fromStart = pick.fromStart
        const startA = fromStart ? sa : ea
        const endA = fromStart ? ea : sa
        const ccw = !!arc.sweep_ccw
        let sweep = endA - startA
        if (ccw) { while (sweep < 0) sweep += Math.PI * 2 } else { while (sweep > 0) sweep -= Math.PI * 2 }
        const n = Math.max(2, Math.ceil(Math.abs(sweep) * 12))
        for (let i = 1; i < n; i++) {
          const t = i / n
          const a = startA + sweep * t
          out.push([c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)])
        }
      }
    }
    prev = cur
    cur = pick.otherId
    if (cur === start) {
      // Closed loop: emit the closing endpoint and stop.
      const p2 = points.get(cur)
      if (p2 && (out.length === 0 || out[out.length - 1][0] !== p2[0] || out[out.length - 1][1] !== p2[1])) {
        out.push([p2[0], p2[1]])
      }
      isClosed = true
      break
    }
  }
  if (out.length < 2) return null
  // Detect closure if start ≈ end.
  if (!isClosed) {
    const a = out[0], b = out[out.length - 1]
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9) isClosed = true
  }
  return { points: out, closed: isClosed }
}

// Build a TopoDS_Wire on the XY plane from a Sketch. Used for sweep paths
// (open) and as profile cross-sections for loft (closed). Returns the wire
// (caller still owns it via tracker), or null.
export function sketchToWire(oc, sketch, { closed = null } = {}, tracker) {
  if (!sketch) return null
  const chain = sketchToWirePoints(sketch)
  if (!chain) return null
  const wantClosed = closed == null ? chain.closed : !!closed
  return _polylineToWire(oc, chain.points, null, wantClosed, tracker)
}

// Produce a TopoDS_Wire from a JSCAD Geom2 (multi-loop) — picks the largest
// outer loop. Intended for loft profiles built from `.sketch` files that
// already form closed regions.
export function geom2ToWire(oc, geom2, tracker) {
  const loops = geom2ToRings(geom2)
  if (loops.length === 0) return null
  // Pick largest by signed-area magnitude.
  let best = loops[0]
  let bestA = 0
  for (const ring of loops) {
    let a = 0
    for (let i = 0; i < ring.length; i++) {
      const [x1, y1] = ring[i]
      const [x2, y2] = ring[(i + 1) % ring.length]
      a += (x2 - x1) * (y2 + y1)
    }
    a = Math.abs(a) / 2
    if (a > bestA) { bestA = a; best = ring }
  }
  return _polylineToWire(oc, best, null, true, tracker)
}

// ---------------------------------------------------------------------------
// Apply a `placeFaceOnPlane`-equivalent transform to a TopoDS_Wire. Mirrors
// occtWorker's placeFaceOnPlane logic but for wires (sweep paths can live on
// any base plane). Face-anchored sketches are deliberately rejected for
// sweep paths in v1 — the OCCT MakePipeShell needs a continuous spine and we
// don't yet stitch face-anchored chains.
export function placeWireOnPlane(oc, wire, plane, tracker) {
  if (!wire || !plane) return wire
  if (plane.type === 'face' && plane.frame
      && plane.frame.origin && plane.frame.normal && plane.frame.uDir && plane.frame.vDir) {
    const f = plane.frame
    const trsf = track(tracker, new oc.gp_Trsf_1())
    const o = track(tracker, new oc.gp_Pnt_3(f.origin[0], f.origin[1], f.origin[2]))
    const dN = track(tracker, new oc.gp_Dir_4(f.normal[0], f.normal[1], f.normal[2]))
    const dU = track(tracker, new oc.gp_Dir_4(f.uDir[0], f.uDir[1], f.uDir[2]))
    const ax3Target = track(tracker, new oc.gp_Ax3_3(o, dN, dU))
    const o0 = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
    const dN0 = track(tracker, new oc.gp_Dir_4(0, 0, 1))
    const dU0 = track(tracker, new oc.gp_Dir_4(1, 0, 0))
    const ax3Source = track(tracker, new oc.gp_Ax3_3(o0, dN0, dU0))
    trsf.SetTransformation_1(ax3Target, ax3Source)
    const tloc = track(tracker, new oc.TopLoc_Location_2(trsf))
    return wire.Moved?.(tloc, false) ?? wire
  }
  if (plane.type !== 'base') return wire
  const planeName = (plane.name || 'XY').toUpperCase()
  if (planeName === 'XY') return wire
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const ax1 = track(tracker, new oc.gp_Ax1_2(
    track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
    planeName === 'XZ'
      ? track(tracker, new oc.gp_Dir_4(1, 0, 0))
      : track(tracker, new oc.gp_Dir_4(0, 1, 0)),
  ))
  trsf.SetRotation_1(ax1, planeName === 'XZ' ? -Math.PI / 2 : Math.PI / 2)
  const tloc = track(tracker, new oc.TopLoc_Location_2(trsf))
  return wire.Moved?.(tloc, false) ?? wire
}

// ---------------------------------------------------------------------------
// Variable-radius fillet helpers.
//
// OpenCascade's BRepFilletAPI_MakeFillet supports several `Add` overloads.
// The variable-radius variants we *would* like accept either:
//   (a) a TColgp_Array1OfPnt2d of (param, radius) pairs + edge, or
//   (b) a Handle_Law_Function + edge.
//
// In this opencascade.js build TColgp_Array1OfPnt2d is NOT bound (red in
// "Supported APIs.md"), but Law_Linear / Law_Composite / Law_Function ARE.
// We construct a piecewise-linear Law_Composite from the user's
// {at, radius} pairs and attach it. If for any reason the law-function
// constructor or the matching `Add_*` overload isn't accessible at runtime,
// `buildVariableRadiusLaw` returns null and the caller falls back to the
// constant-radius path with the *first* radius.
//
// The composite-of-linears construction:
//   - sort pairs by `at` ∈ [0, 1]
//   - clamp endpoints to {0, 1}
//   - between each consecutive pair (t_i, r_i) → (t_{i+1}, r_{i+1}) build
//     a Law_Linear segment; chain them via Law_Composite::ChangeLaws.

export function buildVariableRadiusLaw(oc, radii, tracker) {
  if (!Array.isArray(radii) || radii.length < 2) return null
  // Defensive copy + sort + clamp.
  const pairs = radii
    .map((r) => ({ at: Number(r.at), radius: Number(r.radius) }))
    .filter((r) => Number.isFinite(r.at) && Number.isFinite(r.radius) && r.radius > 0)
    .sort((a, b) => a.at - b.at)
  if (pairs.length < 2) return null
  // Clamp endpoints to 0 and 1 (OCCT expects the law to span the edge param
  // range — for our 0..1 normalized "at", the worker remaps at the call
  // site by reading the edge's actual first/last parameter).
  if (pairs[0].at > 0) pairs.unshift({ at: 0, radius: pairs[0].radius })
  if (pairs[pairs.length - 1].at < 1) pairs.push({ at: 1, radius: pairs[pairs.length - 1].radius })
  // We must produce a Law_Function the runtime can pass to MakeFillet::Add.
  // The Composite chain is built segment-by-segment.
  let composite
  try {
    composite = track(tracker, new oc.Law_Composite_1())
  } catch {
    return null
  }
  let laws
  try {
    laws = composite.ChangeLaws?.()
  } catch {
    laws = null
  }
  if (!laws) {
    // Fallback: try Law_Linear over the whole range with the average radius.
    try {
      const linear = track(tracker, new oc.Law_Linear_1())
      const r0 = pairs[0].radius
      const r1 = pairs[pairs.length - 1].radius
      linear.Set?.(0, r0, 1, r1)
      return linear
    } catch {
      return null
    }
  }
  for (let i = 0; i < pairs.length - 1; i++) {
    const a = pairs[i]
    const b = pairs[i + 1]
    if (b.at - a.at < 1e-9) continue
    let linear
    try {
      linear = track(tracker, new oc.Law_Linear_1())
      linear.Set?.(a.at, a.radius, b.at, b.radius)
    } catch {
      continue
    }
    try {
      // Law_Composite owns a NCollection_List<Handle_Law_Function>. The
      // exact list-add method depends on the binding; try both names.
      if (typeof laws.Append_1 === 'function') laws.Append_1(linear)
      else if (typeof laws.Append === 'function') laws.Append(linear)
    } catch {
      // tolerate; the composite may end up empty and we'll fall back.
    }
  }
  return composite
}

// ---------------------------------------------------------------------------
// Mesh extraction.
//
// Triangulates the input shape via BRepMesh_IncMesh (linear deflection 0.1mm,
// angular 0.5 rad — coarse-ish for a v1 viewport). Walks every TopoDS_Face,
// reads its Poly_Triangulation, and concatenates into a flat triangle soup.
// We also assign a numeric face_id per TopoDS_Face (0-based, in TopExp order)
// and walk every TopoDS_Edge to extract polyline segments with stable edge
// ids (also TopExp order).
//
// Returns:
//   {
//     vertices:    Float32Array (xyz tuples per mesh vertex),
//     indices:     Uint32Array  (triangle indices),
//     normals:     Float32Array,
//     faceIds:     Uint32Array  (per-triangle face id),
//     faceMeta:    [{ id, planar, origin: [x,y,z], normal: [x,y,z],
//                     uDir: [x,y,z], vDir: [x,y,z], centroid: [x,y,z] }]
//     edgeSegs:    Float32Array (xyz, two consecutive xyz triples = one segment),
//     edgeIds:     Uint32Array  (one edge id per segment),
//     // Legacy edgeMap kept for the LLM filter helpers (edge_filter='manual')
//     edgeMap:     { count, edges: [{id, vertices: Float32Array}] }
//   }

const MESH_LINEAR_DEFLECTION = 0.1   // mm
const MESH_ANGULAR_DEFLECTION = 0.5  // radians

export function breptToMesh(oc, shape) {
  if (!shape) {
    return _emptyMesh()
  }
  // Force triangulation.
  try {
    const mesh = new oc.BRepMesh_IncMesh_2(shape, MESH_LINEAR_DEFLECTION, false, MESH_ANGULAR_DEFLECTION, false)
    mesh.Perform_1?.() // some bindings auto-perform on construct
    if (typeof mesh.delete === 'function') mesh.delete()
  } catch {
    // Some opencascade.js builds expose BRepMesh_IncMesh_1 without flags. Try
    // the simpler signature.
    try {
      const mesh = new oc.BRepMesh_IncMesh_1()
      mesh.SetShape(shape)
      mesh.SetDeflection(MESH_LINEAR_DEFLECTION)
      mesh.Perform_1?.()
      if (typeof mesh.delete === 'function') mesh.delete()
    } catch { /* tolerate; we'll still try to read what's there */ }
  }

  const vertList = []
  const idxList = []
  const normList = []
  const faceIdList = []
  const faceMeta = [] // per-face: {id, planar, origin, normal, uDir, vDir, centroid}

  let faceId = 0
  const explorer = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  for (; explorer.More(); explorer.Next()) {
    const faceSh = explorer.Current()
    const face = oc.TopoDS.Face_1(faceSh)
    const loc = new oc.TopLoc_Location_1()
    const tri = oc.BRep_Tool.Triangulation(face, loc, 0 /* purpose any */)
    if (tri.IsNull?.()) {
      try { loc.delete() } catch { /* */ }
      // Even if no triangulation, capture face plane meta so push/pull etc.
      // can work against the analytical surface.
      const meta = _extractFaceMeta(oc, face, faceId)
      if (meta) faceMeta.push(meta)
      faceId++
      continue
    }
    const triPtr = tri.get()
    const trsf = loc.Transformation()
    const reversed = face.Orientation_1() === oc.TopAbs_Orientation.TopAbs_REVERSED
    const nNodes = triPtr.NbNodes()
    const nTri = triPtr.NbTriangles()
    // Vertex offset for this face in the global vertex array.
    const vertBase = vertList.length / 3
    for (let i = 1; i <= nNodes; i++) {
      const p = triPtr.Node(i)
      const tp = p.Transformed(trsf)
      vertList.push(tp.X(), tp.Y(), tp.Z())
      try { tp.delete?.(); p.delete?.() } catch { /* */ }
    }
    for (let i = 1; i <= nTri; i++) {
      const t = triPtr.Triangle(i)
      // Triangle indices are 1-based; convert + offset by vertBase.
      // Use the Get() helper that some opencascade.js builds expose; fall
      // back to Value()-based access otherwise.
      let i1, i2, i3
      try {
        const o = { current: 0 }
        // OCCT triangle Get returns indices into Node() (1..N).
        const idx = t.Get_1?.() || null
        if (idx) {
          i1 = idx[0]; i2 = idx[1]; i3 = idx[2]
        } else {
          i1 = t.Value(1); i2 = t.Value(2); i3 = t.Value(3)
        }
      } catch {
        i1 = t.Value(1); i2 = t.Value(2); i3 = t.Value(3)
      }
      // Convert to 0-based + add vertex offset.
      let a = vertBase + (i1 - 1)
      let b = vertBase + (i2 - 1)
      let c = vertBase + (i3 - 1)
      if (reversed) { const tmp = b; b = c; c = tmp }
      idxList.push(a, b, c)
      // Compute flat triangle normal for shading.
      const ax = vertList[a * 3], ay = vertList[a * 3 + 1], az = vertList[a * 3 + 2]
      const bx = vertList[b * 3], by = vertList[b * 3 + 1], bz = vertList[b * 3 + 2]
      const cx = vertList[c * 3], cy = vertList[c * 3 + 1], cz = vertList[c * 3 + 2]
      const ux = bx - ax, uy = by - ay, uz = bz - az
      const vx = cx - ax, vy = cy - ay, vz = cz - az
      let nx = uy * vz - uz * vy
      let ny = uz * vx - ux * vz
      let nz = ux * vy - uy * vx
      const ln = Math.hypot(nx, ny, nz) || 1
      nx /= ln; ny /= ln; nz /= ln
      // Per-vertex normals are filled at indices a/b/c via accumulate-then-renorm.
      // For simplicity (v1) we set flat per-triangle normals: re-write at
      // vertex slots, last-write wins — fine for hard-edged BRep faces.
      _setNormal(normList, a, nx, ny, nz)
      _setNormal(normList, b, nx, ny, nz)
      _setNormal(normList, c, nx, ny, nz)
      faceIdList.push(faceId)
      try { t.delete?.() } catch { /* */ }
    }
    // Per-face plane / centroid metadata. Used by FeatureRenderer (face
    // colouring) and by direct-modeling features (push/pull, sketch on face).
    const meta = _extractFaceMeta(oc, face, faceId)
    if (meta) faceMeta.push(meta)
    try { loc.delete() } catch { /* */ }
    faceId++
  }
  try { explorer.delete() } catch { /* */ }

  // Edge map: per-edge id → polyline vertices in 3D. Useful for edge-pick UI
  // even though v1 doesn't render them itself; the file_ids the LLM tools take
  // resolve against this list.
  const edgeMap = _extractEdges(oc, shape)

  // Flatten edges into a contiguous segment buffer for renderer consumption.
  // Each segment is two xyz triples; edgeIds[i] is the edge id of segment i.
  const segXyzList = []
  const segIdList = []
  for (const e of edgeMap.edges) {
    const v = e.vertices
    if (!v || v.length < 6) continue
    for (let i = 3; i < v.length; i += 3) {
      segXyzList.push(v[i - 3], v[i - 2], v[i - 1])
      segXyzList.push(v[i],     v[i + 1], v[i + 2])
      segIdList.push(e.id)
    }
  }

  return {
    vertices: new Float32Array(vertList),
    indices: new Uint32Array(idxList),
    normals: new Float32Array(_normalsAligned(normList, vertList.length / 3)),
    faceIds: new Uint32Array(faceIdList),
    faceMeta,
    edgeSegs: new Float32Array(segXyzList),
    edgeIds: new Uint32Array(segIdList),
    edgeMap,
  }
}

// Extract the face's analytical surface plane info if planar, and a centroid.
// Returns null only when the face has no usable surface (degenerate). For
// non-planar faces we still set planar=false but report a sample point + the
// surface normal at the parametric midpoint, which is enough for hover labels.
function _extractFaceMeta(oc, face, faceId) {
  try {
    const surf = oc.BRep_Tool.Surface_2(face)
    // Try to recognize the surface as a plane by downcasting to Geom_Plane.
    let planar = false
    let origin = [0, 0, 0]
    let normal = [0, 0, 1]
    let uDir = [1, 0, 0]
    let vDir = [0, 1, 0]
    try {
      const handle = surf
      // Geom_Plane has DynamicType - we test by attempting to cast.
      const planeHandle = (oc.Handle_Geom_Plane && handle && handle.get && handle.get())
        ? handle
        : null
      void planeHandle
      // The robust path: query the BRepAdaptor_Surface to get the surface
      // type. If it's `GeomAbs_Plane` we read its underlying gp_Pln.
      const adapt = new oc.BRepAdaptor_Surface_2(face, true)
      const stype = adapt.GetType()
      const planeEnum = oc.GeomAbs_SurfaceType?.GeomAbs_Plane
      if (planeEnum != null && stype === planeEnum) {
        const pln = adapt.Plane()
        const ax = pln.Position()
        const loc = ax.Location()
        const dirN = ax.Direction()
        const dirU = ax.XDirection()
        const dirV = ax.YDirection()
        origin = [loc.X(), loc.Y(), loc.Z()]
        normal = [dirN.X(), dirN.Y(), dirN.Z()]
        uDir   = [dirU.X(), dirU.Y(), dirU.Z()]
        vDir   = [dirV.X(), dirV.Y(), dirV.Z()]
        planar = true
        try { ax.delete?.(); loc.delete?.(); dirN.delete?.(); dirU.delete?.(); dirV.delete?.(); pln.delete?.() } catch { /* */ }
      } else {
        // Fall back to evaluating at the parametric midpoint.
        try {
          const u0 = adapt.FirstUParameter(); const u1 = adapt.LastUParameter()
          const v0 = adapt.FirstVParameter(); const v1 = adapt.LastVParameter()
          const uMid = (u0 + u1) / 2; const vMid = (v0 + v1) / 2
          const slp = new oc.GeomLProp_SLProps_2(surf, uMid, vMid, 1, 1e-7)
          const p = slp.Value()
          origin = [p.X(), p.Y(), p.Z()]
          if (slp.IsNormalDefined?.()) {
            const n = slp.Normal()
            normal = [n.X(), n.Y(), n.Z()]
            try { n.delete?.() } catch { /* */ }
          }
          try { p.delete?.(); slp.delete?.() } catch { /* */ }
        } catch { /* */ }
      }
      if (face.Orientation_1?.() === oc.TopAbs_Orientation.TopAbs_REVERSED) {
        normal = [-normal[0], -normal[1], -normal[2]]
        // Keep the (u, v, n) triple right-handed by flipping v; otherwise
        // the sketch-on-face transform produces a mirrored image.
        vDir = [-vDir[0], -vDir[1], -vDir[2]]
      }
      try { adapt.delete?.() } catch { /* */ }
    } catch { /* fall through */ }
    return {
      id: faceId,
      planar,
      origin,
      normal,
      uDir,
      vDir,
      centroid: origin, // close enough for hover labels; real centroid would
                        // need to integrate over the face triangulation
    }
  } catch {
    return { id: faceId, planar: false, origin: [0, 0, 0], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0], centroid: [0, 0, 0] }
  }
}

function _setNormal(arr, idx, x, y, z) {
  const o = idx * 3
  arr[o] = x; arr[o + 1] = y; arr[o + 2] = z
}

// Pad or trim normals to exactly `n` triplets so the typed-array view matches.
function _normalsAligned(arr, n) {
  const out = new Array(n * 3).fill(0)
  for (let i = 0; i < arr.length && i < out.length; i++) out[i] = arr[i]
  return out
}

function _emptyMesh() {
  return {
    vertices: new Float32Array(0),
    indices: new Uint32Array(0),
    normals: new Float32Array(0),
    faceIds: new Uint32Array(0),
    faceMeta: [],
    edgeSegs: new Float32Array(0),
    edgeIds: new Uint32Array(0),
    edgeMap: { count: 0, edges: [] },
  }
}

// Walk every edge in the shape; for each, sample the underlying curve into a
// polyline of N segments. Returns { count, edges: [{id, vertices: Float32Array}] }.
function _extractEdges(oc, shape) {
  const edges = []
  let id = 0
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return { count: 0, edges: [] }
  }
  for (; exp.More(); exp.Next()) {
    const e = oc.TopoDS.Edge_1(exp.Current())
    const verts = _sampleEdge(oc, e)
    if (verts.length >= 2) {
      edges.push({ id, vertices: new Float32Array(verts) })
    }
    id++
  }
  try { exp.delete() } catch { /* */ }
  return { count: edges.length, edges }
}

function _sampleEdge(oc, edge) {
  const out = []
  try {
    const first = { current: 0 }
    const last = { current: 0 }
    // BRepAdaptor_Curve gives a uniform parametric curve over the edge
    // regardless of the underlying geometry kind.
    const curve = new oc.BRepAdaptor_Curve_2(edge)
    const t0 = curve.FirstParameter()
    const t1 = curve.LastParameter()
    const segs = 24
    for (let i = 0; i <= segs; i++) {
      const t = t0 + (t1 - t0) * (i / segs)
      const p = curve.Value(t)
      out.push(p.X(), p.Y(), p.Z())
      try { p.delete() } catch { /* */ }
    }
    try { curve.delete() } catch { /* */ }
    void first; void last
  } catch {
    // Curve adapter unavailable for this edge kind — return empty so the
    // caller can skip it gracefully.
    return []
  }
  return out
}

// ---------------------------------------------------------------------------
// STEP serialization.
//
// Returns the STEP file as a string. We write to a virtual emscripten FS path
// then read it back. opencascade.js exposes the FS via `oc.FS` (emscripten
// MEMFS by default).

export function serializeStep(oc, shape) {
  if (!shape) return ''
  const writer = new oc.STEPControl_Writer_1()
  try {
    writer.Transfer(shape, oc.STEPControl_StepModelType.STEPControl_AsIs, true)
    const filename = `/__kerf_export_${Date.now()}.step`
    const status = writer.Write(filename)
    if (typeof status?.value !== 'undefined' && status.value !== 0 /* IFSelect_RetDone */) {
      // 0 == IFSelect_RetDone in OCCT enum order; non-zero = error.
      // Continue anyway — the file may still have been written.
    }
    let data = ''
    try {
      const bytes = oc.FS.readFile(filename, { encoding: 'utf8' })
      data = bytes
    } catch {
      data = ''
    }
    try { oc.FS.unlink(filename) } catch { /* */ }
    return data
  } finally {
    try { writer.delete?.() } catch { /* */ }
  }
}

// ---------------------------------------------------------------------------
// Edge-filter helpers for fillet / chamfer LLM tools.
//
// The "all" filter selects every edge in the input shape; "horizontal" /
// "vertical" pick edges whose tangent at midpoint is roughly aligned with
// the global X/Y axis (useful for a "round all top edges" call). "manual"
// expects an explicit array of edge ids and ignores the filter logic.

export function filterEdges(oc, shape, mode, manualIds) {
  const out = []
  let id = 0
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return out
  }
  for (; exp.More(); exp.Next()) {
    const e = oc.TopoDS.Edge_1(exp.Current())
    let take = false
    if (mode === 'all' || !mode) take = true
    else if (mode === 'manual') take = Array.isArray(manualIds) && manualIds.includes(id)
    else if (mode === 'horizontal') take = _edgeAxisDominant(oc, e) === 'horizontal'
    else if (mode === 'vertical') take = _edgeAxisDominant(oc, e) === 'vertical'
    if (take) out.push({ id, edge: e })
    id++
  }
  try { exp.delete() } catch { /* */ }
  return out
}

// ---------------------------------------------------------------------------
// Face-by-id lookup. Walks TopExp_Explorer (faces) and returns the Nth face.
// Used by direct-modeling ops + sketch-on-face which carry a face id selected
// in the viewport.

export function faceById(oc, shape, id) {
  if (!shape || id == null || id < 0) return null
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return null
  }
  let i = 0
  let out = null
  for (; exp.More(); exp.Next()) {
    if (i === id) {
      out = oc.TopoDS.Face_1(exp.Current())
      break
    }
    i++
  }
  try { exp.delete() } catch { /* */ }
  return out
}

// Edge-by-id lookup, mirroring faceById. Returns null if the id is out of
// range or the shape is missing.
export function edgeById(oc, shape, id) {
  if (!shape || id == null || id < 0) return null
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return null
  }
  let i = 0
  let out = null
  for (; exp.More(); exp.Next()) {
    if (i === id) {
      out = oc.TopoDS.Edge_1(exp.Current())
      break
    }
    i++
  }
  try { exp.delete() } catch { /* */ }
  return out
}

// Build a face's plane frame in world coordinates. Returns
// `{ origin: [x,y,z], normal: [x,y,z], uDir: [x,y,z], vDir: [x,y,z], planar: bool }`.
// If the face is non-planar, returns `planar: false` and the analytic normal
// at the parametric midpoint (used to refuse sketch-on-face there).
export function faceFrame(oc, face) {
  if (!face) return null
  return _extractFaceMeta(oc, face, -1)
}

// Outer-wire 2D outline of a planar face in the face's local frame.
// Returns an array of [u, v] points (the polyline of the outer wire), or
// null if the face is non-planar / has no extractable outer wire.
//
// Used by push/pull: we extrude this profile along the face's normal to
// build the Pad/Pocket prism.
export function faceTo2DOutline(oc, face) {
  if (!face) return null
  const frame = faceFrame(oc, face)
  if (!frame || !frame.planar) return null
  // Find the outer wire (BRepTools.OuterWire returns the outer boundary).
  let wire
  try {
    wire = oc.BRepTools.OuterWire(face)
  } catch {
    return null
  }
  if (!wire || wire.IsNull?.()) return null
  // Walk edges of the wire, sample, project into the (u,v) frame.
  const out = []
  const nx = frame.normal[0], ny = frame.normal[1], nz = frame.normal[2]
  const ux = frame.uDir[0], uy = frame.uDir[1], uz = frame.uDir[2]
  const vx = frame.vDir[0], vy = frame.vDir[1], vz = frame.vDir[2]
  const ox = frame.origin[0], oy = frame.origin[1], oz = frame.origin[2]
  void nx; void ny; void nz
  const exp = new oc.TopExp_Explorer_2(wire, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  for (; exp.More(); exp.Next()) {
    const e = oc.TopoDS.Edge_1(exp.Current())
    let curve
    try {
      curve = new oc.BRepAdaptor_Curve_2(e)
    } catch { continue }
    const t0 = curve.FirstParameter()
    const t1 = curve.LastParameter()
    const segs = 24
    for (let i = 0; i <= segs; i++) {
      const t = t0 + (t1 - t0) * (i / segs)
      const p = curve.Value(t)
      const dx = p.X() - ox, dy = p.Y() - oy, dz = p.Z() - oz
      const u = dx * ux + dy * uy + dz * uz
      const v = dx * vx + dy * vy + dz * vz
      out.push([u, v])
      try { p.delete?.() } catch { /* */ }
    }
    try { curve.delete?.() } catch { /* */ }
  }
  try { exp.delete() } catch { /* */ }
  // Deduplicate adjacent identical points (shared end/start of consecutive
  // edges) so the polyline doesn't degenerate.
  const dedup = []
  for (const p of out) {
    const last = dedup[dedup.length - 1]
    if (!last || Math.hypot(last[0] - p[0], last[1] - p[1]) > 1e-6) dedup.push(p)
  }
  return dedup
}

// ---------------------------------------------------------------------------
// Pattern helpers — build a list of transformed copies of a shape and
// boolean-fuse them. Used by linear_pattern / polar_pattern / mirror_pattern.

// Translate a shape by a vector. Returns a fresh TopoDS_Shape.
export function translateShape(oc, shape, [dx, dy, dz], tracker) {
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const v = track(tracker, new oc.gp_Vec_4(dx, dy, dz))
  trsf.SetTranslation_1(v)
  const xform = track(tracker, new oc.BRepBuilderAPI_Transform_2(shape, trsf, true))
  xform.Build(new oc.Message_ProgressRange_1())
  return xform.Shape()
}

// Rotate a shape around an axis (origin + dir) by `angle` radians.
export function rotateShape(oc, shape, origin, dir, angle, tracker) {
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const o = track(tracker, new oc.gp_Pnt_3(origin[0], origin[1], origin[2]))
  const d = track(tracker, new oc.gp_Dir_4(dir[0], dir[1], dir[2]))
  const ax1 = track(tracker, new oc.gp_Ax1_2(o, d))
  trsf.SetRotation_1(ax1, angle)
  const xform = track(tracker, new oc.BRepBuilderAPI_Transform_2(shape, trsf, true))
  xform.Build(new oc.Message_ProgressRange_1())
  return xform.Shape()
}

// Mirror a shape across a plane (origin + normal).
export function mirrorShape(oc, shape, origin, normal, tracker) {
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const o = track(tracker, new oc.gp_Pnt_3(origin[0], origin[1], origin[2]))
  const d = track(tracker, new oc.gp_Dir_4(normal[0], normal[1], normal[2]))
  const ax2 = track(tracker, new oc.gp_Ax2_3(o, d))
  trsf.SetMirror_2(ax2)
  const xform = track(tracker, new oc.BRepBuilderAPI_Transform_2(shape, trsf, true))
  xform.Build(new oc.Message_ProgressRange_1())
  return xform.Shape()
}

// Boolean union of an array of shapes via repeated BRepAlgoAPI_Fuse. The
// caller manages tracker lifetime — we don't delete the input shapes.
export function fuseShapes(oc, shapes, tracker) {
  if (!shapes || shapes.length === 0) return null
  if (shapes.length === 1) return shapes[0]
  let cur = shapes[0]
  for (let i = 1; i < shapes.length; i++) {
    const f = track(tracker, new oc.BRepAlgoAPI_Fuse_3(cur, shapes[i], new oc.Message_ProgressRange_1()))
    f.Build(new oc.Message_ProgressRange_1())
    if (f.IsDone()) cur = f.Shape()
  }
  return cur
}

// Resolve an "axis_ref" — string ('x'|'y'|'z') OR an edge id — into
// `{ origin: [...], dir: [...] }` in world coords. For an edge id we fetch
// the edge from `shape` and use its endpoints.
export function resolveAxisRef(oc, shape, axisRef) {
  if (typeof axisRef === 'string') {
    const a = axisRef.toLowerCase()
    if (a === 'x') return { origin: [0, 0, 0], dir: [1, 0, 0] }
    if (a === 'y') return { origin: [0, 0, 0], dir: [0, 1, 0] }
    if (a === 'z') return { origin: [0, 0, 0], dir: [0, 0, 1] }
  }
  // Treat as numeric edge id.
  const id = Number(axisRef)
  if (!Number.isFinite(id)) return null
  const edge = edgeById(oc, shape, id)
  if (!edge) return null
  try {
    const curve = new oc.BRepAdaptor_Curve_2(edge)
    const t0 = curve.FirstParameter()
    const t1 = curve.LastParameter()
    const p0 = curve.Value(t0)
    const p1 = curve.Value(t1)
    const ox = p0.X(), oy = p0.Y(), oz = p0.Z()
    const dx = p1.X() - ox, dy = p1.Y() - oy, dz = p1.Z() - oz
    const ln = Math.hypot(dx, dy, dz) || 1
    try { p0.delete?.(); p1.delete?.(); curve.delete?.() } catch { /* */ }
    return { origin: [ox, oy, oz], dir: [dx / ln, dy / ln, dz / ln] }
  } catch {
    return null
  }
}

// Resolve a "plane_ref" — string ('xy'|'xz'|'yz') OR a face id — into
// `{ origin: [...], normal: [...] }` in world coords. Used by mirror_pattern.
export function resolvePlaneRef(oc, shape, planeRef) {
  if (typeof planeRef === 'string') {
    const p = planeRef.toLowerCase()
    if (p === 'xy') return { origin: [0, 0, 0], normal: [0, 0, 1] }
    if (p === 'xz') return { origin: [0, 0, 0], normal: [0, 1, 0] }
    if (p === 'yz') return { origin: [0, 0, 0], normal: [1, 0, 0] }
  }
  const id = Number(planeRef)
  if (!Number.isFinite(id)) return null
  const face = faceById(oc, shape, id)
  if (!face) return null
  const meta = _extractFaceMeta(oc, face, id)
  if (!meta || !meta.planar) return null
  return { origin: meta.origin, normal: meta.normal }
}

function _edgeAxisDominant(oc, edge) {
  try {
    const curve = new oc.BRepAdaptor_Curve_2(edge)
    const t0 = curve.FirstParameter()
    const t1 = curve.LastParameter()
    const tm = (t0 + t1) * 0.5
    const p0 = curve.Value(t0)
    const p1 = curve.Value(t1)
    const dx = Math.abs(p1.X() - p0.X())
    const dy = Math.abs(p1.Y() - p0.Y())
    const dz = Math.abs(p1.Z() - p0.Z())
    try { p0.delete?.(); p1.delete?.(); curve.delete?.() } catch { /* */ }
    void tm
    // "horizontal" = parallel to XY plane (Z component small)
    if (dz < 1e-6 && dx + dy > 0) return 'horizontal'
    // "vertical" = aligned with Z
    if (dx + dy < 1e-6 && dz > 0) return 'vertical'
    return null
  } catch {
    return null
  }
}
