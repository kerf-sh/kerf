/**
 * localStash.js — IndexedDB-backed L1 local stash for the editor working copy.
 *
 * Object store: 'stash'
 * Key:   `${workspaceId}/${filePath}`
 * Value: { bytes, mtime, flushedToL2 }
 *
 * Exposed API
 * -----------
 * stash(workspaceId, filePath, bytes)          — write entry; caller debounces
 * markFlushed(workspaceId, filePath)           — flip flushedToL2 = true
 * listDirty()                                  — all entries with flushedToL2 === false
 * reconcile(workspaceId, sendToServer)         — flush dirty entries for a workspace;
 *                                                on per-entry success, calls markFlushed
 *
 * The Zustand selector useDirtyL1Count() lives in src/stores/dirtyStore.js
 * and is notified via the _notify helper exported below.
 */

const DB_NAME = 'kerf-l1-stash'
const DB_VERSION = 1
const STORE_NAME = 'stash'

let _db = null
// Allow tests to inject a custom IDBFactory (e.g. fake-indexeddb).
let _idbFactory = null

export function _setIDBFactory(factory) {
  _idbFactory = factory
}

function getIDBFactory() {
  return _idbFactory ?? globalThis.indexedDB
}

function openDB() {
  if (_db) return Promise.resolve(_db)
  return new Promise((resolve, reject) => {
    const req = getIDBFactory().open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME)
      }
    }
    req.onsuccess = (e) => {
      _db = e.target.result
      resolve(_db)
    }
    req.onerror = () => reject(req.error)
  })
}

function key(workspaceId, filePath) {
  return `${workspaceId}/${filePath}`
}

// Callbacks registered by the dirty store so it stays in sync.
const _listeners = new Set()

export function _addListener(fn) {
  _listeners.add(fn)
  return () => _listeners.delete(fn)
}

function _notify() {
  for (const fn of _listeners) fn()
}

/**
 * Write (or overwrite) a stash entry. The caller is responsible for debouncing.
 */
export async function stash(workspaceId, filePath, bytes) {
  const db = await openDB()
  const value = { bytes, mtime: Date.now(), flushedToL2: false }
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const req = tx.objectStore(STORE_NAME).put(value, key(workspaceId, filePath))
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
  _notify()
}

/**
 * Mark a specific entry as flushed to L2 (server file_revisions).
 */
export async function markFlushed(workspaceId, filePath) {
  const db = await openDB()
  const k = key(workspaceId, filePath)
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const getReq = store.get(k)
    getReq.onsuccess = () => {
      const existing = getReq.result
      if (!existing) {
        resolve()
        return
      }
      const putReq = store.put({ ...existing, flushedToL2: true }, k)
      putReq.onsuccess = () => resolve()
      putReq.onerror = () => reject(putReq.error)
    }
    getReq.onerror = () => reject(getReq.error)
  })
  _notify()
}

/**
 * Return all stash entries that have not yet been flushed to L2.
 * Returns an array of { workspaceId, filePath, bytes, mtime }.
 */
export async function listDirty() {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const results = []
    const req = store.openCursor()
    req.onsuccess = (e) => {
      const cursor = e.target.result
      if (!cursor) {
        resolve(results)
        return
      }
      const value = cursor.value
      if (value.flushedToL2 === false) {
        // Reverse the composite key to recover workspaceId + filePath.
        const k = cursor.key
        const slashIdx = k.indexOf('/')
        results.push({
          workspaceId: k.slice(0, slashIdx),
          filePath: k.slice(slashIdx + 1),
          bytes: value.bytes,
          mtime: value.mtime,
        })
      }
      cursor.continue()
    }
    req.onerror = () => reject(req.error)
  })
}

/**
 * Reconcile all dirty entries for a workspace against the server.
 *
 * @param {string}   workspaceId
 * @param {Function} sendToServer  async (filePath, bytes) => void — must throw on failure
 *
 * Entries for which sendToServer resolves successfully are marked flushed.
 * Entries for which sendToServer throws are left dirty (caller can retry).
 */
export async function reconcile(workspaceId, sendToServer) {
  const dirty = await listDirty()
  const mine = dirty.filter((e) => e.workspaceId === workspaceId)
  await Promise.allSettled(
    mine.map(async (entry) => {
      try {
        await sendToServer(entry.filePath, entry.bytes)
        await markFlushed(workspaceId, entry.filePath)
      } catch {
        // Leave dirty; caller retries.
      }
    }),
  )
}

// Reset the singleton DB reference (used by tests to get a clean state).
export function _resetForTest() {
  _db = null
}
