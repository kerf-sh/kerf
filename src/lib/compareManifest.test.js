import { describe, it, expect, beforeEach, vi } from 'vitest'
import { fetchCompareManifest, _resetCompareManifestCache } from './compareManifest.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status, body) {
  const response = {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
}

function mockFetchError(msg = 'Network failure') {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error(msg)))
}

const VALID_MANIFEST = {
  version: 1,
  generatedAt: '2026-05-18T00:00:00.000Z',
  items: [
    {
      slug: 'fusion',
      competitor: 'Autodesk Fusion 360',
      category: 'cad-mechanical',
      left: 'kerf',
      right: 'fusion',
      hero_tagline: 'Cloud-connected mechanical CAD',
    },
  ],
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('compareManifest', () => {
  beforeEach(() => {
    _resetCompareManifestCache()
    vi.unstubAllGlobals()
  })

  it('returns manifest items on a 200 response', async () => {
    mockFetch(200, VALID_MANIFEST)
    const result = await fetchCompareManifest()
    expect(result.items).toHaveLength(1)
    expect(result.items[0].slug).toBe('fusion')
    expect(result.version).toBe(1)
  })

  it('normalises 404 to empty items array', async () => {
    mockFetch(404, null)
    const result = await fetchCompareManifest()
    expect(result.items).toEqual([])
    expect(result.version).toBe(1)
  })

  it('normalises non-ok status (e.g. 500) to empty items array', async () => {
    mockFetch(500, null)
    const result = await fetchCompareManifest()
    expect(result.items).toEqual([])
  })

  it('normalises network errors to empty items array', async () => {
    mockFetchError('Network failure')
    const result = await fetchCompareManifest()
    expect(result.items).toEqual([])
  })

  it('normalises unexpected JSON shape to empty items array', async () => {
    mockFetch(200, { unexpected: true })
    const result = await fetchCompareManifest()
    expect(result.items).toEqual([])
  })

  it('caches the result — fetch called only once even with multiple awaits', async () => {
    mockFetch(200, VALID_MANIFEST)
    await fetchCompareManifest()
    await fetchCompareManifest()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('cache is reset by _resetCompareManifestCache, triggering re-fetch', async () => {
    mockFetch(200, VALID_MANIFEST)
    await fetchCompareManifest()
    _resetCompareManifestCache()
    await fetchCompareManifest()
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
