// jscadRunner.test.js — orchestrator surface that doesn't lean on the @jscad
// module's named exports.
//
// Under vitest's node environment the runner falls through to its main-thread
// evaluator (Worker is undefined). The runner imports `@jscad/modeling` as a
// namespace (`import * as modeling`); under the CJS-compat shim Node hands
// back, the named primitives/transforms/etc. live on `modeling.default`, not
// directly on the namespace. So we can't exercise primitives.cuboid() in a
// node test — but we CAN cover:
//   * DEFAULT_JSCAD       — the seed string handed to fresh `.jscad` files.
//   * runJscad("")        — empty/whitespace source short-circuits.
//   * runJscad(syntax err)— surfaces the error via `{ error }`.
//   * runJscad(returns null) — `{ parts: [] }` regardless of modeling state.
//   * runJscad(plain obj) — normalizeParts wraps a single object with `geom`.
//   * cancelJscad()       — pure no-op when nothing is in flight.
//   * setSketchResolver / setEquationsResolver — accept null + functions.

import { describe, it, expect, afterEach } from 'vitest'
import {
  runJscad,
  cancelJscad,
  DEFAULT_JSCAD,
  setSketchResolver,
  setSketchLister,
  setEquationsResolver,
} from '../lib/jscadRunner.js'

describe('DEFAULT_JSCAD seed', () => {
  it('is a non-empty string with the conventional default-export signature', () => {
    expect(typeof DEFAULT_JSCAD).toBe('string')
    expect(DEFAULT_JSCAD.length).toBeGreaterThan(50)
    expect(DEFAULT_JSCAD).toMatch(/export\s+default\s+function/)
  })

  it('references the modeling primitives the runner injects', () => {
    expect(DEFAULT_JSCAD).toContain('primitives')
    expect(DEFAULT_JSCAD).toContain('cuboid')
  })
})

describe('runJscad — empty input', () => {
  it('returns an empty parts array for empty source', async () => {
    const res = await runJscad('')
    expect(res).toEqual({ parts: [] })
  })

  it('returns an empty parts array for whitespace-only source', async () => {
    const res = await runJscad('   \n\t   ')
    expect(res).toEqual({ parts: [] })
  })
})

describe('runJscad — main-thread evaluation', () => {
  it('returns an empty parts array when the factory returns null', async () => {
    const code = `export default function () { return null }`
    const res = await runJscad(code)
    expect(res.error).toBeUndefined()
    expect(res.parts).toEqual([])
  })

  it('wraps a single returned object that already has a geom field', async () => {
    // normalizeParts(singleObjectWithGeom) → [{ id: out.id ?? 'part-0', geom }]
    const code = `export default function () { return { id: 'solo', geom: { polygons: [] } } }`
    const res = await runJscad(code)
    expect(res.error).toBeUndefined()
    expect(res.parts).toHaveLength(1)
    expect(res.parts[0].id).toBe('solo')
    expect(res.parts[0].geom).toEqual({ polygons: [] })
  })

  it('mints sequential ids when the array entries lack them', async () => {
    const code = `export default function () { return [{ polygons: [] }, { polygons: [] }] }`
    const res = await runJscad(code)
    expect(res.error).toBeUndefined()
    expect(res.parts).toHaveLength(2)
    expect(res.parts[0].id).toBe('part-0')
    expect(res.parts[1].id).toBe('part-1')
  })

  it('preserves user-supplied ids on entries with a geom field', async () => {
    const code = `export default function () {
      return [
        { id: 'a', geom: { polygons: [] } },
        { id: 'b', geom: { polygons: [] } },
      ]
    }`
    const res = await runJscad(code)
    expect(res.error).toBeUndefined()
    expect(res.parts.map((p) => p.id)).toEqual(['a', 'b'])
  })

  it('captures syntax errors as a string in the `error` field', async () => {
    // Unbalanced braces — `new Function` will throw at construction time.
    const res = await runJscad('export default function ({{{ ')
    expect(res.parts).toBeUndefined()
    expect(typeof res.error).toBe('string')
    expect(res.error.length).toBeGreaterThan(0)
  })

  it('captures runtime errors thrown inside the user function', async () => {
    const code = `export default function () { throw new Error('kaboom') }`
    const res = await runJscad(code)
    expect(res.error).toContain('kaboom')
  })

  it('strips top-level `import` lines that would otherwise be illegal in `new Function`', async () => {
    // The runner deliberately removes top-level imports because user code
    // shouldn't need them. Verify the source still evaluates.
    const code = `import * as foo from 'whatever'
export default function () { return [] }`
    const res = await runJscad(code)
    expect(res.error).toBeUndefined()
    expect(res.parts).toEqual([])
  })
})

describe('cancelJscad', () => {
  it('is a no-op when nothing is pending', () => {
    expect(() => cancelJscad()).not.toThrow()
    expect(() => cancelJscad()).not.toThrow()
  })
})

describe('resolver setters', () => {
  it('accepts null to clear the sketch resolver', () => {
    expect(() => setSketchResolver(null)).not.toThrow()
  })

  it('accepts a function for the sketch resolver', () => {
    expect(() => setSketchResolver(() => null)).not.toThrow()
    setSketchResolver(null) // restore
  })

  it('accepts null to clear the equations resolver', () => {
    expect(() => setEquationsResolver(null)).not.toThrow()
  })

  it('accepts a function for the equations resolver', () => {
    expect(() => setEquationsResolver(async () => ({ values: { x: 1 } }))).not.toThrow()
    setEquationsResolver(null) // restore
  })

  it('accepts null to clear the sketch lister', () => {
    expect(() => setSketchLister(null)).not.toThrow()
  })

  it('accepts a function for the sketch lister', () => {
    expect(() => setSketchLister(async () => [])).not.toThrow()
    setSketchLister(null) // restore
  })
})

// ---------------------------------------------------------------------------
// resolveSketchImports error model (exercised via runJscad)
// ---------------------------------------------------------------------------

describe('sketch import — missing path throws and propagates to partsError', () => {
  afterEach(() => {
    setSketchResolver(null)
    setSketchLister(null)
  })

  it('surfaces an error when the sketch path is not found and no resolver is registered', async () => {
    // No resolver → sketchResolver is null → file is null → should throw.
    setSketchResolver(null)
    const code = `import profile from '/missing.sketch'\nexport default function () { return [] }`
    const res = await runJscad(code)
    expect(res.error).toBeDefined()
    expect(res.error).toContain('sketch not found')
    expect(res.error).toContain('/missing.sketch')
  })

  it('error message includes the missing path and the available-sketches list', async () => {
    // Resolver returns null (file not found) but lister knows about other files.
    setSketchResolver(async () => null)
    setSketchLister(async () => ['/parts/profile.sketch', '/parts/rail.sketch'])
    const code = `import profile from '/missing.sketch'\nexport default function () { return [] }`
    const res = await runJscad(code)
    expect(res.error).toBeDefined()
    expect(res.error).toContain('sketch not found: /missing.sketch')
    expect(res.error).toContain('/parts/profile.sketch')
    expect(res.error).toContain('/parts/rail.sketch')
  })

  it('error message says "(no .sketch files in project)" when lister returns empty', async () => {
    setSketchResolver(async () => null)
    setSketchLister(async () => [])
    const code = `import profile from '/empty-project.sketch'\nexport default function () { return [] }`
    const res = await runJscad(code)
    expect(res.error).toBeDefined()
    expect(res.error).toContain('sketch not found: /empty-project.sketch')
    expect(res.error).toContain('(no .sketch files in project)')
  })

  it('happy path — existing sketch resolves correctly without error', async () => {
    // Resolver returns a minimal valid sketch JSON (empty sketch, which produces
    // an empty Geom2 — that is fine; open/empty sketches are allowed to continue
    // evaluating per the design doc).
    const minimalSketch = JSON.stringify({
      version: 1,
      plane: { type: 'base', name: 'XY' },
      entities: [],
      constraints: [],
    })
    setSketchResolver(async () => ({ content: minimalSketch }))
    setSketchLister(async () => ['/parts/outline.sketch'])
    const code = `import profile from '/parts/outline.sketch'\nexport default function () { return [] }`
    const res = await runJscad(code)
    // No error — sketch resolved, JSCAD ran, returned empty parts array.
    expect(res.error).toBeUndefined()
    expect(res.parts).toEqual([])
  })
})
