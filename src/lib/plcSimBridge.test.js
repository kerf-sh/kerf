/**
 * plcSimBridge unit tests — T-224
 *
 * Uses vi.stubGlobal to replace the global `fetch` so no real HTTP calls
 * are made.  All tests are synchronous from the test runner's perspective.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { stepSim, loadFixture } from './plcSimBridge.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

function mockFetchNetworkError(message = 'Network error') {
  return vi.fn().mockRejectedValue(new Error(message))
}

const MINIMAL_PROGRAM = `
PROGRAM test
  VAR_OUTPUT
    q1 : BOOL;
  END_VAR
  q1 := TRUE;
END_PROGRAM
`.trim()

// ---------------------------------------------------------------------------
// stepSim — success path
// ---------------------------------------------------------------------------

describe('stepSim', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns normalised ok response on 200', async () => {
    const serverResponse = {
      ok: true,
      session_id: 'sess-abc',
      outputs: { q1: true },
      trace: [{ tick: 0, outputs: { q1: true }, inputs: {} }],
      last_state: { _tick: 1, q1: true },
      errors: [],
    }
    vi.stubGlobal('fetch', mockFetch(200, serverResponse))

    const result = await stepSim({ program: MINIMAL_PROGRAM })

    expect(result.ok).toBe(true)
    expect(result.status).toBe(200)
    expect(result.session_id).toBe('sess-abc')
    expect(result.outputs).toEqual({ q1: true })
    expect(result.trace).toHaveLength(1)
    expect(result.errors).toEqual([])
  })

  it('passes session_id in request body when provided', async () => {
    const serverResponse = {
      ok: true,
      session_id: 'my-sid',
      outputs: {},
      trace: [],
      last_state: {},
      errors: [],
    }
    const fetchMock = mockFetch(200, serverResponse)
    vi.stubGlobal('fetch', fetchMock)

    await stepSim({ program: MINIMAL_PROGRAM, session_id: 'my-sid' })

    const calledBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(calledBody.session_id).toBe('my-sid')
  })

  it('omits session_id from body when null', async () => {
    const fetchMock = mockFetch(200, {
      ok: true, session_id: 'new', outputs: {}, trace: [], last_state: {}, errors: [],
    })
    vi.stubGlobal('fetch', fetchMock)

    await stepSim({ program: MINIMAL_PROGRAM, session_id: null })

    const calledBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(calledBody.session_id).toBeUndefined()
  })

  // ---- 400 Bad Request ----
  it('returns ok=false with error message on 400', async () => {
    vi.stubGlobal('fetch', mockFetch(400, { detail: 'invalid program' }))

    const result = await stepSim({ program: '' })

    expect(result.ok).toBe(false)
    expect(result.status).toBe(400)
    expect(result.errors).toContain('invalid program')
    expect(result.outputs).toEqual({})
    expect(result.trace).toEqual([])
  })

  // ---- 422 Validation Error ----
  it('returns ok=false with error message on 422', async () => {
    vi.stubGlobal('fetch', mockFetch(422, { detail: 'program failed to parse' }))

    const result = await stepSim({ program: 'BAD SYNTAX !!!!' })

    expect(result.ok).toBe(false)
    expect(result.status).toBe(422)
    expect(result.errors[0]).toContain('program failed to parse')
  })

  // ---- 500 Server Error ----
  it('returns ok=false on 500', async () => {
    vi.stubGlobal('fetch', mockFetch(500, { detail: 'internal server error' }))

    const result = await stepSim({ program: MINIMAL_PROGRAM })

    expect(result.ok).toBe(false)
    expect(result.status).toBe(500)
    expect(result.errors.length).toBeGreaterThan(0)
  })

  // ---- Network error ----
  it('returns ok=false with error message on network error', async () => {
    vi.stubGlobal('fetch', mockFetchNetworkError('Failed to fetch'))

    const result = await stepSim({ program: MINIMAL_PROGRAM })

    expect(result.ok).toBe(false)
    expect(result.status).toBe(0)
    expect(result.errors).toContain('Failed to fetch')
    expect(result.outputs).toEqual({})
    expect(result.trace).toEqual([])
  })

  it('preserves session_id in error response when provided', async () => {
    vi.stubGlobal('fetch', mockFetchNetworkError('offline'))

    const result = await stepSim({ program: MINIMAL_PROGRAM, session_id: 'sid-42' })

    expect(result.session_id).toBe('sid-42')
  })
})

// ---------------------------------------------------------------------------
// loadFixture
// ---------------------------------------------------------------------------

describe('loadFixture', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns fixture data on 200', async () => {
    const fixtureData = {
      ok: true,
      name: 'blinker',
      program: 'PROGRAM blinker ...',
      inputs: [],
      description: 'Single coil that toggles every 5 ticks',
    }
    vi.stubGlobal('fetch', mockFetch(200, fixtureData))

    const result = await loadFixture('blinker')

    expect(result.ok).toBe(true)
    expect(result.name).toBe('blinker')
    expect(result.program).toBe('PROGRAM blinker ...')
    expect(result.errors).toEqual([])
  })

  it('sends the fixture name in the request body', async () => {
    const fetchMock = mockFetch(200, {
      ok: true, name: 'conveyor', program: '...', inputs: [], description: '',
    })
    vi.stubGlobal('fetch', fetchMock)

    await loadFixture('conveyor')

    const calledBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(calledBody.name).toBe('conveyor')
  })

  it('returns ok=false on 404 (unknown fixture)', async () => {
    vi.stubGlobal('fetch', mockFetch(404, { detail: "Unknown fixture 'bad_name'" }))

    const result = await loadFixture('bad_name')

    expect(result.ok).toBe(false)
    expect(result.status).toBe(404)
    expect(result.errors[0]).toMatch(/Unknown fixture/)
  })

  it('returns ok=false on network error', async () => {
    vi.stubGlobal('fetch', mockFetchNetworkError('Connection refused'))

    const result = await loadFixture('blinker')

    expect(result.ok).toBe(false)
    expect(result.errors).toContain('Connection refused')
    expect(result.program).toBe('')
  })
})
