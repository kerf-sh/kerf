/**
 * dirtyStore.js — Zustand store that exposes a live count of L1 dirty entries.
 *
 * Exported hooks
 * --------------
 * useDirtyL1Count()   — React hook: returns the number of entries in IndexedDB
 *                        with flushedToL2 === false. Updates reactively whenever
 *                        localStash writes or flushes.
 *
 * The store registers a listener with localStash._addListener so it stays in
 * sync with every stash/markFlushed call without polling.
 */

import { create } from 'zustand'
import { listDirty, _addListener } from '../lib/localStash.js'

const useDirtyStore = create((set) => ({
  count: 0,
  _setCount: (count) => set({ count }),
}))

// Register the listener once, at module load time. The listener refetches the
// full dirty list from IDB and updates the store count.
async function _syncCount() {
  try {
    const dirty = await listDirty()
    useDirtyStore.getState()._setCount(dirty.length)
  } catch {
    // IDB unavailable (e.g. private browsing with storage blocked) — stay at 0.
  }
}

_addListener(_syncCount)

// Also sync once on startup so the badge is accurate before any edits happen.
_syncCount()

/**
 * useDirtyL1Count — returns the count of unsynced L1 stash entries.
 * Safe to call in any React component; updates reactively.
 */
export function useDirtyL1Count() {
  return useDirtyStore((s) => s.count)
}

export { useDirtyStore }
