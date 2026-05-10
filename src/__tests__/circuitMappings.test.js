// circuitMappings.test.js — round-trip and tolerance tests for the
// `// kerf:library-mappings={...}` marker comment that pins refdes →
// library-part-file-id pairs at the top of `.circuit.tsx` files.

import { describe, it, expect, vi } from 'vitest'
import {
  parseLibraryMappings,
  writeLibraryMappings,
  setCircuitMapping,
  resolveLibraryCadComponent,
  evalLibraryModel3D,
} from '../lib/circuitMappings.js'

describe('parseLibraryMappings', () => {
  it('returns an empty object for non-strings and empty strings', () => {
    expect(parseLibraryMappings(null)).toEqual({})
    expect(parseLibraryMappings(undefined)).toEqual({})
    expect(parseLibraryMappings('')).toEqual({})
    expect(parseLibraryMappings(123)).toEqual({})
  })

  it('reads a single-line marker at the top', () => {
    const src = '// kerf:library-mappings={"R1":"abc","C1":"def"}\nimport x from "y"\n'
    expect(parseLibraryMappings(src)).toEqual({ R1: 'abc', C1: 'def' })
  })

  it('drops non-string and empty-string values defensively', () => {
    const src = '// kerf:library-mappings={"R1":"abc","R2":42,"R3":""}\n'
    expect(parseLibraryMappings(src)).toEqual({ R1: 'abc' })
  })

  it('returns {} on malformed JSON without throwing', () => {
    const src = '// kerf:library-mappings={not json\n'
    expect(parseLibraryMappings(src)).toEqual({})
  })

  it('ignores arrays masquerading as the mappings object', () => {
    const src = '// kerf:library-mappings=["R1","R2"]\n'
    expect(parseLibraryMappings(src)).toEqual({})
  })

  it('returns {} when no marker is present', () => {
    expect(parseLibraryMappings('import x from "y"\nexport default x\n')).toEqual({})
  })
})

describe('writeLibraryMappings', () => {
  it('inserts a marker at the very top when none exists', () => {
    const out = writeLibraryMappings('import a from "b"\n', { R1: 'id-1' })
    expect(out.startsWith('// kerf:library-mappings={"R1":"id-1"}\n')).toBe(true)
    expect(out.includes('import a from "b"')).toBe(true)
  })

  it('replaces an existing marker in place', () => {
    const before = '// kerf:library-mappings={"R1":"old"}\nimport a from "b"\n'
    const out = writeLibraryMappings(before, { R1: 'new' })
    expect(out).toBe('// kerf:library-mappings={"R1":"new"}\nimport a from "b"\n')
  })

  it('removes the marker line when mappings clear to empty', () => {
    const before = '// kerf:library-mappings={"R1":"old"}\nimport a from "b"\n'
    expect(writeLibraryMappings(before, {})).toBe('import a from "b"\n')
  })

  it('returns content untouched when no marker exists and mappings empty', () => {
    const src = 'import x from "y"\n'
    expect(writeLibraryMappings(src, {})).toBe(src)
  })

  it('preserves insertion order across multiple keys', () => {
    const out = writeLibraryMappings('', { R1: 'a', C1: 'b', U1: 'c' })
    expect(out).toBe('// kerf:library-mappings={"R1":"a","C1":"b","U1":"c"}\n')
  })

  it('drops empty-string values when serializing', () => {
    const out = writeLibraryMappings('', { R1: 'a', R2: '' })
    expect(out).toBe('// kerf:library-mappings={"R1":"a"}\n')
  })

  it('round-trips parse → write → parse', () => {
    const src = '// kerf:library-mappings={"R1":"x","C1":"y"}\ncode\n'
    const parsed = parseLibraryMappings(src)
    const written = writeLibraryMappings('different\n', parsed)
    expect(parseLibraryMappings(written)).toEqual({ R1: 'x', C1: 'y' })
  })
})

describe('setCircuitMapping', () => {
  it('adds a new refdes → file_id mapping', () => {
    const { mappings, content } = setCircuitMapping('code\n', 'R1', 'id-1')
    expect(mappings).toEqual({ R1: 'id-1' })
    expect(content.startsWith('// kerf:library-mappings={"R1":"id-1"}\n')).toBe(true)
  })

  it('clears a refdes when partFileId is null', () => {
    const start = '// kerf:library-mappings={"R1":"id-1","C1":"id-2"}\n'
    const { mappings } = setCircuitMapping(start, 'R1', null)
    expect(mappings).toEqual({ C1: 'id-2' })
  })

  it('is a no-op when clearing a missing refdes', () => {
    const { mappings, content } = setCircuitMapping('plain\n', 'R1', undefined)
    expect(mappings).toEqual({})
    expect(content).toBe('plain\n')
  })
})

describe('resolveLibraryCadComponent', () => {
  it('returns the mapped file id when a mapping exists', () => {
    expect(resolveLibraryCadComponent('R1', { R1: 'file-123', C1: 'file-456' })).toBe('file-123')
  })

  it('returns null for an unmapped refdes', () => {
    expect(resolveLibraryCadComponent('U7', { R1: 'file-123' })).toBeNull()
  })

  it('returns null for malformed mappings (non-object, array, null)', () => {
    expect(resolveLibraryCadComponent('R1', null)).toBeNull()
    expect(resolveLibraryCadComponent('R1', undefined)).toBeNull()
    expect(resolveLibraryCadComponent('R1', ['file-1'])).toBeNull()
    expect(resolveLibraryCadComponent('R1', 'not-an-object')).toBeNull()
  })

  it('returns null for empty / non-string refdes', () => {
    expect(resolveLibraryCadComponent('', { R1: 'file-1' })).toBeNull()
    expect(resolveLibraryCadComponent(null, { R1: 'file-1' })).toBeNull()
    expect(resolveLibraryCadComponent(42, { R1: 'file-1' })).toBeNull()
  })

  it('rejects mapping values that are not non-empty strings', () => {
    expect(resolveLibraryCadComponent('R1', { R1: '' })).toBeNull()
    expect(resolveLibraryCadComponent('R1', { R1: 99 })).toBeNull()
    expect(resolveLibraryCadComponent('R1', { R1: null })).toBeNull()
  })
})

// evalLibraryModel3D exercises the JSCAD-eval seam used by the 3D tab when
// a `cad_component` is mapped to a Library Part that carries a `model_3d`
// JSCAD source string. Every failure mode resolves to `null` so the caller
// can fall through to the existing teal cuboid approximation.
describe('evalLibraryModel3D', () => {
  it('returns null for empty / non-string content', async () => {
    expect(await evalLibraryModel3D('')).toBeNull()
    expect(await evalLibraryModel3D(null)).toBeNull()
    expect(await evalLibraryModel3D(undefined)).toBeNull()
    expect(await evalLibraryModel3D(42)).toBeNull()
  })

  it('returns null when the Part JSON has no model_3d field', async () => {
    const content = JSON.stringify({ name: 'Resistor', value: '10k' })
    expect(await evalLibraryModel3D(content)).toBeNull()
  })

  it('returns null when model_3d is present but empty / non-string', async () => {
    expect(await evalLibraryModel3D(JSON.stringify({ model_3d: '' }))).toBeNull()
    expect(await evalLibraryModel3D(JSON.stringify({ model_3d: 42 }))).toBeNull()
    expect(await evalLibraryModel3D(JSON.stringify({ model_3d: null }))).toBeNull()
  })

  it('returns null for a model_3d that looks like a STEP/STL URL (defer to OCCT slice)', async () => {
    // `/api/blobs/...` paths are intentionally skipped — only JSCAD source
    // is evaluated here. The presence of `function`/`=>`/`export` is the
    // discriminator; a bare URL has none of those tokens.
    const content = JSON.stringify({ model_3d: '/api/blobs/users/uid/sha.step' })
    expect(await evalLibraryModel3D(content)).toBeNull()
  })

  it('returns null on malformed Part JSON without throwing', async () => {
    expect(await evalLibraryModel3D('{not valid json')).toBeNull()
    // JSON arrays masquerading as Part objects are also rejected.
    expect(await evalLibraryModel3D('["model_3d", "boom"]')).toBeNull()
  })

  it('returns null when the JSCAD source has a syntax error', async () => {
    // Suppress the runner's internal warn while we verify graceful failure.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const content = JSON.stringify({ model_3d: 'export default function ({{{' })
    expect(await evalLibraryModel3D(content)).toBeNull()
    warn.mockRestore()
  })

  it('returns null when the JSCAD factory returns a malformed value', async () => {
    // The runner accepts any returned value; an explicit `undefined` short-
    // circuits to no parts which we treat as a fall-through. Verifies the
    // zero-parts → null guard so the teal box remains the visible payoff.
    const src = `export default function () { return undefined }`
    const content = JSON.stringify({ model_3d: src })
    expect(await evalLibraryModel3D(content)).toBeNull()
  })

  it('returns parts when the JSCAD source evaluates to a Geom3-shaped object', async () => {
    // The runner accepts a single returned object with a `geom` field and
    // wraps it in a one-entry parts array. We use an explicitly empty
    // polygons list so we don't depend on @jscad/modeling's named exports
    // landing on the namespace under vitest's node environment.
    const src = `export default function () { return { id: 'body', geom: { polygons: [] } } }`
    const content = JSON.stringify({ model_3d: src })
    const res = await evalLibraryModel3D(content)
    expect(res).not.toBeNull()
    expect(Array.isArray(res.parts)).toBe(true)
    expect(res.parts.length).toBe(1)
    expect(res.parts[0].id).toBe('body')
    expect(res.parts[0].geom).toBeTruthy()
  })

  it('returns null when the source returns zero parts', async () => {
    // A factory that returns null short-circuits to no parts; we treat
    // that as a fall-through rather than spliced-empty.
    const src = `export default function () { return null }`
    const content = JSON.stringify({ model_3d: src })
    expect(await evalLibraryModel3D(content)).toBeNull()
  })
})
