/**
 * compareManifest.js — thin fetch wrapper for `public/compare-manifest.json`.
 *
 * Usage:
 *   import { fetchCompareManifest } from './compareManifest.js'
 *   const { items } = await fetchCompareManifest()
 *
 * Normalises errors:
 *   - HTTP 404  → { version: 1, items: [] }   (manifest not yet built)
 *   - Network / parse error → { version: 1, items: [] }  (safe fallback)
 *
 * The module-level singleton cache means the fetch is done at most once per
 * page load (hot-reload in dev resets the module, which is fine).
 */

const MANIFEST_URL = '/compare-manifest.json'

/** @type {{ version: number; items: CompareItem[] } | null} */
let _cache = null

/**
 * @typedef {{ version: number; items: CompareItem[] }} CompareManifest
 * @typedef {{
 *   slug: string;
 *   competitor: string;
 *   category: string;
 *   left: string;
 *   right: string;
 *   hero_tagline: string;
 * }} CompareItem
 */

const EMPTY_MANIFEST = { version: 1, items: [] }

/**
 * Fetch (or return cached) compare-manifest.json.
 * Always resolves — never rejects.
 *
 * @returns {Promise<CompareManifest>}
 */
export async function fetchCompareManifest() {
  if (_cache !== null) return _cache

  try {
    const res = await fetch(MANIFEST_URL)
    if (res.status === 404) {
      _cache = EMPTY_MANIFEST
      return _cache
    }
    if (!res.ok) {
      console.warn(`compareManifest: unexpected HTTP ${res.status} — falling back to empty`)
      _cache = EMPTY_MANIFEST
      return _cache
    }
    const json = await res.json()
    // Basic shape validation
    if (!json || typeof json !== 'object' || !Array.isArray(json.items)) {
      console.warn('compareManifest: unexpected shape — falling back to empty')
      _cache = EMPTY_MANIFEST
      return _cache
    }
    _cache = { version: json.version ?? 1, items: json.items }
    return _cache
  } catch (err) {
    console.warn('compareManifest: fetch/parse error —', err?.message ?? err)
    _cache = EMPTY_MANIFEST
    return _cache
  }
}

/**
 * Reset the module-level cache (useful in tests).
 */
export function _resetCompareManifestCache() {
  _cache = null
}
