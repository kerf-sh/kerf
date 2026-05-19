import { describe, it, expect, vi, beforeEach } from 'vitest'
import { tsiolkovsky, ceaLite, multiStageDeltaV } from './aeroPropulsionBridge.js'

// ---------------------------------------------------------------------------
// Mock globalThis.fetch so tests are hermetic (no real network calls)
// ---------------------------------------------------------------------------

function _mockFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

function _mockFetchError(message = 'Network error') {
  return vi.fn().mockRejectedValue(new Error(message))
}

beforeEach(() => {
  vi.restoreAllMocks()
})

// ===========================================================================
// tsiolkovsky
// ===========================================================================

describe('tsiolkovsky — input validation', () => {
  it('throws TypeError when params is not an object', async () => {
    await expect(tsiolkovsky(null)).rejects.toThrow(TypeError)
    await expect(tsiolkovsky(42)).rejects.toThrow(TypeError)
    await expect(tsiolkovsky('string')).rejects.toThrow(TypeError)
  })

  it('throws TypeError when isp_s is missing', async () => {
    await expect(tsiolkovsky({ m0_kg: 1000, mf_kg: 200 })).rejects.toThrow(TypeError)
  })

  it('throws TypeError when isp_s is NaN', async () => {
    await expect(tsiolkovsky({ isp_s: NaN, m0_kg: 1000, mf_kg: 200 })).rejects.toThrow(TypeError)
  })

  it('throws TypeError when m0_kg is Infinity', async () => {
    await expect(tsiolkovsky({ isp_s: 300, m0_kg: Infinity, mf_kg: 200 })).rejects.toThrow(TypeError)
  })

  it('throws TypeError when mf_kg is undefined', async () => {
    await expect(tsiolkovsky({ isp_s: 300, m0_kg: 1000 })).rejects.toThrow(TypeError)
  })
})

describe('tsiolkovsky — successful response', () => {
  it('returns ok:true body on HTTP 200', async () => {
    const mockBody = {
      ok: true,
      delta_v_m_s: 9200,
      delta_v_km_s: 9.2,
      mass_ratio: 9,
      exhaust_velocity_m_s: 4413,
      propellant_mass_kg: 9000,
      propellant_fraction: 0.9,
    }
    globalThis.fetch = _mockFetch(200, mockBody)

    const result = await tsiolkovsky({ isp_s: 450, m0_kg: 10000, mf_kg: 1000 })
    expect(result.ok).toBe(true)
    expect(result.delta_v_m_s).toBe(9200)
    expect(result.delta_v_km_s).toBe(9.2)
  })

  it('includes g0_m_s2 in request body when provided', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true, delta_v_m_s: 1234, delta_v_km_s: 1.234 })

    await tsiolkovsky({ isp_s: 400, m0_kg: 2000, mf_kg: 500, g0_m_s2: 1.62 })

    const call = globalThis.fetch.mock.calls[0]
    const body = JSON.parse(call[1].body)
    expect(body.g0_m_s2).toBe(1.62)
  })

  it('omits g0_m_s2 from request body when not provided', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true, delta_v_m_s: 5000, delta_v_km_s: 5 })

    await tsiolkovsky({ isp_s: 350, m0_kg: 3000, mf_kg: 600 })

    const call = globalThis.fetch.mock.calls[0]
    const body = JSON.parse(call[1].body)
    expect(body.g0_m_s2).toBeUndefined()
  })
})

describe('tsiolkovsky — error normalisation', () => {
  it('returns pending:true on HTTP 503', async () => {
    globalThis.fetch = _mockFetch(503, { status: 'pending', reason: 'kerf-cad-core not installed' })

    const result = await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 })
    expect(result.ok).toBe(false)
    expect(result.pending).toBe(true)
    expect(result.reason).toBeTruthy()
  })

  it('returns invalid:true on HTTP 422', async () => {
    globalThis.fetch = _mockFetch(422, { ok: false, reason: 'mf_kg must be > 0' })

    const result = await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 0 })
    expect(result.ok).toBe(false)
    expect(result.invalid).toBe(true)
    expect(result.reason).toMatch(/mf_kg/i)
  })

  it('returns error:true on network failure', async () => {
    globalThis.fetch = _mockFetchError('Failed to fetch')

    const result = await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 })
    expect(result.ok).toBe(false)
    expect(result.error).toBe(true)
    expect(result.reason).toContain('Failed to fetch')
  })

  it('returns error:true on HTTP 500', async () => {
    globalThis.fetch = _mockFetch(500, { detail: 'Internal server error' })

    const result = await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 })
    expect(result.ok).toBe(false)
    expect(result.error).toBe(true)
  })

  it('handles malformed JSON response gracefully', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => { throw new SyntaxError('bad json') },
    })

    const result = await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 })
    expect(result.ok).toBe(false)
    expect(result.invalid).toBe(true)
  })
})

describe('tsiolkovsky — Bearer token forwarding', () => {
  it('sends Authorization header when token is provided', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true, delta_v_m_s: 5000, delta_v_km_s: 5 })

    await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 }, 'my-token')

    const call = globalThis.fetch.mock.calls[0]
    expect(call[1].headers['authorization']).toBe('Bearer my-token')
  })

  it('omits Authorization header when token is null', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true, delta_v_m_s: 5000, delta_v_km_s: 5 })

    await tsiolkovsky({ isp_s: 300, m0_kg: 5000, mf_kg: 1000 }, null)

    const call = globalThis.fetch.mock.calls[0]
    expect(call[1].headers['authorization']).toBeUndefined()
  })
})

// ===========================================================================
// ceaLite
// ===========================================================================

describe('ceaLite — input validation', () => {
  it('throws TypeError when params is not an object', async () => {
    await expect(ceaLite(null)).rejects.toThrow(TypeError)
  })

  it('throws TypeError when propellant is empty string', async () => {
    await expect(ceaLite({ propellant: '' })).rejects.toThrow(TypeError)
  })

  it('throws TypeError when propellant is whitespace only', async () => {
    await expect(ceaLite({ propellant: '   ' })).rejects.toThrow(TypeError)
  })

  it('throws TypeError when propellant is not a string', async () => {
    await expect(ceaLite({ propellant: 42 })).rejects.toThrow(TypeError)
  })
})

describe('ceaLite — successful response', () => {
  it('returns ok:true on HTTP 200', async () => {
    const mockBody = {
      ok: true,
      propellant_key: 'lox/lh2',
      isp_vac_s: 450,
      isp_effective_s: 450,
      o_f_optimal: 5.5,
      condition: 'vacuum',
      notes: 'LOX/LH2',
      warning: 'table values',
    }
    globalThis.fetch = _mockFetch(200, mockBody)

    const result = await ceaLite({ propellant: 'lox/lh2' })
    expect(result.ok).toBe(true)
    expect(result.isp_vac_s).toBe(450)
    expect(result.condition).toBe('vacuum')
  })

  it('includes altitude_m in request body when provided', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true })

    await ceaLite({ propellant: 'lox/rp1', altitude_m: 0 })

    const call = globalThis.fetch.mock.calls[0]
    const body = JSON.parse(call[1].body)
    expect(body.altitude_m).toBe(0)
  })

  it('trims propellant string before sending', async () => {
    globalThis.fetch = _mockFetch(200, { ok: true })

    await ceaLite({ propellant: '  lox/ch4  ' })

    const call = globalThis.fetch.mock.calls[0]
    const body = JSON.parse(call[1].body)
    expect(body.propellant).toBe('lox/ch4')
  })
})

describe('ceaLite — error normalisation', () => {
  it('returns pending:true on HTTP 503', async () => {
    globalThis.fetch = _mockFetch(503, { status: 'pending', reason: 'Yosys not installed' })

    const result = await ceaLite({ propellant: 'lox/lh2' })
    expect(result.pending).toBe(true)
    expect(result.ok).toBe(false)
  })

  it('returns invalid:true on HTTP 422 with unknown propellant', async () => {
    globalThis.fetch = _mockFetch(422, { ok: false, reason: 'Unknown propellant' })

    const result = await ceaLite({ propellant: 'unobtanium' })
    expect(result.invalid).toBe(true)
    expect(result.reason).toContain('Unknown')
  })
})

// ===========================================================================
// multiStageDeltaV
// ===========================================================================

describe('multiStageDeltaV — input validation', () => {
  it('throws TypeError for non-array stages', async () => {
    await expect(multiStageDeltaV(null)).rejects.toThrow(TypeError)
    await expect(multiStageDeltaV('stages')).rejects.toThrow(TypeError)
  })

  it('throws TypeError for empty stages array', async () => {
    await expect(multiStageDeltaV([])).rejects.toThrow(TypeError)
  })
})

describe('multiStageDeltaV — successful path', () => {
  it('sums delta_v from each stage', async () => {
    const stageResult = { ok: true, delta_v_m_s: 3000, delta_v_km_s: 3 }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => stageResult,
    })

    const result = await multiStageDeltaV([
      { isp_s: 300, m0_kg: 5000, mf_kg: 1000 },
      { isp_s: 350, m0_kg: 2000, mf_kg: 500 },
    ])

    expect(result.ok).toBe(true)
    expect(result.total_delta_v_m_s).toBe(6000)
    expect(result.total_delta_v_km_s).toBe(6)
    expect(result.stages).toHaveLength(2)
  })

  it('returns ok:false when a stage fails', async () => {
    const failResult = { ok: false, invalid: true, reason: 'bad mass' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => failResult,
    })

    const result = await multiStageDeltaV([
      { isp_s: 300, m0_kg: 500, mf_kg: 1000 },  // m0 < mf — will fail
    ])

    expect(result.ok).toBe(false)
    expect(result.stages).toHaveLength(1)
  })

  it('total_delta_v_km_s = total_delta_v_m_s / 1000', async () => {
    const stageResult = { ok: true, delta_v_m_s: 4500, delta_v_km_s: 4.5 }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => stageResult,
    })

    const result = await multiStageDeltaV([
      { isp_s: 450, m0_kg: 5000, mf_kg: 500 },
    ])

    expect(Math.abs(result.total_delta_v_km_s - result.total_delta_v_m_s / 1000)).toBeLessThan(1e-10)
  })
})
