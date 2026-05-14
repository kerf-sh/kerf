// assembly.test.js — coverage for assembly.js's parse/serialize round-trips
// and the cross-project (external_ref) branch of resolveAssemblyParts.
//
// Notes:
//   - We mock the geometry payloads as plain {id, geom, color?} bags. The
//     resolver's only contract on `geom` is that `applyMatrixToGeom` returns
//     something truthy — for that we use a tiny stand-in object that carries
//     the id through. The real geom3 helper accepts any JSCAD Geom3, so we
//     don't need three.js or jscad here.
//   - applyMatrixToGeom is mocked via vitest's vi.mock so the test stays free
//     of the JSCAD dependency.

import { describe, it, expect, vi } from 'vitest'

vi.mock('../lib/geom3.js', () => ({
  // Pass-through: return whatever geom we got. This is sufficient for the
  // resolver branches we care about — id stitching, external_ref dispatch,
  // and the "permission denied → empty" graceful path.
  applyMatrixToGeom: (geom) => geom,
}))

import {
  parseAssembly,
  serializeAssembly,
  resolveAssemblyParts,
  restampExternalRefSeen,
  identityMatrix,
  loadExternalParts,
  derivedKindForRefKind,
  addMate,
  removeMate,
  mateRefFromPick,
} from '../lib/assembly.js'

describe('parseAssembly / serializeAssembly — external_ref round-trip', () => {
  it('parses a component with external_ref and surfaces it on the row', () => {
    const json = JSON.stringify({
      components: [
        {
          id: 'main-pcb',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: {
            project_id: '11111111-1111-1111-1111-111111111111',
            file_id: '22222222-2222-2222-2222-222222222222',
            kind: 'board_3d',
            pin: 'tracking_latest',
          },
        },
      ],
    })
    const parsed = parseAssembly(json)
    expect(parsed.components).toHaveLength(1)
    const c = parsed.components[0]
    expect(c.id).toBe('main-pcb')
    expect(c.external_ref).toBeTruthy()
    expect(c.external_ref.project_id).toBe('11111111-1111-1111-1111-111111111111')
    expect(c.external_ref.file_id).toBe('22222222-2222-2222-2222-222222222222')
    expect(c.external_ref.kind).toBe('board_3d')
    expect(c.external_ref.pin).toBe('tracking_latest')
  })

  it('round-trips through serialize → parse without losing fields', () => {
    const original = {
      components: [
        {
          id: 'pcb-a',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: {
            project_id: 'pid-1',
            file_id: 'fid-1',
            kind: 'board_outline_2d',
            pin: 'rev-abc',
          },
        },
        {
          id: 'screw-1',
          file_id: 'local-fid-1',
          object_id: 'screw',
          transform: identityMatrix(),
        },
      ],
    }
    const text = serializeAssembly(original)
    const parsed = parseAssembly(text)
    expect(parsed.components).toHaveLength(2)
    expect(parsed.components[0].external_ref).toEqual({
      project_id: 'pid-1',
      file_id: 'fid-1',
      kind: 'board_outline_2d',
      pin: 'rev-abc',
    })
    // Local row is unchanged.
    expect(parsed.components[1].external_ref).toBeFalsy()
    expect(parsed.components[1].file_id).toBe('local-fid-1')
    expect(parsed.components[1].object_id).toBe('screw')
  })

  it('coerces an unknown kind to board_3d (defensive default)', () => {
    const json = JSON.stringify({
      components: [
        {
          id: 'x',
          external_ref: {
            project_id: 'p', file_id: 'f', kind: 'rocket-fuel', pin: '',
          },
          transform: identityMatrix(),
        },
      ],
    })
    const parsed = parseAssembly(json)
    expect(parsed.components[0].external_ref.kind).toBe('board_3d')
    expect(parsed.components[0].external_ref.pin).toBe('tracking_latest')
  })

  it('round-trips last_seen_updated_at on the external_ref blob', () => {
    // Freshness baseline for the "out of date" chip (ROADMAP row 68 Phase 2):
    // the editor stamps the source file's updated_at the first time it sees a
    // tracking_latest ref, then compares to the live value on later renders.
    const original = {
      components: [
        {
          id: 'pcb',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: {
            project_id: 'p',
            file_id: 'f',
            kind: 'board_3d',
            pin: 'tracking_latest',
            last_seen_updated_at: '2026-04-01T12:00:00Z',
          },
        },
      ],
    }
    const text = serializeAssembly(original)
    const parsed = parseAssembly(text)
    expect(parsed.components[0].external_ref.last_seen_updated_at)
      .toBe('2026-04-01T12:00:00Z')
  })

  it('omits last_seen_updated_at when not provided (back-compat)', () => {
    // Older assembly files that predate the freshness chip mustn't gain a
    // spurious empty field on parse — the resolver and chip code both treat
    // "missing" as "never seen yet".
    const json = JSON.stringify({
      components: [
        {
          id: 'pcb',
          external_ref: { project_id: 'p', file_id: 'f', kind: 'board_3d', pin: 'tracking_latest' },
          transform: identityMatrix(),
        },
      ],
    })
    const parsed = parseAssembly(json)
    expect(parsed.components[0].external_ref.last_seen_updated_at).toBeUndefined()
  })

  it('drops external_ref entries missing required ids', () => {
    const json = JSON.stringify({
      components: [
        {
          id: 'x',
          file_id: 'local-1',
          object_id: 'foo',
          external_ref: { project_id: '', file_id: '', kind: 'board_3d' },
          transform: identityMatrix(),
        },
      ],
    })
    const parsed = parseAssembly(json)
    // The component itself stays (file_id is set), but external_ref is gone.
    expect(parsed.components).toHaveLength(1)
    expect(parsed.components[0].external_ref).toBeFalsy()
  })
})

describe('resolveAssemblyParts — external_ref dispatch', () => {
  it('routes external_ref components through loadExternalParts, not loadParts', async () => {
    const content = JSON.stringify({
      components: [
        {
          id: 'pcb-1',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: {
            project_id: 'pid-X', file_id: 'fid-X', kind: 'board_3d', pin: 'tracking_latest',
          },
        },
      ],
    })
    const loadParts = vi.fn(async () => [])
    const loadExternalParts = vi.fn(async (ref) => {
      // The loader sees the full ref object — assert on it.
      expect(ref.project_id).toBe('pid-X')
      expect(ref.file_id).toBe('fid-X')
      expect(ref.kind).toBe('board_3d')
      expect(ref.pin).toBe('tracking_latest')
      return [
        { id: '__board__', geom: { tag: 'board' } },
        { id: 'R1', geom: { tag: 'r1' } },
      ]
    })
    const out = await resolveAssemblyParts({ content, loadParts, loadExternalParts })
    expect(loadParts).not.toHaveBeenCalled()
    expect(loadExternalParts).toHaveBeenCalledOnce()
    // Both objects emitted by the external loader are forwarded; ids are
    // re-stitched as `${componentId}/${origId}`.
    expect(out.map((p) => p.id)).toEqual(['pcb-1/__board__', 'pcb-1/R1'])
    expect(out[0].componentId).toBe('pcb-1')
    expect(out[0].origPartId).toBe('__board__')
  })

  it('falls back to onMissing when no loadExternalParts is supplied', async () => {
    const content = JSON.stringify({
      components: [
        {
          id: 'orphan',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: { project_id: 'p', file_id: 'f', kind: 'board_3d', pin: 'tracking_latest' },
        },
      ],
    })
    const onMissing = vi.fn()
    const out = await resolveAssemblyParts({
      content,
      loadParts: async () => [],
      onMissing,
    })
    expect(out).toEqual([])
    expect(onMissing).toHaveBeenCalledOnce()
    expect(onMissing.mock.calls[0][0]).toBe('orphan')
  })

  it('treats a thrown loadExternalParts as a graceful empty (no crash)', async () => {
    const content = JSON.stringify({
      components: [
        {
          id: 'denied',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: { project_id: 'p', file_id: 'f', kind: 'board_3d', pin: 'tracking_latest' },
        },
      ],
    })
    const loadExternalParts = vi.fn(async () => { throw new Error('permission denied') })
    const onMissing = vi.fn()
    const out = await resolveAssemblyParts({
      content,
      loadParts: async () => [],
      loadExternalParts,
      onMissing,
    })
    expect(out).toEqual([])
    // The resolver surfaces the failure as onMissing so the UI can warn.
    expect(onMissing).toHaveBeenCalledOnce()
  })

  it('mixes external + local components in one assembly', async () => {
    const content = JSON.stringify({
      components: [
        {
          id: 'pcb',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: { project_id: 'p', file_id: 'f', kind: 'board_3d', pin: 'tracking_latest' },
        },
        {
          id: 'screw',
          file_id: 'local-1',
          object_id: 'cap',
          transform: identityMatrix(),
        },
      ],
    })
    const loadParts = vi.fn(async (fileId) => {
      expect(fileId).toBe('local-1')
      return [{ id: 'cap', geom: { tag: 'cap' } }]
    })
    const loadExternalParts = vi.fn(async () => [{ id: '__board__', geom: { tag: 'b' } }])
    const out = await resolveAssemblyParts({ content, loadParts, loadExternalParts })
    expect(loadParts).toHaveBeenCalledOnce()
    expect(loadExternalParts).toHaveBeenCalledOnce()
    expect(out).toHaveLength(2)
    // The local component with a single matching object_id collapses to the
    // bare componentId (existing single-object behaviour). The external
    // component re-stitches as componentId/origId.
    const ids = out.map((p) => p.id).sort()
    expect(ids).toEqual(['pcb/__board__', 'screw'])
  })
})

describe('restampExternalRefSeen — acknowledge "out of date" chip', () => {
  function rowsFixture() {
    return [
      {
        id: 'pcb',
        file_id: '',
        object_id: '',
        external_ref: {
          project_id: 'p1', file_id: 'f1', kind: 'board_3d', pin: 'tracking_latest',
          last_seen_updated_at: '2026-04-01T00:00:00Z',
        },
      },
      {
        id: 'screw',
        file_id: 'local-1',
        object_id: 'cap',
        external_ref: null,
      },
    ]
  }

  it('updates the matching ref last_seen_updated_at to the new value', () => {
    const rows = rowsFixture()
    const next = restampExternalRefSeen(rows, 'pcb', '2026-05-08T12:00:00Z')
    expect(next[0].external_ref.last_seen_updated_at).toBe('2026-05-08T12:00:00Z')
  })

  it('returns a new array; does not mutate input', () => {
    const rows = rowsFixture()
    const before = JSON.stringify(rows)
    const next = restampExternalRefSeen(rows, 'pcb', '2026-05-08T12:00:00Z')
    expect(next).not.toBe(rows)
    expect(JSON.stringify(rows)).toBe(before)
  })

  it('is a no-op for an unknown refId (returns input unchanged)', () => {
    const rows = rowsFixture()
    const next = restampExternalRefSeen(rows, 'nope', '2026-05-08T12:00:00Z')
    expect(next).toBe(rows)
  })

  it('preserves all other ref fields (project_id, file_id, kind, pin)', () => {
    const rows = rowsFixture()
    const next = restampExternalRefSeen(rows, 'pcb', '2026-05-08T12:00:00Z')
    expect(next[0].external_ref).toEqual({
      project_id: 'p1',
      file_id: 'f1',
      kind: 'board_3d',
      pin: 'tracking_latest',
      last_seen_updated_at: '2026-05-08T12:00:00Z',
    })
    // Sibling row untouched.
    expect(next[1]).toBe(rows[1])
  })

  it('round-trips through parseAssembly/serializeAssembly after a restamp', () => {
    const original = {
      components: [
        {
          id: 'pcb',
          file_id: '',
          object_id: '',
          transform: identityMatrix(),
          external_ref: {
            project_id: 'p1', file_id: 'f1', kind: 'board_3d', pin: 'tracking_latest',
            last_seen_updated_at: '2026-04-01T00:00:00Z',
          },
        },
      ],
    }
    const text = serializeAssembly(original)
    const parsed = parseAssembly(text)
    const stamped = restampExternalRefSeen(
      parsed.components,
      'pcb',
      '2026-05-08T12:00:00Z',
    )
    const reText = serializeAssembly({ components: stamped })
    const reParsed = parseAssembly(reText)
    expect(reParsed.components[0].external_ref.last_seen_updated_at)
      .toBe('2026-05-08T12:00:00Z')
    expect(reParsed.components[0].external_ref.project_id).toBe('p1')
    expect(reParsed.components[0].external_ref.kind).toBe('board_3d')
  })
})

describe('loadExternalParts — derived-artifacts cache lookup (ROADMAP row 67)', () => {
  // The lookup-first wrapper returns the decoded payload on a cache hit and
  // falls through to `recompile(ref)` on miss / 501 / decoder failure /
  // network error. The recompile path is the source of truth.

  const REF = { project_id: 'pid-1', file_id: 'fid-1', kind: 'board_3d', pin: 'tracking_latest' }

  it('maps ref.kind onto the backend derived_kind vocab (board_3d / board_outline_2d / mesh)', () => {
    // Standalone helper assertion — the rest of the integration is covered by
    // the wrapper tests below, but pinning every kind here documents the table.
    expect(derivedKindForRefKind('board_3d')).toBe('circuit_board_3d')
    expect(derivedKindForRefKind('board_outline_2d')).toBe('sketch_geom2')
    expect(derivedKindForRefKind('mesh')).toBe('jscad_mesh')
    expect(derivedKindForRefKind('rocket-fuel')).toBeNull()
    expect(derivedKindForRefKind(null)).toBeNull()
  })

  it('cache hit short-circuits the recompile and returns decoded payload', async () => {
    const cachedParts = [{ id: '__board__', geom: { tag: 'cached' } }]
    const lookup = vi.fn(async ({ projectId, fileId, derivedKind }) => {
      // Caller forwards the ref's project/file ids and the mapped derivedKind.
      expect(projectId).toBe('pid-1')
      expect(fileId).toBe('fid-1')
      expect(derivedKind).toBe('circuit_board_3d')
      return { cached: true, derivedKind, payload: new Uint8Array([1, 2, 3]) }
    })
    const decodePayload = vi.fn(async (kind, payload) => {
      expect(kind).toBe('circuit_board_3d')
      expect(payload).toBeInstanceOf(Uint8Array)
      return cachedParts
    })
    const recompile = vi.fn(async () => { throw new Error('should not be called') })
    const out = await loadExternalParts({ ref: REF, recompile, lookup, decodePayload })
    expect(out).toBe(cachedParts)
    expect(lookup).toHaveBeenCalledOnce()
    expect(decodePayload).toHaveBeenCalledOnce()
    expect(recompile).not.toHaveBeenCalled()
  })

  it('cache miss (cached:false / 501) falls through to recompile', async () => {
    const recompiled = [{ id: '__fresh__', geom: { tag: 'fresh' } }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null, error: 'compile-on-demand-not-yet-wired' }))
    const decodePayload = vi.fn()
    const recompile = vi.fn(async (ref) => {
      expect(ref).toBe(REF)
      return recompiled
    })
    const out = await loadExternalParts({ ref: REF, recompile, lookup, decodePayload })
    expect(out).toBe(recompiled)
    expect(decodePayload).not.toHaveBeenCalled()
    expect(recompile).toHaveBeenCalledOnce()
  })

  it('lookup throw is swallowed and falls through to recompile (no surfaced error)', async () => {
    const recompiled = [{ id: 'x', geom: {} }]
    const lookup = vi.fn(async () => { throw new Error('network down') })
    const recompile = vi.fn(async () => recompiled)
    // Must not reject — the recompile path is the source of truth.
    const out = await loadExternalParts({ ref: REF, recompile, lookup })
    expect(out).toBe(recompiled)
    expect(recompile).toHaveBeenCalledOnce()
  })

  it('decoder throw falls through to recompile (cache treated as opaque hint)', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: true, derivedKind: 'circuit_board_3d', payload: new Uint8Array([0]) }))
    const decodePayload = vi.fn(() => { throw new Error('bad bytes') })
    const recompile = vi.fn(async () => recompiled)
    const out = await loadExternalParts({ ref: REF, recompile, lookup, decodePayload })
    expect(out).toBe(recompiled)
    expect(decodePayload).toHaveBeenCalledOnce()
    expect(recompile).toHaveBeenCalledOnce()
  })

  it('skips the cache entirely for unmapped ref.kind (no lookup call) and falls through', async () => {
    const recompiled = [{ id: 'q', geom: {} }]
    const lookup = vi.fn()
    const recompile = vi.fn(async () => recompiled)
    const out = await loadExternalParts({
      ref: { ...REF, kind: 'rocket-fuel' },
      recompile,
      lookup,
    })
    expect(out).toBe(recompiled)
    expect(lookup).not.toHaveBeenCalled()
    expect(recompile).toHaveBeenCalledOnce()
  })
})

describe('loadExternalParts — write-back populate (ROADMAP row 67 Phase 2)', () => {
  // After a successful recompile, the loader fire-and-forgets a store() call
  // so the next consumer skips the recompile. Strict best-effort: failures
  // never block or alter the returned parts.

  const REF = { project_id: 'pid-1', file_id: 'fid-1', kind: 'board_3d', pin: 'tracking_latest' }
  // Helper: wait long enough for a microtask-scheduled fire-and-forget to run.
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

  it('populates the cache after recompile when encodePayload returns bytes', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null }))
    const recompile = vi.fn(async () => recompiled)
    const encoded = new Uint8Array([7, 7, 7])
    const encodePayload = vi.fn(async (kind, parts) => {
      expect(kind).toBe('circuit_board_3d')
      expect(parts).toBe(recompiled)
      return encoded
    })
    const store = vi.fn(async ({ projectId, fileId, derivedKind, payload }) => {
      expect(projectId).toBe('pid-1')
      expect(fileId).toBe('fid-1')
      expect(derivedKind).toBe('circuit_board_3d')
      expect(payload).toBe(encoded)
      return { stored: true, payloadSize: encoded.length }
    })
    const out = await loadExternalParts({
      ref: REF, recompile, lookup, encodePayload, store,
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(encodePayload).toHaveBeenCalledOnce()
    expect(store).toHaveBeenCalledOnce()
  })

  it('skips the populate when encodePayload returns null', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null }))
    const recompile = vi.fn(async () => recompiled)
    const encodePayload = vi.fn(async () => null)
    const store = vi.fn(async () => ({ stored: true, payloadSize: 0 }))
    const out = await loadExternalParts({
      ref: REF, recompile, lookup, encodePayload, store,
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(encodePayload).toHaveBeenCalledOnce()
    expect(store).not.toHaveBeenCalled()
  })

  it('store throw is swallowed (fire-and-forget) — return value stays correct', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null }))
    const recompile = vi.fn(async () => recompiled)
    const encodePayload = vi.fn(async () => new Uint8Array([1]))
    const store = vi.fn(async () => { throw new Error('5xx from server') })
    // Caller must not see the rejection — neither as a thrown error nor as
    // an altered return value.
    const out = await loadExternalParts({
      ref: REF, recompile, lookup, encodePayload, store,
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(store).toHaveBeenCalledOnce()
  })

  it('encode throw is also swallowed; store is never called', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null }))
    const recompile = vi.fn(async () => recompiled)
    const encodePayload = vi.fn(() => { throw new Error('encoder crashed') })
    const store = vi.fn()
    const out = await loadExternalParts({
      ref: REF, recompile, lookup, encodePayload, store,
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(encodePayload).toHaveBeenCalledOnce()
    expect(store).not.toHaveBeenCalled()
  })

  it('skips the populate entirely when encodePayload is absent', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const lookup = vi.fn(async () => ({ cached: false, derivedKind: 'circuit_board_3d', payload: null }))
    const recompile = vi.fn(async () => recompiled)
    const store = vi.fn()
    const out = await loadExternalParts({
      ref: REF, recompile, lookup, store, // no encodePayload
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(store).not.toHaveBeenCalled()
  })

  it('skips the populate when ref.kind is unmapped (no derivedKind, no encode call)', async () => {
    const recompiled = [{ id: 'r', geom: {} }]
    const recompile = vi.fn(async () => recompiled)
    const encodePayload = vi.fn(async () => new Uint8Array([1]))
    const store = vi.fn()
    const out = await loadExternalParts({
      ref: { ...REF, kind: 'rocket-fuel' },
      recompile,
      lookup: vi.fn(),
      encodePayload,
      store,
    })
    expect(out).toBe(recompiled)
    await flush()
    expect(encodePayload).not.toHaveBeenCalled()
    expect(store).not.toHaveBeenCalled()
  })
})

describe('mates — schema-only round-trip (ROADMAP row 49)', () => {
  // Shape-only slice: JSON round-trips through parse/serialize, no solver runs.
  // The eventual SolveSpace subprocess writes/reads against this same shape.

  const COMP_A = '11111111-1111-1111-1111-111111111111'
  const COMP_B = '22222222-2222-2222-2222-222222222222'

  const buildJson = (mates) => JSON.stringify({
    components: [
      { id: 'a', file_id: 'fa', object_id: 'oa', transform: identityMatrix() },
      { id: 'b', file_id: 'fb', object_id: 'ob', transform: identityMatrix() },
    ],
    mates,
  })

  it('parses all 7 mate types and round-trips through serialize → parse', () => {
    const all = [
      { id: 'm-1', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' } },
      { id: 'm-2', type: 'concentric', a: { component_id: COMP_A, feature: 'edge', feature_id: 'e-1' }, b: { component_id: COMP_B, feature: 'edge', feature_id: 'e-2' } },
      { id: 'm-3', type: 'parallel', a: { component_id: COMP_A, feature: 'axis', feature_id: 'x-1' }, b: { component_id: COMP_B, feature: 'axis', feature_id: 'x-2' } },
      { id: 'm-4', type: 'perpendicular', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-3' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-4' } },
      { id: 'm-5', type: 'distance', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-5' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-6' }, value: 25 },
      { id: 'm-6', type: 'angle', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-7' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-8' }, value: 90 },
      { id: 'm-7', type: 'tangent', a: { component_id: COMP_A, feature: 'edge', feature_id: 'e-3' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-9' } },
    ]
    const parsed = parseAssembly(buildJson(all))
    expect(parsed.mates).toHaveLength(7)
    expect(parsed.mates.map((m) => m.type)).toEqual([
      'coincident', 'concentric', 'parallel', 'perpendicular', 'distance', 'angle', 'tangent',
    ])
    // Dimensional mates carry numeric value; non-dimensional are null.
    expect(parsed.mates[4].value).toBe(25)
    expect(parsed.mates[5].value).toBe(90)
    expect(parsed.mates[0].value).toBeNull()
    // Round-trip: serialize → parse preserves every field.
    const reParsed = parseAssembly(serializeAssembly(parsed))
    expect(reParsed.mates).toEqual(parsed.mates)
  })

  it('omits the mates field when empty (back-compat with pre-mates files)', () => {
    const text = serializeAssembly({
      components: [{ id: 'a', file_id: 'fa', object_id: 'oa', transform: identityMatrix() }],
      mates: [],
    })
    const doc = JSON.parse(text)
    expect(doc.mates).toBeUndefined()
    // Absent-field round-trip yields an empty mates array on parse.
    expect(parseAssembly(text).mates).toEqual([])
  })

  it('drops malformed mates: missing type, unknown type, bad feature, missing a/b', () => {
    const malformed = [
      // missing type
      { id: 'bad-1', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' } },
      // unknown type
      { id: 'bad-2', type: 'glue', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' } },
      // bad feature
      { id: 'bad-3', type: 'coincident', a: { component_id: COMP_A, feature: 'plane', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' } },
      // missing b
      { id: 'bad-4', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' } },
      // valid — should survive
      { id: 'ok', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' } },
    ]
    const parsed = parseAssembly(buildJson(malformed))
    expect(parsed.mates).toHaveLength(1)
    expect(parsed.mates[0].id).toBe('ok')
  })

  it('coerces dimensional value; non-dimensional gets null even if value supplied', () => {
    const mates = [
      { id: 'd', type: 'distance', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' }, value: '12.5' },
      { id: 'c', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' }, value: 999 },
    ]
    const parsed = parseAssembly(buildJson(mates))
    expect(parsed.mates[0].value).toBe(12.5)
    expect(parsed.mates[1].value).toBeNull()
  })

  it('addMate appends a valid mate; rejects malformed and is immutable', () => {
    const rows = [
      { id: 'm-1', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' }, value: null },
    ]
    const before = JSON.stringify(rows)
    const next = addMate(rows, {
      id: 'm-2', type: 'distance',
      a: { component_id: COMP_A, feature: 'face', feature_id: 'f-3' },
      b: { component_id: COMP_B, feature: 'face', feature_id: 'f-4' },
      value: 10,
    })
    expect(next).not.toBe(rows)
    expect(JSON.stringify(rows)).toBe(before) // input untouched
    expect(next).toHaveLength(2)
    expect(next[1].id).toBe('m-2')
    expect(next[1].value).toBe(10)
    // Malformed mate → returns a fresh copy with no append.
    const noop = addMate(rows, { type: 'glue' })
    expect(noop).not.toBe(rows)
    expect(noop).toHaveLength(1)
  })

  it('removeMate filters by id and returns a new array', () => {
    const rows = [
      { id: 'm-1', type: 'coincident', a: { component_id: COMP_A, feature: 'face', feature_id: 'f-1' }, b: { component_id: COMP_B, feature: 'face', feature_id: 'f-2' }, value: null },
      { id: 'm-2', type: 'parallel', a: { component_id: COMP_A, feature: 'axis', feature_id: 'x-1' }, b: { component_id: COMP_B, feature: 'axis', feature_id: 'x-2' }, value: null },
    ]
    const next = removeMate(rows, 'm-1')
    expect(next).not.toBe(rows)
    expect(rows).toHaveLength(2)
    expect(next).toHaveLength(1)
    expect(next[0].id).toBe('m-2')
    // Unknown id → returns new array containing all rows.
    const same = removeMate(rows, 'nope')
    expect(same).toHaveLength(2)
  })
})

describe('mateRefFromPick — viewport pick → mate ref (Phase 2 face picker)', () => {
  it('single-object component: partId is the componentId', () => {
    const ref = mateRefFromPick('body-1', 'face', 'face-3')
    expect(ref).toEqual({ component_id: 'body-1', feature: 'face', feature_id: 'face-3' })
  })

  it('multi-object component: strips the /origPartId suffix', () => {
    const ref = mateRefFromPick('assembly-cap/cap-body', 'face', 'face-0')
    expect(ref).toEqual({ component_id: 'assembly-cap', feature: 'face', feature_id: 'face-0' })
  })

  it('edge kind maps to "edge"', () => {
    const ref = mateRefFromPick('shaft', 'edge', 'edge-12')
    expect(ref).toEqual({ component_id: 'shaft', feature: 'edge', feature_id: 'edge-12' })
  })

  it('vertex kind maps to "vertex"', () => {
    const ref = mateRefFromPick('pin', 'vertex', 'vertex-2')
    expect(ref).toEqual({ component_id: 'pin', feature: 'vertex', feature_id: 'vertex-2' })
  })

  it('unsupported kinds and null inputs return null', () => {
    expect(mateRefFromPick('part', 'pushpull', 'face-1')).toBeNull()
    expect(mateRefFromPick('part', null, 'face-1')).toBeNull()
    expect(mateRefFromPick(null, 'face', 'face-1')).toBeNull()
    expect(mateRefFromPick('', 'face', 'face-1')).toBeNull()
    expect(mateRefFromPick('part', 'face', '')).toBeNull()
    expect(mateRefFromPick('part', 'face', null)).toBeNull()
  })

  it('addMate round-trip: pick result produces a valid parseable mate', () => {
    const ref = mateRefFromPick('comp-a', 'face', 'face-5')
    const refB = mateRefFromPick('comp-b', 'face', 'face-2')
    expect(ref).not.toBeNull()
    expect(refB).not.toBeNull()
    const next = addMate([], {
      type: 'coincident',
      a: ref,
      b: refB,
    })
    expect(next).toHaveLength(1)
    expect(next[0].a.component_id).toBe('comp-a')
    expect(next[0].b.component_id).toBe('comp-b')
    expect(next[0].a.feature).toBe('face')
  })
})
