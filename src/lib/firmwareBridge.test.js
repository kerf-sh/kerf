/**
 * firmwareBridge.test.js — vitest unit tests for firmwareBridge.js
 *
 * All tests are hermetic: fetch is mocked via vi.stubGlobal so no network
 * calls are made.  The key invariant tested is that normalise() always returns
 * { ok, status, errors } regardless of what the server sends.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { normalise, buildFirmware, uploadFirmware, monitorFirmware } from './firmwareBridge.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeFetchMock(body, { ok = true, status = 200 } = {}) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
}

function makeFetchError(message = 'Network failure') {
  return vi.fn().mockRejectedValue(new Error(message))
}

function makeParseError() {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.reject(new Error('invalid json')),
  })
}

// ---------------------------------------------------------------------------
// normalise() unit tests
// ---------------------------------------------------------------------------

describe('normalise', () => {
  it('returns ok:true when body.ok is true', () => {
    const result = normalise({}, { ok: true, status: 'success', errors: [] })
    expect(result.ok).toBe(true)
    expect(result.status).toBe('success')
    expect(result.errors).toEqual([])
  })

  it('returns ok:false when body.ok is false', () => {
    const result = normalise({}, { ok: false, status: 'error', errors: ['oops'] })
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
    expect(result.errors).toEqual(['oops'])
  })

  it('maps pending status correctly', () => {
    const result = normalise({}, {
      ok: false,
      status: 'pending',
      errors: ['No compiler found.'],
    })
    expect(result.ok).toBe(false)
    expect(result.status).toBe('pending')
    expect(result.errors[0]).toMatch(/compiler/i)
  })

  it('returns error shape when body is null', () => {
    const result = normalise(null, null, 'Network error: timeout')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
    expect(result.errors).toEqual(['Network error: timeout'])
  })

  it('defaults errors to [] when body.errors is missing', () => {
    const result = normalise({}, { ok: true, status: 'success' })
    expect(result.errors).toEqual([])
  })

  it('defaults errors to [] when body.errors is not an array', () => {
    const result = normalise({}, { ok: false, status: 'error', errors: 'oops' })
    expect(result.errors).toEqual([])
  })

  it('merges extra body fields into the result', () => {
    const result = normalise({}, {
      ok: true,
      status: 'success',
      errors: [],
      hex_path: '/tmp/sketch.hex',
      warnings: ['deprecated'],
    })
    expect(result.hex_path).toBe('/tmp/sketch.hex')
    expect(result.warnings).toEqual(['deprecated'])
  })

  it('infers status from ok when body.status is absent', () => {
    const success = normalise({}, { ok: true, errors: [] })
    expect(success.status).toBe('success')
    const failure = normalise({}, { ok: false, errors: ['x'] })
    expect(failure.status).toBe('error')
  })
})

// ---------------------------------------------------------------------------
// buildFirmware()
// ---------------------------------------------------------------------------

describe('buildFirmware', () => {
  beforeEach(() => { vi.unstubAllGlobals() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('posts to /api/firmware/build and returns normalised result on success', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: true,
      status: 'success',
      hex_path: '/tmp/sketch.hex',
      errors: [],
      warnings: [],
    }))
    const result = await buildFirmware('/tmp/mysketch')
    expect(result.ok).toBe(true)
    expect(result.status).toBe('success')
    expect(result.hex_path).toBe('/tmp/sketch.hex')
    expect(result.errors).toEqual([])
  })

  it('returns pending when no compiler is available', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: false,
      status: 'pending',
      hex_path: null,
      errors: ['No compiler found. Install arduino-cli.'],
      warnings: [],
    }))
    const result = await buildFirmware('/tmp/mysketch')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('pending')
    expect(result.errors.length).toBeGreaterThan(0)
  })

  it('returns error shape on network failure', async () => {
    vi.stubGlobal('fetch', makeFetchError('Network failure'))
    const result = await buildFirmware('/tmp/mysketch')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
    expect(result.errors[0]).toMatch(/Network error/i)
  })

  it('returns error shape on JSON parse failure', async () => {
    vi.stubGlobal('fetch', makeParseError())
    const result = await buildFirmware('/tmp/mysketch')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
  })

  it('sends source_path and fw_config in the request body', async () => {
    const mockFetch = makeFetchMock({ ok: true, status: 'success', errors: [] })
    vi.stubGlobal('fetch', mockFetch)
    await buildFirmware('/tmp/sketch', { board: { fqbn: 'arduino:avr:uno' } })
    const [_url, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body.source_path).toBe('/tmp/sketch')
    expect(body.fw_config.board.fqbn).toBe('arduino:avr:uno')
  })
})

// ---------------------------------------------------------------------------
// uploadFirmware()
// ---------------------------------------------------------------------------

describe('uploadFirmware', () => {
  beforeEach(() => { vi.unstubAllGlobals() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('posts to /api/firmware/upload and returns normalised result on success', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: true,
      status: 'success',
      port: '/dev/ttyUSB0',
      errors: [],
    }))
    const result = await uploadFirmware('/tmp/sketch.hex')
    expect(result.ok).toBe(true)
    expect(result.status).toBe('success')
    expect(result.port).toBe('/dev/ttyUSB0')
  })

  it('returns pending when no port is found', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: false,
      status: 'pending',
      port: null,
      errors: ['No serial port found.'],
    }))
    const result = await uploadFirmware('/tmp/sketch.hex')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('pending')
  })

  it('sends hex_path, fw_config, and port in the request body', async () => {
    const mockFetch = makeFetchMock({ ok: true, status: 'success', errors: [] })
    vi.stubGlobal('fetch', mockFetch)
    await uploadFirmware('/tmp/sketch.hex', null, '/dev/ttyACM0')
    const [_url, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body.hex_path).toBe('/tmp/sketch.hex')
    expect(body.port).toBe('/dev/ttyACM0')
  })

  it('returns error shape on network failure', async () => {
    vi.stubGlobal('fetch', makeFetchError('timeout'))
    const result = await uploadFirmware('/tmp/sketch.hex')
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
  })
})

// ---------------------------------------------------------------------------
// monitorFirmware()
// ---------------------------------------------------------------------------

describe('monitorFirmware', () => {
  beforeEach(() => { vi.unstubAllGlobals() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('posts to /api/firmware/monitor and returns lines on success', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: true,
      status: 'success',
      port: '/dev/ttyUSB0',
      lines: ['Hello from board', 'Temp: 23.5C'],
      errors: [],
    }))
    const result = await monitorFirmware()
    expect(result.ok).toBe(true)
    expect(result.lines).toEqual(['Hello from board', 'Temp: 23.5C'])
  })

  it('returns pending when no port is available', async () => {
    vi.stubGlobal('fetch', makeFetchMock({
      ok: false,
      status: 'pending',
      port: null,
      lines: [],
      errors: ['No serial port found.'],
    }))
    const result = await monitorFirmware()
    expect(result.ok).toBe(false)
    expect(result.status).toBe('pending')
  })

  it('sends fw_config, port, and baud in the request body', async () => {
    const mockFetch = makeFetchMock({ ok: true, status: 'success', lines: [], errors: [] })
    vi.stubGlobal('fetch', mockFetch)
    await monitorFirmware({ monitor: { baud: 115200 } }, '/dev/ttyACM0', 115200)
    const [_url, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body.baud).toBe(115200)
    expect(body.port).toBe('/dev/ttyACM0')
  })

  it('returns error shape on network failure', async () => {
    vi.stubGlobal('fetch', makeFetchError('connection reset'))
    const result = await monitorFirmware()
    expect(result.ok).toBe(false)
    expect(result.status).toBe('error')
  })
})
