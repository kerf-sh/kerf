// Run a user's JSCAD source and return parts.
//
// Convention (see backend/llm_docs/jscad.md / seed file): the user's file's default export is
//   function (modeling) { return [{id, geom}, ...] }
// This avoids depending on importmap / module resolution at runtime — we just
// hand them the @jscad/modeling namespace.
//
// We accept a few legacy shapes too:
//   - `export default function ({primitives, ...}) {...}`
//   - The traditional JSCAD `export const main = (params) => ...` returning a
//     single Geom3 or array of Geom3 (we'll wrap with auto-generated ids).
//
// We evaluate by stripping the `export default`/named-export keywords and
// wrapping the body in `new Function('modeling', body)`.
//
// Phase 1 perf change: evaluation runs in a Web Worker so boolean ops don't
// freeze the editor. The worker is created lazily on first call. If the
// worker can't be spun up (e.g. running in a test/Node env, or a runtime
// failure), we fall back to running on the main thread so a worker bug
// can never break the editor entirely.
//
// Cancellation: callers may queue evaluations faster than the worker can
// finish them (typing in Monaco). Each call gets a monotonic runId; only
// the latest run's result is delivered to its caller, older runs resolve
// with `{ stale: true }` so callers can discard them. `cancelJscad()`
// invalidates everything in flight (used when navigating away from a file).

import * as modeling from '@jscad/modeling'
import { parseSketch } from './sketchSolver.js'
import { sketchToGeom2 } from './sketchGeom2.js'

// Equations injection — see store/workspace.js loadProject for the resolver
// that walks the project tree, parses every `.equations` file, evaluates the
// rows, and returns the merged scope. The runner pulls the scope on every
// evaluation so a user editing equations triggers a re-run via the standard
// debounce pipeline (the workspace store touches the JSCAD source after the
// equations file mutates).
let equationsResolver = null
export function setEquationsResolver(fn) {
  // fn: () => Promise<{ values: { [name]: number }, errors, duplicates }> | null
  equationsResolver = fn || null
}

async function resolveEquationsScope() {
  if (!equationsResolver) return {}
  try {
    const res = await equationsResolver()
    return res?.values || {}
  } catch {
    return {}
  }
}

// ---- Main-thread fallback (also used inline if the worker never spins up) --

// Pull out `import X from '/foo.sketch'` lines so the main thread can resolve
// each one to a Geom2 (asynchronously, before the worker call). Returns the
// stripped source plus an array of {binding, path}. We deliberately handle
// only the default-import form — `import { ... } from '/foo.sketch'` is not a
// thing in our runtime since sketches export a single profile.
//   Matches: import foo from "/path.sketch"
//            import foo from '/path.sketch'
//            import foo from "./path.sketch"  (resolved later)
const SKETCH_IMPORT_RE = /^[ \t]*import\s+([A-Za-z_$][\w$]*)\s+from\s+['"]([^'"\n]+\.sketch)['"];?[ \t]*$/gm

function extractSketchImports(code) {
  const imports = []
  const stripped = code.replace(SKETCH_IMPORT_RE, (_m, binding, path) => {
    imports.push({ binding, path })
    return `// resolved sketch import: ${binding} <- ${path}`
  })
  return { stripped, imports }
}

function transformSource(code) {
  // Remove top-level imports — the user's code shouldn't need them, but seeded
  // examples sometimes include `import * as modeling from '@jscad/modeling'`.
  // Sketch imports are removed by the caller before we land here.
  let src = code.replace(/^[ \t]*import[^\n;]*['"][^'"\n]+['"][^\n;]*;?[ \t]*$/gm, '')

  // Capture `export default <expr>` and rewrite to `return <expr>`.
  // Also handle `export default function ...` and `export default async function ...`.
  if (/export\s+default\s+/.test(src)) {
    src = src.replace(/export\s+default\s+/, 'return ')
  } else if (/export\s+(?:const|let|var|function)\s+main\b/.test(src)) {
    // Legacy main entry — strip the `export` keyword and `return main` at end.
    src = src.replace(/export\s+(const|let|var|function)\s+main\b/, '$1 main')
    src += '\n;return main;'
  } else {
    // Last resort: assume the file ends with a function expression.
    src += '\n;return (typeof main !== "undefined" ? main : null);'
  }
  return src
}

// Hook used by the editor: lets the caller register a project-scoped resolver
// for `.sketch` paths → Geom2. We keep this as a global mutable so the runner
// stays decoupled from the workspace store; jscadRunner.js doesn't import
// from store/workspace.js (which would create a cycle through the store's
// own runJscad call).
let sketchResolver = null
export function setSketchResolver(fn) {
  // fn: (path: string) => Promise<{ content: string } | null>
  sketchResolver = fn || null
}

async function resolveSketchImports(imports) {
  const out = {}
  if (!imports || imports.length === 0) return out
  if (!sketchResolver) {
    if (typeof console !== 'undefined') {
      console.warn('jscadRunner: .sketch imports requested but no resolver registered; returning empty Geom2 for each')
    }
  }
  for (const { binding, path } of imports) {
    try {
      const file = sketchResolver ? await sketchResolver(path) : null
      const sketch = parseSketch(file?.content || '')
      const geom = sketchToGeom2(sketch)
      out[binding] = geom
    } catch (err) {
      if (typeof console !== 'undefined') {
        console.warn(`jscadRunner: failed to resolve sketch ${path}:`, err)
      }
      out[binding] = sketchToGeom2(parseSketch(''))
    }
  }
  return out
}

function normalizeParts(out) {
  if (out == null) return []
  if (Array.isArray(out)) {
    if (out.length === 0) return []
    if (out[0] && typeof out[0] === 'object' && 'geom' in out[0]) {
      return out.map((p, i) => ({ id: p.id ?? `part-${i}`, geom: p.geom }))
    }
    return out.map((g, i) => ({ id: `part-${i}`, geom: g }))
  }
  if (typeof out === 'object' && 'geom' in out) return [{ id: out.id ?? 'part-0', geom: out.geom }]
  return [{ id: 'part-0', geom: out }]
}

const SCOPE_KEYS = [
  'primitives', 'transforms', 'booleans', 'extrusions', 'expansions',
  'measurements', 'colors', 'utils', 'maths', 'curves', 'geometries',
  'hulls', 'text',
]

async function runJscadOnMainThread(code, configParams) {
  if (!code || !code.trim()) return { parts: [] }
  try {
    const { stripped, imports } = extractSketchImports(code)
    const sketchProfiles = await resolveSketchImports(imports)
    const equationsValues = await resolveEquationsScope()
    // Configurations / variants — the active config's params layer over the
    // equations scope (config wins on collision). Passing configParams=null
    // (the common case for a file without configurations) is a no-op.
    const mergedParams = (configParams && typeof configParams === 'object')
      ? { ...equationsValues, ...configParams }
      : equationsValues
    const body = transformSource(stripped)
    const sketchKeys = Object.keys(sketchProfiles)
    const args = ['modeling', 'params', ...SCOPE_KEYS, ...sketchKeys]
    const values = [
      modeling,
      mergedParams,
      ...SCOPE_KEYS.map((k) => modeling[k]),
      ...sketchKeys.map((k) => sketchProfiles[k]),
    ]
    const factory = new Function(...args, body)
    const exported = factory(...values)
    // Build a scope the user's main-export function can destructure.
    // Matches the worker's contract: { ...modeling, params } so a single
    // `function ({ primitives, transforms, params })` argument list works.
    const userScope = { ...modeling, params: mergedParams }
    let result = typeof exported === 'function' ? exported(userScope) : exported
    if (result && typeof result.then === 'function') result = await result
    const parts = normalizeParts(result)
    return { parts }
  } catch (err) {
    return { error: err && err.message ? err.message : String(err) }
  }
}

// ---- Worker plumbing --------------------------------------------------------

let worker = null
let workerBroken = false
let nextRunId = 1
const pending = new Map() // runId → { resolve, reject }
let latestRunId = 0

function ensureWorker() {
  if (workerBroken) return null
  if (worker) return worker
  if (typeof Worker === 'undefined') {
    workerBroken = true
    return null
  }
  try {
    worker = new Worker(new URL('./jscadWorker.js', import.meta.url), { type: 'module' })
    worker.addEventListener('message', (ev) => {
      const { type, runId } = ev.data || {}
      const entry = pending.get(runId)
      if (!entry) return
      pending.delete(runId)
      if (runId !== latestRunId) {
        // Stale — discard. Caller awaits but receives the canonical
        // empty-stale shape so it can no-op.
        entry.resolve({ stale: true })
        return
      }
      if (type === 'error') {
        entry.resolve({ error: ev.data.error })
      } else if (type === 'result') {
        entry.resolve({ parts: ev.data.parts || [] })
      } else {
        entry.resolve({ error: 'unknown worker message' })
      }
    })
    worker.addEventListener('error', (ev) => {
      // Fatal worker error: tear it down and mark broken so subsequent calls
      // run inline. Reject any pending callers with an error so they fall back.
      try { worker.terminate() } catch { /* ignore */ }
      worker = null
      workerBroken = true
      for (const [, entry] of pending) entry.reject(new Error(ev.message || 'jscad worker error'))
      pending.clear()
    })
    return worker
  } catch {
    workerBroken = true
    worker = null
    return null
  }
}

// Public API ------------------------------------------------------------------

// runJscad(code, configParams?) — the optional `configParams` is the active
// configuration's `params` map for the file (per-file parameter overrides;
// see src/lib/part.js getActiveConfig). Merged OVER the equations scope so
// configs always win on key collision. The workspace store passes it; the
// public surface stays backwards compatible (one-arg callers behave as
// before).
export async function runJscad(code, configParams) {
  const w = ensureWorker()
  // Pre-resolve any `.sketch` imports on the main thread so the worker only
  // ever evaluates pure JSCAD code with sketch profiles already converted to
  // Geom2 values. The transferred Geom2 is structured-cloneable (plain
  // arrays + numbers), so this round-trips cleanly. If there are no sketch
  // imports the work is essentially zero.
  const { stripped, imports } = extractSketchImports(code || '')
  const sketchProfiles = imports.length > 0 ? await resolveSketchImports(imports) : {}
  const equationsValues = await resolveEquationsScope()
  const mergedParams = (configParams && typeof configParams === 'object')
    ? { ...equationsValues, ...configParams }
    : equationsValues
  if (!w) {
    // Inline fallback: still respect runId so a later call wins on the main
    // thread too (used by tests and worker-failure paths).
    const runId = ++nextRunId
    latestRunId = runId
    const res = await runJscadOnMainThread(code, configParams)
    if (runId !== latestRunId) return { stale: true }
    return res
  }
  const runId = ++nextRunId
  latestRunId = runId
  let promise
  try {
    promise = new Promise((resolve, reject) => {
      pending.set(runId, { resolve, reject })
      // The worker contract uses `equationsValues` as the param map; we send
      // the merged scope so the worker doesn't need to know about configs.
      w.postMessage({ type: 'run', runId, code: stripped, sketchProfiles, equationsValues: mergedParams })
    })
    const res = await promise
    return res
  } catch {
    // Worker died mid-flight → fall back to main thread.
    return runJscadOnMainThread(code, configParams)
  }
}

// Invalidate all in-flight runs so their results are dropped. Called when the
// user navigates away from a file or closes the editor.
export function cancelJscad() {
  latestRunId = ++nextRunId
  for (const [, entry] of pending) entry.resolve({ stale: true })
  pending.clear()
}

// Default seed for new files. Backend mirrors this when creating main.jscad.
export const DEFAULT_JSCAD = `// Kerf: default export receives the @jscad/modeling module and returns parts.
export default function ({ primitives, transforms, booleans }) {
  const base = primitives.cuboid({ size: [40, 40, 10] })
  const peg  = transforms.translate([0, 0, 10], primitives.cylinder({ radius: 6, height: 20 }))
  return [
    { id: 'base', geom: base },
    { id: 'peg',  geom: peg  },
  ]
}
`
