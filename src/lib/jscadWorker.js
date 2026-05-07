// JSCAD evaluation worker.
//
// Receives `{type: 'run', code, runId}` messages on the main thread, evaluates
// the user's JSCAD source against the @jscad/modeling namespace, and posts back
// `{type: 'result', runId, parts}` or `{type: 'error', runId, error}`.
//
// Trade-off (see ROADMAP.md "Performance roadmap" Phase 1):
//   We send Geom3 parts back via structured-clone (no transferables). Geom3
//   polygons are deeply nested arrays, so structured-clone handles them but
//   isn't cheap for huge models. We picked the simpler path; if a profiler
//   later shows the postMessage clone dominating, switch to flattening
//   polygons into per-polygon Float32Arrays and transferring those.
//
// The main thread (jscadRunner.js) handles cancellation by ignoring stale
// results whose runId doesn't match the latest. We don't actually interrupt
// the evaluator inside the worker — JS doesn't expose a way to do that
// without terminating the worker. For a debounced editor-driven loop this
// is fine: the next `run` message overwrites the in-flight runId, and we
// just discard the eventual stale result. If a single eval is huge enough to
// matter, the user will already have moved on by the time it returns.

import * as modeling from '@jscad/modeling'

function transformSource(code) {
  let src = code.replace(/^[ \t]*import[^\n;]*['"][^'"\n]+['"][^\n;]*;?[ \t]*$/gm, '')
  if (/export\s+default\s+/.test(src)) {
    src = src.replace(/export\s+default\s+/, 'return ')
  } else if (/export\s+(?:const|let|var|function)\s+main\b/.test(src)) {
    src = src.replace(/export\s+(const|let|var|function)\s+main\b/, '$1 main')
    src += '\n;return main;'
  } else {
    src += '\n;return (typeof main !== "undefined" ? main : null);'
  }
  return src
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

async function runJscadInWorker(code, sketchProfiles) {
  if (!code || !code.trim()) return { parts: [] }
  try {
    const body = transformSource(code)
    const sketchKeys = sketchProfiles ? Object.keys(sketchProfiles) : []
    const args = ['modeling', ...SCOPE_KEYS, ...sketchKeys]
    const values = [
      modeling,
      ...SCOPE_KEYS.map((k) => modeling[k]),
      ...sketchKeys.map((k) => sketchProfiles[k]),
    ]
    const factory = new Function(...args, body)
    const exported = factory(...values)
    let result = typeof exported === 'function' ? exported(modeling) : exported
    if (result && typeof result.then === 'function') result = await result
    const parts = normalizeParts(result)
    // Strip non-cloneable members defensively. JSCAD Geom3s are { polygons: [{vertices}], transforms? }.
    // structuredClone handles plain arrays/objects fine; we don't need to do anything extra here.
    return { parts }
  } catch (err) {
    return { error: err && err.message ? err.message : String(err) }
  }
}

self.addEventListener('message', async (ev) => {
  const msg = ev.data || {}
  if (msg.type === 'run') {
    const { runId, code, sketchProfiles } = msg
    const res = await runJscadInWorker(code, sketchProfiles || {})
    if (res.error) {
      self.postMessage({ type: 'error', runId, error: res.error })
    } else {
      self.postMessage({ type: 'result', runId, parts: res.parts })
    }
  }
})
