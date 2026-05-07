// Pragmatic JSCAD source mutators for color + translate.
//
// We do NOT parse the file's AST — we use targeted regex over the
// {id: '<partId>', geom: <expr>} shape that the contract pins down. This is
// good enough for the conventional Kerf JSCAD layout (matching the seed file)
// and bails out cleanly when the source doesn't fit.
//
// Caller pattern:
//   const next = withColorizedPart(currentSource, partId, [r,g,b])
//   if (!next) return /* show toast: couldn't safely edit */
//   await api.updateFile(...)
//
// Limitation: if the user nests transforms inside the part definition (e.g.
// `geom: someHelper(transforms.translate(...))`), or if the part is built
// procedurally instead of as a literal `{id, geom}` entry, we won't find a
// match → caller falls back to a no-op + toast.

// ---------------------------------------------------------------------------
// Locate the `geom: <expr>` slice for a given part id.

// Match a balanced parenthesised expression starting at `start` (which must
// point at an opening `(`). Returns the index just AFTER the matching `)`,
// or -1 on failure. Handles nested parens + simple single/double quoted
// strings + template literal backticks. Doesn't handle regex literals (which
// shouldn't appear inside JSCAD expressions in practice).
function matchParen(src, start) {
  if (src[start] !== '(') return -1
  let depth = 0
  let inS = null // ' " or `
  for (let i = start; i < src.length; i++) {
    const c = src[i]
    if (inS) {
      if (c === '\\') { i++; continue }
      if (c === inS) inS = null
      continue
    }
    if (c === '"' || c === "'" || c === '`') { inS = c; continue }
    if (c === '(') depth++
    else if (c === ')') {
      depth--
      if (depth === 0) return i + 1
    }
  }
  return -1
}

// Match a balanced expression up to a delimiter (`,` or `}` at depth 0).
// Used to capture the `<expr>` after `geom:`. Honors nested `()`, `[]`, `{}`,
// and string literals.
function matchExprUntil(src, start, stops) {
  let i = start
  let depth = 0
  let inS = null
  while (i < src.length) {
    const c = src[i]
    if (inS) {
      if (c === '\\') { i += 2; continue }
      if (c === inS) inS = null
      i++
      continue
    }
    if (c === '"' || c === "'" || c === '`') { inS = c; i++; continue }
    if (c === '(' || c === '[' || c === '{') { depth++; i++; continue }
    if (c === ')' || c === ']' || c === '}') {
      if (depth === 0) {
        if (stops.includes(c)) return i
      }
      depth--
      i++
      continue
    }
    if (depth === 0 && stops.includes(c)) return i
    i++
  }
  return -1
}

// Find the slice describing `{ id: '<partId>', geom: <expr> }` and return
// { startIdx, endIdx, geomExpr } pointing at the `<expr>` substring.
// Returns null if not found / ambiguous.
function locatePartGeom(source, partId) {
  // Match either `id: 'name'`, `id: "name"`, or `id: \`name\`` followed (in
  // either order) by `geom: <expr>`. We scan all matches; if zero or >1, bail.
  const escapedId = partId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const idRe = new RegExp(`id\\s*:\\s*['"\`]${escapedId}['"\`]`, 'g')
  const matches = []
  let m
  while ((m = idRe.exec(source)) !== null) {
    matches.push(m.index)
  }
  if (matches.length !== 1) return null

  // Scan backwards from the match for the enclosing `{`, then forward to find
  // the `geom:` field.
  const idAt = matches[0]
  let braceStart = -1
  let depth = 0
  for (let i = idAt; i >= 0; i--) {
    const c = source[i]
    if (c === '}') depth++
    else if (c === '{') {
      if (depth === 0) { braceStart = i; break }
      depth--
    }
  }
  if (braceStart < 0) return null
  // Find matching `}`.
  let braceEnd = -1
  depth = 0
  let inS = null
  for (let i = braceStart; i < source.length; i++) {
    const c = source[i]
    if (inS) {
      if (c === '\\') { i++; continue }
      if (c === inS) inS = null
      continue
    }
    if (c === '"' || c === "'" || c === '`') { inS = c; continue }
    if (c === '{') depth++
    else if (c === '}') {
      depth--
      if (depth === 0) { braceEnd = i; break }
    }
  }
  if (braceEnd < 0) return null

  const slice = source.slice(braceStart, braceEnd + 1)
  const localGeomRe = /geom\s*:\s*/g
  const geomMatch = localGeomRe.exec(slice)
  if (!geomMatch) return null
  const exprStart = braceStart + geomMatch.index + geomMatch[0].length
  // Read until `,` or `}` at depth 0.
  const exprEnd = matchExprUntil(source, exprStart, [',', '}'])
  if (exprEnd < 0) return null

  let geomExpr = source.slice(exprStart, exprEnd).trimEnd()
  // Trim trailing whitespace; keep position intact for splice.
  return {
    braceStart, braceEnd,
    exprStart, exprEnd: exprStart + geomExpr.length,
    geomExpr,
  }
}

// ---------------------------------------------------------------------------
// colors.colorize wrap/replace

// Match `colors.colorize([r,g,b(,a)?], <inner>)` at the start of `expr` —
// returns { rgba, inner } if `expr` is exactly that wrap, else null.
function matchColorize(expr) {
  const re = /^\s*colors\s*\.\s*colorize\s*\(\s*(\[[^\]]+\])\s*,\s*/
  const m = re.exec(expr)
  if (!m) return null
  const innerStart = m[0].length - 0 // index in expr
  // From `colors.colorize(`, the matching `)` closes the call. We need to
  // walk from that opening paren.
  // Find the opening paren of colorize:
  const openIdx = expr.indexOf('(', expr.indexOf('colorize'))
  if (openIdx < 0) return null
  const closeIdx = matchParen(expr, openIdx)
  if (closeIdx < 0) return null
  const inner = expr.slice(innerStart, closeIdx - 1).trimEnd()
  const rgbaText = m[1]
  const trailing = expr.slice(closeIdx).trimEnd()
  if (trailing.length > 0) return null // trailing chars → not a clean wrap
  return { rgbaText, inner }
}

function rgbaArrayText(rgb) {
  return `[${rgb.map((c) => +c.toFixed(4)).join(', ')}]`
}

export function withColorizedPart(source, partId, rgb) {
  const loc = locatePartGeom(source, partId)
  if (!loc) return null
  const colorWrap = matchColorize(loc.geomExpr)
  let nextExpr
  if (colorWrap) {
    // Replace existing rgba.
    nextExpr = `colors.colorize(${rgbaArrayText(rgb)}, ${colorWrap.inner})`
  } else {
    nextExpr = `colors.colorize(${rgbaArrayText(rgb)}, ${loc.geomExpr.trim()})`
  }
  return source.slice(0, loc.exprStart) + nextExpr + source.slice(loc.exprEnd)
}

// ---------------------------------------------------------------------------
// transforms.translate wrap/accumulate

function matchTranslate(expr) {
  // `transforms.translate([x,y,z], <inner>)`
  const re = /^\s*transforms\s*\.\s*translate\s*\(\s*(\[[^\]]+\])\s*,\s*/
  const m = re.exec(expr)
  if (!m) return null
  const innerStart = m[0].length
  const openIdx = expr.indexOf('(', expr.indexOf('translate'))
  if (openIdx < 0) return null
  const closeIdx = matchParen(expr, openIdx)
  if (closeIdx < 0) return null
  const inner = expr.slice(innerStart, closeIdx - 1).trimEnd()
  const trailing = expr.slice(closeIdx).trimEnd()
  if (trailing.length > 0) return null
  // Parse the existing [x,y,z]. We deliberately use Function rather than
  // JSON.parse because users may write `[10, 20, 0.5]` which JSON allows
  // anyway, but also `[10, 20, 30,]` which it doesn't.
  let xyz
  try {
    const parsed = new Function(`return ${m[1]}`)()
    xyz = (Array.isArray(parsed) && parsed.length >= 3) ? parsed : [0, 0, 0]
  } catch {
    xyz = [0, 0, 0]
  }
  return { xyz, inner }
}

function xyzText(xyz) {
  return `[${xyz.map((n) => +n.toFixed(4)).join(', ')}]`
}

// Wrap (or accumulate) a translate around `partId`'s geom. `mode` decides
// between additive (`add`) and absolute (`set`).
export function withTranslatedPart(source, partId, deltaXYZ, mode = 'add') {
  const loc = locatePartGeom(source, partId)
  if (!loc) return null
  const tr = matchTranslate(loc.geomExpr)
  let xyz, inner
  if (tr) {
    xyz = mode === 'set' ? deltaXYZ : [
      tr.xyz[0] + deltaXYZ[0],
      tr.xyz[1] + deltaXYZ[1],
      tr.xyz[2] + deltaXYZ[2],
    ]
    inner = tr.inner
  } else {
    xyz = mode === 'set' ? deltaXYZ : deltaXYZ
    inner = loc.geomExpr.trim()
  }
  // If both translate and colorize are wrapped, we want the order to be:
  //   transforms.translate(..., colors.colorize(..., <bare>))
  // Wrapping translate around the existing inner preserves any colorize wrap.
  const nextExpr = `transforms.translate(${xyzText(xyz)}, ${inner})`
  return source.slice(0, loc.exprStart) + nextExpr + source.slice(loc.exprEnd)
}
