// circuitTSX.js — pure helpers for round-tripping interactive edits
// (drag-to-move, rotate) back into a `.circuit.tsx` source file.
//
// The strategy is intentionally minimal: regex-driven attribute splicing
// against the JSX opener of a tscircuit element matched by `name="..."`
// (which is the refdes — `R1`, `U2`, etc.). We do NOT parse the TSX with
// a real AST. Trade-offs:
//
//   * tscircuit elements are flat — `<resistor name="R1" resistance="1k"
//     pcb_x={4.5} pcb_y={2} />` — the opener is a single line in the vast
//     majority of files, and even multi-line openers are well-formed JSX.
//     A regex that matches `<\w+ ... name="R1" ... />` (or `>`) is robust
//     against the patterns the tscircuit toolchain actually emits.
//   * If the regex fails (no element found, or a name collision), the
//     helpers return the input unchanged so a buggy edit can never corrupt
//     the user's source. The caller treats "no change" as "edit didn't
//     land" and surfaces nothing — the next compile will reflect the
//     pre-edit state.
//   * Numeric attributes are written as `pcb_x={4.5}` (JSX expression form).
//     tscircuit accepts `pcb_x="4.5"` too, but the expression form is the
//     idiomatic style and survives prettier round-trips cleanly.
//
// Edge cases covered by the vitest suite:
//   - element absent → unchanged source
//   - attribute already present (with int / float / negative / expression
//     value) → replaced
//   - attribute absent → inserted just before the closing `/>` or `>`
//   - element name doesn't matter (matches any tag with the given `name`)
//   - whitespace before `/>` preserved (we splice INSIDE the opener, not
//     after it)

const POSITION_AXES = new Set(['pcb_x', 'pcb_y', 'schematic_x', 'schematic_y'])
const ROTATION_AXES = new Set(['pcb_rotation', 'schematic_rotation'])

// Find the opener of a JSX element whose `name="<refdes>"` attribute
// matches. Returns { start, end, opener } or null. `start` and `end` are
// indices into `source` covering the entire opener including the trailing
// `>` or `/>`. `opener` is the matched substring.
//
// Why scan instead of regex-match the whole thing in one go? JSX openers
// can contain `>` inside JSX expressions (e.g. `prop={a > b}`) which
// breaks naive `<...>` regexes. We instead scan for `<` then walk forward
// counting brace depth so a `>` inside `{...}` doesn't terminate the
// opener.
function findOpener(source, refdes) {
  if (typeof source !== 'string' || !refdes) return null
  const escapedRefdes = String(refdes).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // Pattern looks for an opener literal whose `name="<refdes>"` is present.
  // Allow `name='R1'` too. Anchored on `<\w+` to skip JSX `</…>` closers.
  const nameAttrRe = new RegExp(`name\\s*=\\s*(?:"${escapedRefdes}"|'${escapedRefdes}')`)
  let i = 0
  while (i < source.length) {
    const lt = source.indexOf('<', i)
    if (lt < 0) return null
    // Skip closer tags / JSX fragments / comments-ish.
    const next = source[lt + 1]
    if (next === '/' || next === '!' || next === '?' || !next || !/[A-Za-z]/.test(next)) {
      i = lt + 1
      continue
    }
    // Walk forward to find the matching closing `>` of THIS opener,
    // skipping `>` inside `{...}` (brace depth) and inside string
    // attributes ("..." / '...').
    let j = lt + 1
    let depth = 0
    let inStr = null
    let end = -1
    while (j < source.length) {
      const ch = source[j]
      if (inStr) {
        if (ch === inStr) inStr = null
        j++
        continue
      }
      if (ch === '"' || ch === "'") {
        // Only treat as string if we're at a JSX attribute boundary
        // (i.e. we're outside any `{...}`). Inside expressions, strings
        // don't matter for `>` matching.
        if (depth === 0) inStr = ch
        j++
        continue
      }
      if (ch === '{') { depth++; j++; continue }
      if (ch === '}') { if (depth > 0) depth--; j++; continue }
      if (depth === 0 && ch === '>') { end = j; break }
      j++
    }
    if (end < 0) return null
    const opener = source.slice(lt, end + 1)
    if (nameAttrRe.test(opener)) {
      return { start: lt, end: end + 1, opener }
    }
    i = end + 1
  }
  return null
}

// Render a JS number into the source: prefer integers when exact, otherwise
// trim trailing zeros. We keep up to 4 decimals — finer than that is below
// the user's grid in any sensible unit (mm or "schematic units").
function formatNumber(n) {
  if (!Number.isFinite(n)) return '0'
  if (Number.isInteger(n)) return String(n)
  const s = n.toFixed(4)
  // Trim trailing zeros and a dangling `.`.
  return s.replace(/\.?0+$/, '')
}

// Replace or insert `<attr>={<value>}` inside the matched opener. Returns
// the modified opener.
function spliceAttr(opener, attr, valueLiteral) {
  // Match `attr={...}` first (expression form), then `attr="..."` (string).
  // We allow whitespace around the `=` and arbitrary content inside `{...}`
  // (no nested-brace support — tscircuit values are simple literals).
  const reExpr = new RegExp(`(\\b${attr}\\s*=\\s*)\\{[^}]*\\}`)
  const reStr = new RegExp(`(\\b${attr}\\s*=\\s*)(?:"[^"]*"|'[^']*')`)
  if (reExpr.test(opener)) {
    return opener.replace(reExpr, `$1{${valueLiteral}}`)
  }
  if (reStr.test(opener)) {
    return opener.replace(reStr, `$1{${valueLiteral}}`)
  }
  // Insert just before the trailing `/>` or `>`.
  // Self-closing form: `... />`
  const m = opener.match(/(\s*)(\/?\s*>)\s*$/)
  if (!m) return opener
  const tail = m[0]
  const head = opener.slice(0, opener.length - tail.length)
  // Ensure exactly one space between the previous attribute (or tag name)
  // and the new attribute.
  const sep = head.endsWith(' ') || head.endsWith('\n') || head.endsWith('\t') ? '' : ' '
  return `${head}${sep}${attr}={${valueLiteral}}${tail}`
}

// Update a single positional/rotational numeric attribute on a tscircuit
// JSX element. Returns the updated source, or the original source on
// failure (element not found, axis invalid, value not finite).
function setNumericAttr(source, refdes, attr, value, allowedSet) {
  if (typeof source !== 'string') return source
  if (!refdes || !allowedSet.has(attr)) return source
  if (!Number.isFinite(value)) return source
  const found = findOpener(source, refdes)
  if (!found) return source
  const valueLit = formatNumber(value)
  const next = spliceAttr(found.opener, attr, valueLit)
  if (next === found.opener) return source
  return source.slice(0, found.start) + next + source.slice(found.end)
}

// Public API: position attribute setter.
//
// `axis` ∈ {pcb_x, pcb_y, schematic_x, schematic_y}.
export function setPositionAttr(source, refdes, axis, value) {
  return setNumericAttr(source, refdes, axis, Number(value), POSITION_AXES)
}

// Public API: rotation attribute setter.
//
// `axis` ∈ {pcb_rotation, schematic_rotation}. Value is in degrees (the
// unit tscircuit accepts).
export function setRotationAttr(source, refdes, axis, value) {
  return setNumericAttr(source, refdes, axis, Number(value), ROTATION_AXES)
}

// Append a fresh tscircuit element inside the parent `<board>...</board>`
// tag. Returns updated source (or unchanged source if no `<board>` found).
// The element is on its own indented line just before `</board>`.
export function appendComponent(source, jsx) {
  if (typeof source !== 'string' || !jsx) return source
  const close = source.lastIndexOf('</board>')
  if (close < 0) return source
  // Find the indent of the `</board>` line so the inserted element lines
  // up. We look back to the previous newline.
  const prevNl = source.lastIndexOf('\n', close)
  const indent = prevNl >= 0 ? source.slice(prevNl + 1, close).match(/^\s*/)?.[0] ?? '  ' : '  '
  const insertion = `${indent}  ${jsx}\n${indent}`
  return source.slice(0, close) + insertion + source.slice(close)
}

// Snap a value to a grid. Helper exported for the views.
export function snap(value, grid) {
  if (!Number.isFinite(value) || !Number.isFinite(grid) || grid <= 0) return value
  return Math.round(value / grid) * grid
}

// Find the lowest unused integer suffix for a given refdes prefix in the
// source. Used by the LibraryPicker drop path so newly-inserted parts get a
// deterministic, collision-free name (`R3`, `C7`, etc.) without forcing the
// user to pick one.
//
// Strategy:
//   * Scan all `name="<prefix><digits>"` and `name='<prefix><digits>'`
//     occurrences in the source. We don't restrict to JSX openers — the
//     attribute is unambiguous enough that grepping the whole file is fine
//     and survives multi-line openers / commented-out elements (the latter
//     conservatively reserves the number, which is the safer choice).
//   * Pick the smallest positive integer NOT in the set. Always returns at
//     least `<prefix>1`.
//   * Prefix is treated literally (no regex meta chars) — common cases are
//     'R', 'C', 'U', 'D', 'L', but any string works.
export function nextRefdes(source, prefix) {
  if (typeof source !== 'string' || !prefix) return `${prefix || ''}1`
  const escaped = String(prefix).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`name\\s*=\\s*["']${escaped}(\\d+)["']`, 'g')
  const used = new Set()
  let m
  while ((m = re.exec(source)) !== null) {
    const n = parseInt(m[1], 10)
    if (Number.isFinite(n) && n > 0) used.add(n)
  }
  let i = 1
  while (used.has(i)) i++
  return `${prefix}${i}`
}

// Splice a `// @kerf-probe NAME=<name> KIND=<V|I> PORT=<portId>` comment line
// just before `</board>`. Returns updated source (or unchanged on no-op).
export function appendProbe(source, { name, kind, portId } = {}) {
  if (typeof source !== 'string') return source
  if (!name || !portId) return source
  const k = kind === 'I' ? 'I' : 'V'
  const safeName = String(name).replace(/\s+/g, '_')
  const safePort = String(portId).replace(/\s+/g, '_')
  const comment = `// @kerf-probe NAME=${safeName} KIND=${k} PORT=${safePort}`
  return appendComponent(source, comment)
}

// Delete the `// @kerf-probe NAME=<name> …` line for `name`. Tolerant: returns
// `source` unchanged if no such line exists.
export function removeProbe(source, name) {
  if (typeof source !== 'string' || !name) return source
  const safeName = String(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`^[ \\t]*\\/\\/\\s*@kerf-probe\\s+[^\\n\\r]*\\bNAME\\s*=\\s*${safeName}\\b[^\\n\\r]*(?:\\r?\\n)?`, 'm')
  if (!re.test(source)) return source
  return source.replace(re, '')
}

// Rename a `// @kerf-probe NAME=<oldName> …` line's NAME field to `<newName>`,
// leaving KIND/PORT untouched. No-op on missing probe / invalid newName.
export function renameProbe(source, oldName, newName) {
  if (typeof source !== 'string' || !oldName || !newName) return source
  if (/[\s=]/.test(newName)) return source
  const safeOld = String(oldName).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(^[ \\t]*\\/\\/\\s*@kerf-probe\\s+[^\\n\\r]*\\bNAME\\s*=\\s*)${safeOld}(\\b[^\\n\\r]*)`, 'm')
  if (!re.test(source)) return source
  return source.replace(re, `$1${newName}$2`)
}

// Extract every `// @kerf-probe …` line from `source` into
// `{ name, kind, portId }` records. Malformed lines are skipped.
export function parseProbes(source) {
  if (typeof source !== 'string') return []
  const out = []
  const re = /\/\/\s*@kerf-probe\s+([^\n\r]*)/g
  let m
  while ((m = re.exec(source)) !== null) {
    const tail = m[1]
    const fields = {}
    const kvRe = /(\w+)\s*=\s*(\S+)/g
    let kv
    while ((kv = kvRe.exec(tail)) !== null) {
      fields[kv[1].toUpperCase()] = kv[2]
    }
    const name = fields.NAME
    const kindRaw = fields.KIND
    const portId = fields.PORT
    if (!name || !portId) continue
    if (kindRaw !== 'V' && kindRaw !== 'I') continue
    out.push({ name, kind: kindRaw, portId })
  }
  return out
}

// Append a `<trace from="..." to="..." />` just inside the `<board>...</board>`
// closer. A thin specialization of `appendComponent` — kept as its own export
// so callers don't have to construct the JSX string at the call site (and so
// the test suite can assert the exact emitted form).
//
// Selectors are tscircuit's standard `.<refdes> > .<pin>` form, e.g.
// `.R1 > .pin1`, but we accept any string the caller passes — the splice is
// purely textual, so an alternate selector style (`net.VCC` etc.) round-trips
// fine.
//
// Returns the original source unchanged if either selector is empty or no
// `<board>` closer exists in the file (matching `appendComponent`'s
// graceful-no-op contract).
export function appendTrace(source, fromSelector, toSelector) {
  if (typeof source !== 'string') return source
  if (!fromSelector || !toSelector) return source
  // Escape `"` in selectors to keep the emitted JSX well-formed. tscircuit
  // selectors don't normally contain `"`, but guarding here means we can't
  // produce a syntactically broken file from a hostile input.
  const safeFrom = String(fromSelector).replace(/"/g, '\\"')
  const safeTo = String(toSelector).replace(/"/g, '\\"')
  const jsx = `<trace from="${safeFrom}" to="${safeTo}" />`
  return appendComponent(source, jsx)
}
