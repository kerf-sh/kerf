// Worker that compiles a `.circuit.tsx` source through tscircuit and returns
// the resulting Circuit JSON.
//
// Trade-off (mirrors jscadWorker.js): we keep the eval off the main thread so
// large designs don't freeze the editor. tscircuit's renderer is single-pass
// and synchronous beyond a few async layout phases — the bulk of cost is in
// the schematic-layout + autorouting code, both of which can take hundreds of
// ms even for 20-component designs. Doing this off-thread keeps Monaco
// responsive while a compile is in flight.
//
// Compile pipeline:
//   1. sucrase.transform(source, { transforms: ['typescript', 'jsx'], ... })
//      → CommonJS-shaped JS we can wrap with `new Function(...)`.
//      We rewrite `import` statements to references (R, Capacitor, ...) we
//      pre-bind from `@tscircuit/core`.
//   2. Run the compiled function with the React + tscircuit globals injected.
//      Capture either:
//        - a default export of a JSX element (return Function form), or
//        - a default export that's a function returning JSX, or
//        - a top-level call sequence that constructed a Circuit (legacy).
//   3. new Circuit() ; circuit.add(<element>) ; await circuit.renderUntilSettled()
//      → circuit.getCircuitJson()
//   4. Return the full circuit JSON. Splitting it into schematic / pcb / 3d
//      buckets is done by the main thread (cheap filter on the .type field).
//
// We DO NOT split the circuit JSON server-side because consumers may want
// access to source_* and any/* records that don't cleanly fit one bucket
// (e.g. error objects). Filtering happens at render time.
//
// Cancellation: messages carry a runId. The main thread only forwards the
// latest run's result; older runs return as `stale` so callers no-op.

import { transform as sucraseTransform } from 'sucrase'
import * as React from 'react'
import * as TSC from '@tscircuit/core'

// Build a binding map exposed to user code as the module's `exports`.
// We import everything from @tscircuit/core eagerly inside the worker (the
// worker is itself lazily-loaded from the main thread, so first-paint cost
// stays in the main bundle).
const TSC_EXPORTS = TSC

// The set of names users typically import from tscircuit/@tscircuit/core. We
// pre-resolve every named import to its TSC value; unknown names fall back
// to undefined so `new Function` can still bind them.
const KNOWN_IMPORTS = TSC_EXPORTS && typeof TSC_EXPORTS === 'object'
  ? Object.keys(TSC_EXPORTS)
  : []

// Strip & collect import statements. Returns the rewritten JS body plus a
// list of {binding, source, kind} so the caller knows which symbols it must
// bind. We support:
//   - `import X from 'm'`
//   - `import { A, B as C } from 'm'`
//   - `import * as NS from 'm'`
//   - `import 'm'` (side-effect)
// All are stripped — we manually inject the resolved values via the wrapping
// `Function` factory.
const IMPORT_RE = /^[ \t]*import\s+([^;\n]+?)\s+from\s+['"]([^'"\n]+)['"];?[ \t]*$/gm
const SIDE_EFFECT_IMPORT_RE = /^[ \t]*import\s+['"][^'"\n]+['"];?[ \t]*$/gm

function parseImports(src) {
  const bindings = []
  const stripped = src
    .replace(IMPORT_RE, (_match, clause, source) => {
      const trimmed = clause.trim()
      // `* as NS`
      const ns = trimmed.match(/^\*\s+as\s+([A-Za-z_$][\w$]*)$/)
      if (ns) {
        bindings.push({ kind: 'namespace', binding: ns[1], source })
        return ''
      }
      // `Default, { A, B }`
      const dual = trimmed.match(/^([A-Za-z_$][\w$]*)\s*,\s*\{([^}]*)\}$/)
      if (dual) {
        bindings.push({ kind: 'default', binding: dual[1], source })
        for (const part of dual[2].split(',')) {
          const p = part.trim()
          if (!p) continue
          const aliased = p.match(/^([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)$/)
          if (aliased) bindings.push({ kind: 'named', orig: aliased[1], binding: aliased[2], source })
          else bindings.push({ kind: 'named', orig: p, binding: p, source })
        }
        return ''
      }
      // `{ A, B }`
      const namedOnly = trimmed.match(/^\{([^}]*)\}$/)
      if (namedOnly) {
        for (const part of namedOnly[1].split(',')) {
          const p = part.trim()
          if (!p) continue
          const aliased = p.match(/^([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)$/)
          if (aliased) bindings.push({ kind: 'named', orig: aliased[1], binding: aliased[2], source })
          else bindings.push({ kind: 'named', orig: p, binding: p, source })
        }
        return ''
      }
      // Plain default import.
      if (/^[A-Za-z_$][\w$]*$/.test(trimmed)) {
        bindings.push({ kind: 'default', binding: trimmed, source })
        return ''
      }
      // Anything we don't recognise: drop the line and warn via console.
      // The compile may still succeed if the user didn't actually need it.
      try {
        // eslint-disable-next-line no-console
        console.warn('circuitWorker: unrecognised import clause, dropping:', trimmed)
      } catch { /* ignore */ }
      return ''
    })
    .replace(SIDE_EFFECT_IMPORT_RE, '') // bare side-effect imports are no-ops
  return { stripped, bindings }
}

// Resolve a binding to a runtime value. We treat `tscircuit`, `@tscircuit/core`,
// and `react` as the three known sources; other module specifiers fall through
// to undefined (the user's code will hit a NameError if it tries to use them,
// which surfaces as a clean compile error).
function resolveBinding(b) {
  const src = b.source
  const isTSC = src === 'tscircuit' || src === '@tscircuit/core'
  const isReact = src === 'react'
  if (b.kind === 'namespace') {
    if (isTSC) return TSC_EXPORTS
    if (isReact) return React
    return {}
  }
  if (b.kind === 'default') {
    if (isReact) return React.default ?? React
    if (isTSC) return TSC_EXPORTS // `import t from 'tscircuit'` → namespace-ish
    return undefined
  }
  // named
  const ns = isReact ? React : isTSC ? TSC_EXPORTS : null
  if (!ns) return undefined
  return ns[b.orig]
}

// Rewrite a `default export ...` so the wrapping function returns the value.
// We support `export default <expr>` only; named exports of `circuit` / `board`
// are still recognised for parity with tscircuit's CLI, but the v1 flow expects
// a default export.
function rewriteExport(src) {
  // Quick path: explicit default export (most common).
  if (/export\s+default\s+/.test(src)) {
    return src.replace(/export\s+default\s+/, 'return ')
  }
  // Named-export form: `export const circuit = <board>...</board>` or fn.
  const matchConst = src.match(/export\s+(?:const|let|var)\s+(circuit|board|root)\b/)
  if (matchConst) {
    const name = matchConst[1]
    return src
      .replace(/export\s+(const|let|var)\s+/, '$1 ')
      + `\n;return ${name};`
  }
  const matchFn = src.match(/export\s+function\s+(circuit|board|root)\b/)
  if (matchFn) {
    const name = matchFn[1]
    return src.replace(/export\s+function\s+/, 'function ')
      + `\n;return ${name};`
  }
  // Last resort: assume a global `circuit` / `board` was constructed.
  return src + '\n;return (typeof circuit !== "undefined" ? circuit : (typeof board !== "undefined" ? board : null));'
}

async function compileCircuitInWorker(source) {
  if (!source || !source.trim()) {
    // Empty file → empty circuit JSON. Don't error.
    return { circuitJson: [] }
  }
  // 1. Parse imports, strip them.
  const { stripped, bindings } = parseImports(source)

  // 2. Compile TSX → JS via sucrase. We use `automatic` jsx so the user
  //    doesn't need an explicit `import React`. tscircuit's runtime supplies
  //    the JSX factory via React.createElement / Fragment.
  let compiled
  try {
    const out = sucraseTransform(stripped, {
      transforms: ['typescript', 'jsx'],
      jsxRuntime: 'classic',
      jsxPragma: 'React.createElement',
      jsxFragmentPragma: 'React.Fragment',
      production: true,
    })
    compiled = out.code
  } catch (err) {
    return { error: 'Compile error: ' + (err?.message || String(err)) }
  }

  // 3. Find the export and rewrite to a `return`.
  const body = rewriteExport(compiled)

  // 4. Build the Function. We bind:
  //    - React (for JSX factory)
  //    - everything from @tscircuit/core (if not already shadowed by user imports)
  //    - the user's resolved imports
  //
  //    Order matters: user imports win over the built-in TSC names, so
  //    `import { Resistor } from 'tscircuit'` shadows our default Resistor
  //    binding cleanly.
  const argNames = ['React']
  const argValues = [React]
  // First, expose every TSC export as a top-level binding (so user code can
  // reference `<resistor ... />` lowercase tags too — tscircuit registers
  // those via JSX intrinsic lowercase names, no import needed).
  for (const name of KNOWN_IMPORTS) {
    if (argNames.includes(name)) continue
    argNames.push(name)
    argValues.push(TSC_EXPORTS[name])
  }
  // Then user imports — these can override TSC defaults (`import Resistor from
  // './my-r.tsx'` shadows ours). We dedupe by name.
  for (const b of bindings) {
    if (argNames.includes(b.binding)) {
      // overwrite the previous arg value
      const idx = argNames.indexOf(b.binding)
      argValues[idx] = resolveBinding(b)
      continue
    }
    argNames.push(b.binding)
    argValues.push(resolveBinding(b))
  }

  let exported
  try {
    // eslint-disable-next-line no-new-func
    const factory = new Function(...argNames, body)
    exported = factory(...argValues)
  } catch (err) {
    return { error: 'Eval error: ' + (err?.message || String(err)) }
  }

  // 5. The user's default export may be:
  //    - a JSX element (React element)         → wrap into a Circuit and add
  //    - a function returning a JSX element    → call, then wrap
  //    - a Circuit instance (already wrapped)  → use directly
  //    - null/undefined                        → empty circuit
  let element = exported
  if (typeof element === 'function') {
    try { element = element() }
    catch (err) { return { error: 'Default export threw: ' + (err?.message || String(err)) } }
  }
  if (element && typeof element.then === 'function') {
    try { element = await element }
    catch (err) { return { error: 'Default export rejected: ' + (err?.message || String(err)) } }
  }

  let circuitInstance
  if (element && typeof element === 'object' && typeof element.getCircuitJson === 'function') {
    // Already a Circuit/RootCircuit/IsolatedCircuit-shaped object.
    circuitInstance = element
  } else if (element == null) {
    // Empty file or null export — return an empty CircuitJSON.
    return { circuitJson: [] }
  } else {
    // Treat as a React element to wrap.
    try {
      const Ctor = TSC_EXPORTS.Circuit || TSC_EXPORTS.RootCircuit
      if (!Ctor) {
        return { error: '@tscircuit/core did not expose a Circuit class' }
      }
      circuitInstance = new Ctor()
      circuitInstance.add(element)
    } catch (err) {
      return { error: 'Could not wrap in Circuit: ' + (err?.message || String(err)) }
    }
  }

  // 6. Render until settled, then pull the JSON.
  try {
    if (typeof circuitInstance.renderUntilSettled === 'function') {
      await circuitInstance.renderUntilSettled()
    } else if (typeof circuitInstance.render === 'function') {
      circuitInstance.render()
    }
  } catch (err) {
    return { error: 'Render error: ' + (err?.message || String(err)) }
  }
  let circuitJson
  try {
    circuitJson = circuitInstance.getCircuitJson()
  } catch (err) {
    return { error: 'getCircuitJson failed: ' + (err?.message || String(err)) }
  }
  // Strip non-cloneable fields defensively. We've seen tscircuit attach
  // function references to a few records; structuredClone refuses those.
  const cleaned = sanitiseForClone(circuitJson)
  return { circuitJson: cleaned }
}

// Recursively replace function values with `null` so structuredClone can
// transit the result. We don't try to be clever about typed arrays — circuit
// JSON is plain objects + numbers + strings.
function sanitiseForClone(value, depth = 0) {
  if (depth > 12) return null
  if (value == null) return value
  const t = typeof value
  if (t === 'function') return null
  if (t !== 'object') return value
  if (Array.isArray(value)) {
    return value.map((v) => sanitiseForClone(v, depth + 1))
  }
  const out = {}
  for (const k of Object.keys(value)) {
    const v = value[k]
    out[k] = sanitiseForClone(v, depth + 1)
  }
  return out
}

self.addEventListener('message', async (ev) => {
  const msg = ev.data || {}
  if (msg.type === 'compile') {
    const { runId, source } = msg
    let res
    try {
      res = await compileCircuitInWorker(source)
    } catch (err) {
      res = { error: err?.message || String(err) }
    }
    if (res.error) {
      self.postMessage({ type: 'error', runId, message: res.error })
    } else {
      self.postMessage({ type: 'result', runId, circuitJson: res.circuitJson || [] })
    }
  }
})
