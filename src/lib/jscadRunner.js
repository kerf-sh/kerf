// Run a user's JSCAD source and return parts.
//
// Convention (see CONTRACT.md / seed file): the user's file's default export is
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
// wrapping the body in `new Function('modeling', body)` — this runs on the
// main thread but is cheap and safe enough for v1 (no network, no DOM access
// beyond what `Function` itself provides). The brief explicitly notes the
// worker approach is fragile across bundler boundaries and OK to drop.

import * as modeling from '@jscad/modeling'

function transformSource(code) {
  // Remove top-level imports — the user's code shouldn't need them, but seeded
  // examples sometimes include `import * as modeling from '@jscad/modeling'`.
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

function normalizeParts(out) {
  // Accepted return shapes:
  //   [{id, geom}, ...]    — preferred
  //   Geom3                — single
  //   [Geom3, Geom3, ...]  — auto-id 'part-0', 'part-1', ...
  if (out == null) return []
  if (Array.isArray(out)) {
    // If it's a list of {id, geom} objects, keep as-is.
    if (out.length === 0) return []
    if (out[0] && typeof out[0] === 'object' && 'geom' in out[0]) {
      return out.map((p, i) => ({ id: p.id ?? `part-${i}`, geom: p.geom }))
    }
    // Otherwise treat as array of geoms.
    return out.map((g, i) => ({ id: `part-${i}`, geom: g }))
  }
  // Single object: either {id, geom} or a raw Geom3.
  if (typeof out === 'object' && 'geom' in out) return [{ id: out.id ?? 'part-0', geom: out.geom }]
  return [{ id: 'part-0', geom: out }]
}

export async function runJscad(code) {
  if (!code || !code.trim()) return { parts: [] }
  try {
    const body = transformSource(code)
    const factory = new Function('modeling', body)
    const exported = factory(modeling)
    let result = typeof exported === 'function' ? exported(modeling) : exported
    if (result && typeof result.then === 'function') result = await result
    const parts = normalizeParts(result)
    return { parts }
  } catch (err) {
    return { error: err && err.message ? err.message : String(err) }
  }
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
