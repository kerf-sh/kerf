// Run a `.circuit.tsx` source through tscircuit and return the resulting
// Circuit JSON, split into the three pragmatic buckets the editor cares about
// (schematic, pcb, and 3D).
//
// Mirrors jscadRunner.js:
//   - Lazy-spun module worker; cancellation via runId.
//   - Falls back to a no-op error result if the worker can't spin up. We
//     deliberately don't run the user's TSX on the main thread because:
//       * sucrase + tscircuit + manifold + react-reconciler push ~6 MB of
//         dependencies. Loading them on the main thread freezes the editor.
//       * Sandbox-eval'ing user TSX inside the renderer process is a
//         security smell. The worker is sandboxed enough.
//
// The split is purely a frontend convenience — it's a flat .filter() over
// the AnyCircuitElement[] returned by tscircuit's getCircuitJson(). Anything
// not in the schematic/pcb/3d buckets stays available via .raw for tools that
// need source_* / errors / simulation_*.

let worker = null
let workerBroken = false
let nextRunId = 1
let latestRunId = 0
const pending = new Map()

function ensureWorker() {
  if (workerBroken) return null
  if (worker) return worker
  if (typeof Worker === 'undefined') {
    workerBroken = true
    return null
  }
  try {
    worker = new Worker(new URL('./circuitWorker.js', import.meta.url), { type: 'module' })
    worker.addEventListener('message', (ev) => {
      const { type, runId } = ev.data || {}
      const entry = pending.get(runId)
      if (!entry) return
      pending.delete(runId)
      if (runId !== latestRunId) {
        entry.resolve({ stale: true })
        return
      }
      if (type === 'error') {
        entry.resolve({ error: ev.data.message || 'unknown circuit worker error' })
        return
      }
      if (type === 'result') {
        const json = Array.isArray(ev.data.circuitJson) ? ev.data.circuitJson : []
        entry.resolve(splitCircuitJson(json))
        return
      }
      entry.resolve({ error: 'unknown circuit worker message' })
    })
    worker.addEventListener('error', (ev) => {
      try { worker.terminate() } catch { /* ignore */ }
      worker = null
      workerBroken = true
      for (const [, entry] of pending) entry.reject(new Error(ev.message || 'circuit worker error'))
      pending.clear()
    })
    return worker
  } catch {
    workerBroken = true
    worker = null
    return null
  }
}

// Bucket the flat circuit_json into the three views the editor tabs render.
//
// Buckets (by `type` prefix):
//   - schematic: schematic_*, source_component (for ref designators / values)
//   - pcb:       pcb_*
//   - threeD:    cad_component, cad_*
// `raw` is the whole array so renderers that already accept circuit-to-svg's
// input shape can pass it straight through (we don't materialise per-bucket
// arrays for them — splitting twice is wasteful).
export function splitCircuitJson(json) {
  const schematic = []
  const pcb = []
  const threeD = []
  const errors = []
  if (Array.isArray(json)) {
    for (const el of json) {
      if (!el || typeof el !== 'object' || typeof el.type !== 'string') continue
      const t = el.type
      if (t.startsWith('schematic_')) schematic.push(el)
      else if (t === 'source_component' || t === 'source_port' || t === 'source_trace' || t === 'source_net') schematic.push(el)
      else if (t.startsWith('pcb_')) pcb.push(el)
      else if (t === 'cad_component' || t.startsWith('cad_')) threeD.push(el)
      // Errors are buried in *_error records or a top-level error array; we
      // surface anything with an explicit `error_type` field.
      if (typeof el.error_type === 'string') errors.push(el)
    }
  }
  return {
    raw: json,
    schematic,
    pcb,
    threeD,
    errors,
  }
}

// Public API ------------------------------------------------------------------

// Compile a .circuit.tsx source. Resolves to:
//   { raw, schematic, pcb, threeD, errors }    on success
//   { stale: true }                              if a newer call superseded it
//   { error: string }                            on compile/eval failure
export async function runCircuit(source) {
  const w = ensureWorker()
  if (!w) {
    // No fallback — the dependency surface is too big to import on the main
    // thread. Surface an explicit error and let the editor's error pane render
    // it. This path only triggers in non-Worker environments (Node tests).
    return { error: 'Circuit compiler requires a Web Worker; not available in this environment.' }
  }
  const runId = ++nextRunId
  latestRunId = runId
  return new Promise((resolve, reject) => {
    pending.set(runId, { resolve, reject })
    try {
      w.postMessage({ type: 'compile', runId, source: source || '' })
    } catch (err) {
      pending.delete(runId)
      resolve({ error: err?.message || 'failed to post message' })
    }
  })
}

// Invalidate every in-flight run. Called when the user closes the editor or
// switches off a .circuit.tsx file mid-compile.
export function cancelCircuit() {
  latestRunId = ++nextRunId
  for (const [, entry] of pending) entry.resolve({ stale: true })
  pending.clear()
}

// Default seed for a brand-new circuit file. Three-resistor voltage divider —
// minimal but enough to exercise the full pipeline (schematic + PCB + 3D).
export const DEFAULT_CIRCUIT = `import { Circuit } from "tscircuit"

// Kerf: default export is a JSX element OR a Circuit instance. The editor
// renders the schematic, PCB, and 3D views in their respective tabs.
export default (
  <board width="20mm" height="20mm">
    <resistor name="R1" resistance="10k" footprint="0402" pcbX={-5} pcbY={0} schX={-3} />
    <resistor name="R2" resistance="10k" footprint="0402" pcbX={0}  pcbY={0} schX={0}  />
    <resistor name="R3" resistance="10k" footprint="0402" pcbX={5}  pcbY={0} schX={3}  />
    <trace from=".R1 .pin2" to=".R2 .pin1" />
    <trace from=".R2 .pin2" to=".R3 .pin1" />
  </board>
)
`
