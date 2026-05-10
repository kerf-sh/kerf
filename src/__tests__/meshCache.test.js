// meshCache.test.js — surface that doesn't require an IndexedDB shim.
//
// In vitest's node environment `indexedDB` is undefined, so every persistence
// call (get/put/prune) takes the documented graceful-disable path:
//   * get → null   * put → false   * prune → undefined
// This is the SAME path the production code takes when running in private
// browsing or some corporate-IT-managed browsers, and the call sites already
// branch on those return values, so locking it in here is meaningful.
//
// The hash helper (hashContent) is genuinely pure — it uses Web Crypto, which
// Node 18+ exposes globally — and it's the cache key generator. We exercise:
//   * deterministic SHA-256 across calls
//   * known-vector for "hello" (well-publicised)
//   * empty / null / number coerce to the empty-string digest
//   * different inputs → different digests
// Plus the namespaced re-export.

import { describe, it, expect } from 'vitest'
import {
  hashContent,
  get,
  put,
  prune,
  meshCache,
} from '../lib/meshCache.js'

const SHA256_EMPTY = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
const SHA256_HELLO = '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'

describe('hashContent', () => {
  it('returns a 64-char lowercase hex string for arbitrary input', async () => {
    const h = await hashContent('the quick brown fox')
    expect(h).toMatch(/^[0-9a-f]{64}$/)
  })

  it('matches the well-known SHA-256 of the empty string', async () => {
    expect(await hashContent('')).toBe(SHA256_EMPTY)
  })

  it('matches the well-known SHA-256 of "hello"', async () => {
    expect(await hashContent('hello')).toBe(SHA256_HELLO)
  })

  it('is deterministic — same input → same digest across calls', async () => {
    const a = await hashContent('export default function () { return [] }')
    const b = await hashContent('export default function () { return [] }')
    expect(a).toBe(b)
  })

  it('produces different digests for different inputs', async () => {
    const a = await hashContent('a')
    const b = await hashContent('b')
    expect(a).not.toBe(b)
  })

  it('treats null / undefined as the empty-string digest', async () => {
    expect(await hashContent(null)).toBe(SHA256_EMPTY)
    expect(await hashContent(undefined)).toBe(SHA256_EMPTY)
  })

  it('coerces non-string input via String()', async () => {
    // 42 → "42"; should match hashContent("42") exactly.
    const a = await hashContent(42)
    const b = await hashContent('42')
    expect(a).toBe(b)
  })
})

// ----- IndexedDB-disabled fallbacks ---------------------------------------
//
// Vitest's node env has no `indexedDB`, so `openDb()` resolves to null and
// every persistence call takes its safe-default branch.

describe('persistence calls when IndexedDB is unavailable', () => {
  it('get(key) resolves to null without throwing', async () => {
    expect(typeof globalThis.indexedDB).toBe('undefined')
    const v = await get('any-key')
    expect(v).toBeNull()
  })

  it('get("") resolves to null up-front (empty key short-circuit)', async () => {
    expect(await get('')).toBeNull()
  })

  it('put(key, parts) resolves to false without throwing', async () => {
    const ok = await put('k', [{ id: 'p', geom: { polygons: [] } }])
    expect(ok).toBe(false)
  })

  it('put("") resolves to false up-front (empty key short-circuit)', async () => {
    const ok = await put('', [])
    expect(ok).toBe(false)
  })

  it('prune() resolves silently without throwing', async () => {
    await expect(prune()).resolves.toBeUndefined()
  })

  it('prune(customMaxBytes) resolves silently without throwing', async () => {
    await expect(prune(1024)).resolves.toBeUndefined()
  })
})

// ----- Namespace export ---------------------------------------------------

describe('meshCache namespace re-export', () => {
  it('exposes the same functions as the named exports', () => {
    expect(meshCache.get).toBe(get)
    expect(meshCache.put).toBe(put)
    expect(meshCache.prune).toBe(prune)
    expect(meshCache.hashContent).toBe(hashContent)
  })

  it('namespaced hashContent produces the same digest as the named export', async () => {
    const a = await hashContent('xyz')
    const b = await meshCache.hashContent('xyz')
    expect(a).toBe(b)
  })
})
