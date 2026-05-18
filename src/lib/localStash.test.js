/**
 * localStash.test.js — Vitest unit tests for the IndexedDB L1 local stash.
 *
 * Uses fake-indexeddb to run entirely in Node without a real browser.
 * A fresh IDBFactory is injected per test so state never leaks between tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { IDBFactory } from 'fake-indexeddb'
import { stash, markFlushed, listDirty, reconcile, _resetForTest, _setIDBFactory } from './localStash.js'

beforeEach(() => {
  // Each test gets its own in-memory IDB database — no leakage.
  _resetForTest()
  _setIDBFactory(new IDBFactory())
})

// ── stash + listDirty round-trip ─────────────────────────────────────────────

describe('stash + listDirty', () => {
  it('stores an entry and returns it from listDirty', async () => {
    await stash('ws-1', 'src/main.ks', new Uint8Array([1, 2, 3]))
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
    expect(dirty[0].workspaceId).toBe('ws-1')
    expect(dirty[0].filePath).toBe('src/main.ks')
    expect(dirty[0].bytes).toEqual(new Uint8Array([1, 2, 3]))
  })

  it('stores multiple entries across different files', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'b.ks', new Uint8Array([2]))
    const dirty = await listDirty()
    expect(dirty).toHaveLength(2)
  })

  it('overwrites an existing entry when stashed again', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'a.ks', new Uint8Array([99]))
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
    expect(dirty[0].bytes).toEqual(new Uint8Array([99]))
  })

  it('returns no entries when the stash is empty', async () => {
    const dirty = await listDirty()
    expect(dirty).toHaveLength(0)
  })
})

// ── markFlushed ───────────────────────────────────────────────────────────────

describe('markFlushed', () => {
  it('flips flushedToL2 so the entry no longer appears in listDirty', async () => {
    await stash('ws-1', 'main.ks', new Uint8Array([1]))
    await markFlushed('ws-1', 'main.ks')
    const dirty = await listDirty()
    expect(dirty).toHaveLength(0)
  })

  it('is a no-op for a key that does not exist', async () => {
    // Should not throw.
    await expect(markFlushed('ws-1', 'ghost.ks')).resolves.toBeUndefined()
  })

  it('only flushes the specified file, leaving others dirty', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'b.ks', new Uint8Array([2]))
    await markFlushed('ws-1', 'a.ks')
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
    expect(dirty[0].filePath).toBe('b.ks')
  })
})

// ── reconcile ─────────────────────────────────────────────────────────────────

describe('reconcile', () => {
  it('calls sendToServer for each dirty entry in the workspace', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'b.ks', new Uint8Array([2]))
    const sendToServer = vi.fn().mockResolvedValue(undefined)
    await reconcile('ws-1', sendToServer)
    expect(sendToServer).toHaveBeenCalledTimes(2)
    const paths = sendToServer.mock.calls.map((c) => c[0]).sort()
    expect(paths).toEqual(['a.ks', 'b.ks'])
  })

  it('marks entries flushed on success', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    const sendToServer = vi.fn().mockResolvedValue(undefined)
    await reconcile('ws-1', sendToServer)
    const dirty = await listDirty()
    expect(dirty).toHaveLength(0)
  })

  it('does NOT mark flushed when sendToServer throws (caller retries)', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    const sendToServer = vi.fn().mockRejectedValue(new Error('network error'))
    await reconcile('ws-1', sendToServer)
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
  })

  it('partially flushes: success entries marked, failed entries stay dirty', async () => {
    await stash('ws-1', 'ok.ks', new Uint8Array([1]))
    await stash('ws-1', 'fail.ks', new Uint8Array([2]))
    const sendToServer = vi.fn().mockImplementation(async (filePath) => {
      if (filePath === 'fail.ks') throw new Error('network error')
    })
    await reconcile('ws-1', sendToServer)
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
    expect(dirty[0].filePath).toBe('fail.ks')
  })

  it('only reconciles the given workspaceId, not other workspaces', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-2', 'b.ks', new Uint8Array([2]))
    const sendToServer = vi.fn().mockResolvedValue(undefined)
    await reconcile('ws-1', sendToServer)
    // ws-2's entry must remain dirty.
    const dirty = await listDirty()
    expect(dirty).toHaveLength(1)
    expect(dirty[0].workspaceId).toBe('ws-2')
  })

  it('is idempotent: reconciling twice has no side-effects', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    const sendToServer = vi.fn().mockResolvedValue(undefined)
    await reconcile('ws-1', sendToServer)
    await reconcile('ws-1', sendToServer)
    // Second call finds nothing dirty.
    expect(sendToServer).toHaveBeenCalledTimes(1)
  })
})
