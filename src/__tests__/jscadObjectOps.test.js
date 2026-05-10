// jscadObjectOps.test.js — covers the bracket-matching mutators in
// src/lib/jscadObjectOps.js. The file is large (637 LOC) and ships its own
// hand-rolled tokeniser; we focus on the public surface and a few
// adversarial inputs that have historically tripped up similar string-walkers
// (nested braces, trailing commas, quote-style preservation, comments).

import { describe, it, expect } from 'vitest'
import {
  duplicateObject,
  deleteObject,
  hasObjectEntry,
  listObjectIds,
  mintFeatureId,
  appendObjectEntry,
  replaceObjectEntry,
  readObjectGeomExpr,
  ensureSketchImport,
} from '../lib/jscadObjectOps.js'

const SIMPLE = `export default function () {
  return [
    { id: 'base', geom: cuboid({ size: [10, 10, 10] }) },
    { id: 'peg', geom: cylinder({ radius: 2, height: 5 }) },
  ]
}
`

const NESTED = `export default function () {
  return [
    { id: 'a', geom: translate([0, 0, 5], cuboid({ size: [1, 1, 1] })) },
    { id: 'b', geom: subtract(cuboid({ size: [4, 4, 4] }), sphere({ radius: 2 })) },
  ]
}
`

const WITH_COMMENTS = `export default function () {
  return [
    // leading comment
    { id: 'a', geom: cuboid({ size: [1, 1, 1] }) /* inline */ },
    { id: 'b', geom: sphere({ radius: 2 }) }, // trailer
  ]
}
`

const DOUBLE_QUOTED = `export default function () {
  return [
    { id: "alpha", geom: cuboid({ size: [1, 1, 1] }) },
  ]
}
`

const NOT_PARTS_ARRAY = `export default function () {
  const xs = [1, 2, 3]
  return xs
}
`

describe('listObjectIds', () => {
  it('returns ids in source order', () => {
    expect(listObjectIds(SIMPLE)).toEqual(['base', 'peg'])
  })
  it('handles nested {} inside the entry', () => {
    expect(listObjectIds(NESTED)).toEqual(['a', 'b'])
  })
  it('handles inline + line comments', () => {
    expect(listObjectIds(WITH_COMMENTS)).toEqual(['a', 'b'])
  })
  it('returns null when file is not a parts array', () => {
    expect(listObjectIds(NOT_PARTS_ARRAY)).toBeNull()
  })
  it('returns null on empty / null source', () => {
    expect(listObjectIds('')).toBeNull()
    expect(listObjectIds(null)).toBeNull()
  })
})

describe('hasObjectEntry', () => {
  it('finds existing ids', () => {
    expect(hasObjectEntry(SIMPLE, 'base')).toBe(true)
    expect(hasObjectEntry(SIMPLE, 'peg')).toBe(true)
  })
  it('returns false for missing ids', () => {
    expect(hasObjectEntry(SIMPLE, 'nope')).toBe(false)
  })
  it('returns false on unparseable source', () => {
    expect(hasObjectEntry(NOT_PARTS_ARRAY, 'x')).toBe(false)
  })
})

describe('mintFeatureId', () => {
  it('mints pad-1 when no pads exist', () => {
    expect(mintFeatureId(SIMPLE, 'pad')).toBe('pad-1')
  })
  it('skips colliding suffixes', () => {
    const src = SIMPLE.replace("'base'", "'pad-1'")
    expect(mintFeatureId(src, 'pad')).toBe('pad-2')
  })
  it('returns null when source unparseable', () => {
    expect(mintFeatureId(NOT_PARTS_ARRAY, 'pad')).toBeNull()
  })
})

describe('duplicateObject', () => {
  it('clones the matched entry with a "-copy" id', () => {
    const out = duplicateObject(SIMPLE, 'base')
    expect(out).not.toBeNull()
    expect(listObjectIds(out)).toEqual(['base', 'base-copy', 'peg'])
  })
  it('mints "-copy-2" on collision with existing -copy', () => {
    const src = SIMPLE.replace("'peg'", "'base-copy'")
    const out = duplicateObject(src, 'base')
    expect(listObjectIds(out)).toEqual(['base', 'base-copy-2', 'base-copy'])
  })
  it('uses an explicit newId when provided', () => {
    const out = duplicateObject(SIMPLE, 'base', 'foo')
    expect(listObjectIds(out)).toEqual(['base', 'foo', 'peg'])
  })
  it('returns null when newId collides with an existing id', () => {
    expect(duplicateObject(SIMPLE, 'base', 'peg')).toBeNull()
  })
  it('returns null for a missing source id', () => {
    expect(duplicateObject(SIMPLE, 'ghost')).toBeNull()
  })
  it('returns null on falsy inputs', () => {
    expect(duplicateObject('', 'base')).toBeNull()
    expect(duplicateObject(SIMPLE, '')).toBeNull()
    expect(duplicateObject(null, 'base')).toBeNull()
  })
  it('preserves quote style (double quotes)', () => {
    const out = duplicateObject(DOUBLE_QUOTED, 'alpha')
    expect(out).toContain('"alpha-copy"')
  })
  it('handles entries with nested braces', () => {
    const out = duplicateObject(NESTED, 'b')
    expect(listObjectIds(out)).toEqual(['a', 'b', 'b-copy'])
    // The clone should still contain its full nested geom expression.
    expect(out).toContain("subtract(cuboid({ size: [4, 4, 4] }), sphere({ radius: 2 }))")
  })
})

describe('deleteObject', () => {
  it('removes the matched entry', () => {
    const out = deleteObject(SIMPLE, 'base')
    expect(out).not.toBeNull()
    expect(listObjectIds(out)).toEqual(['peg'])
  })
  it('removes the last entry too', () => {
    const out = deleteObject(SIMPLE, 'peg')
    expect(listObjectIds(out)).toEqual(['base'])
  })
  it('returns null for missing ids', () => {
    expect(deleteObject(SIMPLE, 'ghost')).toBeNull()
  })
  it('returns null on unparseable source', () => {
    expect(deleteObject(NOT_PARTS_ARRAY, 'x')).toBeNull()
  })
  it('returns null on falsy inputs', () => {
    expect(deleteObject('', 'a')).toBeNull()
    expect(deleteObject(SIMPLE, '')).toBeNull()
  })
})

describe('appendObjectEntry', () => {
  it('appends a new entry to the end', () => {
    const out = appendObjectEntry(SIMPLE, "{ id: 'extra', geom: sphere({ radius: 1 }) }")
    expect(listObjectIds(out)).toEqual(['base', 'peg', 'extra'])
  })
  it('returns null when input is unparseable', () => {
    expect(appendObjectEntry(NOT_PARTS_ARRAY, "{ id: 'x' }")).toBeNull()
  })
  it('returns null on falsy entry text', () => {
    expect(appendObjectEntry(SIMPLE, '')).toBeNull()
    expect(appendObjectEntry(SIMPLE, null)).toBeNull()
  })
})

describe('replaceObjectEntry', () => {
  it('swaps the matched entry verbatim', () => {
    const out = replaceObjectEntry(SIMPLE, 'base', "{ id: 'base', geom: sphere({ radius: 9 }) }")
    expect(listObjectIds(out)).toEqual(['base', 'peg'])
    expect(out).toContain('sphere({ radius: 9 })')
    expect(out).not.toContain('cuboid({ size: [10, 10, 10] })')
  })
  it('returns null on missing id', () => {
    expect(replaceObjectEntry(SIMPLE, 'ghost', "{ id: 'ghost' }")).toBeNull()
  })
})

describe('readObjectGeomExpr', () => {
  it('returns the verbatim geom expression', () => {
    expect(readObjectGeomExpr(SIMPLE, 'base')).toBe('cuboid({ size: [10, 10, 10] })')
  })
  it('handles nested commas inside the geom value', () => {
    expect(readObjectGeomExpr(NESTED, 'a')).toBe('translate([0, 0, 5], cuboid({ size: [1, 1, 1] }))')
  })
  it('returns null for missing id', () => {
    expect(readObjectGeomExpr(SIMPLE, 'ghost')).toBeNull()
  })
})

describe('ensureSketchImport', () => {
  it('inserts a fresh import at the top when none exists', () => {
    const { source, binding } = ensureSketchImport('export default function(){}\n', './sketches/foo.js')
    expect(binding).toBe('foo')
    expect(source.startsWith("import foo from './sketches/foo.js'\n")).toBe(true)
  })
  it('reuses an existing import for the same path', () => {
    const src = "import existing from './sketches/foo.js'\nexport default function(){}\n"
    const out = ensureSketchImport(src, './sketches/foo.js')
    expect(out.binding).toBe('existing')
    expect(out.source).toBe(src) // unchanged
  })
  it('uniquifies the binding on collision', () => {
    const src = "import foo from './sketches/other.js'\nexport default function(){}\n"
    const out = ensureSketchImport(src, './sketches/foo.js')
    expect(out.binding).toBe('foo2')
    expect(out.source).toContain("import foo2 from './sketches/foo.js'")
  })
  it('places new imports after existing import block', () => {
    const src = "import a from './a.js'\nimport b from './b.js'\nexport default function(){}\n"
    const out = ensureSketchImport(src, './sketches/c.js')
    // The new import lands after the b-import (and before `export default`).
    const lines = out.source.split('\n')
    expect(lines[0]).toBe("import a from './a.js'")
    expect(lines[1]).toBe("import b from './b.js'")
    expect(lines[2]).toBe("import c from './sketches/c.js'")
  })
  it('sanitises non-identifier basenames', () => {
    const out = ensureSketchImport('', './sketches/123-weird name.js')
    // Leading digit gets a `_` prefix; spaces/hyphens become `_`.
    expect(out.binding).toMatch(/^_?[A-Za-z_$][\w$]*$/)
  })
  it('falls back to "profile" when basename is empty', () => {
    const out = ensureSketchImport('', '')
    expect(out.binding).toBe('profile')
  })
})
