// equations.js — parse + evaluate `.equations` JSON files.
//
// File shape (mirrors backend/llm_docs/equations.md):
//
//   { "version": 1, "params": [
//     { "name": "wall", "expr": "2",     "unit": "mm", "comment": "Default" },
//     { "name": "h",    "expr": "wall*5", "unit": "mm" }
//   ]}
//
// Public API:
//   - parseEquations(content)      → { version, params, errors:[{paramIndex,message}] }
//   - evaluateEquations(parsed)    → { values:{name:number}, errors:[{paramIndex,name,message}] }
//   - mergeEquationFiles(files)    → { values, errors, duplicates:[{name,files:[...]}] }
//   - substituteParams(value, scope) → string|number — expand `${name}` in a value
//   - substituteFeatureTree(tree, scope) → tree with placeholders substituted
//   - extractParamPlaceholders(s)  → list of param names referenced by ${name} placeholders
//
// We keep `mathjs` evaluation per-row in a scope object so a bad row doesn't
// poison the whole sheet — the row records its error, but later rows can
// still resolve against the partial scope.

import { create, all } from 'mathjs'

// A locked-down mathjs instance. We exclude the dynamic `import` and `createUnit`
// surfaces — equation files should never have side effects.
const math = create(all, {})
math.import({
  import: function () { throw new Error('Function import is disabled inside equations') },
  createUnit: function () { throw new Error('Function createUnit is disabled inside equations') },
}, { override: true })

// ---- parse ------------------------------------------------------------------

// parseEquations tolerates malformed or empty input and returns a
// canonicalized doc. The caller can render the error list inline next to the
// affected param row.
export function parseEquations(content) {
  const out = { version: 1, params: [], errors: [] }
  const text = (content || '').trim()
  if (!text) return out
  let raw
  try {
    raw = JSON.parse(text)
  } catch (err) {
    out.errors.push({ paramIndex: -1, message: `parse: ${err.message || String(err)}` })
    return out
  }
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    if (typeof raw.version === 'number') out.version = raw.version
    if (Array.isArray(raw.params)) {
      raw.params.forEach((p, i) => {
        if (!p || typeof p !== 'object') {
          out.errors.push({ paramIndex: i, message: 'row is not an object' })
          return
        }
        const name = String(p.name || '').trim()
        const expr = String(p.expr ?? '').trim()
        const unit = p.unit != null ? String(p.unit) : ''
        const comment = p.comment != null ? String(p.comment) : ''
        out.params.push({ name, expr, unit, comment })
      })
    }
  }
  return out
}

// serializeEquations returns the canonical JSON form for persistence.
export function serializeEquations(parsed) {
  const doc = {
    version: parsed?.version || 1,
    params: (parsed?.params || []).map((p) => {
      const row = { name: p.name || '', expr: p.expr || '' }
      if (p.unit) row.unit = p.unit
      if (p.comment) row.comment = p.comment
      return row
    }),
  }
  return JSON.stringify(doc, null, 2)
}

// ---- evaluate ---------------------------------------------------------------

// validIdent enforces the JS-identifier shape. JSCAD destructuring and the
// scope spread both require this — mathjs is more forgiving but we want
// uniform rules across the surface.
export function validIdent(s) {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(s || '')
}

// evaluateEquations walks the params in declaration order, evaluating each
// expression against a fresh scope and recording per-row errors. A row that
// errors leaves its previous value (if any) in scope — downstream rows that
// reference it see `undefined` and surface their own error.
export function evaluateEquations(parsed) {
  const values = {}
  const errors = []
  const seen = new Set()
  const params = parsed?.params || []
  for (let i = 0; i < params.length; i++) {
    const row = params[i]
    if (!row.name) {
      errors.push({ paramIndex: i, name: '', message: 'name is required' })
      continue
    }
    if (!validIdent(row.name)) {
      errors.push({ paramIndex: i, name: row.name, message: 'name must be a valid identifier' })
      continue
    }
    if (seen.has(row.name)) {
      errors.push({ paramIndex: i, name: row.name, message: `duplicate name "${row.name}"` })
      continue
    }
    seen.add(row.name)
    if (!row.expr || !row.expr.trim()) {
      errors.push({ paramIndex: i, name: row.name, message: 'expr is required' })
      continue
    }
    try {
      const v = math.evaluate(row.expr, values)
      const num = toNumber(v)
      if (!Number.isFinite(num)) {
        errors.push({ paramIndex: i, name: row.name, message: `evaluated to ${String(v)}` })
        continue
      }
      values[row.name] = num
    } catch (err) {
      errors.push({ paramIndex: i, name: row.name, message: err?.message || String(err) })
    }
  }
  return { values, errors }
}

// toNumber coerces a mathjs result to a plain number. Units are stripped
// (consumers explicitly opted into "units are display only"); BigNumbers are
// converted; complex/array/object results error out via NaN.
function toNumber(v) {
  if (typeof v === 'number') return v
  if (v == null) return NaN
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'object') {
    if (typeof v.toNumber === 'function') {
      try { return v.toNumber() } catch { /* fallthrough */ }
    }
    if (typeof v.value === 'number') return v.value
    if (typeof v.valueOf === 'function') {
      const x = v.valueOf()
      if (typeof x === 'number') return x
    }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : NaN
}

// ---- merge multiple files --------------------------------------------------

// mergeEquationFiles takes a list of `{ path, content }` and returns a single
// merged scope. Last-loaded wins per duplicate name (callers should sort the
// list alphabetically by path for deterministic ordering).
export function mergeEquationFiles(files) {
  const merged = {}
  const errors = []
  const dupes = new Map() // name → [paths]
  for (const f of files || []) {
    const parsed = parseEquations(f.content || '')
    const { values, errors: rowErrors } = evaluateEquations(parsed)
    for (const e of parsed.errors) {
      errors.push({ ...e, file: f.path })
    }
    for (const e of rowErrors) {
      errors.push({ ...e, file: f.path })
    }
    for (const [name, value] of Object.entries(values)) {
      if (Object.prototype.hasOwnProperty.call(merged, name)) {
        if (!dupes.has(name)) dupes.set(name, [])
        dupes.get(name).push(f.path)
      }
      merged[name] = value
    }
  }
  const duplicates = []
  for (const [name, paths] of dupes.entries()) {
    duplicates.push({ name, files: paths })
  }
  return { values: merged, errors, duplicates }
}

// ---- placeholder substitution ----------------------------------------------

// matches ${...} where ... is non-greedy and doesn't contain a `}`.
//
// IMPORTANT: do NOT share a /g-flagged regex across substituteParams calls —
// `.test()` and `.exec()` mutate `lastIndex`, so a second call can spuriously
// fail to detect a placeholder it should have matched. This was the silent
// root-cause of "dimensional constraints with ${param} all resolve to 0":
// the first call to numericValue advanced lastIndex, the second call's
// `.test()` against a different string returned false, substituteParams
// returned the raw string, Number() coerced it to NaN, and numericValue
// fell through to its `return 0` branch — making every parameterised
// distance / radius / angle constraint a silent zero.
//
// The fix is to instantiate a fresh regex per call (the `g` flag matters for
// `.replace`'s multi-match behaviour, so we keep it). The PLACEHOLDER_HAS
// non-global twin is used for the cheap "any placeholder?" test.
const PLACEHOLDER_HAS = /\$\{[^}]+\}/

// substituteParams expands `${expr}` placeholders inside a string value. If the
// expression resolves to a finite number, returns that number. If the *whole*
// value is a single placeholder, the result is a number; otherwise the
// substituted segments are stringified and rejoined. Non-string inputs are
// returned untouched.
export function substituteParams(value, scope) {
  if (typeof value !== 'string') return value
  if (!PLACEHOLDER_HAS.test(value)) return value
  // Single full-string placeholder → return the raw number when possible.
  const single = value.match(/^\s*\$\{([^}]+)\}\s*$/)
  if (single) {
    const expr = single[1].trim()
    const num = evalPlaceholder(expr, scope)
    return Number.isFinite(num) ? num : value
  }
  // Fresh /g regex per call so we don't trip over a stale lastIndex.
  const re = /\$\{([^}]+)\}/g
  return value.replace(re, (_m, expr) => {
    const num = evalPlaceholder(String(expr).trim(), scope)
    return Number.isFinite(num) ? String(num) : _m
  })
}

function evalPlaceholder(expr, scope) {
  if (!expr) return NaN
  // Cheap fast-path: pure identifier in scope.
  if (validIdent(expr) && Object.prototype.hasOwnProperty.call(scope || {}, expr)) {
    return Number(scope[expr])
  }
  try {
    const v = math.evaluate(expr, scope || {})
    return toNumber(v)
  } catch {
    return NaN
  }
}

// extractParamPlaceholders pulls every ${...} expression out of a string
// (handy for the editor's "this row depends on …" tooltip).
export function extractParamPlaceholders(s) {
  if (typeof s !== 'string') return []
  const out = []
  let m
  // Fresh regex per call — see substituteParams for why we don't share one.
  const re = /\$\{([^}]+)\}/g
  while ((m = re.exec(s)) != null) {
    out.push(m[1].trim())
  }
  return out
}

// ---- feature-tree substitution ---------------------------------------------

// substituteFeatureTree walks an array of feature nodes and substitutes any
// `${name}` placeholders inside string fields. We recurse into nested arrays
// and objects. Values that aren't strings or that don't contain a placeholder
// pass through untouched.
export function substituteFeatureTree(tree, scope) {
  if (!Array.isArray(tree)) return tree
  return tree.map((node) => substituteValue(node, scope))
}

function substituteValue(value, scope) {
  if (Array.isArray(value)) return value.map((v) => substituteValue(v, scope))
  if (value && typeof value === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(value)) {
      out[k] = substituteValue(v, scope)
    }
    return out
  }
  if (typeof value === 'string') return substituteParams(value, scope)
  return value
}

// substituteSketch returns a copy of the sketch JSON with `${name}`
// placeholders expanded inside dimensional constraint values. Non-dimensional
// constraints pass through.
const DIMENSIONAL_TYPES = new Set([
  'distance', 'distance_x', 'distance_y', 'angle', 'radius', 'diameter',
])

export function substituteSketch(sketch, scope) {
  if (!sketch || typeof sketch !== 'object') return sketch
  const constraints = Array.isArray(sketch.constraints) ? sketch.constraints : []
  const next = constraints.map((c) => {
    if (!c || typeof c !== 'object') return c
    if (!DIMENSIONAL_TYPES.has(c.type)) return c
    if (typeof c.value !== 'string') return c
    const sub = substituteParams(c.value, scope)
    if (sub === c.value) return c
    return { ...c, value: sub }
  })
  return { ...sketch, constraints: next }
}
