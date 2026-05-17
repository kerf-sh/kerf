import { create } from 'zustand'
import { buildIndex } from './searchIndex.js'
import { isInternalPlanning } from './groupTaxonomy.js'

// Single in-memory store for the docs corpus. The manifest is a static asset
// emitted by `scripts/build-docs-manifest.mjs` at build time, so we just fetch
// it once on mount, build the search index, and hold both for the rest of the
// session. The store is also the cache layer when the user navigates between
// articles — we don't refetch the manifest on /docs/:slug pages.

export const useDocs = create((set, get) => ({
  status: 'idle', // idle | loading | ready | error
  error: null,
  manifest: null, // raw manifest (flat or grouped — taxonomy helpers normalize)
  entries: [],    // flat, internal-planning entries already stripped
  bySlug: new Map(),
  byGroup: [],   // legacy by-manifest-group buckets (still consumed by search results)
  recent: [],    // top 5 by mtime, descending
  index: null,   // search index from buildIndex(entries)

  load: async () => {
    if (get().status === 'ready' || get().status === 'loading') return
    set({ status: 'loading', error: null })
    try {
      const res = await fetch('/docs-manifest.json', { cache: 'no-cache' })
      if (!res.ok) throw new Error(`manifest fetch failed: ${res.status}`)
      const manifest = await res.json()
      // Tolerate either { entries: [...] } (flat) or { groups: [{ items }] }
      // (grouped). We extract a flat entries[] for the legacy consumers
      // (search, recent, articles) and hand the raw manifest to the new
      // sidebar taxonomy code via the store.
      const flat = flattenManifest(manifest)
      const entries = flat.filter((e) => !isInternalPlanning(e))
      const bySlug = new Map(entries.map((e) => [e.slug, e]))
      const byGroup = groupEntries(entries)
      const recent = [...entries].sort((a, b) => b.mtime - a.mtime).slice(0, 5)
      const index = buildIndex(entries)
      set({ status: 'ready', manifest, entries, bySlug, byGroup, recent, index })
    } catch (e) {
      console.error('[docs] manifest load failed', e)
      set({ status: 'error', error: e.message })
    }
  },
}))

function flattenManifest(manifest) {
  if (!manifest) return []
  const out = []
  const seen = new Set()
  if (Array.isArray(manifest.groups)) {
    for (const g of manifest.groups) {
      for (const item of g.items || []) {
        if (!item || !item.slug || seen.has(item.slug)) continue
        seen.add(item.slug)
        out.push({ ...item, group: item.group || g.label })
      }
    }
  }
  if (Array.isArray(manifest.entries)) {
    for (const e of manifest.entries) {
      if (!e || !e.slug || seen.has(e.slug)) continue
      seen.add(e.slug)
      out.push(e)
    }
  }
  return out
}

// Sidebar group order. Anything outside this list falls to the bottom.
const GROUP_ORDER = [
  'Getting Started',
  'Modeling',
  'Electronics',
  'Library & BOM',
  'Workspaces',
  'API & Reference',
  'Roadmap',
  'Legal',
]

function groupEntries(entries) {
  const map = new Map()
  for (const e of entries) {
    let bucket = map.get(e.group)
    if (!bucket) { bucket = []; map.set(e.group, bucket) }
    bucket.push(e)
  }
  for (const items of map.values()) {
    items.sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
  }
  return GROUP_ORDER
    .filter((g) => map.has(g))
    .map((group) => ({ group, items: map.get(group) }))
    .concat(
      [...map.keys()]
        .filter((g) => !GROUP_ORDER.includes(g))
        .map((group) => ({ group, items: map.get(group) })),
    )
}
