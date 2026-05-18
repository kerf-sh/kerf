/**
 * gdsLoader.test.js — Vitest suite for the parseGds fetch wrapper.
 *
 * All network I/O is mocked with vi.fn(); no real server required.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const GOOD_LAYOUT = {
  cells: [
    {
      name: 'TOP',
      shapes: [
        { kind: 'box', layer: 68, datatype: 20, x: 0, y: 0, w: 1000, h: 500 },
      ],
    },
  ],
  layers: [{ layer: 68, datatype: 20 }],
  topCell: 'TOP',
  db_unit: 1e-9,
  user_unit: 1e-6,
}

function makeGoodResponse() {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => GOOD_LAYOUT,
  }
}

function makeErrorResponse(status, detail) {
  return {
    ok: false,
    status,
    statusText: 'Error',
    json: async () => ({ detail }),
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('parseGds', () => {
  let parseGds
  let fetchMock

  beforeEach(async () => {
    vi.resetModules()
    fetchMock = vi.fn()
    globalThis.fetch = fetchMock
    const mod = await import('./gdsLoader.js')
    parseGds = mod.parseGds
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete globalThis.fetch
  })

  it('POSTs to /api/silicon/gds/parse by default', async () => {
    fetchMock.mockResolvedValueOnce(makeGoodResponse())
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'application/octet-stream' })
    await parseGds(blob, { filename: 'test.gds' })
    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/silicon/gds/parse')
    expect(init.method).toBe('POST')
  })

  it('sends multipart FormData with the file', async () => {
    fetchMock.mockResolvedValueOnce(makeGoodResponse())
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'application/octet-stream' })
    await parseGds(blob, { filename: 'chip.gds' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBeInstanceOf(FormData)
  })

  it('returns layout JSON on 200', async () => {
    fetchMock.mockResolvedValueOnce(makeGoodResponse())
    const blob = new Blob([new Uint8Array([1])], { type: 'application/octet-stream' })
    const layout = await parseGds(blob, { filename: 'x.gds' })
    expect(layout).toEqual(GOOD_LAYOUT)
    expect(Array.isArray(layout.cells)).toBe(true)
    expect(layout.topCell).toBe('TOP')
  })

  it('allows a custom endpoint via opts.endpoint', async () => {
    fetchMock.mockResolvedValueOnce(makeGoodResponse())
    const blob = new Blob([new Uint8Array([1])], { type: 'application/octet-stream' })
    await parseGds(blob, { endpoint: 'http://localhost:9999/custom', filename: 'x.gds' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:9999/custom')
  })

  it('throws with status code on non-2xx responses', async () => {
    fetchMock.mockResolvedValueOnce(makeErrorResponse(422, 'Failed to parse GDS file: bad data'))
    const blob = new Blob([new Uint8Array([0])], { type: 'application/octet-stream' })
    await expect(parseGds(blob, { filename: 'bad.gds' })).rejects.toThrow('422')
  })

  it('throws a human-readable error when the server returns a detail string', async () => {
    fetchMock.mockResolvedValueOnce(makeErrorResponse(422, 'Uploaded file is empty'))
    const blob = new Blob([new Uint8Array([0])], { type: 'application/octet-stream' })
    await expect(parseGds(blob, { filename: 'empty.gds' })).rejects.toThrow('Uploaded file is empty')
  })

  it('throws on network error', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const blob = new Blob([new Uint8Array([1])], { type: 'application/octet-stream' })
    await expect(parseGds(blob, { filename: 'x.gds' })).rejects.toThrow('network')
  })

  it('throws when called with no file', async () => {
    await expect(parseGds(null)).rejects.toThrow('no file provided')
  })

  it('throws when response JSON is missing cells array', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ topCell: 'TOP' }),  // missing cells
    })
    const blob = new Blob([new Uint8Array([1])], { type: 'application/octet-stream' })
    await expect(parseGds(blob, { filename: 'x.gds' })).rejects.toThrow('"cells" array')
  })
})
