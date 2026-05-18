/**
 * dirtyStore.test.js — Vitest unit tests for the Zustand dirty-count store.
 *
 * Uses fake-indexeddb to run without a real browser.
 * Tests confirm that useDirtyL1Count reflects stash writes and flushes.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { IDBFactory } from 'fake-indexeddb'
import { stash, markFlushed, _resetForTest, _setIDBFactory } from '../lib/localStash.js'
import { useDirtyStore } from './dirtyStore.js'

function getCount() {
  return useDirtyStore.getState().count
}

// Allow async listeners (IDB reads + Zustand set) to propagate.
function tick() {
  return new Promise((r) => setTimeout(r, 10))
}

beforeEach(async () => {
  // Fresh IDB + clear cached DB handle.
  _setIDBFactory(new IDBFactory())
  _resetForTest()
  // Reset Zustand count so tests start clean.
  useDirtyStore.setState({ count: 0 })
  // Let any pending async work settle.
  await tick()
})

describe('useDirtyL1Count via useDirtyStore', () => {
  it('starts at 0', () => {
    expect(getCount()).toBe(0)
  })

  it('increments when an entry is stashed', async () => {
    await stash('ws-1', 'main.ks', new Uint8Array([1]))
    await tick()
    expect(getCount()).toBe(1)
  })

  it('reflects multiple dirty entries', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'b.ks', new Uint8Array([2]))
    await tick()
    expect(getCount()).toBe(2)
  })

  it('decrements when an entry is marked flushed', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await tick()
    expect(getCount()).toBe(1)

    await markFlushed('ws-1', 'a.ks')
    await tick()
    expect(getCount()).toBe(0)
  })

  it('does not double-count when the same file is stashed twice', async () => {
    await stash('ws-1', 'a.ks', new Uint8Array([1]))
    await stash('ws-1', 'a.ks', new Uint8Array([2]))
    await tick()
    expect(getCount()).toBe(1)
  })
})
