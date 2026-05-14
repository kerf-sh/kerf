// Assembly content + matrix helpers.
//
// Terminology (locked in by docs/architecture.md):
//   - **Object**: one entry in a `.jscad` file's exported array, identified
//     by its `id` field. Clickable in the renderer.
//   - **Part**: a whole `.jscad` file. Contains 1+ Objects.
//   - **Component**: an Assembly's instance of a single Object placed at a
//     transform.
//
// An assembly file is a JSON document of the shape:
//   {
//     components: [
//       {
//         id: string,                  // unique within the assembly
//         file_id: string,             // references another file (the Part)
//         object_id: string,           // a single Object id from that Part's
//                                      //   exported array. Required.
//         transform: number[16],       // row-major 4x4 matrix (Three convention)
//         params?: object,             // optional params passed to JSCAD function
//         visible?: boolean,           // default true
//         color?: [r,g,b]              // 0-1 rgb override
//       },
//       ...
//     ]
//   }
//
// We use a flat 16-number matrix instead of separate position/rotation/scale so
// callers can express any affine transform (skew, mirror, etc.) with one slot
// in the JSON. The editor UI still exposes Position/Rotation/Scale fields and
// composes them via `composeMatrix` for round-tripping.
//
// Back-compat / legacy data:
//   - The earlier shape used `part_id` (renamed → `object_id`) and accepted a
//     wildcard `"*"` meaning "every Object in the source file". `parseAssembly`
//     accepts both names on read and preserves `"*"` as a transitional marker.
//     `resolveAssemblyParts` expands `"*"` at render time. The "Insert" dialog
//     and `assembly_add` LLM tool no longer produce `"*"` — new data is always
//     a concrete `object_id`. Saving an in-memory `"*"` is allowed but the
//     AssemblyEditor proactively expands wildcards once the source's object
//     list is known, so the next save migrates the file.

import * as THREE from 'three'
import { applyMatrixToGeom } from './geom3.js'
import { library } from '../cloud/api.js'

const DEG = Math.PI / 180

// Three's Matrix4.elements is column-major. We persist row-major to keep the
// JSON readable (rows of [Rxx Rxy Rxz Tx, ...]) — convert at the boundary.

function matrixToRowMajor(m4) {
  const e = m4.elements
  // e is column-major: [m11 m21 m31 m41 m12 m22 m32 m42 ...]. Transpose.
  return [
    e[0], e[4], e[8], e[12],
    e[1], e[5], e[9], e[13],
    e[2], e[6], e[10], e[14],
    e[3], e[7], e[11], e[15],
  ]
}

function matrixFromRowMajor(arr) {
  const m = new THREE.Matrix4()
  // arr is row-major; THREE.Matrix4.set takes row-major args.
  m.set(
    arr[0], arr[1], arr[2], arr[3],
    arr[4], arr[5], arr[6], arr[7],
    arr[8], arr[9], arr[10], arr[11],
    arr[12], arr[13], arr[14], arr[15],
  )
  return m
}

export function identityMatrix() {
  return [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
  ]
}

export function translationMatrix([x = 0, y = 0, z = 0] = []) {
  return [
    1, 0, 0, x,
    0, 1, 0, y,
    0, 0, 1, z,
    0, 0, 0, 1,
  ]
}

// XYZ Euler order (Three's default). Inputs in radians.
export function rotationMatrixXYZ([rx = 0, ry = 0, rz = 0] = []) {
  const m = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(rx, ry, rz, 'XYZ'))
  return matrixToRowMajor(m)
}

// Compose translation + rotation (radians, XYZ Euler) + uniform-or-vector scale.
export function composeMatrix({ position = [0, 0, 0], rotationEuler = [0, 0, 0], scale = 1 } = {}) {
  const t = new THREE.Vector3(position[0] || 0, position[1] || 0, position[2] || 0)
  const q = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(rotationEuler[0] || 0, rotationEuler[1] || 0, rotationEuler[2] || 0, 'XYZ'),
  )
  const s = Array.isArray(scale)
    ? new THREE.Vector3(scale[0] || 1, scale[1] || 1, scale[2] || 1)
    : new THREE.Vector3(scale, scale, scale)
  const m = new THREE.Matrix4().compose(t, q, s)
  return matrixToRowMajor(m)
}

// Inverse of composeMatrix. Returns { position, rotationEuler (radians, XYZ),
// scale (Vector3) }. Best-effort — if the matrix has shear it'll be approximate.
export function decomposeMatrix(rowMajorOrM4) {
  const m = Array.isArray(rowMajorOrM4) ? matrixFromRowMajor(rowMajorOrM4) : rowMajorOrM4
  const t = new THREE.Vector3()
  const q = new THREE.Quaternion()
  const s = new THREE.Vector3()
  m.decompose(t, q, s)
  const e = new THREE.Euler().setFromQuaternion(q, 'XYZ')
  return {
    position: [t.x, t.y, t.z],
    rotationEuler: [e.x, e.y, e.z],
    scale: [s.x, s.y, s.z],
  }
}

// Convert a row-major 16-array to a Three.Matrix4 (used by the renderer path).
export function toMatrix4(rowMajor) {
  if (!Array.isArray(rowMajor) || rowMajor.length !== 16) return new THREE.Matrix4()
  return matrixFromRowMajor(rowMajor)
}

// ----- Parsing / serialization ----------------------------------------------

const EMPTY = { components: [], overrides: [], mates: [] }

// Mate vocabulary — ROADMAP row 49. Dimensional types (distance/angle) carry
// a numeric `value`; the rest pin geometry directly. SolveSpace is the
// eventual solver but no solver runs in this slice — schema-only round-trip.
const MATE_TYPES = new Set([
  'coincident', 'concentric', 'parallel', 'perpendicular', 'distance', 'angle', 'tangent',
])
const DIMENSIONAL_MATE_TYPES = new Set(['distance', 'angle'])
const MATE_FEATURES = new Set(['face', 'edge', 'vertex', 'axis'])

// Wildcard sentinel for legacy `"*"` Object ids. Kept as a distinct constant
// so call sites read clearly; it's only ever produced by `parseAssembly`
// reading older data (or in-flight migration before the AssemblyEditor expands
// it on first display).
export const LEGACY_WILDCARD = '*'

// parseAssembly: tolerant JSON parser. Always returns {components: [...], overrides: [...]} —
// invalid shapes coerce to an empty assembly so the editor can still render.
//
// Legacy shapes accepted on read:
//   - `children` instead of `components`
//   - `part_id` instead of `object_id` (renamed in the new model)
//   - missing/empty object_id → '*' (legacy wildcard)
//
// `overrides` is a per-Part-file BOM override list (BOM rework):
//   [{ part_file_id, quantity_override?, non_stocked?, note? }]
// Items missing part_file_id are dropped. Used by the inline BOM panel and
// the /bom endpoint to adjust the rolled-up quantities/cost.
export function parseAssembly(jsonStr) {
  if (!jsonStr || !jsonStr.trim()) return { components: [], overrides: [] }
  let raw
  try {
    raw = JSON.parse(jsonStr)
  } catch {
    return { components: [], overrides: [], _parseError: 'Invalid JSON' }
  }
  if (!raw || typeof raw !== 'object') return { components: [], overrides: [] }

  // Back-compat shim: an earlier draft used `children` with `transform`.
  const list = Array.isArray(raw.components)
    ? raw.components
    : (Array.isArray(raw.children) ? raw.children : [])

  const components = []
  const seenIds = new Set()
  for (let i = 0; i < list.length; i++) {
    const c = list[i] || {}
    const preRef = parseExternalRef(c.external_ref)
    // External_ref components don't need a local `file_id`; the ref carries
    // the cross-project pointer. Local components still require file_id.
    if (!c.file_id && !preRef) continue
    let id = typeof c.id === 'string' && c.id.trim() ? c.id : `c${i}`
    // Force unique ids by suffixing on collision.
    let base = id
    let n = 1
    while (seenIds.has(id)) {
      id = `${base}-${n++}`
    }
    seenIds.add(id)

    let transform = Array.isArray(c.transform) && c.transform.length === 16
      ? c.transform.map((x) => Number(x) || 0)
      : identityMatrix()

    // Renamed: `part_id` → `object_id`. Accept either; missing/empty defaults
    // to the legacy wildcard `"*"` so resolution still finds geometry. Newly
    // authored data never produces `"*"`.
    const rawObj = (typeof c.object_id === 'string' && c.object_id.trim())
      ? c.object_id
      : (typeof c.part_id === 'string' && c.part_id.trim())
        ? c.part_id
        : LEGACY_WILDCARD

    const out = {
      id,
      file_id: c.file_id ? String(c.file_id) : '',
      object_id: rawObj,
      transform,
    }
    if (c.params && typeof c.params === 'object') out.params = c.params
    if (c.visible === false) out.visible = false
    if (Array.isArray(c.color) && c.color.length >= 3) {
      out.color = [
        clamp01(Number(c.color[0])),
        clamp01(Number(c.color[1])),
        clamp01(Number(c.color[2])),
      ]
    }
    // Configurations / variants — a Component may pin a specific config of
    // its referenced file ("M3" vs "M4" of a single screw Part). Empty/missing
    // means "use the file's default_config" (resolved at render time). When
    // the referenced file has no configurations, the field is ignored.
    if (typeof c.config_id === 'string' && c.config_id.trim()) {
      out.config_id = c.config_id.trim()
    }
    // Cross-project parts (ROADMAP row 68): a component may carry an
    // `external_ref` pointing at a file in another project. When present and
    // valid, the resolver dispatches via `loadExternalParts(ref)` instead of
    // the local `loadParts(file_id)` path. Required ids are project_id +
    // file_id; kind defaults to 'board_3d', pin to 'tracking_latest'.
    if (preRef) out.external_ref = preRef
    components.push(out)
  }

  // BOM overrides — optional. Tolerant: drop entries without a part_file_id,
  // coerce types so the editor never sees a malformed row.
  const overrides = []
  if (Array.isArray(raw.overrides)) {
    for (const o of raw.overrides) {
      if (!o || typeof o !== 'object') continue
      const pfid = typeof o.part_file_id === 'string' ? o.part_file_id.trim() : ''
      if (!pfid) continue
      const row = { part_file_id: pfid }
      if (o.quantity_override != null) {
        const n = Number(o.quantity_override)
        if (Number.isFinite(n) && n >= 0) row.quantity_override = Math.floor(n)
      }
      if (o.non_stocked === true) row.non_stocked = true
      if (typeof o.note === 'string' && o.note.trim()) row.note = o.note
      overrides.push(row)
    }
  }

  // Mates — ROADMAP row 49 (3D assembly mates Tier 0). Shape-only on the
  // frontend; the eventual SolveSpace subprocess writes/reads against this
  // shape. Tolerant parser: drop malformed entries.
  const mates = []
  if (Array.isArray(raw.mates)) {
    for (const m of raw.mates) {
      const parsed = parseMate(m)
      if (parsed) mates.push(parsed)
    }
  }
  return { components, overrides, mates }
}

function clamp01(n) {
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(1, n))
}

const EXTERNAL_REF_KINDS = new Set(['board_3d', 'board_outline_2d'])

// parseExternalRef: tolerant — returns null when project_id/file_id missing.
// Unknown kinds collapse to 'board_3d'; missing/empty pin → 'tracking_latest'.
//
// `last_seen_updated_at` is an ISO8601 string captured by the editor the last
// time the user viewed/consumed this cross-project source. The
// `tracking_latest` freshness chip in AssemblyEditor compares it to the live
// source's `updated_at`; when the live value is newer, the chip flips to
// "source advanced". Optional — older data without the field is treated as
// "never seen" (chip stays hidden until the first fetch records a baseline).
function parseExternalRef(raw) {
  if (!raw || typeof raw !== 'object') return null
  const projectId = typeof raw.project_id === 'string' ? raw.project_id.trim() : ''
  const fileId = typeof raw.file_id === 'string' ? raw.file_id.trim() : ''
  if (!projectId || !fileId) return null
  const rawKind = typeof raw.kind === 'string' ? raw.kind.trim() : ''
  const kind = EXTERNAL_REF_KINDS.has(rawKind) ? rawKind : 'board_3d'
  const rawPin = typeof raw.pin === 'string' ? raw.pin.trim() : ''
  const pin = rawPin || 'tracking_latest'
  const out = { project_id: projectId, file_id: fileId, kind, pin }
  const lastSeen = typeof raw.last_seen_updated_at === 'string'
    ? raw.last_seen_updated_at.trim()
    : ''
  if (lastSeen) out.last_seen_updated_at = lastSeen
  return out
}

// parseMate: tolerant — returns null for missing type/a/b, unknown type, or
// invalid feature on either side. Coerces `value` to a finite number for
// dimensional mates (distance/angle); non-dimensional types get value=null.
function parseMate(raw) {
  if (!raw || typeof raw !== 'object') return null
  const type = typeof raw.type === 'string' ? raw.type.trim() : ''
  if (!MATE_TYPES.has(type)) return null
  const a = parseMateRef(raw.a)
  const b = parseMateRef(raw.b)
  if (!a || !b) return null
  const id = typeof raw.id === 'string' && raw.id.trim() ? raw.id.trim() : ''
  const out = { id, type, a, b, value: null }
  if (DIMENSIONAL_MATE_TYPES.has(type) && raw.value != null) {
    const n = Number(raw.value)
    if (Number.isFinite(n)) out.value = n
  }
  return out
}

function parseMateRef(raw) {
  if (!raw || typeof raw !== 'object') return null
  const componentId = typeof raw.component_id === 'string' ? raw.component_id.trim() : ''
  const feature = typeof raw.feature === 'string' ? raw.feature.trim() : ''
  const featureId = typeof raw.feature_id === 'string' ? raw.feature_id.trim() : ''
  if (!componentId || !MATE_FEATURES.has(feature) || !featureId) return null
  return { component_id: componentId, feature, feature_id: featureId }
}

// serializeAssembly: produce stable, pretty JSON for storage. Always writes
// `object_id`. Components missing an object_id are dropped (defensive — the
// only way to hit this is a programmatic mutation that bypassed parseAssembly).
//
// Round-trips an optional `overrides` array (BOM rework). Empty/missing
// overrides are omitted so legacy assembly files that never gained an override
// stay byte-identical on save.
export function serializeAssembly(obj) {
  const components = (obj && Array.isArray(obj.components) ? obj.components : []).map((c) => {
    const objectId = (typeof c.object_id === 'string' && c.object_id.trim())
      ? c.object_id
      // Fall back to legacy field name in case a caller forgot to rename.
      : (typeof c.part_id === 'string' && c.part_id.trim())
        ? c.part_id
        : LEGACY_WILDCARD
    const out = {
      id: c.id,
      file_id: c.file_id,
      object_id: objectId,
      transform: Array.isArray(c.transform) && c.transform.length === 16
        ? c.transform
        : identityMatrix(),
    }
    if (c.params && typeof c.params === 'object') out.params = c.params
    if (c.visible === false) out.visible = false
    if (Array.isArray(c.color) && c.color.length >= 3) out.color = c.color
    if (typeof c.config_id === 'string' && c.config_id.trim()) {
      out.config_id = c.config_id.trim()
    }
    const ref = parseExternalRef(c.external_ref)
    if (ref) out.external_ref = ref
    return out
  })
  const overrides = (obj && Array.isArray(obj.overrides) ? obj.overrides : [])
    .map((o) => {
      if (!o || typeof o !== 'object') return null
      const pfid = typeof o.part_file_id === 'string' ? o.part_file_id.trim() : ''
      if (!pfid) return null
      const row = { part_file_id: pfid }
      if (o.quantity_override != null) {
        const n = Number(o.quantity_override)
        if (Number.isFinite(n) && n >= 0) row.quantity_override = Math.floor(n)
      }
      if (o.non_stocked === true) row.non_stocked = true
      if (typeof o.note === 'string' && o.note.trim()) row.note = o.note.trim()
      // Drop entries with no actual override content.
      if (
        row.quantity_override == null &&
        !row.non_stocked &&
        !row.note
      ) return null
      return row
    })
    .filter(Boolean)
  // Mates round-trip — drop malformed entries via the same parser.
  const mates = (obj && Array.isArray(obj.mates) ? obj.mates : [])
    .map(parseMate)
    .filter(Boolean)
  const doc = { components }
  if (overrides.length > 0) doc.overrides = overrides
  if (mates.length > 0) doc.mates = mates
  return JSON.stringify(doc, null, 2)
}

/** Append a mate row; returns a new array (input untouched). Drops invalid mates. */
export function addMate(rows, mate) {
  const list = Array.isArray(rows) ? rows : []
  const parsed = parseMate(mate)
  if (!parsed) return list.slice()
  return [...list, parsed]
}

/** Filter out the mate with the given id; returns a new array (input untouched). */
export function removeMate(rows, mateId) {
  const list = Array.isArray(rows) ? rows : []
  return list.filter((m) => m && m.id !== mateId)
}

export const EMPTY_ASSEMBLY = EMPTY

/** Restamp a row's external_ref.last_seen_updated_at; no-op if refId unmatched. */
export function restampExternalRefSeen(rows, refId, newUpdatedAt) {
  if (!Array.isArray(rows)) return rows
  let hit = false
  const next = rows.map((r) => {
    if (!r || r.id !== refId || !r.external_ref) return r
    hit = true
    return { ...r, external_ref: { ...r.external_ref, last_seen_updated_at: newUpdatedAt } }
  })
  return hit ? next : rows
}

// ----- Wildcard expansion (legacy migration) -------------------------------
//
// Expand any `object_id === "*"` components into N real components — one per
// Object in the referenced source file. Each expansion shares the original
// component's transform/visible/color so the rigid grouping is preserved.
//
// The expansion is async because we need the source's Object list (which only
// the JSCAD runner / STEP loader can produce). Caller passes a `loadObjectIds`
// fn: `(file_id) => Promise<string[]>`.
//
// Returns { components, changed } — `changed` is true iff any expansion
// occurred. Callers use this to decide whether to persist a migration.
export async function expandWildcardComponents(parsed, loadObjectIds) {
  const list = (parsed && Array.isArray(parsed.components)) ? parsed.components : []
  let changed = false
  const out = []
  const seen = new Set()
  function uniqueId(base) {
    let id = base
    let n = 1
    while (seen.has(id)) id = `${base}-${n++}`
    seen.add(id)
    return id
  }
  for (const c of list) {
    if (c.object_id !== LEGACY_WILDCARD) {
      const id = uniqueId(c.id)
      out.push({ ...c, id })
      continue
    }
    let ids
    try {
      ids = await loadObjectIds(c.file_id)
    } catch {
      ids = []
    }
    if (!Array.isArray(ids) || ids.length === 0) {
      // Source didn't resolve — keep the wildcard component as-is so the
      // resolver can still no-op it. A subsequent resolve attempt will retry.
      const id = uniqueId(c.id)
      out.push({ ...c, id })
      continue
    }
    changed = true
    for (let i = 0; i < ids.length; i++) {
      const oid = ids[i]
      const baseName = ids.length === 1 ? c.id : `${c.id}-${oid}`
      const newId = uniqueId(baseName)
      out.push({
        ...c,
        id: newId,
        object_id: oid,
      })
    }
  }
  return { components: out, changed }
}

// ----- Cycle detection ------------------------------------------------------

// cycleCheck: returns true if adding (or having) a component pointing at
// `targetFileId` from `assemblyFileId` would form a cycle.
//
// Walks the project's files map and recurses through any assembly's component
// file_ids. We require the caller to pass `getAssemblyContent(file)` — usually
// just `f => f.content` for files that already have content loaded, otherwise
// returns null and we treat it as opaque (no cycle through it).
export function cycleCheck({ assemblyFileId, targetFileId, files, getAssemblyContent }) {
  if (!assemblyFileId || !targetFileId) return false
  if (assemblyFileId === targetFileId) return true
  const byId = new Map((files || []).map((f) => [f.id, f]))
  const visited = new Set()

  function walk(fileId) {
    if (fileId === assemblyFileId) return true
    if (visited.has(fileId)) return false
    visited.add(fileId)
    const f = byId.get(fileId)
    if (!f || f.kind !== 'assembly') return false
    const content = getAssemblyContent ? getAssemblyContent(f) : (f.content ?? null)
    if (content == null) return false // unloaded; conservatively assume no cycle
    const parsed = parseAssembly(content)
    for (const c of parsed.components) {
      if (walk(c.file_id)) return true
    }
    return false
  }
  return walk(targetFileId)
}

// degToRad / radToDeg helpers for the editor UI.
export const degToRad = (d) => Number(d) * DEG
export const radToDeg = (r) => Number(r) / DEG

// ----- Resolution -----------------------------------------------------------
//
// resolveAssemblyParts: pure helper that walks an assembly's components and
// returns the flat parts list ready for the renderer/projection pipeline.
//
//   loadParts: async (fileId, configId?) => Promise<[{id, geom, color?}]>
//     Resolves a referenced file's exported Objects. The caller decides how —
//     JSCAD run, STEP load, or recursive assembly resolve. Implementation
//     lives in the workspace store so this module stays free of API/store
//     dependencies. `configId` is the component's pinned configuration (or
//     undefined when the component doesn't pin one) — the loader should
//     fall back to the file's `default_config` when this is empty.
//   loadExternalParts?: async (ref) => Promise<[{id, geom, color?}]>
//     Cross-project dispatch (ROADMAP row 68). When a component carries an
//     `external_ref`, the resolver calls this loader instead of `loadParts`.
//     Optional: when missing or throwing, the component falls through to
//     `onMissing` and contributes zero parts (graceful, no crash).
//   onMissing?: (componentId, objectId, fileId) => void   // optional warning hook
//
// Behaviour:
//   - Skip components with visible === false.
//   - For object_id === "*" (legacy): include every Object from the source
//     file. Re-id as `${componentId}/${origObjectId}`.
//   - For a specific object_id: include ONLY the Object with that id; drop
//     everything else. Re-id as just `${componentId}` (single-object body).
//   - Apply the component's 4x4 transform to each Object.
//   - Apply color override if present.
//   - If the named Object isn't found in the source's output, call
//     onMissing(componentId, objectId, fileId) and contribute zero parts for
//     that component (don't crash).
export async function resolveAssemblyParts({ content, loadParts, loadExternalParts, onMissing } = {}) {
  const parsed = parseAssembly(content)
  if (!parsed.components || parsed.components.length === 0) return []
  const out = []
  for (const c of parsed.components) {
    if (c.visible === false) continue
    const isExternal = !!c.external_ref
    if (!isExternal && !c.file_id) continue

    // External_ref dispatch: route to `loadExternalParts(ref)`. When the
    // loader is absent or throws, fall through to `onMissing` so the UI can
    // render a placeholder instead of crashing.
    let baseParts
    if (isExternal) {
      if (typeof loadExternalParts !== 'function') {
        if (typeof onMissing === 'function') {
          try { onMissing(c.id, c.object_id || '', c.external_ref.file_id) } catch { /* ignore */ }
        }
        continue
      }
      try {
        baseParts = await loadExternalParts(c.external_ref)
      } catch (err) {
        console.warn(`assembly: external_ref load failed for ${c.id}:`, err)
        if (typeof onMissing === 'function') {
          try { onMissing(c.id, c.object_id || '', c.external_ref.file_id) } catch { /* ignore */ }
        }
        continue
      }
    } else {
      try {
        baseParts = await loadParts(c.file_id, c.config_id || null)
      } catch (err) {
        console.warn(`assembly: failed to load component ${c.id}:`, err)
        continue
      }
    }
    if (!Array.isArray(baseParts) || baseParts.length === 0) continue

    // External_ref components forward every Object the loader returns
    // (no object_id filter — the cross-project loader has already resolved
    // the right part). Local components filter by object_id unless wildcard.
    const objectId = c.object_id || LEGACY_WILDCARD
    let selected
    if (isExternal || objectId === LEGACY_WILDCARD) {
      selected = baseParts
    } else {
      selected = baseParts.filter((p) => p && p.id === objectId)
      if (selected.length === 0) {
        console.warn(`assembly: component ${c.id} references missing object_id "${objectId}" in file ${c.file_id}`)
        if (typeof onMissing === 'function') {
          try { onMissing(c.id, objectId, c.file_id) } catch { /* ignore */ }
        }
        continue
      }
    }

    const m = toMatrix4(c.transform)
    const colorOverride = c.color
      ? // pack [r,g,b] in 0-1 → 0xrrggbb int (renderer accepts both ints and undefined)
        ((Math.round(c.color[0] * 255) << 16) |
         (Math.round(c.color[1] * 255) << 8) |
          Math.round(c.color[2] * 255))
      : null
    const isSingle = !isExternal && objectId !== LEGACY_WILDCARD && selected.length === 1
    for (const p of selected) {
      const transformed = applyMatrixToGeom(p.geom, m)
      if (!transformed) continue
      out.push({
        id: isSingle ? c.id : `${c.id}/${p.id}`,
        geom: transformed,
        // Preserve original component metadata so the editor can map back.
        componentId: c.id,
        origPartId: p.id,
        color: colorOverride != null ? colorOverride : p.color,
      })
    }
  }
  return out
}

// ----- Cross-project derived-artifacts cache (ROADMAP row 67 Phase 2) ------
//
// The backend exposes a per-source cache of compiled artifacts at
// `POST /api/projects/:pid/files/:fid/derived` so that consumers of a
// cross-project ref can short-circuit the recompile when the source hasn't
// changed. The on-disk cache layer just shipped (#86); the compile-on-demand
// half is still pending — a miss returns 501 with `{cached:false}` and the
// caller is expected to fall through to its own recompile path.
//
// `external_ref.kind` (the assembly-level vocab — what the consumer is asking
// for) maps onto a `derived_kind` (the backend cache vocab — what the
// producer stamps into the cache):
//
//   external_ref kind   →  derived_kind
//   --------------------  --------------------
//   board_3d            →  circuit_board_3d
//   board_outline_2d    →  sketch_geom2
//   mesh                →  jscad_mesh
//
// Unknown kinds → null (caller skips the cache and goes straight to recompile).
const DERIVED_KIND_BY_REF_KIND = {
  board_3d: 'circuit_board_3d',
  board_outline_2d: 'sketch_geom2',
  mesh: 'jscad_mesh',
}

/** Map an external_ref.kind onto its derived_kind. Returns null when unmapped. */
export function derivedKindForRefKind(kind) {
  if (!kind || typeof kind !== 'string') return null
  return DERIVED_KIND_BY_REF_KIND[kind] || null
}

// loadExternalParts: cache-aware cross-project loader. Tries the derived
// cache first (via `library.lookupDerivedArtifact`, #86) and on hit decodes
// the payload via `decodePayload(kind, payload)` — a caller-supplied decoder
// that knows how to turn the bytes into the resolver's `[{id, geom, color?}]`
// shape. On any of:
//
//   - cache miss (501) / `cached:false`
//   - decoder threw or returned an empty/invalid result
//   - lookup itself threw (network, auth, unexpected 4xx/5xx)
//
// the loader falls through to the supplied `recompile(ref)` — the existing
// fetch-source-and-run path. The cache is strictly an optimisation; the
// recompile path remains the source of truth.
//
// `lookup` defaults to `library.lookupDerivedArtifact` but can be injected
// for tests. `decodePayload` is optional: if missing or returns null/[] we
// also fall through.
//
// Write-back: after a successful recompile, if `encodePayload(kind, parts)`
// is supplied AND returns a non-null Uint8Array, we fire-and-forget call
// `store({projectId, fileId, derivedKind, payload})` so the next consumer
// skips the recompile cost. The encoder lives outside this module
// (kernel-agnostic per the existing pattern); for v1 callers can omit it
// (cache stays unpopulated until a downstream consumer wires the encoder).
// Failures (encode returns null, store throws, network error) are swallowed
// silently — the populate is a best-effort optimisation and MUST NOT block
// or alter the resolver's return value.
//
// Contract:
//   encodePayload(kind: string, parts: [{id, geom, color?}]) → Uint8Array | null
//     - Synchronous or async; awaited inside a try/catch.
//     - Return null (or throw) to skip the populate.
//   store({projectId, fileId, derivedKind, payload: Uint8Array}) → Promise
//     - Defaults to `library.storeDerivedArtifact`. Tests inject mocks.
//     - Any rejection is swallowed (debug-logged only).
export async function loadExternalParts({
  ref,
  recompile,
  // Default to the cloud library helpers so callers in production paths get
  // both the lookup and the populate for free. Tests inject mocks to keep
  // the module pure.
  lookup = library.lookupDerivedArtifact.bind(library),
  decodePayload,
  encodePayload,
  store = library.storeDerivedArtifact.bind(library),
} = {}) {
  if (!ref || typeof recompile !== 'function') return []
  const derivedKind = derivedKindForRefKind(ref.kind)
  if (derivedKind && typeof lookup === 'function') {
    let res = null
    try {
      res = await lookup({
        projectId: ref.project_id,
        fileId: ref.file_id,
        derivedKind,
      })
    } catch (err) {
      // Defensive: lookup failure must not break the resolver. Fall through.
      console.debug(`derived-cache lookup failed for ${ref.project_id}/${ref.file_id} (${derivedKind}); falling through:`, err)
      res = null
    }
    if (res && res.cached && res.payload && typeof decodePayload === 'function') {
      try {
        const parts = await decodePayload(res.derivedKind || derivedKind, res.payload)
        if (Array.isArray(parts) && parts.length > 0) return parts
        console.debug(`derived-cache decode produced empty parts for ${ref.project_id}/${ref.file_id} (${derivedKind}); falling through`)
      } catch (err) {
        console.debug(`derived-cache decode failed for ${ref.project_id}/${ref.file_id} (${derivedKind}); falling through:`, err)
      }
    } else if (res && !res.cached) {
      console.debug(`derived-cache miss for ${ref.project_id}/${ref.file_id} (${derivedKind})${res.error ? `: ${res.error}` : ''}`)
    }
  }
  const parts = await recompile(ref)
  // Fire-and-forget cache populate. Strict best-effort: any failure (encoder
  // returns null/throws, store throws, network error) is swallowed and never
  // affects the returned `parts`.
  if (
    derivedKind &&
    typeof encodePayload === 'function' &&
    typeof store === 'function' &&
    Array.isArray(parts) && parts.length > 0
  ) {
    Promise.resolve()
      .then(async () => {
        let payload
        try {
          payload = await encodePayload(derivedKind, parts)
        } catch (err) {
          console.debug(`derived-cache encode failed for ${ref.project_id}/${ref.file_id} (${derivedKind}); skipping populate:`, err)
          return
        }
        if (!(payload instanceof Uint8Array) || payload.length === 0) return
        try {
          await store({
            projectId: ref.project_id,
            fileId: ref.file_id,
            derivedKind,
            payload,
          })
        } catch (err) {
          console.debug(`derived-cache store failed for ${ref.project_id}/${ref.file_id} (${derivedKind}); ignoring:`, err)
        }
      })
      .catch(() => { /* unreachable — inner handler swallows everything */ })
  }
  return parts
}
