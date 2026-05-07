// Bracket-matching mutators for the conventional Kerf JSCAD layout:
//
//   export default function () {
//     return [
//       { id: 'base',  geom: ... },
//       { id: 'peg',   geom: ... },
//     ]
//   }
//
// Two top-level operations:
//   - duplicateObject(source, objectId, newId?) → source with the matched
//     `{id, geom}` entry cloned (id renamed) and inserted just after the
//     original. `newId` defaults to `<objectId>-copy`, with a numeric suffix
//     appended on collision.
//   - deleteObject(source, objectId) → source with the matched entry removed
//     (including its trailing comma/whitespace).
//
// Both walk the source as a string (no AST). They tolerate:
//   - Nested {} inside the entry (e.g. `geom: transforms.translate([0,0,5],
//     primitives.cuboid({size:[1,1,1]}))`)
//   - String literals containing braces (`{id: 'a-{b}', ...}`)
//   - Single-line `// ...` and block `/* ... */` comments inside the entry
//   - Both `'` and `"` (and template-literal `` ` ``) quoted ids
//   - Trailing commas
//
// Both return null when the file's structure isn't `return [{id:..., geom:...},
// ...]` — e.g. dynamic generation, conditional pushes, or a non-object element
// in the array. Callers fall back to a toast.

// ---------------------------------------------------------------------------
// Tokeniser-aware skipping. We need to walk forward from a position and
// understand string literals + comments so braces inside them don't unbalance
// our depth counters.

// If `src[i]` opens a string literal (`'` `"` `` ` ``), advance past the
// closing delimiter (respecting `\\` escapes and `${...}` template
// substitutions for backticks). Returns the new index, or i if not a string.
function skipString(src, i) {
  const q = src[i]
  if (q !== '"' && q !== "'" && q !== '`') return i
  let j = i + 1
  while (j < src.length) {
    const c = src[j]
    if (c === '\\') { j += 2; continue }
    if (q === '`' && c === '$' && src[j + 1] === '{') {
      // Template literal substitution — recurse into a balanced { } block.
      let depth = 1
      j += 2
      while (j < src.length && depth > 0) {
        const cc = src[j]
        if (cc === '"' || cc === "'" || cc === '`') {
          j = skipString(src, j); continue
        }
        if (cc === '/' && (src[j + 1] === '/' || src[j + 1] === '*')) {
          j = skipComment(src, j); continue
        }
        if (cc === '{') depth++
        else if (cc === '}') depth--
        j++
      }
      continue
    }
    if (c === q) return j + 1
    j++
  }
  return j
}

// If `src[i]` opens a `//` or `/*` comment, advance past its end. Returns the
// new index, or i if not a comment.
function skipComment(src, i) {
  if (src[i] !== '/') return i
  const next = src[i + 1]
  if (next === '/') {
    let j = i + 2
    while (j < src.length && src[j] !== '\n') j++
    return j // leave the newline in place — outer loop handles it
  }
  if (next === '*') {
    let j = i + 2
    while (j < src.length) {
      if (src[j] === '*' && src[j + 1] === '/') return j + 2
      j++
    }
    return j
  }
  return i
}

// Generic forward-skip past a string OR comment at position i. Returns the
// index after the skipped span, or i unchanged if neither applies.
function skipAux(src, i) {
  const c = src[i]
  if (c === '"' || c === "'" || c === '`') return skipString(src, i)
  if (c === '/' && (src[i + 1] === '/' || src[i + 1] === '*')) return skipComment(src, i)
  return i
}

// ---------------------------------------------------------------------------
// Locate the top-level `return [ ... ]` and walk its entries.

// Scan source for the unique top-level `return [`. Returns
// { arrStart, arrEnd } pointing at `[` and `]` (inclusive). Returns null if
// the file doesn't have exactly one return-an-array, or if the array can't be
// matched.
function locateReturnArray(source) {
  // We want the LAST top-level `return [` — that's the function's exit. Most
  // Kerf files have a single function with a single return statement, but if
  // there are nested helper functions we want the outer one. We do this by
  // scanning forward, recording every `return [` we find, and picking the
  // last whose enclosing brace depth is 1 (inside the default-export
  // function).
  //
  // For robustness against arbitrary helper structures we instead require the
  // ONLY `return [` whose array contains `{id:` patterns (the marker for a
  // Kerf parts array). Other `return [...]` calls don't have those.
  const candidates = []
  let i = 0
  while (i < source.length) {
    const j = skipAux(source, i)
    if (j !== i) { i = j; continue }
    // Match `return` keyword at a word boundary.
    if (
      source[i] === 'r' &&
      source.slice(i, i + 6) === 'return' &&
      /\W|^/.test(source[i - 1] || '\n') &&
      /\s/.test(source[i + 6] || '')
    ) {
      // Skip whitespace + comments after `return` to find a `[`.
      let k = i + 6
      while (k < source.length) {
        const a = skipAux(source, k)
        if (a !== k) { k = a; continue }
        if (/\s/.test(source[k])) { k++; continue }
        break
      }
      if (source[k] === '[') {
        const arrEnd = matchBracket(source, k, '[', ']')
        if (arrEnd >= 0) {
          // Sniff for `{` `id` inside — cheap heuristic to filter out
          // arrays of numbers etc.
          const slice = source.slice(k, arrEnd + 1)
          if (/\bid\s*:/.test(slice)) {
            candidates.push({ arrStart: k, arrEnd })
          }
          i = arrEnd + 1
          continue
        }
      }
      i = k
      continue
    }
    i++
  }
  if (candidates.length === 0) return null
  // Prefer the LAST one — that's the outer function's return. If there are
  // multiple (e.g. branches of an if), bail; we can't safely identify the
  // active path without execution.
  if (candidates.length > 1) return null
  return candidates[0]
}

// Match a balanced opening bracket. `open` and `close` are the bracket pair
// (e.g. `[`, `]` or `{`, `}`). Returns the index of the matching close, or -1.
function matchBracket(src, start, open, close) {
  if (src[start] !== open) return -1
  let depth = 0
  let i = start
  while (i < src.length) {
    const a = skipAux(src, i)
    if (a !== i) { i = a; continue }
    const c = src[i]
    if (c === open) depth++
    else if (c === close) {
      depth--
      if (depth === 0) return i
    }
    i++
  }
  return -1
}

// Walk the array body and return one descriptor per top-level entry. Each
// descriptor: { entryStart, entryEnd, sepEnd, id, valid }
//
//   - entryStart/entryEnd are inclusive bounds of `{ ... }`.
//   - sepEnd is the index AFTER the trailing comma (or === entryEnd+1 if
//     none). Used for clean removal/insertion.
//   - id is the `id: '...'` value, or null when not parseable.
//   - valid is true only when the entry is a literal object with an id field
//     parseable as a string.
function parseArrayEntries(source, arrStart, arrEnd) {
  const entries = []
  let i = arrStart + 1
  while (i < arrEnd) {
    const a = skipAux(source, i)
    if (a !== i) { i = a; continue }
    const c = source[i]
    if (/\s/.test(c) || c === ',') { i++; continue }
    if (c !== '{') {
      // Non-object element (e.g. a spread, a function call). Bail: we don't
      // understand this layout.
      return null
    }
    const entryStart = i
    const entryEnd = matchBracket(source, i, '{', '}')
    if (entryEnd < 0) return null
    // Find trailing comma (skipping whitespace/comments).
    let s = entryEnd + 1
    while (s < arrEnd) {
      const sa = skipAux(source, s)
      if (sa !== s) { s = sa; continue }
      if (/\s/.test(source[s])) { s++; continue }
      break
    }
    let sepEnd = entryEnd + 1
    if (source[s] === ',') sepEnd = s + 1
    const id = readEntryId(source, entryStart, entryEnd)
    entries.push({
      entryStart,
      entryEnd,
      sepEnd,
      id,
      valid: id != null,
    })
    i = sepEnd
  }
  return entries
}

// Read the `id: '<name>'` field from inside an entry's `{ ... }`. Returns the
// string value, or null if absent / not a literal.
function readEntryId(source, entryStart, entryEnd) {
  let i = entryStart + 1
  while (i < entryEnd) {
    const a = skipAux(source, i)
    if (a !== i) { i = a; continue }
    // Look for `id` at a word boundary.
    if (
      source[i] === 'i' &&
      source[i + 1] === 'd' &&
      !/[A-Za-z0-9_$]/.test(source[i - 1] || ' ') &&
      !/[A-Za-z0-9_$]/.test(source[i + 2] || ' ')
    ) {
      let k = i + 2
      while (k < entryEnd && /\s/.test(source[k])) k++
      if (source[k] !== ':') { i++; continue }
      k++
      while (k < entryEnd && /\s/.test(source[k])) k++
      const q = source[k]
      if (q !== '"' && q !== "'" && q !== '`') return null
      const end = skipString(source, k)
      if (end < 0 || end > entryEnd) return null
      // Slice inside the quotes.
      return source.slice(k + 1, end - 1)
    }
    i++
  }
  return null
}

// ---------------------------------------------------------------------------
// Public API

// Find the entry matching `objectId`. Returns a descriptor (or null), plus the
// full entries list (for callers that want to mint unique new ids).
function findObjectEntry(source, objectId) {
  const arr = locateReturnArray(source)
  if (!arr) return null
  const entries = parseArrayEntries(source, arr.arrStart, arr.arrEnd)
  if (!entries) return null
  // Every entry must be valid for the operation to be safe — otherwise we
  // might be scribbling next to a dynamic spread we can't reason about.
  if (!entries.every((e) => e.valid)) return null
  const target = entries.find((e) => e.id === objectId)
  if (!target) return null
  return { arr, entries, target }
}

// Mint a unique `<base>-copy[-N]` id given the existing entries.
function mintCopyId(base, taken) {
  const t = new Set(taken)
  const root = `${base}-copy`
  if (!t.has(root)) return root
  let n = 2
  while (t.has(`${root}-${n}`)) n++
  return `${root}-${n}`
}

// Duplicate the {id, geom} entry whose id matches `objectId`. The clone is
// inserted just AFTER the original with a renamed id. Returns the new source
// string, or null if the file's shape isn't `return [{id,geom},...]`.
//
// `newId` is optional; when omitted we mint `<objectId>-copy[-N]` against
// the existing ids.
export function duplicateObject(source, objectId, newId) {
  if (!source || !objectId) return null
  const found = findObjectEntry(source, objectId)
  if (!found) return null
  const { entries, target } = found
  const taken = entries.map((e) => e.id).filter(Boolean)
  const cloneId = (typeof newId === 'string' && newId.trim()) ? newId.trim() : mintCopyId(objectId, taken)
  if (taken.includes(cloneId)) return null

  // Clone the {…} text and rename its id literal. We rewrite ONLY the first
  // `id: 'objectId'` occurrence inside the entry — readEntryId already
  // verified that an id field exists at the top level, but a defensive
  // string-replace inside a sub-object would be wrong, so we re-locate it.
  const entryText = source.slice(target.entryStart, target.entryEnd + 1)
  const renamed = renameIdInEntry(entryText, objectId, cloneId)
  if (renamed == null) return null

  // Determine the indentation of the original entry — copy its leading
  // whitespace (spaces/tabs since the previous newline) so the clone aligns.
  let lineStart = target.entryStart
  while (lineStart > 0 && source[lineStart - 1] !== '\n') lineStart--
  const indent = source.slice(lineStart, target.entryStart)

  // Insert after the existing trailing comma if present, otherwise add one.
  const insertAt = target.sepEnd
  const hasTrailingComma = source[target.entryEnd + 1] === ',' || target.sepEnd > target.entryEnd + 1
  const insertion = hasTrailingComma
    ? `\n${indent}${renamed},`
    : `,\n${indent}${renamed}`

  return source.slice(0, insertAt) + insertion + source.slice(insertAt)
}

// Replace the id literal inside an entry's leading {…} brace. We re-locate
// the `id: '<old>'` field to avoid clobbering a lookalike substring inside a
// nested expression. Returns the new entry text, or null if the literal can't
// be found (shouldn't happen — readEntryId already validated).
function renameIdInEntry(entryText, oldId, newId) {
  let i = 1 // skip opening `{`
  while (i < entryText.length - 1) {
    const a = skipAux(entryText, i)
    if (a !== i) { i = a; continue }
    if (
      entryText[i] === 'i' &&
      entryText[i + 1] === 'd' &&
      !/[A-Za-z0-9_$]/.test(entryText[i - 1] || ' ') &&
      !/[A-Za-z0-9_$]/.test(entryText[i + 2] || ' ')
    ) {
      let k = i + 2
      while (k < entryText.length && /\s/.test(entryText[k])) k++
      if (entryText[k] !== ':') { i++; continue }
      k++
      while (k < entryText.length && /\s/.test(entryText[k])) k++
      const q = entryText[k]
      if (q !== '"' && q !== "'" && q !== '`') return null
      const end = skipString(entryText, k)
      if (end < 0) return null
      const literal = entryText.slice(k + 1, end - 1)
      if (literal !== oldId) return null
      // Use the same quote style we found.
      return entryText.slice(0, k) + q + escapeForQuote(newId, q) + q + entryText.slice(end)
    }
    i++
  }
  return null
}

function escapeForQuote(s, q) {
  // Conservative: backslash-escape the matching quote and any backslashes.
  return s.replace(/\\/g, '\\\\').replace(new RegExp(q.replace(/[\\^$.*+?()[\]{}|]/g, '\\$&'), 'g'), `\\${q}`)
}

// Remove the entry whose id matches `objectId`. Returns the new source string,
// or null if the file's shape isn't `return [{id,geom},...]`.
export function deleteObject(source, objectId) {
  if (!source || !objectId) return null
  const found = findObjectEntry(source, objectId)
  if (!found) return null
  const { target } = found

  // Delete from the start of the entry (incl. its leading whitespace on the
  // same line) through its trailing comma + the newline that follows, when
  // possible. This keeps the file from gaining a blank line.
  let from = target.entryStart
  let to = target.sepEnd
  // Pull `from` back to the start of the line (consume leading indent).
  while (from > 0 && (source[from - 1] === ' ' || source[from - 1] === '\t')) from--
  // If the previous char is a newline, also consume it — but only when we
  // also have content after `to`, so we don't strip the array's trailing
  // newline.
  if (source[from - 1] === '\n') {
    // Look-ahead: skip whitespace after `to` and check we're not at `]`.
    let look = to
    while (look < source.length && (source[look] === ' ' || source[look] === '\t')) look++
    if (source[look] === '\n') {
      // Consume the trailing newline (keep the leading one) so we don't double-blank.
      to = look + 1
    } else {
      // Consume the leading newline (keep the trailing chars) — neighbour stays put.
      from--
    }
  }

  return source.slice(0, from) + source.slice(to)
}

// Test whether `source` exposes an object with the given id. Used by the UI
// to disable the duplicate/delete buttons on an unrecognised file shape.
export function hasObjectEntry(source, objectId) {
  return findObjectEntry(source, objectId) != null
}

// ---------------------------------------------------------------------------
// Insertion helpers used by the FeaturePanel (Pad / Pocket / Revolve / Loft /
// Sweep). These reuse the same bracket-matched return-array locator as
// duplicate/delete; we expose them so the feature panel doesn't reimplement
// the tokeniser.

// Return the existing top-level Object ids in source order. `null` if the
// file doesn't conform to the `return [{id, geom}, ...]` shape.
export function listObjectIds(source) {
  if (!source) return null
  const arr = locateReturnArray(source)
  if (!arr) return null
  const entries = parseArrayEntries(source, arr.arrStart, arr.arrEnd)
  if (!entries) return null
  if (!entries.every((e) => e.valid)) return null
  return entries.map((e) => e.id)
}

// Mint a unique `<base>-N` id (1-based) given the source's existing ids.
// Used by the FeaturePanel to choose `pad-1`, `pad-2`, ... that don't collide.
// Returns null if the source's structure isn't parseable.
export function mintFeatureId(source, base) {
  const taken = listObjectIds(source)
  if (!taken) return null
  const t = new Set(taken)
  let n = 1
  while (t.has(`${base}-${n}`)) n++
  return `${base}-${n}`
}

// Append an entry to the return array. `entryText` is the literal source for
// the entry (e.g. `{ id: 'pad-1', geom: extrudeLinear({height:5}, profile) }`)
// — the caller is responsible for matching the file's quote/comma style. The
// indentation of the inserted line copies the file's existing entry indent
// when we can find one; otherwise falls back to two spaces past the array's
// `[`. Returns the new source string, or null if the file's shape isn't
// `return [{id, geom}, ...]`.
export function appendObjectEntry(source, entryText) {
  if (!source || !entryText) return null
  const arr = locateReturnArray(source)
  if (!arr) return null
  const entries = parseArrayEntries(source, arr.arrStart, arr.arrEnd)
  if (!entries) return null
  if (!entries.every((e) => e.valid)) return null

  // Determine indent: copy the leading whitespace of the last entry, or
  // failing that, the array's own indent + two spaces.
  let indent = '    '
  if (entries.length > 0) {
    const last = entries[entries.length - 1]
    let lineStart = last.entryStart
    while (lineStart > 0 && source[lineStart - 1] !== '\n') lineStart--
    indent = source.slice(lineStart, last.entryStart)
  } else {
    let lineStart = arr.arrStart
    while (lineStart > 0 && source[lineStart - 1] !== '\n') lineStart--
    indent = source.slice(lineStart, arr.arrStart) + '  '
  }

  // Find the closing `]` and back up over trailing whitespace to the last
  // non-space char, so we can insert just after the previous entry's comma.
  let insertAt = arr.arrEnd
  while (insertAt > arr.arrStart + 1 && /\s/.test(source[insertAt - 1])) insertAt--

  // If the previous content ended with `,` we just append. Otherwise we
  // prepend a comma. Empty arrays (`[]`) need no leading comma.
  const prev = source[insertAt - 1]
  const needsLeadingComma = prev !== ',' && prev !== '['

  const insertion = `${needsLeadingComma ? ',' : ''}\n${indent}${entryText},`

  return source.slice(0, insertAt) + insertion + source.slice(insertAt)
}

// Replace the entry whose id matches `objectId`. `entryText` is the new entry
// source (including the surrounding `{ ... }`). Returns the new source string
// or null on failure. Used by Pocket to swap a target Object for its
// "<target> minus tool" version while preserving position in the array.
export function replaceObjectEntry(source, objectId, entryText) {
  if (!source || !objectId || !entryText) return null
  const found = findObjectEntry(source, objectId)
  if (!found) return null
  const { target } = found
  return source.slice(0, target.entryStart) + entryText + source.slice(target.entryEnd + 1)
}

// Read the raw text of an entry's `geom: <expr>` value. Returns the string
// expression (verbatim, no normalisation), or null if the entry doesn't have
// a parseable geom field. Used by Pocket to wrap the existing target geom in
// a `subtract(<old>, ...)` call.
export function readObjectGeomExpr(source, objectId) {
  const found = findObjectEntry(source, objectId)
  if (!found) return null
  const { target } = found
  return readGeomExprInEntry(source, target.entryStart, target.entryEnd)
}

function readGeomExprInEntry(source, entryStart, entryEnd) {
  let i = entryStart + 1
  while (i < entryEnd) {
    const a = skipAux(source, i)
    if (a !== i) { i = a; continue }
    // Look for `geom` at word boundary (also accept `'geom'` / `"geom"`).
    const matchedKey = matchKey(source, i, entryEnd, 'geom')
    if (matchedKey) {
      let k = matchedKey
      while (k < entryEnd && /\s/.test(source[k])) k++
      if (source[k] !== ':') { i++; continue }
      k++
      while (k < entryEnd && /\s/.test(source[k])) k++
      // Walk forward until we hit a top-level comma or the closing `}`.
      // Tokeniser-aware: respect nested (), [], {} and skip strings/comments.
      const valStart = k
      let depthParen = 0, depthBrack = 0, depthBrace = 0
      while (k < entryEnd) {
        const aa = skipAux(source, k)
        if (aa !== k) { k = aa; continue }
        const c = source[k]
        if (c === '(') depthParen++
        else if (c === ')') depthParen--
        else if (c === '[') depthBrack++
        else if (c === ']') depthBrack--
        else if (c === '{') depthBrace++
        else if (c === '}') depthBrace--
        else if (c === ',' && depthParen === 0 && depthBrack === 0 && depthBrace === 0) break
        k++
      }
      // Trim trailing whitespace.
      let end = k
      while (end > valStart && /\s/.test(source[end - 1])) end--
      return source.slice(valStart, end)
    }
    i++
  }
  return null
}

// If src starting at i matches the property key `name` (bare or quoted),
// returns the index just AFTER the key (before the optional whitespace and
// `:`). Returns 0 if no match.
function matchKey(src, i, end, name) {
  // Bare identifier match.
  if (
    src.slice(i, i + name.length) === name &&
    !/[A-Za-z0-9_$]/.test(src[i - 1] || ' ') &&
    !/[A-Za-z0-9_$]/.test(src[i + name.length] || ' ')
  ) {
    return i + name.length
  }
  // Quoted match: `'name'` or `"name"`.
  const q = src[i]
  if (q === '"' || q === "'") {
    const after = skipString(src, i)
    if (after > i + 1 && src.slice(i + 1, after - 1) === name) {
      return after
    }
  }
  return 0
}

// Insert (idempotently) `import <binding> from '<path>'` at the top of the
// file. If a sketch import for `path` already exists, returns the source
// unchanged AND surfaces that binding via the second tuple element so
// callers can reference it. Returns { source, binding }.
//
// The chosen binding mirrors the file's basename, sanitised to a JS
// identifier and uniquified against any existing identifiers used as
// `import X from ...`. We deliberately don't rename existing imports — if
// the user already imports a sketch under a wonky name, we use it as-is.
export function ensureSketchImport(source, path, suggestedBinding) {
  if (!source) source = ''
  // Look for a pre-existing `import X from '<path>'` (single OR double quotes).
  const re = /^[ \t]*import\s+([A-Za-z_$][\w$]*)\s+from\s+(['"])([^'"\n]+)\2;?[ \t]*$/gm
  let m
  while ((m = re.exec(source)) != null) {
    if (m[3] === path) return { source, binding: m[1] }
  }

  // Mint a binding. Sanitise + uniquify against existing import bindings.
  const taken = new Set()
  const r2 = /^[ \t]*import\s+([A-Za-z_$][\w$]*)\s+/gm
  let mm
  while ((mm = r2.exec(source)) != null) taken.add(mm[1])
  let bind = sanitiseBinding(suggestedBinding || basenameNoExt(path) || 'profile')
  if (taken.has(bind)) {
    let n = 2
    while (taken.has(`${bind}${n}`)) n++
    bind = `${bind}${n}`
  }

  const line = `import ${bind} from '${path}'\n`
  // Insert above all other code. If the file already opens with imports,
  // append after the last existing import for a tidier block; else prepend.
  const lastImport = findLastImportEnd(source)
  if (lastImport >= 0) {
    return {
      source: source.slice(0, lastImport) + line + source.slice(lastImport),
      binding: bind,
    }
  }
  return {
    source: line + source,
    binding: bind,
  }
}

function sanitiseBinding(s) {
  let out = String(s).replace(/[^A-Za-z0-9_$]/g, '_')
  if (!out) out = 'profile'
  if (/^[0-9]/.test(out)) out = '_' + out
  return out
}

function basenameNoExt(path) {
  const segs = String(path).split('/')
  const last = segs[segs.length - 1] || ''
  return last.replace(/\.[^.]*$/, '')
}

// Returns the index just after the last top-level `import ... from '...'`
// line (including its trailing newline), or -1 if no imports exist.
function findLastImportEnd(source) {
  const re = /^[ \t]*import\s+[^\n]*?from\s+['"][^'"\n]+['"];?[ \t]*\n/gm
  let last = -1
  let m
  while ((m = re.exec(source)) != null) {
    last = m.index + m[0].length
  }
  return last
}
