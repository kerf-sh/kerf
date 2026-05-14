// Zustand store for the editor workspace. One instance per browser tab — when
// the user opens a new project we just call loadProject(id) again.
//
// Owns:
//   - project metadata + file tree
//   - currently-open file's content + dirty flag
//   - chat threads + active thread + messages (incl. tool messages)
//   - "picked part" state (renderer click) and pending part_refs queued for the
//     next chat message.
//   - per-file part visibility (hiddenPartIds), session-only.
//   - the live `parts` array for the currently-open file (JSCAD or STEP).
import { create } from 'zustand'
import { api, ApiError } from '../lib/api.js'
import { runJscad, setSketchResolver, setSketchLister, setEquationsResolver as setJscadEquationsResolver, SKETCH_IMPORT_RE } from '../lib/jscadRunner.js'
import { setEquationsResolver as setOcctEquationsResolver, setActiveConfigResolver as setOcctActiveConfigResolver } from '../lib/occtRunner.js'
import { loadStep } from '../lib/stepLoader.js'
import { loadMeshFromURL } from '../lib/meshLoader.js'
import { withColorizedPart, withTranslatedPart } from '../lib/sourceEdit.js'
import { parseAssembly, resolveAssemblyParts as resolveAssemblyPartsHelper, loadExternalParts } from '../lib/assembly.js'
import { encodePayload, decodePayload } from '../lib/derivedPayload.js'
import { parseSketch, serializeSketch, defaultSketch, setSketchEquationsResolverSync } from '../lib/sketchSolver.js'
import { mergeEquationFiles } from '../lib/equations.js'
import { parsePart, serializePart, defaultPart, getActiveConfig } from '../lib/part.js'
import { parseLibraryMappings, setCircuitMapping as setCircuitMappingHelper } from '../lib/circuitMappings.js'
import {
  parseFeature, serializeFeature, DEFAULT_FEATURE, cancelFeatures, destroyOcct,
} from '../lib/occtRunner.js'
import { runCircuit, cancelCircuit, DEFAULT_CIRCUIT } from '../lib/circuitRunner.js'
import * as JSCADModeling from '@jscad/modeling'
import { extractBoardOutline } from '../lib/circuitOutline.js'
import { sketchToGeom2 } from '../lib/sketchGeom2.js'
import { meshCache } from '../lib/meshCache.js'
import { subdToBufferGeometry, meshDocToBufferGeometry } from '../lib/subdToBufferGeometry.js'
import { git as gitApi } from '../cloud/api.js'

// Prune the IndexedDB mesh cache on first store import (i.e. app start). Best-
// effort: any failure is silently swallowed so a corrupted DB can't keep the
// app from booting.
try { meshCache.prune().catch(() => {}) } catch { /* ignore */ }

// Tool names whose effects mutate files; sendMessage() refetches the tree
// and the open file's content when one of these shows up in the response.
// `restore_revision` mutates the target file (writes the historical content
// back); `list_revisions` is read-only and intentionally excluded.
const FILE_MUTATING_TOOLS = new Set([
  'write_file', 'edit_file', 'create_file', 'delete_file', 'import_step',
  'create_drawing', 'add_view_to_drawing', 'add_standard_views', 'add_dimension',
  'drawing_remove_view', 'drawing_remove_dimension',
  'add_annotation', 'remove_annotation',
  'add_centerline', 'add_break', 'add_sheet',
  'set_drawing_scale', 'set_title_field',
  'assembly_add', 'assembly_set_transform', 'assembly_set_object',
  'assembly_remove_component',
  'duplicate_object', 'delete_object',
  'create_sketch',
  // sketch_* mutation tools — these modify .sketch files and must trigger
  // a JSCAD re-eval if the open file imports the mutated sketch.
  'sketch_add_entity', 'sketch_add_constraint', 'sketch_set_constraint_value',
  'sketch_delete_entity', 'sketch_carbon_copy',
  'create_part', 'set_part_metadata', 'add_distributor_link',
  'create_feature', 'feature_pad', 'feature_pocket', 'feature_revolve',
  'feature_fillet', 'feature_chamfer', 'feature_shell', 'feature_hole',
  'restore_revision',
])

// Default seed for a new sketch file. Mirrors the LLM tool's seed so the UI
// and create_sketch produce identical starting points.
export const DEFAULT_SKETCH = serializeSketch(defaultSketch('XY'))

// Default seed for a new Part file (Library entry).
export const DEFAULT_PART = serializePart(defaultPart('New Part'))

// Default seed for a new tscircuit file. Mirrors the runner's seed so the
// editor and create_circuit tool produce identical starting points.
export { DEFAULT_CIRCUIT } from '../lib/circuitRunner.js'

// Default seed for a new Feature file (B-rep timeline). Mirrors the
// LLM tool's create_feature seed.
export { DEFAULT_FEATURE } from '../lib/occtRunner.js'

// Default seed for a new drawing file. Mirrors the LLM tool's default.
export const DEFAULT_DRAWING = JSON.stringify({
  frame: {
    size: 'A3',
    orientation: 'landscape',
    title: 'Untitled Drawing',
  },
  views: [],
  dimensions: [],
  annotations: [],
}, null, 2)

function fileKindFor(file) {
  // Map a File row → {kind: 'jscad' | 'step' | 'assembly' | 'drawing' | 'sketch' | 'part' | 'circuit' | 'folder'}
  // for the editor pipeline. We sniff by extension since the DB `kind` is the
  // broader ('file', 'folder', 'assembly', 'drawing', 'sketch', 'part') taxonomy.
  if (!file) return 'jscad'
  if (file.kind === 'folder') return 'folder'
  if (file.kind === 'assembly') return 'assembly'
  if (file.kind === 'drawing') return 'drawing'
  if (file.kind === 'sketch') return 'sketch'
  if (file.kind === 'part') return 'part'
  if (file.kind === 'feature') return 'feature'
  if (file.kind === 'circuit') return 'circuit'
  if (file.kind === 'equations') return 'equations'
  if (file.kind === 'script') return 'script'
  if (file.kind === 'subd') return 'subd'
  if (file.kind === 'mesh') return 'mesh'
  const name = (file.name || '').toLowerCase()
  // Circuit must be checked BEFORE generic .tsx so a tscircuit file routes to
  // the CircuitEditor; pure .tsx files (if we ever support them) keep the
  // default JSCAD/text path. Script (.script.ts) checked BEFORE generic .ts
  // for the same reason — engine is deferred but the read-only viewer routes
  // by extension today.
  if (name.endsWith('.script.ts')) return 'script'
  if (name.endsWith('.circuit.tsx')) return 'circuit'
  if (name.endsWith('.step') || name.endsWith('.stp')) return 'step'
  if (name.endsWith('.assembly')) return 'assembly'
  if (name.endsWith('.drawing')) return 'drawing'
  if (name.endsWith('.sketch')) return 'sketch'
  if (name.endsWith('.part')) return 'part'
  if (name.endsWith('.feature')) return 'feature'
  if (name.endsWith('.equations')) return 'equations'
  if (name.endsWith('.subd')) return 'subd'
  if (name.endsWith('.mesh')) return 'mesh'
  return 'jscad'
}

const initial = {
  projectId: null,
  project: null,
  files: [],
  currentFileId: null,
  currentFile: null,
  currentFileContent: '',
  dirty: false,
  saving: false,
  loadingProject: false,
  loadError: null,

  // Live parts for the currently-open file, regardless of source.
  parts: [],
  partsError: null,
  loadingParts: false,

  threads: [],
  currentThreadId: null,
  messages: [],
  loadingMessages: false,
  sending: false,

  pickedPart: null,        // {file_id, part_id, label?} — last clicked
  pendingPartRefs: [],     // attached to next message

  // Per-file visibility map: Map<file_id, Set<part_id>>. Session-only.
  hiddenPartIds: new Map(),

  // Measure-tool state (session-only; not persisted).
  // mode ∈ 'object' | 'face' | 'edge' | 'vertex'
  measureMode: 'object',
  // Up to 2 entries: { partId, kind, featureId }
  selectedFeatures: [],
  // Transient toast for source-edit failures, etc.
  toast: null,

  // Assembly state (only set when current file is an assembly):
  //   parsedAssembly  — the {components: [...]} object parsed from file content
  //   selectedComponentId — for per-component highlight in the renderer
  parsedAssembly: null,
  selectedComponentId: null,

  // Drawing state (only set when current file is a drawing):
  //   parsedDrawing       — the {frame, views, dimensions} object
  //   drawingSourceParts  — Map<source_file_id, parts[]>
  //   selectedDimensionId — id of the dim under user selection (for highlight)
  parsedDrawing: null,
  drawingSourceParts: new Map(),
  selectedDimensionId: null,
  // Annotations: id of the user-selected annotation (for highlight + delete).
  selectedAnnotationId: null,

  // Sketch state (only set when current file is a sketch):
  //   parsedSketch         — the {version, plane, entities, constraints, ...} object
  //   sketchStatus         — solver status: 'fully' | 'under' | 'over' | 'conflict' | null
  //   sketchDof            — degrees-of-freedom estimate
  //   sketchConflicts      — ids of conflicting constraints from planegcs
  parsedSketch: null,
  sketchStatus: null,
  sketchDof: 0,
  sketchConflicts: [],

  // Part state (only set when current file is kind='part'):
  //   currentPart — the parsed Part object for the open file. Updates flow
  //                 through updatePart(patch) which serializes + records a
  //                 revision so Cmd+Z works.
  currentPart: null,

  // Feature state (only set when current file is kind='feature'):
  //   currentFeature — the parsed FeatureTree for the open file. Updates flow
  //                    through updateFeature(patch) which serializes +
  //                    records a revision so Cmd+Z works.
  //   featureMeshes  — last successful occt evaluation result. Held here so
  //                    Renderer reuses the previous mesh while a new
  //                    evaluation is in flight.
  //   featureError   — last evaluation error string; null on success.
  //   featureLoading — true while the worker is mid-evaluate.
  currentFeature: null,
  featureMeshes: [],
  featureError: null,
  featureLoading: false,

  // Phase 3 viewport selection state (per-feature-file, session-only).
  //   featureSelection.faceIds — Set<"partId|faceId"> (string keys)
  //   featureSelection.edgeIds — Set<"epartId|edgeId">
  //   featurePickMode          — null | 'face' | 'edge' | 'pushpull' | 'sketch_on_face' | 'one_shot_face' | 'one_shot_edge'
  //   featurePickTarget        — when pickMode is one-shot, the inspector field
  //                              key that should receive the picked id(s).
  //                              { featureId, fieldKey, accept: 'face'|'edge'|'edge_multi' }
  // Note: cleared on file switch + on structural tree edits (FeatureView
  // owns the clear-on-tree-change logic).
  featureSelection: { faceIds: new Set(), edgeIds: new Set() },
  featurePickMode: null,
  featurePickTarget: null,

  // Circuit state (only set when current file is kind='circuit', i.e.
  // `.circuit.tsx` files routed through tscircuit). The compile pipeline
  // produces a bucketed CircuitJSON that the editor's Schematic / PCB / 3D
  // tabs all read from. Nothing here is persisted — the .circuit.tsx source
  // is the single source of truth and we recompile on every meaningful edit.
  //   currentCircuit  — { raw, schematic, pcb, threeD, errors } | null
  //   circuitError    — string error from the most recent compile, or null
  //   circuitLoading  — true while a compile is in flight
  currentCircuit: null,
  circuitError: null,
  circuitLoading: false,
  // Cross-view selection for the circuit editor: refdes (e.g. "R1") of the
  // active component, and/or a net name. Set by the CircuitComponentsPanel
  // and consumed by CircuitEditor to highlight Schematic / PCB / 3D.
  selectedCircuitRefdes: null,
  selectedCircuitNet: null,
  selectedCircuitComponentId: null,

  // BOM state (project-level, set on demand by loadBOM(projectId)):
  bomState: { rows: [], total: null, warnings: [], loading: false, error: null },

  // Configurations / variants — per-file picked-config map (session-only).
  // Keyed by fileId; the value is the picked `configurations[].id`. When a
  // file has configurations and no entry here, the parsed file's
  // `default_config` (or the first config) wins. Persisted in-memory only:
  // navigating away and back resets to the file's default.
  // Set via setCurrentConfig(fileId, configId); read via getActiveConfigParams(fileId)
  // and the editor's <select> control.
  currentConfigByFile: {},

  // Equations cache (project-level). Populated by refreshEquationsCache —
  // walks every `.equations` file in the tree, parses + evaluates them in
  // declaration order, merges (last-loaded wins on duplicate name), and
  // exposes the result as { values, errors, duplicates }.
  // Consumed by:
  //   - jscadRunner (async, via setEquationsResolver) → injected as `params`
  //   - occtRunner (async)                            → substitutes ${name} in features/sketches
  //   - sketchSolver (sync)                            → resolves dimensional constraint values
  // Refreshed whenever a `.equations` file is created/edited/deleted.
  equationsScope: { values: {}, errors: [], duplicates: [] },

  // In-flight chunked upload state. Null when no upload is running.
  // {filename, received, total, bytes, totalBytes, status: 'hashing'|'uploading'|'error',
  //  uploadId, abort, error}. The FileTree subscribes to this to draw a
  //  progress bar + Cancel button.
  uploadProgress: null,

  // File revision drawer + soft-undo/redo state. `revisions` is the most
  // recent slice for `currentFileId` (newest first). `redoStack` lets
  // Cmd+Shift+Z reapply a revision the user just undid (per-file scope —
  // entries carry their fileId so switching files clears the relevant ones).
  // `editorFocused` mirrors Monaco focus so workspace-level Cmd+Z can yield
  // to Monaco's buffer-undo while the editor has focus.
  revisionDrawerOpen: false,
  revisions: [],
  loadingRevisions: false,
  redoStack: [],
  editorFocused: false,

  // ---- Git (cloud-only) ----
  // Owned by the GitPanel. `gitRepoState` is 'unknown' until we probe; the
  // panel renders an empty-state CTA when it's 'absent' and the graph + branch
  // selector when 'ready'. `gitError` surfaces the last failed op as an inline
  // banner — the panel has its own dedicated real estate, so we deliberately
  // don't route git failures through the global `toast` channel.
  gitOpen: false,
  gitRepoState: 'unknown',
  gitBranch: '',
  gitBranches: [],
  gitCommits: [],
  gitLoading: false,
  gitError: null,

  // ---- Activity timeline ----
  // Slide-out panel showing the merged event feed for a project. Lazily
  // populated — the panel calls loadActivity() on mount, so projects the
  // user never opens the panel for don't pay the round-trip cost.
  // `activityNextCursor` is the oldest ISO timestamp on the current page,
  // returned by the backend; nil means "no more pages".
  activityOpen: false,
  activityEvents: [],
  activityLoading: false,
  activityError: null,
  activityNextCursor: null,
}

// Tolerant JSON parse for drawing content. Empty/blank → defaults.
//
// Multi-sheet shape (canonical):
//   { sheets: [{ id, frame, views, dimensions, annotations, centerlines, breaks, symbols }, ...] }
// Legacy single-sheet shape:
//   { frame, views, dimensions, annotations }
//
// On read we ALWAYS produce a `sheets[]` array. If the file is in the legacy
// shape we wrap it in a single-element sheets array so the renderer code can
// be sheet-agnostic. The serializer writes both formats: `sheets[]` plus a
// top-level mirror of sheets[0] so downstream tools still compatible with the
// old shape see something meaningful.
//
// Back-compat: older angular dimensions stored {a:vertex, b:firstArm,
// offset:degrees} (offset reused as fan-open angle, radius implicit). Migrate
// those into the new {vertex, a, b, radius} shape on read.
function defaultSheet(idx = 0) {
  return {
    id: shortId('sh'),
    frame: { size: 'A3', orientation: 'landscape', title: 'Untitled Drawing', template: 'default' },
    views: [],
    dimensions: [],
    annotations: [],
    centerlines: [],
    breaks: [],
    symbols: [],
  }
}

function migrateAnnotations(arr) {
  if (!Array.isArray(arr)) return []
  return arr.map((a) => (a && a.id) ? a : { ...(a || {}), id: shortId('ann') })
}

function normalizeSheet(s) {
  // Coerce a sheet-shaped object to the canonical form, generating ids and
  // filling missing arrays. Tolerant of either the legacy {frame,views,...}
  // top-level shape or a partial sheet payload from a fresh tool call.
  const dimensions = Array.isArray(s?.dimensions) ? s.dimensions.map(migrateDimension) : []
  const annotations = migrateAnnotations(s?.annotations)
  const symbols = Array.isArray(s?.symbols)
    ? s.symbols.map((y) => (y && y.id) ? y : { ...(y || {}), id: shortId('sym') })
    : []
  const centerlines = Array.isArray(s?.centerlines)
    ? s.centerlines.map((c) => (c && c.id) ? c : { ...(c || {}), id: shortId('cl') })
    : []
  const breaks = Array.isArray(s?.breaks)
    ? s.breaks.map((b) => (b && b.id) ? b : { ...(b || {}), id: shortId('br') })
    : []
  return {
    id: s?.id || shortId('sh'),
    frame: s?.frame || { size: 'A3', orientation: 'landscape', title: 'Untitled Drawing', template: 'default' },
    views: Array.isArray(s?.views) ? s.views : [],
    dimensions, annotations, centerlines, breaks, symbols,
  }
}

function parseDrawing(content) {
  const text = (content || '').trim()
  if (!text) {
    return { sheets: [defaultSheet()], currentSheet: 0 }
  }
  try {
    const obj = JSON.parse(text)
    let sheets
    if (Array.isArray(obj.sheets) && obj.sheets.length > 0) {
      sheets = obj.sheets.map(normalizeSheet)
    } else {
      sheets = [normalizeSheet(obj)]
    }
    return { sheets, currentSheet: 0 }
  } catch {
    return { sheets: [defaultSheet()], currentSheet: 0 }
  }
}

// Serialize the canonical multi-sheet shape back to JSON. Writes `sheets[]`
// AND mirrors sheets[0]'s frame/views/dimensions/annotations to top-level
// for back-compat with any reader that still expects the old shape.
function serializeDrawing(parsed) {
  const sheets = parsed?.sheets?.map(normalizeSheet) || [defaultSheet()]
  const head = sheets[0]
  const out = {
    sheets,
    // Legacy top-level mirror of sheet 0:
    frame: head.frame,
    views: head.views,
    dimensions: head.dimensions,
    annotations: head.annotations,
  }
  return JSON.stringify(out, null, 2)
}

function migrateDimension(d) {
  if (!d || typeof d !== 'object') return d
  if (d.kind !== 'angular') return d
  // Already in the new shape — has explicit `vertex` field.
  if (d.vertex && typeof d.vertex.x === 'number') return d
  // Old shape: a = vertex, b = arm-1 endpoint, offset = arm-2 angle in
  // degrees relative to a→b. Build the new {vertex, a, b, radius} form.
  const vertex = d.a || { x: 0, y: 0 }
  const armA = d.b || { x: 1, y: 0 }
  const dx = armA.x - vertex.x
  const dy = armA.y - vertex.y
  const r = Math.hypot(dx, dy) || 10
  const a0 = Math.atan2(dy, dx)
  const a1 = a0 + (Number(d.offset) || 0) * Math.PI / 180
  const armB = {
    x: vertex.x + r * Math.cos(a1),
    y: vertex.y + r * Math.sin(a1),
  }
  const next = {
    ...d,
    vertex,
    a: armA,
    b: armB,
    radius: r,
  }
  // Drop the legacy `offset` so the migrated form serializes cleanly.
  delete next.offset
  return next
}

// Mint short ids for view/dimension entries created in the UI. Backend uses
// the same prefix convention (see drawing_tools.go) but generates UUIDs;
// crypto.randomUUID is fine for a frontend-only id.
function shortId(prefix) {
  let s
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    s = crypto.randomUUID().slice(0, 8)
  } else {
    s = Math.random().toString(36).slice(2, 10)
  }
  return `${prefix}-${s}`
}

// Per-(file_id + content-hash) cache of {parts} produced by running a JSCAD
// or STEP file. Module-scoped so it survives store resets and the editor
// reusing the same source file across many assemblies.
const componentResultCache = new Map()
function cacheKey(fileId, contentSig) {
  return `${fileId}::${contentSig}`
}
// Tiny djb2 string hash; used to invalidate the cache when a referenced file's
// content changes. updated_at would also work but isn't always available on
// list-only File rows.
function strHash(s) {
  if (!s) return '0'
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return String(h >>> 0)
}

// Compute the absolute path (leading '/') for a file in the project tree by
// walking its parent_id chain. Returns '' if the file is not found.
export function fileAbsPath(files, fileId) {
  if (!Array.isArray(files) || !fileId) return ''
  const byId = new Map(files.map((f) => [f.id, f]))
  const file = byId.get(fileId)
  if (!file) return ''
  const segs = []
  let cur = file
  let safety = 0
  while (cur && safety++ < 64) {
    segs.unshift(cur.name)
    if (!cur.parent_id) break
    cur = byId.get(cur.parent_id)
  }
  return '/' + segs.join('/')
}

// Return true if `jscadSource` contains an `import X from '...path'` line
// whose path matches `sketchAbsPath`. The regex is reset before each use
// because it's a stateful `/gm` pattern exported from jscadRunner.
export function jscadImportsSketch(jscadSource, sketchAbsPath) {
  if (!jscadSource || !sketchAbsPath) return false
  // Build a fresh copy of the regex to avoid stateful lastIndex issues.
  const re = new RegExp(SKETCH_IMPORT_RE.source, SKETCH_IMPORT_RE.flags)
  let match
  while ((match = re.exec(jscadSource)) !== null) {
    const importedPath = match[2]
    // Normalise: strip a leading './' so './foo.sketch' and '/foo.sketch' don't
    // mismatch; the resolver accepts both forms.
    const norm = importedPath.startsWith('./')
      ? importedPath.slice(1)     // './foo.sketch' → '/foo.sketch'
      : importedPath.startsWith('/')
        ? importedPath            // '/foo.sketch' unchanged
        : '/' + importedPath      // 'foo.sketch' → '/foo.sketch'
    if (norm === sketchAbsPath) return true
  }
  return false
}

export const useWorkspace = create((set, get) => ({
  ...initial,

  // ---- Project + files ----
  loadProject: async (id) => {
    set({ projectId: id, loadingProject: true, loadError: null })
    // Register the sketch resolver so JSCAD code in this project can do
    // `import profile from '/foo.sketch'`. The resolver looks up the file
    // by path against the current project's tree, fetches its content, and
    // returns it; the runner then parses + builds a Geom2.
    setSketchResolver(async (path) => {
      const state = useWorkspace.getState()
      if (state.projectId !== id) return null
      const file = findFileByPath(state.files, path)
      if (!file) return null
      try {
        const fresh = await api.getFile(state.projectId, file.id)
        return { content: fresh.content || '' }
      } catch {
        return null
      }
    })
    // Sketch lister: returns absolute paths of every .sketch file in the
    // current project tree. Used by resolveSketchImports to generate a
    // diagnostic "available sketches: ..." hint when an import can't be found.
    setSketchLister(() => {
      const state = useWorkspace.getState()
      if (state.projectId !== id) return []
      return collectSketchPaths(state.files)
    })
    // Equations resolver: walks every `.equations` file in the project,
    // parses + evaluates them in declaration order, and returns the merged
    // {values, errors, duplicates} scope. The async variant is consumed by
    // jscadRunner / occtRunner (substitution happens before posting to the
    // worker); the sync variant feeds the planegcs solver in sketchSolver,
    // which can't await per-constraint. Both share an in-store cache that
    // the equations editor invalidates on save (see refreshEquationsCache).
    const equationsAsync = async () => {
      const state = useWorkspace.getState()
      if (state.projectId !== id) return { values: {}, errors: [], duplicates: [] }
      // Cached from the most recent refreshEquationsCache call.
      if (state.equationsScope) return state.equationsScope
      return await get().refreshEquationsCache()
    }
    setJscadEquationsResolver(equationsAsync)
    setOcctEquationsResolver(equationsAsync)
    setSketchEquationsResolverSync(() => {
      const state = useWorkspace.getState()
      return state.equationsScope || { values: {}, errors: [], duplicates: [] }
    })
    // Configurations / variants — the OCCT runner pulls the open feature
    // file's active-config params via this resolver every runFeatures call,
    // so a config switch triggers a fresh substitution. JSCAD calls pass
    // configParams explicitly via the editor's debounced run loop.
    setOcctActiveConfigResolver(() => {
      const state = useWorkspace.getState()
      if (!state.currentFileId) return null
      return state.getActiveConfigParams(state.currentFileId)
    })
    try {
      const [project, files, threads] = await Promise.all([
        api.getProject(id),
        api.listFiles(id),
        api.listThreads(id).catch(() => []),
      ])

      // Pick a default file: first non-folder, prefer name === 'main.jscad'.
      const editable = files.filter((f) => f.kind !== 'folder')
      const main = editable.find((f) => f.name === 'main.jscad') || editable[0] || null

      set({
        project, files, threads,
        loadingProject: false,
        currentThreadId: threads[0]?.id ?? null,
      })

      // Warm the equations cache so the first JSCAD/feature evaluation has
      // resolved params available. This runs before selectFile() so the
      // initial render of main.jscad sees the param scope.
      try { await get().refreshEquationsCache() } catch { /* tolerate */ }

      if (main) await get().selectFile(main.id)
      if (threads[0]) await get().selectThread(threads[0].id)
    } catch (err) {
      set({ loadingProject: false, loadError: err?.message || String(err) })
    }
  },

  selectFile: async (fileId) => {
    if (!fileId) return
    set({ currentFileId: fileId, dirty: false })
    await get().loadFileForEditor(fileId)
  },

  // Routes a file load to the JSCAD or STEP pipeline depending on extension.
  // Sets currentFile, currentFileContent, parts, partsError as appropriate.
  loadFileForEditor: async (fileId) => {
    const { projectId } = get()
    if (!projectId || !fileId) return
    set({ loadingParts: true, partsError: null })
    try {
      const file = await api.getFile(projectId, fileId)
      const kind = fileKindFor(file)
      if (kind === 'drawing') {
        // Drawings are JSON; the DrawingView re-projects sources on the fly
        // using parts pulled from `drawingSourceParts`. We don't populate
        // `parts` for the open drawing itself.
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          parsedDrawing: parseDrawing(file.content ?? ''),
          loadingParts: false,
          partsError: null,
        })
        // Resolve source files asynchronously; results land in
        // drawingSourceParts (a Map<file_id, parts>). Triggers a re-render
        // of DrawingView once each source resolves.
        await get().resolveDrawingSources()
        return
      }
      if (kind === 'sketch') {
        // Sketches are JSON edited via the dedicated SketchView. The 3D
        // renderer above shows context geometry only (visible_3d files);
        // the sketch's own geometry is 2D and lives inside SketchView.
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          parsedSketch: parseSketch(file.content ?? ''),
          sketchStatus: null,
          sketchDof: 0,
          sketchConflicts: [],
          loadingParts: false,
          partsError: null,
        })
        return
      }
      if (kind === 'feature') {
        // Feature files are JSON edited via FeatureView. The OCCT worker
        // produces meshes that FeatureView feeds into Renderer directly;
        // the standard `parts` array isn't used for the open feature
        // (FeatureView keeps its own meshes state via the store slice
        // `featureMeshes`). Cancel any in-flight occt run from a previously
        // open feature so the next one's debounce starts clean.
        cancelFeatures()
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          currentFeature: parseFeature(file.content ?? ''),
          featureMeshes: [],
          featureError: null,
          featureLoading: false,
          // Reset viewport selection on file switch — selection state is
          // session-only AND scoped to one feature file at a time.
          featureSelection: { faceIds: new Set(), edgeIds: new Set() },
          featurePickMode: null,
          featurePickTarget: null,
          loadingParts: false,
          partsError: null,
        })
        return
      }
      if (kind === 'circuit') {
        // .circuit.tsx files. The CircuitEditor owns the Source/Schematic/PCB/3D
        // tabs and reads from currentCircuit / circuitError. We don't populate
        // `parts` for the open circuit — the 3D tab rebuilds its parts list
        // from the circuit JSON internally.
        cancelCircuit()
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          currentCircuit: null,
          circuitError: null,
          circuitLoading: false,
          selectedCircuitRefdes: null,
          selectedCircuitNet: null,
          loadingParts: false,
          partsError: null,
        })
        // Kick off an initial compile so the tabs aren't empty on first open.
        // The CircuitEditor's debounced compile will take over from here as
        // the user types.
        get().compileCircuit(file.content ?? '')
        return
      }
      if (kind === 'part') {
        // Parts are JSON metadata edited via LibraryEditor. We DO populate
        // `parts` if the Part has a model_storage_key — the LibraryEditor's
        // 3D preview reuses the standard Renderer with a single-file scene,
        // and that scene needs a parts array.
        const part = parsePart(file.content ?? '')
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          currentPart: part,
          loadingParts: false,
          partsError: null,
        })
        // Defer 3D-model resolution to LibraryEditor (it knows when the user
        // wants the preview rendered) so loading a Part with a 100MB STEP
        // model doesn't block the UI on every focus.
        return
      }
      if (kind === 'equations') {
        // Equations files are JSON edited via the dedicated EquationsEditor.
        // The 3D renderer above shows nothing — equations have no geometry of
        // their own; they affect every other open file via the param scope.
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          loadingParts: false,
          partsError: null,
        })
        return
      }
      if (kind === 'subd') {
        // Subdivision surface file (.subd): JSON with a control_mesh +
        // subdivision_level.  We run the Catmull-Clark subdivider client-side
        // and push the resulting BufferGeometry into parts so the standard
        // Renderer displays it immediately.
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          loadingParts: false,
          partsError: null,
        })
        try {
          const doc = JSON.parse(file.content ?? '{}')
          const geom = subdToBufferGeometry(doc)
          if (get().currentFileId === fileId) {
            set({
              parts: [{ id: file.id, geom, color: 0xc9a96b }],
              loadingParts: false,
              partsError: null,
            })
          }
        } catch (err) {
          if (get().currentFileId === fileId) {
            set({ loadingParts: false, partsError: err?.message || 'Failed to load subd' })
          }
        }
        return
      }
      if (kind === 'mesh') {
        // Triangle mesh file (.mesh): JSON with vertices, indices, optional normals.
        // Push directly into a BufferGeometry; no subdivision step.
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          loadingParts: false,
          partsError: null,
        })
        try {
          const meshDoc = JSON.parse(file.content ?? '{}')
          const geom = meshDocToBufferGeometry(meshDoc)
          if (get().currentFileId === fileId) {
            set({
              parts: [{ id: file.id, geom, color: 0x6b9bc9 }],
              loadingParts: false,
              partsError: null,
            })
          }
        } catch (err) {
          if (get().currentFileId === fileId) {
            set({ loadingParts: false, partsError: err?.message || 'Failed to load mesh' })
          }
        }
        return
      }
      if (kind === 'assembly') {
        set({
          currentFile: file,
          currentFileContent: file.content ?? '',
          dirty: false,
          parts: [],
          parsedAssembly: parseAssembly(file.content ?? ''),
        })
        try {
          const parts = await resolveAssemblyParts(get, projectId, file.content ?? '')
          if (get().currentFileId === fileId) {
            set({ parts, loadingParts: false, partsError: null })
          }
        } catch (err) {
          if (get().currentFileId === fileId) {
            set({ loadingParts: false, partsError: err?.message || 'Assembly load failed', parts: [] })
          }
        }
        return
      }
      if (kind === 'step') {
        // Binary asset. Performance Phase 3: when the server has produced
        // a pre-tessellated .glb (file.mesh_url is set), fetch + parse via
        // GLTFLoader — orders of magnitude cheaper than re-running the
        // OCCT WASM in-browser. Fall back to loadStep when:
        //   - the tessellation job hasn't finished (mesh_url null), or
        //   - fetch / parse of the .glb fails for any reason (network,
        //     stale cache, malformed blob).
        // We never let a glb-path failure surface to the user without
        // first trying the legacy in-browser path; that keeps existing
        // projects (uploaded before Phase 3) working unchanged.
        set({
          currentFile: file,
          currentFileContent: '',
          dirty: false,
          parts: [],
        })
        try {
          let parts = null
          if (file.mesh_url) {
            try {
              const out = await loadMeshFromURL(file.mesh_url)
              if (out?.parts?.length) parts = out.parts
            } catch (err) {
              // Don't fail loudly — log and let the STEP fallback run.
              console.warn('mesh url load failed, falling back to STEP:', err)
            }
          }
          if (!parts) {
            const buf = await api.downloadFileURL(projectId, fileId)
            const out = await loadStep(buf)
            parts = out.parts || []
          }
          // Only commit if this is still the open file.
          if (get().currentFileId === fileId) {
            set({ parts, loadingParts: false, partsError: null })
          }
        } catch (err) {
          if (get().currentFileId === fileId) {
            set({
              loadingParts: false,
              partsError: err?.message || 'Failed to load STEP',
              parts: [],
            })
          }
        }
        return
      }
      // JSCAD / text path.
      set({
        currentFile: file,
        currentFileContent: file.content ?? '',
        dirty: false,
      })
      // Try the IndexedDB mesh cache first (keyed by SHA-256 of source). Hit
      // → instant parts without touching the worker. Miss → run JSCAD via the
      // worker, then store the result for next time.
      try {
        const content = file.content ?? ''
        const key = await meshCache.hashContent(content)
        const cached = await meshCache.get(key)
        if (cached && get().currentFileId === fileId) {
          set({ parts: cached.parts || [], partsError: null, loadingParts: false })
          return
        }
        // Configurations / variants — for JSCAD files we keep configs in a
        // structured leading comment for later. For Part/Feature/Sketch the
        // workspace has parsed-* slots already populated by the relevant
        // branch above; this JSCAD-text path passes null (no configs on
        // raw .jscad files in v1; the dropdown stays hidden).
        const res = await runJscad(content, null)
        if (get().currentFileId !== fileId) return
        if (res?.stale) return
        if (res.error) {
          set({ partsError: res.error, loadingParts: false })
        } else {
          set({ parts: res.parts || [], partsError: null, loadingParts: false })
          // Best-effort cache store; tolerate failure silently.
          meshCache.put(key, res.parts || []).catch(() => {})
        }
      } catch (err) {
        if (get().currentFileId === fileId) {
          set({ partsError: err?.message || String(err), loadingParts: false })
        }
      }
    } catch (err) {
      set({ loadingParts: false, loadError: err?.message || String(err) })
    }
  },

  // Setter used by the editor's debounced re-run — keeps parts in sync with
  // the user's typing without re-fetching the file.
  setLiveParts: (parts) => set({ parts: parts || [] }),
  setPartsError: (msg) => set({ partsError: msg }),

  // Compile a `.circuit.tsx` source through tscircuit and stash the result.
  //
  // Mirrors the JSCAD compile loop:
  //   - Sets circuitLoading=true while the worker is busy.
  //   - Discards stale results via the runner's runId mechanism — only the
  //     latest run wins, older ones resolve as `{ stale: true }` and we
  //     no-op.
  //   - On error we keep the previous successful currentCircuit visible so
  //     the user can keep editing without the views going blank.
  compileCircuit: async (source) => {
    set({ circuitLoading: true })
    let res
    try {
      res = await runCircuit(source || '')
    } catch (err) {
      set({ circuitLoading: false, circuitError: err?.message || String(err) })
      return
    }
    if (res?.stale) {
      // A newer compile took over; do nothing.
      return
    }
    if (res?.error) {
      set({ circuitLoading: false, circuitError: res.error })
      return
    }
    set({
      circuitLoading: false,
      circuitError: null,
      currentCircuit: {
        raw: res.raw || [],
        schematic: res.schematic || [],
        pcb: res.pcb || [],
        threeD: res.threeD || [],
        errors: res.errors || [],
      },
    })
  },

  editContent: (text) => {
    set({ currentFileContent: text, dirty: true })
  },

  // Update the open assembly's JSON content. Used by the AssemblyEditor on
  // every field change. Updates parsedAssembly + parts in lock-step (debounced
  // by the editor). Setting `skipReresolve=true` lets the caller avoid the
  // re-render cost when only stale serialized JSON differs (rare).
  editAssemblyContent: async (text, { skipReresolve = false } = {}) => {
    const { projectId, currentFileId } = get()
    set({ currentFileContent: text, dirty: true, parsedAssembly: parseAssembly(text) })
    if (skipReresolve || !projectId || !currentFileId) return
    try {
      const parts = await resolveAssemblyParts(get, projectId, text)
      if (get().currentFileId === currentFileId) {
        set({ parts, partsError: null })
      }
    } catch (err) {
      if (get().currentFileId === currentFileId) {
        set({ partsError: err?.message || 'Assembly resolve failed' })
      }
    }
  },

  selectComponent: (componentId) => {
    set({ selectedComponentId: componentId || null })
  },

  selectCircuitRefdes: (refdes) => {
    set({ selectedCircuitRefdes: refdes || null, selectedCircuitNet: null })
  },
  selectCircuitNet: (name) => {
    set({ selectedCircuitNet: name || null, selectedCircuitRefdes: null })
  },
  selectCircuitComponent: (id) => {
    set({ selectedCircuitComponentId: id || null })
  },

  // Library-mapping accessors for the active circuit file. The mapping lives
  // as a top-of-file comment in the TSX source (see lib/circuitMappings.js).
  // Reading is a pure parse off the in-memory content; writing rewrites the
  // marker comment, marks the file dirty, and lets the autosave loop persist.
  circuitLibraryMappings: () => parseLibraryMappings(get().currentFileContent),
  setCircuitLibraryMapping: (refdes, partFileId) => {
    if (!refdes) return
    const next = setCircuitMappingHelper(get().currentFileContent || '', refdes, partFileId)
    set({ currentFileContent: next.content, dirty: true })
  },

  saveFile: async () => {
    const { projectId, currentFileId, currentFileContent, dirty, currentFile } = get()
    if (!projectId || !currentFileId || !dirty) return
    // Don't try to save STEP files — they're binary.
    if (fileKindFor(currentFile) === 'step') {
      set({ dirty: false })
      return
    }
    set({ saving: true })
    try {
      const updated = await api.updateFile(projectId, currentFileId, { content: currentFileContent })
      set((s) => ({
        saving: false,
        dirty: false,
        currentFile: updated,
        files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
      }))
      // If we just saved an `.equations` file, refresh the cached scope so the
      // next JSCAD/feature/sketch evaluation picks up the new values.
      if (currentFile && (currentFile.kind === 'equations' ||
          (currentFile.name || '').toLowerCase().endsWith('.equations'))) {
        try { await get().refreshEquationsCache() } catch { /* tolerate */ }
      }
    } catch (err) {
      set({ saving: false, loadError: err?.message || String(err) })
    }
  },

  // Create a sketch on a feature file's face. The new sketch's plane is
  // `{type: 'face', file_id, feature_node_id, face_id}` — the sketch view uses
  // these to compute the world-space transform via faceFrame from the OCCT
  // worker. v1 only supports planar faces (the worker rejects non-planar).
  // Returns the created file row, or null on failure.
  createSketchOnFace: async ({ parentId = null, name = 'sketch-on-face.sketch', featureFileId, featureNodeId, faceId }) => {
    const { projectId } = get()
    if (!projectId || !featureFileId || faceId == null) return null
    const seed = JSON.stringify({
      version: 1,
      plane: {
        type: 'face',
        file_id: featureFileId,
        feature_node_id: featureNodeId || null,
        face_id: faceId,
      },
      entities: [{ id: 'origin', type: 'point', x: 0, y: 0 }],
      constraints: [],
      visible_3d: [],
      solved: {},
      metadata: {},
    }, null, 2)
    try {
      const created = await api.createFile(projectId, {
        name,
        kind: 'sketch',
        parent_id: parentId,
        content: seed,
      })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      return created
    } catch (err) {
      set({ toast: err?.message || 'Failed to create sketch on face' })
      return null
    }
  },

  createFile: async (parentId, kind) => {
    const { projectId } = get()
    if (!projectId) return
    const defaults = {
      file: 'untitled.jscad',
      folder: 'New folder',
      assembly: 'main.assembly',
      drawing: 'untitled.drawing',
      sketch: 'untitled.sketch',
      part: 'untitled.part',
      circuit: 'untitled.circuit.tsx',
      feature: 'untitled.feature',
    }
    let seedContent = ''
    if (kind === 'assembly') seedContent = '{"components":[]}'
    else if (kind === 'drawing') seedContent = DEFAULT_DRAWING
    else if (kind === 'sketch') seedContent = DEFAULT_SKETCH
    else if (kind === 'part') seedContent = DEFAULT_PART
    else if (kind === 'circuit') seedContent = DEFAULT_CIRCUIT
    else if (kind === 'feature') seedContent = '{"features":[]}'
    else if (kind === 'equations') seedContent = JSON.stringify({ version: 1, params: [] }, null, 2)
    if (!defaults.equations) defaults.equations = 'params.equations'
    try {
      const created = await api.createFile(projectId, {
        name: defaults[kind] || 'untitled',
        kind,
        parent_id: parentId,
        content: seedContent,
      })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      if (kind === 'equations') {
        try { await get().refreshEquationsCache() } catch { /* tolerate */ }
      }
      if (kind !== 'folder') await get().selectFile(created.id)
      return created
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  createFeatureFromSketch: async (sketchFileId) => {
    const { projectId, files } = get()
    if (!projectId) return
    const sketch = (files || []).find((f) => f.id === sketchFileId)
    if (!sketch) return
    // Compute the sketch's path: walk parent_id chain for the prefix.
    const byId = new Map(files.map((f) => [f.id, f]))
    const segs = []
    let cur = sketch
    let safety = 0
    while (cur && safety++ < 64) {
      segs.unshift(cur.name)
      if (!cur.parent_id) break
      cur = byId.get(cur.parent_id)
    }
    const sketchPath = '/' + segs.join('/')
    const baseName = sketch.name.replace(/\.sketch$/, '')
    const seed = JSON.stringify({
      features: [{
        id: 'f1', op: 'pad', sketch_path: sketchPath, height: 10, direction: 'up',
      }],
    })
    try {
      const created = await api.createFile(projectId, {
        name: baseName + '.feature',
        kind: 'feature',
        parent_id: sketch.parent_id,
        content: seed,
      })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      await get().selectFile(created.id)
    } catch (err) {
      set({ toast: 'Could not create feature: ' + (err?.message || String(err)) })
    }
  },

  // Upload a binary asset to the project, add the resulting File row to the
  // tree, and switch to it.
  //
  // STEP files use the chunked, resumable upload pipeline (Phase 2). Other
  // small assets keep using the simple multipart endpoint for now. While the
  // chunked upload is in flight, the FileTree renders an inline progress
  // bar driven by `uploadProgress` (set here, cleared on completion).
  uploadAsset: async (browserFile, { kind = 'step', parent_id = null, signal } = {}) => {
    const { projectId } = get()
    if (!projectId || !browserFile) return null
    if (kind === 'step') {
      const ctrl = signal ? null : new AbortController()
      const usedSignal = signal || ctrl?.signal
      set({
        uploadProgress: {
          filename: browserFile.name,
          received: 0,
          total: 0,
          bytes: 0,
          totalBytes: browserFile.size,
          status: 'hashing',
          uploadId: null,
          // Expose the AbortController so the FileTree's Cancel button can
          // also stop the in-flight PUTs. The DELETE is fired separately
          // once we know the upload_id.
          abort: () => {
            try { ctrl?.abort() } catch { /* ignore */ }
          },
          error: null,
        },
      })
      try {
        const created = await api.uploadAssetChunked(projectId, browserFile, {
          kind,
          parent_id,
          signal: usedSignal,
          onInit: ({ uploadId, totalChunks }) => {
            set((s) => ({
              uploadProgress: s.uploadProgress
                ? { ...s.uploadProgress, uploadId, total: totalChunks }
                : s.uploadProgress,
            }))
          },
          onProgress: ({ received, total, bytes }) => {
            // Switch the displayed status to 'uploading' on the first
            // progress callback (we know the chunk count by then).
            set((s) => ({
              uploadProgress: s.uploadProgress
                ? { ...s.uploadProgress, received, total, bytes, status: 'uploading' }
                : s.uploadProgress,
            }))
          },
        })
        set({ uploadProgress: null })
        set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
        await get().selectFile(created.id)
        return created
      } catch (err) {
        // Aborted uploads are user-initiated; clear silently.
        if (err && err.aborted) {
          set({ uploadProgress: null })
          return null
        }
        set((s) => ({
          uploadProgress: s.uploadProgress
            ? { ...s.uploadProgress, status: 'error', error: err?.message || String(err) }
            : null,
          loadError: err?.message || String(err),
        }))
        return null
      }
    }
    try {
      const created = await api.uploadAsset(projectId, browserFile, { kind, parent_id })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      await get().selectFile(created.id)
      return created
    } catch (err) {
      set({ loadError: err?.message || String(err) })
      return null
    }
  },

  // Cancel the in-flight chunked upload, if any. Triggers the AbortController
  // to short-circuit any pending PUTs and fires DELETE /uploads/:uid so the
  // server tears down the session and temp chunks. Safe to call when there
  // is no upload in flight (no-op).
  cancelUpload: async () => {
    const { projectId, uploadProgress } = get()
    if (!uploadProgress) return
    try { uploadProgress.abort?.() } catch { /* ignore */ }
    if (projectId && uploadProgress.uploadId) {
      try { await api.cancelUpload(projectId, uploadProgress.uploadId) }
      catch { /* best-effort */ }
    }
    set({ uploadProgress: null })
  },

  // Clear an error-state upload progress card so the user can dismiss it
  // (the actual error toast is handled by `loadError`).
  dismissUploadError: () => {
    set((s) => (s.uploadProgress && s.uploadProgress.status === 'error'
      ? { uploadProgress: null }
      : {}))
  },

  renameFile: async (id, name) => {
    const { projectId } = get()
    try {
      const updated = await api.updateFile(projectId, id, { name })
      set((s) => ({
        files: s.files.map((f) => f.id === id ? { ...f, name: updated.name } : f),
        currentFile: s.currentFile?.id === id ? { ...s.currentFile, name: updated.name } : s.currentFile,
      }))
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  deleteFile: async (id) => {
    const { projectId, currentFileId, files } = get()
    const target = files.find((f) => f.id === id)
    const wasEquations = target && (target.kind === 'equations' ||
      (target.name || '').toLowerCase().endsWith('.equations'))
    try {
      await api.deleteFile(projectId, id)
      set((s) => {
        const remaining = s.files.filter((f) => f.id !== id && f.parent_id !== id)
        const next = currentFileId === id
          ? (remaining.find((f) => f.kind !== 'folder') || null)
          : s.currentFile
        return {
          files: remaining,
          currentFileId: currentFileId === id ? (next?.id ?? null) : currentFileId,
          currentFile: currentFileId === id ? null : s.currentFile,
          currentFileContent: currentFileId === id ? '' : s.currentFileContent,
        }
      })
      if (wasEquations) {
        try { await get().refreshEquationsCache() } catch { /* tolerate */ }
      }
      if (currentFileId === id) {
        const f = get().files.find((f) => f.kind !== 'folder')
        if (f) await get().selectFile(f.id)
      }
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  updateProjectName: async (name) => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const updated = await api.updateProject(projectId, { name })
      set({ project: updated })
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  // ---- Picking ----
  pickPart: (partId) => {
    const { currentFileId, currentFile } = get()
    if (!partId) {
      set({ pickedPart: null })
      return
    }
    set({
      pickedPart: {
        part_id: partId,
        file_id: currentFileId,
        label: currentFile?.name,
      },
    })
  },

  attachPickedToChat: () => {
    const { pickedPart, pendingPartRefs } = get()
    if (!pickedPart) return
    // Avoid duplicates.
    const exists = pendingPartRefs.some((r) =>
      r.part_id === pickedPart.part_id && r.file_id === pickedPart.file_id,
    )
    if (exists) return
    set({ pendingPartRefs: [...pendingPartRefs, pickedPart] })
  },

  removePartRef: (idx) => {
    set((s) => ({ pendingPartRefs: s.pendingPartRefs.filter((_, i) => i !== idx) }))
  },

  clearPendingPartRefs: () => set({ pendingPartRefs: [] }),

  // ---- Visibility ----
  togglePartVisibility: (fileId, partId) => {
    if (!fileId || !partId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      const current = new Set(next.get(fileId) || [])
      if (current.has(partId)) current.delete(partId)
      else current.add(partId)
      next.set(fileId, current)
      return { hiddenPartIds: next }
    })
  },

  isolatePart: (fileId, partId) => {
    if (!fileId || !partId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      const all = new Set(s.parts.map((p) => p.id).filter((id) => id !== partId))
      next.set(fileId, all)
      return { hiddenPartIds: next }
    })
  },

  showAllParts: (fileId) => {
    if (!fileId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      next.set(fileId, new Set())
      return { hiddenPartIds: next }
    })
  },

  // ---- Measure tool ----
  setMeasureMode: (mode) => {
    // Switching out of object mode keeps any picked-part for the chat panel
    // (so click-to-attach still resumes when the user switches back).
    set({ measureMode: mode })
  },

  // partId/kind/featureId may all be null → clears selection.
  // shift=true → append (cap 2). Otherwise replace the first slot (so single-
  // click swaps).
  pickFeature: (partId, kind, featureId, shift = false) => {
    if (!partId || !kind || !featureId) {
      set({ selectedFeatures: [] })
      return
    }
    set((s) => {
      const item = { partId, kind, featureId }
      // Avoid duplicates.
      const eq = (a, b) => a.partId === b.partId && a.kind === b.kind && a.featureId === b.featureId
      if (s.selectedFeatures.some((x) => eq(x, item))) return {}
      if (shift) {
        const next = [...s.selectedFeatures, item].slice(-2)
        return { selectedFeatures: next }
      }
      // Non-shift: replace single slot, but if the user already has 2 we drop
      // the oldest.
      if (s.selectedFeatures.length === 0) return { selectedFeatures: [item] }
      if (s.selectedFeatures.length === 1) return { selectedFeatures: [s.selectedFeatures[0], item] }
      return { selectedFeatures: [s.selectedFeatures[1], item] }
    })
  },

  clearSelectedFeatures: () => set({ selectedFeatures: [] }),

  // Add a feature reference to pendingPartRefs so the next chat message can
  // call it out. We re-use the existing PartRef shape with a richer label.
  attachFeatureToChat: (partId, kind, featureId) => {
    const { currentFileId, pendingPartRefs } = get()
    if (!partId || !currentFileId) return
    const label = `${partId}#${featureId}`
    const exists = pendingPartRefs.some((r) =>
      r.part_id === partId && r.file_id === currentFileId && r.label === label,
    )
    if (exists) return
    set({
      pendingPartRefs: [...pendingPartRefs, {
        file_id: currentFileId,
        part_id: partId,
        label,
        feature_kind: kind,
        feature_id: featureId,
      }],
    })
  },

  // ---- Source mutators (color + translate) ----
  // All call api.updateFile (PATCH) directly — same path as autosave. The
  // store updates currentFileContent locally, then re-runs JSCAD so parts
  // refresh on the next render.
  recolorPart: async (partId, rgb) => {
    const { projectId, currentFileId, currentFile, currentFileContent } = get()
    if (!projectId || !currentFileId || !currentFile) return
    if ((currentFile.name || '').match(/\.(step|stp)$/i)) {
      set({ toast: 'STEP files are read-only' })
      return
    }
    const next = withColorizedPart(currentFileContent, partId, rgb)
    if (!next) {
      set({ toast: "Couldn't safely edit source — try via chat instead" })
      return
    }
    await applySourceEdit(set, get, next)
  },

  movePart: async (partId, deltaXYZ) => {
    const { projectId, currentFileId, currentFile, currentFileContent } = get()
    if (!projectId || !currentFileId || !currentFile) return
    if ((currentFile.name || '').match(/\.(step|stp)$/i)) {
      set({ toast: 'STEP files are read-only' })
      return
    }
    const next = withTranslatedPart(currentFileContent, partId, deltaXYZ, 'add')
    if (!next) {
      set({ toast: "Couldn't safely edit source — try via chat instead" })
      return
    }
    await applySourceEdit(set, get, next)
  },

  setPartPosition: async (partId, xyz) => {
    const { projectId, currentFileId, currentFile, currentFileContent } = get()
    if (!projectId || !currentFileId || !currentFile) return
    if ((currentFile.name || '').match(/\.(step|stp)$/i)) {
      set({ toast: 'STEP files are read-only' })
      return
    }
    const next = withTranslatedPart(currentFileContent, partId, xyz, 'set')
    if (!next) {
      set({ toast: "Couldn't safely edit source — try via chat instead" })
      return
    }
    await applySourceEdit(set, get, next)
  },

  dismissToast: () => set({ toast: null }),

  // ---- Threads + messages ----
  selectThread: async (threadId) => {
    const { projectId } = get()
    if (!threadId || !projectId) {
      set({ currentThreadId: null, messages: [] })
      return
    }
    set({ currentThreadId: threadId, loadingMessages: true, messages: [] })
    try {
      const messages = await api.listMessages(projectId, threadId)
      set({ messages: messages || [], loadingMessages: false })
    } catch (err) {
      set({ loadingMessages: false, loadError: err?.message || String(err) })
    }
  },

  createThread: async ({ title, file_id, model } = {}) => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const t = await api.createThread(projectId, { title, file_id, model })
      set((s) => ({ threads: [t, ...s.threads] }))
      await get().selectThread(t.id)
      return t
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  setThreadModel: async (threadId, model) => {
    const { projectId, threads } = get()
    if (!projectId || !threadId) return
    set({ threads: threads.map((t) => t.id === threadId ? { ...t, model } : t) })
    try {
      await api.updateThread(projectId, threadId, { model })
    } catch {
      // Server is the source of truth on next load; UI keeps optimistic value.
    }
  },

  toggleStar: async (threadId) => {
    const { projectId, threads } = get()
    const t = threads.find((x) => x.id === threadId)
    if (!t) return
    const next = !t.is_starred
    // Optimistic.
    set({ threads: threads.map((x) => x.id === threadId ? { ...x, is_starred: next } : x) })
    try {
      await api.updateThread(projectId, threadId, { is_starred: next })
    } catch {
      set({ threads: get().threads.map((x) => x.id === threadId ? { ...x, is_starred: !next } : x) })
    }
  },

  deleteThread: async (threadId) => {
    const { projectId, currentThreadId, threads } = get()
    try {
      await api.deleteThread(projectId, threadId)
      const remaining = threads.filter((t) => t.id !== threadId)
      set({ threads: remaining })
      if (currentThreadId === threadId) {
        await get().selectThread(remaining[0]?.id ?? null)
      }
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  sendMessage: async (content, { model } = {}) => {
    const { projectId, currentThreadId, pendingPartRefs, currentFileId } = get()
    if (!projectId || !content.trim()) return

    let threadId = currentThreadId
    if (!threadId) {
      const title = content.trim().slice(0, 60)
      const t = await get().createThread({ title, file_id: currentFileId, model })
      threadId = t?.id
      if (!threadId) return
    }

    // Optimistic user message.
    const optimistic = {
      id: `local-${Date.now()}`,
      thread_id: threadId,
      role: 'user',
      content,
      part_refs: pendingPartRefs,
      created_at: new Date().toISOString(),
      _pending: true,
    }
    set((s) => ({
      messages: [...s.messages, optimistic],
      sending: true,
      pendingPartRefs: [],
    }))
    try {
      const res = await api.sendMessage(projectId, threadId, {
        content,
        part_refs: optimistic.part_refs,
        model,
      })
      set((s) => {
        // Replace optimistic with server's user_message + tool_messages + assistant_message.
        const filtered = s.messages.filter((m) => m.id !== optimistic.id)
        const next = [...filtered]
        if (res?.user_message) next.push(res.user_message)
        if (Array.isArray(res?.tool_messages)) {
          for (const m of res.tool_messages) next.push(m)
        }
        if (res?.assistant_message) next.push(res.assistant_message)
        // Bump thread last_message_at locally.
        const threads = s.threads.map((t) => t.id === threadId
          ? { ...t, last_message_at: new Date().toISOString() }
          : t)
        return { messages: next, sending: false, threads }
      })

      // If any tool message used a file-mutating tool, refresh the tree and
      // (if it's the open file) reload its content. Backend denormalizes
      // tool_name onto each tool_messages row so we don't have to cross-walk
      // back to the (unreturned) intermediate assistant messages.
      const toolMsgs = res?.tool_messages || []
      const mutated =
        toolMsgs.some((m) => m?.tool_name && FILE_MUTATING_TOOLS.has(m.tool_name)) ||
        (Array.isArray(res?.assistant_message?.tool_calls)
          && res.assistant_message.tool_calls.some((c) => FILE_MUTATING_TOOLS.has(c.name))) ||
        // Defensive fallback: if the backend forgets tool_name, refresh
        // anytime we got tool messages back. Cheap (file list is small).
        (toolMsgs.length > 0 && toolMsgs.every((m) => !m?.tool_name))

      if (mutated) {
        try {
          const fresh = await api.listFiles(projectId)
          set({ files: fresh })
        } catch { /* tolerate */ }
        const { currentFileId: openId } = get()
        if (openId) {
          await get().loadFileForEditor(openId)
        }
        // If the History drawer is open for the current file, refresh it so
        // the user sees the new tool-source revisions appear immediately.
        if (get().revisionDrawerOpen && openId) {
          await get().loadRevisions(openId)
        }
      }
    } catch (err) {
      set((s) => ({
        sending: false,
        messages: s.messages.map((m) => m.id === optimistic.id
          ? { ...m, _error: err?.message || 'Failed to send' }
          : m),
      }))
    }
  },

  reset: () => {
    setSketchResolver(null)
    setSketchLister(null)
    setJscadEquationsResolver(null)
    setOcctEquationsResolver(null)
    setSketchEquationsResolverSync(null)
    setOcctActiveConfigResolver(null)
    // Drop any in-flight OCCT run + tear down the worker so the next project's
    // first feature evaluation pays only the wasm-compile cost (not the heap
    // accumulated from the previous project).
    destroyOcct()
    // Cancel any in-flight tscircuit compile so a stale result from the
    // closing project can't write into the next project's circuit state.
    cancelCircuit()
    set({
      ...initial,
      hiddenPartIds: new Map(),
      selectedFeatures: [],
      parsedAssembly: null,
      selectedComponentId: null,
      selectedCircuitRefdes: null,
      selectedCircuitNet: null,
      parsedDrawing: null,
      drawingSourceParts: new Map(),
      selectedDimensionId: null,
      selectedAnnotationId: null,
      parsedSketch: null,
      sketchStatus: null,
      sketchDof: 0,
      sketchConflicts: [],
      currentPart: null,
      currentFeature: null,
      featureMeshes: [],
      featureError: null,
      featureLoading: false,
      featureSelection: { faceIds: new Set(), edgeIds: new Set() },
      featurePickMode: null,
      featurePickTarget: null,
      currentCircuit: null,
      circuitError: null,
      circuitLoading: false,
      bomState: { rows: [], total: null, warnings: [], loading: false, error: null },
    })
  },

  // ---- Drawing actions ----
  // Update the drawing JSON (parsed + serialized) and persist via the same
  // PATCH path autosave uses. The DrawingView reads from `parsedDrawing`.
  //
  // `mutate` receives the whole parsed object (with sheets[] + currentSheet)
  // and returns a new parsed object. Use updateSheet() for sheet-scoped edits.
  updateDrawing: async (mutate) => {
    const { projectId, currentFileId, parsedDrawing } = get()
    if (!projectId || !currentFileId || !parsedDrawing) return
    const next = mutate(parsedDrawing)
    if (!next) return
    const body = serializeDrawing(next)
    set({ parsedDrawing: next, currentFileContent: body, dirty: false, saving: true })
    try {
      const updated = await api.updateFile(projectId, currentFileId, { content: body })
      set((s) => ({
        saving: false,
        currentFile: updated,
        files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
      }))
      // If a new view's source isn't in our source-parts cache yet, resolve it.
      await get().resolveDrawingSources()
    } catch (err) {
      set({ saving: false, toast: err?.message || 'Failed to save drawing' })
    }
  },

  // Apply `mutate(sheet)` → newSheet to the active sheet, then persist via
  // updateDrawing. The vast majority of drawing actions use this helper.
  updateSheet: (mutate) => {
    return get().updateDrawing((doc) => {
      const idx = doc.currentSheet ?? 0
      const sheets = doc.sheets || []
      const cur = sheets[idx] || sheets[0]
      if (!cur) return doc
      const next = mutate(cur)
      if (!next) return doc
      const out = sheets.slice()
      out[idx] = next
      return { ...doc, sheets: out }
    })
  },

  // Switch which sheet is active. Pure UI state — not persisted.
  selectSheet: (idx) => {
    set((s) => {
      if (!s.parsedDrawing) return {}
      const n = (s.parsedDrawing.sheets || []).length
      const clamped = Math.max(0, Math.min(n - 1, idx | 0))
      return {
        parsedDrawing: { ...s.parsedDrawing, currentSheet: clamped },
        selectedDimensionId: null,
        selectedAnnotationId: null,
      }
    })
  },

  // Add a new sheet to the drawing.
  addSheet: ({ size = 'A3', orientation = 'landscape', template = 'default', title } = {}) => {
    return get().updateDrawing((doc) => {
      const sheets = doc.sheets ? doc.sheets.slice() : []
      const sheet = {
        id: shortId('sh'),
        frame: {
          size, orientation, template,
          title: title || `Sheet ${sheets.length + 1}`,
          sheet_number: `${sheets.length + 1}/${sheets.length + 1}`,
        },
        views: [], dimensions: [], annotations: [],
        centerlines: [], breaks: [], symbols: [],
      }
      sheets.push(sheet)
      return { ...doc, sheets, currentSheet: sheets.length - 1 }
    })
  },

  // Delete a sheet by index. The last remaining sheet is preserved.
  removeSheet: (idx) => {
    return get().updateDrawing((doc) => {
      const sheets = (doc.sheets || []).slice()
      if (sheets.length <= 1) return doc
      sheets.splice(idx, 1)
      const cur = Math.min(doc.currentSheet ?? 0, sheets.length - 1)
      return { ...doc, sheets, currentSheet: cur }
    })
  },

  // Walk the open drawing's views and ensure each source_file_id has a
  // resolved parts list cached in `drawingSourceParts`. Sources may be JSCAD,
  // STEP, or an assembly (which gets recursively resolved into its flat parts
  // list, transforms baked in). Iterates over EVERY sheet's views, not just
  // the active sheet.
  resolveDrawingSources: async () => {
    const { projectId, parsedDrawing } = get()
    if (!projectId || !parsedDrawing) return
    const sourceIds = []
    for (const sh of parsedDrawing.sheets || []) {
      for (const v of sh.views || []) {
        if (v.source_file_id) sourceIds.push(v.source_file_id)
      }
    }
    const uniq = Array.from(new Set(sourceIds))
    if (uniq.length === 0) return
    const next = new Map(get().drawingSourceParts)
    for (const id of uniq) {
      if (next.has(id)) continue
      try {
        const parts = await loadComponentParts(projectId, id)
        next.set(id, parts)
      } catch (err) {
        console.warn(`drawing: failed to load source ${id}:`, err)
        // Cache an empty array so we don't re-attempt every frame.
        next.set(id, [])
      }
    }
    set({ drawingSourceParts: next })
  },

  selectDimension: (id) => set({ selectedDimensionId: id || null }),

  // Build a dimension entry from a payload. `payload.kind` covers all the
  // supported kinds: linear|aligned|radius|diameter|angular|baseline|chain|
  // ordinate. `payload.value` (string) is the manual override; null/missing
  // means auto-measured.
  addDimension: (payload) => {
    if (!payload || !payload.kind) return
    const { kind } = payload
    const base = {
      id: shortId('d'),
      view_id: payload.view_id,
      kind,
    }
    if (payload.value != null) base.value = String(payload.value)
    if (payload.text_override) base.text_override = String(payload.text_override) // legacy alias
    if (payload.position) base.position = payload.position

    let dim
    if (kind === 'angular') {
      dim = {
        ...base,
        vertex: payload.vertex,
        a: payload.a,
        b: payload.b,
        radius: Number(payload.radius) || 10,
      }
    } else if (kind === 'baseline' || kind === 'chain') {
      dim = {
        ...base,
        picks: Array.isArray(payload.picks) ? payload.picks : [],
        offset: Number(payload.offset) || 8,
      }
    } else if (kind === 'ordinate') {
      dim = {
        ...base,
        picks: Array.isArray(payload.picks) ? payload.picks : [],
        origin: payload.origin || { x: 0, y: 0 },
      }
    } else {
      dim = {
        ...base,
        a: payload.a,
        b: payload.b,
        offset: Number(payload.offset) || 0,
      }
    }
    return get().updateSheet((s) => ({
      ...s,
      dimensions: [...(s.dimensions || []), dim],
    }))
  },

  updateDimension: (id, patch) => {
    if (!id || !patch) return
    return get().updateSheet((s) => ({
      ...s,
      dimensions: (s.dimensions || []).map((d) => d.id === id ? { ...d, ...patch } : d),
    }))
  },

  deleteDimension: (id) => {
    return get().updateSheet((s) => ({
      ...s,
      dimensions: (s.dimensions || []).filter((x) => x.id !== id),
    }))
  },

  updateFrame: (patch) => {
    return get().updateSheet((s) => ({
      ...s,
      frame: { ...s.frame, ...patch },
    }))
  },

  // Place a new view at a sensible position next to the existing views.
  // `part_id` is optional: empty / missing / '*' = all parts of the source.
  addView: ({ source_file_id, part_id, projection, position, scale = 1, is_section = false }) => {
    return get().updateSheet((s) => {
      const existing = s.views || []
      let pos = position
      if (!pos) {
        let rightX = 25
        let topY = 25
        for (const v of existing) {
          if (v.position && v.position[0] > rightX) {
            rightX = v.position[0] + 100
            topY = v.position[1]
          }
        }
        pos = [rightX, topY]
      }
      const view = {
        id: shortId('v'),
        source_file_id,
        part_id: (typeof part_id === 'string' && part_id.trim()) ? part_id : '*',
        projection,
        scale,
        position: pos,
        show_hidden: true,
        show_silhouette: true,
        is_section: !!is_section,
        label: projection ? projection[0].toUpperCase() + projection.slice(1) : '',
      }
      return { ...s, views: [...existing, view] }
    })
  },

  // Add multiple views in one persisted update.
  addViews: (specs) => {
    if (!Array.isArray(specs) || specs.length === 0) return
    return get().updateSheet((s) => {
      const newViews = specs.map((sp) => ({
        id: shortId('v'),
        source_file_id: sp.source_file_id,
        part_id: (typeof sp.part_id === 'string' && sp.part_id.trim()) ? sp.part_id : '*',
        projection: sp.projection,
        scale: Number(sp.scale) || 1,
        position: Array.isArray(sp.position) ? sp.position : [25, 25],
        show_hidden: true,
        show_silhouette: true,
        is_section: !!sp.is_section,
        label: sp.projection ? sp.projection[0].toUpperCase() + sp.projection.slice(1) : '',
      }))
      return { ...s, views: [...(s.views || []), ...newViews] }
    })
  },

  updateView: (viewId, patch) => {
    return get().updateSheet((s) => ({
      ...s,
      views: (s.views || []).map((v) => v.id === viewId ? { ...v, ...patch } : v),
    }))
  },

  removeView: (viewId) => {
    return get().updateSheet((s) => ({
      ...s,
      views: (s.views || []).filter((v) => v.id !== viewId),
      dimensions: (s.dimensions || []).filter((x) => x.view_id !== viewId),
      annotations: (s.annotations || []).filter((x) => !x.view_id || x.view_id !== viewId),
      centerlines: (s.centerlines || []).filter((x) => !x.view_id || x.view_id !== viewId),
      breaks: (s.breaks || []).filter((x) => !x.view_id || x.view_id !== viewId),
      symbols: (s.symbols || []).filter((x) => !x.view_id || x.view_id !== viewId),
    }))
  },

  // ---- Annotations ----
  selectAnnotation: (id) => set({ selectedAnnotationId: id || null }),

  addAnnotation: (annotation) => {
    if (!annotation || !annotation.kind) return
    const ann = annotation.id ? annotation : { ...annotation, id: shortId('ann') }
    return get().updateSheet((s) => ({
      ...s,
      annotations: [...(s.annotations || []), ann],
    }))
  },

  updateAnnotation: (id, patch) => {
    if (!id || !patch) return
    return get().updateSheet((s) => ({
      ...s,
      annotations: (s.annotations || []).map((a) => a.id === id ? { ...a, ...patch } : a),
    }))
  },

  removeAnnotation: (id) => {
    if (!id) return
    set((s) => ({ selectedAnnotationId: s.selectedAnnotationId === id ? null : s.selectedAnnotationId }))
    return get().updateSheet((s) => ({
      ...s,
      annotations: (s.annotations || []).filter((a) => a.id !== id),
    }))
  },

  // ---- Centerlines / break lines / symbols ----
  addCenterline: (payload) => {
    if (!payload) return
    const cl = {
      id: shortId('cl'),
      view_id: payload.view_id,
      style: payload.style || 'center_dashed',
      ...(payload.refs ? { refs: payload.refs } : {}),
      ...(payload.custom ? { custom: payload.custom } : {}),
      ...(payload.cx != null ? { cx: payload.cx, cy: payload.cy, r: payload.r } : {}),
    }
    return get().updateSheet((s) => ({
      ...s,
      centerlines: [...(s.centerlines || []), cl],
    }))
  },

  removeCenterline: (id) => {
    return get().updateSheet((s) => ({
      ...s,
      centerlines: (s.centerlines || []).filter((c) => c.id !== id),
    }))
  },

  addBreak: (payload) => {
    if (!payload) return
    const br = {
      id: shortId('br'),
      view_id: payload.view_id,
      orientation: payload.orientation || 'vertical',
      p1: payload.p1,
      p2: payload.p2,
      style: payload.style || 'zigzag',
    }
    return get().updateSheet((s) => ({
      ...s,
      breaks: [...(s.breaks || []), br],
    }))
  },

  removeBreak: (id) => {
    return get().updateSheet((s) => ({
      ...s,
      breaks: (s.breaks || []).filter((c) => c.id !== id),
    }))
  },

  addSymbol: (payload) => {
    if (!payload || !payload.kind) return
    const sym = {
      id: shortId('sym'),
      kind: payload.kind, // surface_finish | weld | gdt
      view_id: payload.view_id,
      position: payload.position || { x: 0, y: 0 },
      params: payload.params || {},
      ...(payload.leader ? { leader: payload.leader } : {}),
    }
    return get().updateSheet((s) => ({
      ...s,
      symbols: [...(s.symbols || []), sym],
    }))
  },

  updateSymbol: (id, patch) => {
    if (!id || !patch) return
    return get().updateSheet((s) => ({
      ...s,
      symbols: (s.symbols || []).map((y) => y.id === id ? { ...y, ...patch, params: { ...(y.params || {}), ...(patch.params || {}) } } : y),
    }))
  },

  removeSymbol: (id) => {
    return get().updateSheet((s) => ({
      ...s,
      symbols: (s.symbols || []).filter((y) => y.id !== id),
    }))
  },

  // ---- Sketch actions ----
  // Update the open sketch's JSON content + persist. Used by the SketchView
  // after every solve. We dedupe by content equality so an idempotent solve
  // (no value changes) doesn't churn through autosave/revisions.
  updateSketch: async (mutate) => {
    const { projectId, currentFileId, parsedSketch, currentFileContent } = get()
    if (!projectId || !currentFileId || !parsedSketch) return
    const next = mutate(parsedSketch)
    if (!next) return
    const body = serializeSketch(next)
    if (body === currentFileContent) {
      set({ parsedSketch: next })
      return
    }
    set({ parsedSketch: next, currentFileContent: body, dirty: false, saving: true })
    try {
      const updated = await api.updateFile(projectId, currentFileId, { content: body })
      set((s) => ({
        saving: false,
        currentFile: updated,
        files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
      }))
      // Reactive re-eval: if a JSCAD file is currently open and its source
      // imports the sketch we just saved, re-run it so the 3D viewport stays
      // in sync without requiring a manual refresh.
      // Scope (v1): only the currently-open file. Cross-file graph invalidation
      // (assembly C → jscad B → sketch A) is deferred — see ROADMAP.
      const sketchPath = fileAbsPath(get().files, currentFileId)
      await get()._reEvalJscadForSketch(sketchPath)
    } catch (err) {
      set({ saving: false, toast: err?.message || 'Failed to save sketch' })
    }
  },

  // Internal helper: if the currently-open file is a .jscad that imports the
  // sketch at `sketchAbsPath`, re-run it and update parts / partsError.
  // Called by updateSketch after a sketch is saved, and indirectly by
  // sendMessage after LLM sketch_* tool calls trigger loadFileForEditor
  // (which already re-runs runJscad via the standard JSCAD branch — so the
  // LLM path is fully covered once sketch_* tools are in FILE_MUTATING_TOOLS).
  _reEvalJscadForSketch: async (sketchAbsPath) => {
    const state = get()
    const { currentFile, currentFileContent, currentFileId } = state
    if (!currentFile || !currentFileId) return
    if (fileKindFor(currentFile) !== 'jscad') return
    if (!jscadImportsSketch(currentFileContent, sketchAbsPath)) return
    // The sketch content changed; re-resolve sketch imports and re-eval.
    const cfgParams = state.getActiveConfigParams ? state.getActiveConfigParams(currentFileId) : null
    const res = await runJscad(currentFileContent, cfgParams)
    // Guard: user may have navigated away while JSCAD was running.
    if (get().currentFileId !== currentFileId) return
    if (res?.stale) return
    if (res.error) {
      set({ partsError: res.error, loadingParts: false })
    } else {
      set({ parts: res.parts || [], partsError: null, loadingParts: false })
    }
  },

  // ---- Feature actions ----
  // Update the open feature's parsed tree + persist. Mirrors updateSketch:
  // dedupes by content equality so an idempotent change (e.g. re-typing the
  // same value) doesn't churn through autosave/revisions. The actual OCCT
  // re-evaluation is owned by FeatureView's debounced effect — the store
  // just records authoritative tree state and persists it.
  updateFeature: async (mutate) => {
    const { projectId, currentFileId, currentFeature, currentFileContent } = get()
    if (!projectId || !currentFileId || !currentFeature) return
    const next = typeof mutate === 'function' ? mutate(currentFeature) : mutate
    if (!next) return
    const body = serializeFeature(next)
    if (body === currentFileContent) {
      set({ currentFeature: next })
      return
    }
    set({ currentFeature: next, currentFileContent: body, dirty: false, saving: true })
    try {
      const updated = await api.updateFile(projectId, currentFileId, { content: body })
      set((s) => ({
        saving: false,
        currentFile: updated,
        files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
      }))
    } catch (err) {
      set({ saving: false, toast: err?.message || 'Failed to save feature' })
    }
  },

  // Stash the latest OCCT evaluation result. Held centrally so a remount of
  // the FeatureView re-picks up the mesh without re-evaluating.
  setFeatureMeshes: (meshes, { error = null, loading = false } = {}) => {
    set({
      featureMeshes: Array.isArray(meshes) ? meshes : [],
      featureError: error,
      featureLoading: !!loading,
    })
  },

  // ---- Phase 3 viewport selection actions ----
  // Replace the entire viewport selection set. Called by FeatureRenderer on
  // every click; the FeatureView watches `featureSelection` to drive the
  // edge-id field of the active inspector.
  setFeatureSelection: (selection) => {
    const next = {
      faceIds: selection?.faceIds instanceof Set ? new Set(selection.faceIds) : new Set(),
      edgeIds: selection?.edgeIds instanceof Set ? new Set(selection.edgeIds) : new Set(),
    }
    set({ featureSelection: next })
  },

  // Clear the viewport selection. Useful on tree mutations (face/edge ids
  // shuffle when topology changes — see "persistent naming" caveat in the
  // FeatureView's selection bar).
  clearFeatureSelection: () => set({
    featureSelection: { faceIds: new Set(), edgeIds: new Set() },
    featurePickMode: null,
    featurePickTarget: null,
  }),

  // Switch the viewport pick mode. 'face' / 'edge' = persistent multi-pick.
  // 'pushpull' = drag a face to extrude/cut. 'sketch_on_face' = single-shot
  // face pick that creates a new sketch on the picked face. 'one_shot_face'
  // / 'one_shot_edge' = single-shot pick that fills a feature param via
  // featurePickTarget.
  setFeaturePickMode: (mode, target = null) => {
    set({ featurePickMode: mode || null, featurePickTarget: target })
  },

  // ---- Part actions ----
  // Apply a partial patch to the open Part: shallow-merge into currentPart,
  // re-serialize, and route through editContent + saveFile so the standard
  // revisions pipeline records the edit (Cmd+Z works). The autosave timer
  // already runs for Part files (kind='part') because they're not in the
  // skip-list.
  updatePart: (patch) => {
    const { currentPart } = get()
    if (!currentPart || !patch) return
    const next = { ...currentPart, ...patch, version: 1 }
    if (Array.isArray(patch.distributors)) next.distributors = patch.distributors
    const body = serializePart(next)
    set({ currentPart: next, currentFileContent: body, dirty: true })
  },

  // Replace the open Part's attached 3D model. Uploads the picked browser
  // File via the chunked-upload pipeline (same path STEP imports use), then
  // updates the Part's model_storage_key + model_mime_type. We DON'T create
  // a separate kind='step' file row — the upload flow normally inserts one,
  // so we delete that row and keep just the storage object.
  //
  // TODO Phase 2: a dedicated "raw upload, no file row" endpoint to avoid
  // the create-then-delete dance.
  replacePartModel: async (browserFile) => {
    const { projectId, currentFileId, currentPart } = get()
    if (!projectId || !currentFileId || !currentPart || !browserFile) return
    set({ uploadProgress: {
      filename: browserFile.name, received: 0, total: 0, bytes: 0,
      totalBytes: browserFile.size, status: 'hashing', uploadId: null,
      abort: () => {}, error: null,
    } })
    try {
      const created = await api.uploadAssetChunked(projectId, browserFile, {
        kind: 'step',
        parent_id: null,
        onInit: ({ uploadId, totalChunks }) => {
          set((s) => ({
            uploadProgress: s.uploadProgress
              ? { ...s.uploadProgress, uploadId, total: totalChunks }
              : s.uploadProgress,
          }))
        },
        onProgress: ({ received, total, bytes }) => {
          set((s) => ({
            uploadProgress: s.uploadProgress
              ? { ...s.uploadProgress, received, total, bytes, status: 'uploading' }
              : s.uploadProgress,
          }))
        },
      })
      // Patch the Part to point at the new storage_key, then drop the
      // intermediate STEP file row (the blob stays — we own it via the
      // Part now).
      const next = {
        ...currentPart,
        model_storage_key: created.storage_key,
        model_mime_type: created.mime_type || 'model/step',
      }
      const body = serializePart(next)
      await api.updateFile(projectId, currentFileId, { content: body })
      try { await api.deleteFile(projectId, created.id) } catch { /* tolerate */ }
      set({
        currentPart: next,
        currentFileContent: body,
        dirty: false,
        uploadProgress: null,
      })
      // Force a re-resolve so any open assembly using this Part picks up
      // the new geometry.
      componentResultCache.clear()
    } catch (err) {
      set((s) => ({
        uploadProgress: s.uploadProgress
          ? { ...s.uploadProgress, status: 'error', error: err?.message || String(err) }
          : null,
        toast: err?.message || 'Failed to upload model',
      }))
    }
  },

  // ---- Equations cache ----
  // Walk every `.equations` file in the project, fetch its content, parse +
  // evaluate it, and stash the merged scope under `equationsScope`. Called
  // from loadProject (warm-up) and after any file mutation that touches an
  // `.equations` file (createFile / updateFile / deleteFile branches that
  // detect the kind). The runners consume the cached scope synchronously
  // (sketchSolver) and asynchronously (jscadRunner / occtRunner via the
  // resolver hook registered in loadProject).
  refreshEquationsCache: async () => {
    const state = get()
    const pid = state.projectId
    if (!pid) {
      const empty = { values: {}, errors: [], duplicates: [] }
      set({ equationsScope: empty })
      return empty
    }
    // Find every .equations file in the tree (kind='equations' OR name
    // ends in .equations — tolerate both surfaces).
    const equationsFiles = (state.files || []).filter((f) => {
      if (!f) return false
      if (f.kind === 'equations') return true
      const n = (f.name || '').toLowerCase()
      return n.endsWith('.equations')
    })
    // Sort alphabetically by name so duplicate-resolution order is stable.
    equationsFiles.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
    const fetched = []
    for (const f of equationsFiles) {
      try {
        const fresh = await api.getFile(pid, f.id)
        fetched.push({ path: '/' + (fresh.name || f.name), content: fresh.content || '' })
      } catch {
        // Skip on fetch failure; the row's params just stay missing from the scope.
      }
    }
    const scope = mergeEquationFiles(fetched)
    set({ equationsScope: scope })
    return scope
  },

  // ---- Configurations / variants ----
  //
  // Pick the active configuration for a given file. Re-runs the JSCAD /
  // OCCT pipeline on change so the renderer reflects the new params.
  // Triggering a re-run here mirrors what the equations editor does on
  // save, and keeps the runner pull-only (no extra event bus).
  setCurrentConfig: (fileId, configId) => {
    if (!fileId) return
    const next = { ...get().currentConfigByFile }
    if (configId == null || configId === '') {
      delete next[fileId]
    } else {
      next[fileId] = String(configId)
    }
    set({ currentConfigByFile: next })
    // Re-evaluate the open file if the change targeted it. The cheap path:
    // call the same loadFileForEditor that originally produced the parts —
    // it picks up the new configParams via getActiveConfigParams.
    const state = get()
    if (state.currentFileId === fileId) {
      const file = state.currentFile
      const kind = file ? fileKindFor(file) : null
      if (kind === 'jscad') {
        // Re-run JSCAD with the new merged params. We don't want to refetch
        // the file content from the server — just re-evaluate.
        ;(async () => {
          try {
            const cfgParams = get().getActiveConfigParams(fileId)
            const res = await runJscad(state.currentFileContent || '', cfgParams)
            if (get().currentFileId !== fileId) return
            if (res?.stale) return
            if (res.error) {
              set({ partsError: res.error })
            } else {
              set({ parts: res.parts || [], partsError: null })
            }
          } catch { /* ignore */ }
        })()
      } else if (kind === 'feature') {
        // FeatureView's own debounced run-loop will pick up the new config
        // on its next pass (it reads currentConfigByFile via the store).
        // We still nudge the renderer by clearing stale meshes? — no, that
        // would flash. Just let the next runFeatures call merge fresh.
      }
    }
  },

  // Returns the active configuration's params object for `fileId`, or null
  // when the file has no configurations. The lookup considers the
  // user-picked config first, then the file's default_config, then the
  // first declared config. Used by the JSCAD/OCCT runner integration so
  // the renderer reflects the picked variant.
  getActiveConfigParams: (fileId) => {
    const state = get()
    const file = state.files?.find?.((f) => f.id === fileId)
    // For the open file we rely on the parsed-* slots so this works even
    // for content the user has typed but not saved.
    let parsed = null
    if (state.currentFileId === fileId) {
      // The parsed slot for the OPEN file:
      if (state.currentPart) parsed = state.currentPart
      else if (state.currentFeature) parsed = state.currentFeature
      else if (state.parsedSketch) parsed = state.parsedSketch
    }
    if (!parsed && file) {
      // Fall back to parsing whatever cached content the file row carries
      // (parts of the tree never opened in this session won't have it,
      // which is fine — those configs are invisible to runners anyway).
      const content = file.content
      if (content == null) return null
      const kind = fileKindFor(file)
      if (kind === 'part') parsed = parsePart(content)
      else if (kind === 'feature') parsed = parseFeature(content)
      else if (kind === 'sketch') parsed = parseSketch(content)
      else return null
    }
    if (!parsed) return null
    const picked = state.currentConfigByFile?.[fileId]
    const cfg = getActiveConfig(parsed, picked)
    return cfg?.params || null
  },

  // ---- BOM actions ----
  // Pull the project's bill-of-materials and stash it in the store. The
  // BOMPanel + BOMPage subscribe; calling loadBOM again refetches from
  // scratch (no caching beyond the live state).
  loadBOM: async (projectId) => {
    const pid = projectId || get().projectId
    if (!pid) return
    set({ bomState: { rows: [], total: null, warnings: [], loading: true, error: null } })
    try {
      const res = await api.getBOM(pid)
      set({
        bomState: {
          rows: res?.rows || [],
          total: typeof res?.total_price_usd === 'number' ? res.total_price_usd : null,
          warnings: res?.warnings || [],
          loading: false,
          error: null,
        },
      })
    } catch (err) {
      set({
        bomState: {
          rows: [],
          total: null,
          warnings: [],
          loading: false,
          error: err?.message || 'Failed to load BOM',
        },
      })
    }
  },

  // Replace the entire parsed sketch (used after a successful solve writes
  // back numeric coords). Persistence is debounced by the caller (SketchView)
  // since solves may run on every drag tick.
  setSketchSolved: (next, status, dofCount, conflicts) => {
    set({
      parsedSketch: next,
      sketchStatus: status || null,
      sketchDof: typeof dofCount === 'number' ? dofCount : 0,
      sketchConflicts: Array.isArray(conflicts) ? conflicts : [],
    })
  },

  // ---- Revisions / soft-undo/redo ----
  setEditorFocused: (focused) => set({ editorFocused: !!focused }),

  openRevisionDrawer: () => {
    set({ revisionDrawerOpen: true })
    const { currentFileId } = get()
    if (currentFileId) get().loadRevisions(currentFileId)
  },

  closeRevisionDrawer: () => set({ revisionDrawerOpen: false }),

  loadRevisions: async (fileId) => {
    const { projectId } = get()
    if (!projectId || !fileId) return
    set({ loadingRevisions: true })
    try {
      const revisions = await api.listRevisions(projectId, fileId, 50)
      // Only commit if the open file hasn't changed under us.
      if (get().currentFileId === fileId) {
        set({ revisions: revisions || [], loadingRevisions: false })
      }
    } catch (err) {
      set({ loadingRevisions: false, toast: err?.message || 'Failed to load history' })
    }
  },

  // Restore a specific revision by id (using currentFileId). Reloads the
  // open file so the editor + renderer reflect the restored content.
  restoreRevision: async (revisionId) => {
    const { projectId, currentFileId } = get()
    if (!projectId || !currentFileId || !revisionId) return
    try {
      await api.restoreRevision(projectId, currentFileId, revisionId)
      await get().loadFileForEditor(currentFileId)
      // Refresh the file tree (deleted_at could have been cleared) and the
      // revisions list (the restore inserted a new row).
      try {
        const fresh = await api.listFiles(projectId)
        set({ files: fresh })
      } catch { /* tolerate */ }
      if (get().revisionDrawerOpen) await get().loadRevisions(currentFileId)
    } catch (err) {
      set({ toast: err?.message || 'Restore failed' })
    }
  },

  // Cmd+Z handler: pull the latest revisions, then restore the SECOND-newest
  // (the newest is the current state). Push the previous-current onto the
  // redo stack so Cmd+Shift+Z can put it back.
  undoLastRevision: async () => {
    const { projectId, currentFileId, revisions } = get()
    if (!projectId || !currentFileId) return
    let list = revisions
    // If we don't have revisions in memory (drawer never opened), fetch.
    if (!list || list.length === 0 || (list[0] && list[0]?.file_id !== currentFileId)) {
      await get().loadRevisions(currentFileId)
      list = get().revisions
    }
    if (!list || list.length < 2) {
      set({ toast: 'Nothing to undo' })
      return
    }
    const current = list[0]
    const previous = list[1]
    try {
      await api.restoreRevision(projectId, currentFileId, previous.id)
      await get().loadFileForEditor(currentFileId)
      if (get().revisionDrawerOpen) await get().loadRevisions(currentFileId)
      set((s) => ({
        redoStack: [...s.redoStack, { fileId: currentFileId, revisionId: current.id }],
      }))
    } catch (err) {
      set({ toast: err?.message || 'Undo failed' })
    }
  },

  // Cmd+Shift+Z handler: pop the most-recent redo entry; if it matches the
  // current file, restore that revision. Mismatches are silently dropped (the
  // user moved on to a different file — replaying would be confusing).
  redoRevision: async () => {
    const { projectId, currentFileId, redoStack } = get()
    if (!projectId || !redoStack.length) return
    const next = redoStack[redoStack.length - 1]
    set((s) => ({ redoStack: s.redoStack.slice(0, -1) }))
    if (!next || next.fileId !== currentFileId) return
    try {
      await api.restoreRevision(projectId, currentFileId, next.revisionId)
      await get().loadFileForEditor(currentFileId)
      if (get().revisionDrawerOpen) await get().loadRevisions(currentFileId)
    } catch (err) {
      set({ toast: err?.message || 'Redo failed' })
    }
  },

  // ---- Git actions ----
  // The GitPanel drives these. We don't auto-load on project open: the panel
  // calls loadGitState() on mount, so projects without a backing repo never
  // pay the round-trip cost when the user doesn't open the panel.

  openGitPanel: () => set({ gitOpen: true }),
  closeGitPanel: () => set({ gitOpen: false }),
  dismissGitError: () => set({ gitError: null }),

  // Probe /branches; on 404 we mark the repo absent (empty-state UI). On
  // success we pick the current branch (default if available, else first)
  // and follow up with /log for that branch. Subsequent calls reuse the
  // existing branch unless it disappeared from the list.
  loadGitState: async () => {
    const { projectId, gitBranch } = get()
    if (!projectId) return
    set({ gitLoading: true, gitError: null })
    try {
      const branches = await gitApi.branches(projectId)
      const list = Array.isArray(branches) ? branches : []
      const current = list.find((b) => b.name === gitBranch)
        || list.find((b) => b.is_default)
        || list[0]
      const branchName = current?.name || ''
      set({
        gitBranches: list,
        gitBranch: branchName,
        gitRepoState: 'ready',
      })
      if (branchName) {
        const commits = await gitApi.log(projectId, branchName, 50)
        set({ gitCommits: Array.isArray(commits) ? commits : [] })
      } else {
        set({ gitCommits: [] })
      }
      set({ gitLoading: false })
    } catch (err) {
      // 404 → no repo yet (the panel's empty state takes over). Other errors
      // surface as inline banners and leave repoState alone so a transient
      // failure doesn't blow away an already-loaded view.
      if (err instanceof ApiError && err.status === 404) {
        set({
          gitRepoState: 'absent',
          gitBranches: [],
          gitBranch: '',
          gitCommits: [],
          gitLoading: false,
          gitError: null,
        })
      } else {
        set({
          gitLoading: false,
          gitError: err?.message || 'Could not load git state.',
        })
      }
    }
  },

  switchBranch: async (name, { force = false } = {}) => {
    const { projectId } = get()
    if (!projectId || !name) return
    set({ gitLoading: true, gitError: null })
    try {
      await gitApi.checkout(projectId, name, force)
      set({ gitBranch: name })
      // Refresh commits for the new branch + the file tree (server may have
      // swapped contents on the server side; local cached file content is
      // stale on the next selectFile).
      const commits = await gitApi.log(projectId, name, 50)
      set({ gitCommits: Array.isArray(commits) ? commits : [], gitLoading: false })
      try {
        const files = await api.listFiles(projectId)
        set({ files })
        // Reload current file content if it still exists, otherwise the
        // user will see the next file when they click around.
        const fid = get().currentFileId
        if (fid && files.some((f) => f.id === fid)) {
          await get().loadFileForEditor(fid)
        }
      } catch { /* tolerate */ }
    } catch (err) {
      // 409 with has_uncommitted: confirm and force.
      if (err instanceof ApiError && err.status === 409) {
        set({ gitLoading: false })
        if (typeof window !== 'undefined' && window.confirm(
          'You have uncommitted changes. Switch anyway and discard them?',
        )) {
          await get().switchBranch(name, { force: true })
          return
        }
      }
      set({
        gitLoading: false,
        gitError: err instanceof ApiError ? err.message : 'Checkout failed.',
      })
    }
  },

  gitCommit: async (message, branch) => {
    const { projectId } = get()
    if (!projectId || !message) return
    set({ gitError: null })
    try {
      const res = await gitApi.commit(projectId, message, branch || undefined)
      await get().loadGitState()
      // After a commit the file tree might have new sha-anchored content;
      // we rely on the user's next interaction to refresh the open file.
      return res
    } catch (err) {
      set({ gitError: err instanceof ApiError ? err.message : 'Commit failed.' })
      throw err
    }
  },

  gitPush: async () => {
    const { projectId } = get()
    if (!projectId) return
    set({ gitError: null })
    try {
      await gitApi.push(projectId)
      set({ toast: 'Pushed to GitHub' })
    } catch (err) {
      set({ gitError: err instanceof ApiError ? err.message : 'Push failed.' })
    }
  },

  gitPull: async (branch) => {
    const { projectId, gitBranch } = get()
    if (!projectId) return
    set({ gitError: null })
    try {
      await gitApi.pull(projectId, branch || gitBranch)
      await get().loadGitState()
      const fid = get().currentFileId
      if (fid) await get().loadFileForEditor(fid)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Diverged history — the backend hands back {ahead, behind}. We
        // surface a hint and stop short of forcing.
        let msg = 'Branches diverged — push or rebase before pulling.'
        try {
          const parsed = JSON.parse(err.message)
          if (parsed && (parsed.ahead != null || parsed.behind != null)) {
            msg = `Diverged (${parsed.ahead ?? '?'} ahead / ${parsed.behind ?? '?'} behind). Push or merge first.`
          }
        } catch { /* ignore */ }
        set({ gitError: msg })
      } else {
        set({ gitError: err instanceof ApiError ? err.message : 'Pull failed.' })
      }
    }
  },

  gitMerge: async (from_branch, into_branch) => {
    const { projectId } = get()
    if (!projectId) return
    set({ gitError: null })
    try {
      const res = await gitApi.merge(projectId, from_branch, into_branch)
      await get().loadGitState()
      return res
    } catch (err) {
      // Conflicts are handled in the MergeDialog itself (it parses the 409).
      set({ gitError: err instanceof ApiError ? err.message : 'Merge failed.' })
      throw err
    }
  },

  gitDelete: async () => {
    const { projectId } = get()
    if (!projectId) return
    set({ gitError: null })
    try {
      await gitApi.deleteRepo(projectId)
      set({
        gitRepoState: 'absent',
        gitBranches: [],
        gitBranch: '',
        gitCommits: [],
      })
    } catch (err) {
      set({ gitError: err instanceof ApiError ? err.message : 'Delete failed.' })
    }
  },

  // ---- Activity timeline ----
  // The ActivityTimeline panel drives these. We don't auto-load on project
  // open — the panel calls loadActivity() once on mount. `loadActivity(true)`
  // appends the next page using the in-state cursor; `loadActivity(false)`
  // (or no arg) refreshes from the top.
  openActivity: () => {
    set({ activityOpen: true })
    // Refresh from the top each time the user re-opens; cheap and avoids the
    // panel showing stale entries after a long idle.
    const { activityEvents, activityLoading } = useWorkspace.getState()
    if (!activityLoading && activityEvents.length === 0) {
      // First-time open — kick off the initial fetch. Subsequent opens with
      // existing rows do NOT re-fetch automatically; the user's Refresh
      // button drives that explicitly.
      void useWorkspace.getState().loadActivity(false)
    }
  },
  closeActivity: () => set({ activityOpen: false }),

  loadActivity: async (more = false) => {
    const { projectId, activityLoading, activityNextCursor, activityEvents } = get()
    if (!projectId || activityLoading) return
    if (more && !activityNextCursor) return
    set({ activityLoading: true, activityError: null })
    try {
      const before = more ? activityNextCursor : null
      const resp = await api.getActivity(projectId, before, 50)
      const events = Array.isArray(resp?.events) ? resp.events : []
      set({
        activityEvents: more ? [...activityEvents, ...events] : events,
        activityNextCursor: resp?.next_cursor || null,
        activityLoading: false,
      })
    } catch (err) {
      set({
        activityLoading: false,
        activityError: err instanceof ApiError ? err.message : (err?.message || 'Could not load activity.'),
      })
    }
  },
}))

// Resolve an assembly's components → flat parts list. Thin wrapper around
// the pure helper in src/lib/assembly.js — supplies the per-file loader and
// surfaces missing-part_id warnings as toasts.
async function resolveAssemblyParts(_get, projectId, contentJson) {
  return resolveAssemblyPartsHelper({
    content: contentJson,
    loadParts: (fileId) => loadComponentParts(projectId, fileId),
    // Cross-project external_ref dispatch (ROADMAP row 67 Phase 2/3). The
    // cache-aware wrapper (loadExternalParts from assembly.js) handles
    // lookup/encode/decode; loadExternalComponentParts is the recompile fn.
    loadExternalParts: (ref) => loadExternalParts({
      ref,
      recompile: loadExternalComponentParts,
      encodePayload,
      decodePayload,
    }),
    onMissing: (componentId, partId) => {
      // Best-effort UI surface; the renderer will simply skip the component.
      try {
        useWorkspace.setState({
          toast: `Component "${componentId}": missing part "${partId}"`,
        })
      } catch { /* ignore */ }
    },
  })
}

// Cross-project loader: turn an `external_ref` into the resolver's expected
// `[{id, geom, color?}]` shape. Handles board_outline_2d, board_3d, and mesh.
// Caches by (file_id, content-hash) so a re-render of the same external source
// is free. The derived-artifacts cache (assembly.js loadExternalParts) handles
// the server-side encode/decode round-trip for cross-session caching.
async function loadExternalComponentParts(ref) {
  if (!ref || !ref.kind) return []
  let file
  try {
    file = await api.getFile(ref.project_id, ref.file_id)
  } catch (err) {
    console.warn(`${ref.kind}: failed to fetch ${ref.project_id}/${ref.file_id}:`, err)
    return []
  }
  const sig = strHash(file?.content || '')
  const cachePrefix = ref.kind === 'board_outline_2d' ? 'bo2d' : ref.kind === 'board_3d' ? 'b3d' : ref.kind === 'mesh' ? 'mesh' : 'unk'
  const k = cacheKey(ref.file_id, `${cachePrefix}::${sig}`)
  const hit = componentResultCache.get(k)
  if (hit) return hit.parts

  let parts = []
  if (ref.kind === 'board_outline_2d') {
    parts = await loadBoardOutlineParts(file)
  } else if (ref.kind === 'board_3d') {
    parts = await loadBoard3DParts(file)
  } else if (ref.kind === 'mesh') {
    parts = await loadMeshParts(file)
  }

  componentResultCache.set(k, { parts })
  return parts
}

async function loadBoardOutlineParts(file) {
  const res = await runCircuit(file?.content || '')
  if (res && res.error) {
    console.warn(`board_outline_2d: compile failed for ${file.id}: ${res.error}`)
  }
  const sketchLike = extractBoardOutline(Array.isArray(res?.raw) ? res.raw : null)
  let geom
  try {
    geom = sketchToGeom2(sketchLike)
  } catch (err) {
    console.warn(`board_outline_2d: sketchToGeom2 failed for ${file.id}:`, err)
    return []
  }
  return [{ id: '__board_outline__', geom }]
}

async function loadBoard3DParts(file) {
  const res = await runCircuit(file?.content || '')
  if (res && res.error) {
    console.warn(`board_3d: compile failed for ${file.id}: ${res.error}`)
  }
  return buildCircuitBoardParts(Array.isArray(res?.raw) ? res.raw : [])
}

async function loadMeshParts(file) {
  if (!file.mesh_url) return []
  try {
    const out = await loadMeshFromURL(file.mesh_url)
    return out?.parts || []
  } catch (err) {
    console.warn(`mesh: load failed for ${file.id}:`, err)
    return []
  }
}

function buildCircuitBoardParts(circuitJson) {
  if (!Array.isArray(circuitJson)) return []
  const { primitives, transforms, colors } = JSCADModeling
  const parts = []

  const board = circuitJson.find((e) => e && e.type === 'pcb_board')
  const thickness = (board && Number(board.thickness)) > 0 ? Number(board.thickness) : 1.6
  if (board) {
    const cx = Number(board.center?.x) || 0
    const cy = Number(board.center?.y) || 0
    let boardGeom = null
    if (Array.isArray(board.outline) && board.outline.length >= 3) {
      try {
        const points = board.outline.map((p) => [Number(p.x) || 0, Number(p.y) || 0])
        const poly = primitives.polygon({ points })
        boardGeom = JSCADModeling.extrusions.extrudeLinear({ height: thickness }, poly)
      } catch {
        boardGeom = null
      }
    }
    if (!boardGeom) {
      const w = Number(board.width) || 50
      const h = Number(board.height) || 50
      boardGeom = primitives.cuboid({ size: [w, h, thickness], center: [cx, cy, thickness / 2] })
    }
    boardGeom = colors.colorize([0.62, 0.49, 0.27], boardGeom)
    parts.push({ id: '__board__', geom: boardGeom })
  } else {
    const fallback = primitives.cuboid({ size: [50, 50, thickness], center: [0, 0, thickness / 2] })
    parts.push({ id: '__board__', geom: colors.colorize([0.62, 0.49, 0.27], fallback) })
  }

  const pcbComponentById = new Map()
  for (const e of circuitJson) {
    if (e && e.type === 'pcb_component') pcbComponentById.set(e.pcb_component_id, e)
  }
  const sourceById = new Map()
  for (const e of circuitJson) {
    if (e && e.type === 'source_component') sourceById.set(e.source_component_id, e)
  }

  let idx = 0
  for (const e of circuitJson) {
    if (!e || e.type !== 'cad_component') continue
    const pcbC = pcbComponentById.get(e.pcb_component_id)
    const src = sourceById.get(e.source_component_id)
    const px = Number(e.position?.x) || 0
    const py = Number(e.position?.y) || 0
    const pz = Number(e.position?.z) || thickness
    const rx = (Number(e.rotation?.x) || 0) * Math.PI / 180
    const ry = (Number(e.rotation?.y) || 0) * Math.PI / 180
    const rz = (Number(e.rotation?.z) || 0) * Math.PI / 180

    let sx = Number(e.size?.x) || Number(pcbC?.width) || 2.0
    let sy = Number(e.size?.y) || Number(pcbC?.height) || 1.2
    let sz = Number(e.size?.z) || 0.6
    if (sx <= 0) sx = 1.0
    if (sy <= 0) sy = 1.0
    if (sz <= 0) sz = 0.5

    const name = src?.name || `C${idx}`
    let geom = primitives.cuboid({ size: [sx, sy, sz] })
    geom = transforms.rotate([rx, ry, rz], geom)
    geom = transforms.translate([px, py, pz + sz / 2], geom)
    geom = colors.colorize(componentColor(name), geom)
    parts.push({ id: name, geom })
    idx++
  }
  return parts
}

function componentColor(name) {
  const c = String(name || '').charAt(0).toUpperCase()
  switch (c) {
    case 'R': return [0.85, 0.30, 0.30]
    case 'C': return [0.30, 0.55, 0.85]
    case 'L': return [0.85, 0.65, 0.30]
    case 'D': return [0.55, 0.85, 0.30]
    case 'U': return [0.50, 0.40, 0.65]
    case 'Q': return [0.85, 0.50, 0.65]
    case 'J': return [0.65, 0.65, 0.65]
    case 'S': return [0.80, 0.55, 0.40]
    default:  return [0.55, 0.60, 0.65]
  }
}

// loadComponentParts: fetch + run a referenced file. JSCAD or STEP or nested
// assembly. Cached by (file_id, content-hash, config_id) so re-rendering
// after a transform tweak is fast and switching configs invalidates only
// what it should. Exported via the store action so the AssemblyEditor can
// probe a source's part-id list for its dropdown.
//
// `configId` is the component's pinned configuration (see
// src/lib/assembly.js parseAssembly). For files that declare configurations
// the active config's `params` are merged OVER the equations scope before
// running JSCAD. STEP-backed Parts ignore configurations for geometry
// purposes (the STEP file is fixed) but their config_id still flows
// through to the BOM aggregation backend.
async function loadComponentParts(projectId, fileId, configId) {
  // First-pass: cheap content fetch (we always need the latest text/blob).
  const file = await api.getFile(projectId, fileId)
  const name = (file.name || '').toLowerCase()
  const cfgKey = configId ? `::cfg=${configId}` : ''
  if (file.kind === 'assembly') {
    // Nested assemblies — recursive resolve. Cache by content hash.
    const sig = strHash(file.content || '')
    const k = cacheKey(file.id, sig) + cfgKey
    const hit = componentResultCache.get(k)
    if (hit) return hit.parts
    const parts = await resolveAssemblyParts(() => ({}), projectId, file.content || '')
    componentResultCache.set(k, { parts })
    return parts
  }
  if (file.kind === 'part') {
    // Library Part. The 3D geometry (if any) lives behind `model_storage_key`
    // which points at a Storage blob — same shape as a STEP upload. We pull
    // the blob, parse via the STEP loader (only STEP is supported in v1; GLB
    // arrives in Phase 2), and emit a single Object id'd by the Part's name.
    // Parts without a model contribute zero parts (BOM still counts them).
    const sig = strHash(file.content || '')
    const k = cacheKey(file.id, sig) + cfgKey
    const hit = componentResultCache.get(k)
    if (hit) return hit.parts
    const meta = parsePart(file.content || '')
    if (!meta.model_storage_key) {
      componentResultCache.set(k, { parts: [] })
      return []
    }
    try {
      const buf = await fetchStorageBlob(meta.model_storage_key)
      const { parts: stepParts } = await loadStep(buf)
      // Re-id everything under a single Part-named id so downstream
      // assembly resolution gives the user a clean single-handle Object.
      // When a config is pinned, suffix it so the assembly's Object picker
      // can distinguish M3 vs M4 instances of the same Part.
      const cfg = configId ? getActiveConfig(meta, configId) : null
      const labelSuffix = cfg?.label ? ` (${cfg.label})` : ''
      const baseLabel = `${meta.name}${labelSuffix}`
      const partsOut = (stepParts || []).map((p, idx) => ({
        ...p,
        id: stepParts.length === 1 ? baseLabel : `${baseLabel}/${p.id || idx}`,
      }))
      componentResultCache.set(k, { parts: partsOut })
      return partsOut
    } catch (err) {
      console.warn(`Library Part ${meta.name}: failed to load 3D model:`, err)
      componentResultCache.set(k, { parts: [] })
      return []
    }
  }
  if (name.endsWith('.step') || name.endsWith('.stp') || file.kind === 'step') {
    // STEP — cache by file id (binary content unlikely to change in place).
    // Performance Phase 3: prefer the server-tessellated .glb when present.
    const k = cacheKey(file.id, 'step')
    const hit = componentResultCache.get(k)
    if (hit) return hit.parts
    let parts = null
    if (file.mesh_url) {
      try {
        const out = await loadMeshFromURL(file.mesh_url)
        if (out?.parts?.length) parts = out.parts
      } catch (err) {
        console.warn('component mesh url load failed, falling back to STEP:', err)
      }
    }
    if (!parts) {
      const buf = await api.downloadFileURL(projectId, file.id)
      const out = await loadStep(buf)
      parts = out.parts || []
    }
    componentResultCache.set(k, { parts })
    return parts
  }
  // JSCAD — cache by content hash so saves reload it. Config_id is only
  // meaningful here when the JSCAD source destructures `params` (it
  // probably doesn't, since plain `.jscad` files don't currently declare
  // configurations); we still carry it in the cache key for forward-compat.
  const sig = strHash(file.content || '')
  const k = cacheKey(file.id, sig) + cfgKey
  const hit = componentResultCache.get(k)
  if (hit) return hit.parts
  const res = await runJscad(file.content || '', null)
  if (res.error) throw new Error(res.error)
  const parts = res.parts || []
  componentResultCache.set(k, { parts })
  return parts
}

// Fetch a blob from the local-storage backend's auth-protected /api/blobs/
// route. Returns an ArrayBuffer suitable for occt-import-js. We re-use the
// auth-token plumbing of the api wrapper via a thin call — the blob route
// is a standard authed GET.
async function fetchStorageBlob(storageKey) {
  const url = `/api/blobs/${encodeURI(storageKey)}`
  const { useAuth } = await import('./auth.js')
  const token = useAuth.getState().accessToken
  const headers = {}
  if (token) headers.authorization = `Bearer ${token}`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`blob fetch ${res.status}`)
  return res.arrayBuffer()
}

// Public re-export: the AssemblyEditor uses this to populate its part_id
// dropdown without poking at module-private internals. `configId` is
// optional — pass it when previewing a specific configuration (e.g. the
// component's pinned config); otherwise the file's default_config wins.
export function loadFilePartsForProject(projectId, fileId, configId) {
  return loadComponentParts(projectId, fileId, configId || null)
}

// Resolve an absolute POSIX-like path (e.g. "/folder/foo.sketch") against
// the project's file list. Returns the matched File row or undefined. Used
// by the JSCAD sketch-import resolver and the SketchView's 3D-context
// multi-select. Tolerates both leading and trailing slashes.
export function findFileByPath(files, path) {
  if (!Array.isArray(files) || !path) return undefined
  const norm = path.startsWith('/') ? path.slice(1) : path
  const segs = norm.split('/').filter(Boolean)
  if (segs.length === 0) return undefined
  const byId = new Map(files.map((f) => [f.id, f]))
  // Walk from each root match downward.
  let parents = files.filter((f) => f.parent_id == null)
  let current
  for (let i = 0; i < segs.length; i++) {
    const want = segs[i]
    current = parents.find((f) => f.name === want)
    if (!current) return undefined
    if (i < segs.length - 1) {
      parents = files.filter((f) => f.parent_id === current.id)
    }
  }
  return current && byId.get(current.id)
}

// Return absolute POSIX paths (e.g. "/parts/outline.sketch") for every
// .sketch file in the project's file tree. Used by the JSCAD sketch-import
// error message to list available alternatives when a referenced sketch path
// can't be resolved.
export function collectSketchPaths(files) {
  if (!Array.isArray(files)) return []
  const byId = new Map(files.map((f) => [f.id, f]))
  function pathOf(file) {
    const parts = []
    let cur = file
    while (cur) {
      parts.unshift(cur.name)
      cur = cur.parent_id != null ? byId.get(cur.parent_id) : null
    }
    return '/' + parts.join('/')
  }
  return files
    .filter((f) => f.name && f.name.endsWith('.sketch'))
    .map(pathOf)
    .sort()
}

// Persist a programmatic source edit: update the local content, run JSCAD to
// refresh parts, and PATCH the file (so other clients pick it up too). We
// don't go through the autosave timer because the user didn't type — they
// clicked an action and expects an immediate result.
async function applySourceEdit(set, get, nextSource) {
  const { projectId, currentFileId } = get()
  if (!projectId || !currentFileId) return
  set({ currentFileContent: nextSource, dirty: false, saving: true })
  try {
    // Run JSCAD locally first so the renderer updates without waiting on PATCH.
    const res = await runJscad(nextSource)
    if (!res.error) {
      set({ parts: res.parts || [], partsError: null })
    } else {
      set({ partsError: res.error })
    }
    const updated = await api.updateFile(projectId, currentFileId, { content: nextSource })
    set((s) => ({
      saving: false,
      currentFile: updated,
      files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
    }))
  } catch (err) {
    set({ saving: false, toast: err?.message || 'Failed to save edit' })
  }
}
