// IndexedDB mesh cache (Phase 1, browser-only).
//
// Caches `runJscad()` output (parts) keyed by the SHA-256 of the JSCAD source.
// On editor open / re-eval we hash the source first; cache hit → set parts
// without spinning up the worker. Miss → run JSCAD, then store the result.
//
// Storage shape: each entry is `{key, parts, bytes, lastAccess}` where
// `parts` matches the runJscad output (`[{id, geom}]`). The geom is a JSCAD
// Geom3 (`{polygons: [{vertices: [[x,y,z], ...]}]}`) — same shape the worker
// posts back. The Renderer turns it into BufferGeometry on render. We do NOT
// cache BufferGeometry: it isn't structured-clone friendly across sessions
// and would require explicit (de)serialization.
//
// STEP files use their own SHA-256 cache in `stepLoader.js` and are skipped
// here.
//
// Pruning: best-effort LRU. On `prune(maxBytes)` we sum `bytes` across all
// entries and delete oldest-`lastAccess` rows until total ≤ maxBytes. Run on
// app start (cheap) and after every put when the rolling estimate looks high.

const DB_NAME = 'kerf-mesh-cache'
const DB_VERSION = 1
const STORE = 'parts'
const DEFAULT_MAX_BYTES = 100 * 1024 * 1024

let dbPromise = null

function isAvailable() {
  return typeof indexedDB !== 'undefined'
}

function openDb() {
  if (!isAvailable()) return Promise.resolve(null)
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve) => {
    let req
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION)
    } catch {
      resolve(null)
      return
    }
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        const os = db.createObjectStore(STORE, { keyPath: 'key' })
        os.createIndex('lastAccess', 'lastAccess')
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => resolve(null) // tolerate failure → cache disabled
    req.onblocked = () => resolve(null)
  })
  return dbPromise
}

// SHA-256 of a string → hex. Same digest the STEP loader uses on binary input;
// reusing the algorithm so cache keys are stable across reloads/sessions.
export async function hashContent(content) {
  const text = content == null ? '' : String(content)
  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.digest) {
    const enc = new TextEncoder().encode(text)
    const digest = await crypto.subtle.digest('SHA-256', enc)
    const bytes = new Uint8Array(digest)
    let hex = ''
    for (const b of bytes) hex += b.toString(16).padStart(2, '0')
    return hex
  }
  // Fallback (should never happen in modern browsers).
  return `len-${text.length}`
}

// Approximate byte count of a parts array. Walks polygons → vertices, charges
// 24 bytes per vec3 (3×Float64). Cheap heuristic; we only need it for LRU
// pruning, not exact accounting.
function estimateBytes(parts) {
  let total = 0
  for (const p of parts || []) {
    total += 64 // {id, geom: {...}}
    const polys = p?.geom?.polygons
    if (!Array.isArray(polys)) continue
    for (const poly of polys) {
      const n = poly?.vertices?.length || 0
      total += 32 + n * 24
    }
  }
  return total
}

function txStore(db, mode) {
  const tx = db.transaction(STORE, mode)
  return [tx, tx.objectStore(STORE)]
}

function awaitTx(tx) {
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(true)
    tx.onerror = () => resolve(false)
    tx.onabort = () => resolve(false)
  })
}

// Returns `{parts}` on hit, null on miss. Touches `lastAccess` so LRU pruning
// keeps recently-opened files alive.
export async function get(key) {
  if (!key) return null
  const db = await openDb()
  if (!db) return null
  return new Promise((resolve) => {
    let entry = null
    try {
      const [tx, store] = txStore(db, 'readwrite')
      const req = store.get(key)
      req.onsuccess = () => {
        entry = req.result || null
        if (entry) {
          entry.lastAccess = Date.now()
          try { store.put(entry) } catch { /* ignore */ }
        }
      }
      req.onerror = () => { entry = null }
      tx.oncomplete = () => resolve(entry ? { parts: entry.parts } : null)
      tx.onerror = () => resolve(null)
      tx.onabort = () => resolve(null)
    } catch {
      resolve(null)
    }
  })
}

export async function put(key, parts) {
  if (!key) return false
  const db = await openDb()
  if (!db) return false
  const bytes = estimateBytes(parts)
  return new Promise((resolve) => {
    try {
      const [tx, store] = txStore(db, 'readwrite')
      store.put({
        key,
        parts: parts || [],
        bytes,
        lastAccess: Date.now(),
      })
      awaitTx(tx).then(resolve)
    } catch {
      resolve(false)
    }
  })
}

// Best-effort LRU prune: walk all entries by lastAccess ascending and delete
// oldest until total bytes ≤ maxBytes. Tolerant of write failures (it's
// best-effort — next prune sweeps anything we missed).
export async function prune(maxBytes = DEFAULT_MAX_BYTES) {
  const db = await openDb()
  if (!db) return
  const entries = await new Promise((resolve) => {
    try {
      const [tx, store] = txStore(db, 'readonly')
      const out = []
      const req = store.openCursor()
      req.onsuccess = () => {
        const c = req.result
        if (!c) return
        out.push({ key: c.value.key, bytes: c.value.bytes || 0, lastAccess: c.value.lastAccess || 0 })
        c.continue()
      }
      req.onerror = () => { /* fall through */ }
      tx.oncomplete = () => resolve(out)
      tx.onerror = () => resolve(out)
      tx.onabort = () => resolve(out)
    } catch {
      resolve([])
    }
  })
  let total = entries.reduce((s, e) => s + e.bytes, 0)
  if (total <= maxBytes) return
  // Sort oldest first.
  entries.sort((a, b) => a.lastAccess - b.lastAccess)
  const toDelete = []
  for (const e of entries) {
    if (total <= maxBytes) break
    toDelete.push(e.key)
    total -= e.bytes
  }
  if (toDelete.length === 0) return
  await new Promise((resolve) => {
    try {
      const [tx, store] = txStore(db, 'readwrite')
      for (const k of toDelete) store.delete(k)
      awaitTx(tx).then(resolve)
    } catch {
      resolve(false)
    }
  })
}

// Convenience export grouping the public API. Some callers prefer the
// namespaced form (`meshCache.get(key)`).
export const meshCache = { get, put, prune, hashContent }
