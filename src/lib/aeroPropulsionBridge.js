// aeroPropulsionBridge.js — Frontend helpers for the aero propulsion API.
//
// Wraps POST /api/aero/propulsion/tsiolkovsky and /cea-lite with:
//   - Input validation (throws TypeError on bad arguments)
//   - Fetch with optional auth token
//   - Error normalisation:
//       • HTTP 503 → { pending: true, reason }
//       • HTTP 422 → { invalid: true, reason }
//       • network / other → { error: true, reason }
//   - Returns the raw response body on success (ok: true)

const API_URL = typeof import.meta !== 'undefined'
  ? (import.meta.env?.VITE_API_URL || '')
  : ''

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * POST to the given path with JSON body.  Returns the parsed JSON body.
 * Normalises error shapes so callers get a consistent result.
 *
 * @param {string} path
 * @param {object} body
 * @param {string|null} [token]  — Bearer token (optional)
 * @returns {Promise<object>}
 */
async function _post(path, body, token = null) {
  const headers = { 'content-type': 'application/json' }
  if (token) headers['authorization'] = `Bearer ${token}`

  let res
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
  } catch (err) {
    return { ok: false, error: true, reason: err.message || String(err) }
  }

  let data
  try {
    data = await res.json()
  } catch {
    data = {}
  }

  if (res.status === 503) {
    return {
      ok: false,
      pending: true,
      reason: data.reason || 'Service unavailable — backend package not installed',
      status: data.status || 'pending',
    }
  }

  if (res.status === 422) {
    return {
      ok: false,
      invalid: true,
      reason: data.reason || data.detail || 'Invalid request',
    }
  }

  if (!res.ok) {
    return {
      ok: false,
      error: true,
      reason: data.reason || data.detail || `HTTP ${res.status}`,
      httpStatus: res.status,
    }
  }

  return data
}

// ---------------------------------------------------------------------------
// Tsiolkovsky rocket equation
// ---------------------------------------------------------------------------

/**
 * Compute Δv via the Tsiolkovsky ideal rocket equation.
 *
 * @param {object} params
 * @param {number} params.isp_s       — Specific impulse (s).  Must be > 0.
 * @param {number} params.m0_kg       — Initial (wet) mass (kg).  Must be > mf_kg.
 * @param {number} params.mf_kg       — Final (dry) mass (kg).  Must be > 0.
 * @param {number} [params.g0_m_s2]   — Standard gravity override (default: 9.80665).
 * @param {string|null} [token]        — Optional Bearer token.
 *
 * @returns {Promise<{
 *   ok: boolean,
 *   delta_v_m_s?: number,
 *   delta_v_km_s?: number,
 *   mass_ratio?: number,
 *   exhaust_velocity_m_s?: number,
 *   propellant_mass_kg?: number,
 *   propellant_fraction?: number,
 *   pending?: boolean,
 *   invalid?: boolean,
 *   error?: boolean,
 *   reason?: string,
 * }>}
 */
export async function tsiolkovsky(params, token = null) {
  if (typeof params !== 'object' || params === null) {
    throw new TypeError('aeroPropulsionBridge.tsiolkovsky: params must be an object')
  }
  const { isp_s, m0_kg, mf_kg, g0_m_s2 } = params
  if (typeof isp_s !== 'number' || !isFinite(isp_s)) {
    throw new TypeError('aeroPropulsionBridge.tsiolkovsky: isp_s must be a finite number')
  }
  if (typeof m0_kg !== 'number' || !isFinite(m0_kg)) {
    throw new TypeError('aeroPropulsionBridge.tsiolkovsky: m0_kg must be a finite number')
  }
  if (typeof mf_kg !== 'number' || !isFinite(mf_kg)) {
    throw new TypeError('aeroPropulsionBridge.tsiolkovsky: mf_kg must be a finite number')
  }

  const body = { isp_s, m0_kg, mf_kg }
  if (g0_m_s2 != null) body.g0_m_s2 = g0_m_s2

  return _post('/api/aero/propulsion/tsiolkovsky', body, token)
}

// ---------------------------------------------------------------------------
// CEA-lite — propellant Isp lookup
// ---------------------------------------------------------------------------

/**
 * Look up approximate specific impulse for a propellant combination.
 *
 * @param {object} params
 * @param {string} params.propellant     — Propellant key (e.g. 'lox/lh2', 'lox/rp1').
 * @param {number} [params.altitude_m]   — Altitude for Isp correction (m); omit for vacuum.
 * @param {number} [params.expansion_ratio] — Nozzle expansion ratio (default: 1.0 = vacuum).
 * @param {string|null} [token]
 *
 * @returns {Promise<{
 *   ok: boolean,
 *   propellant_key?: string,
 *   isp_vac_s?: number,
 *   isp_effective_s?: number,
 *   o_f_optimal?: number,
 *   condition?: string,
 *   notes?: string,
 *   warning?: string,
 *   pending?: boolean,
 *   invalid?: boolean,
 *   error?: boolean,
 *   reason?: string,
 * }>}
 */
export async function ceaLite(params, token = null) {
  if (typeof params !== 'object' || params === null) {
    throw new TypeError('aeroPropulsionBridge.ceaLite: params must be an object')
  }
  const { propellant, altitude_m, expansion_ratio } = params
  if (typeof propellant !== 'string' || propellant.trim() === '') {
    throw new TypeError('aeroPropulsionBridge.ceaLite: propellant must be a non-empty string')
  }

  const body = { propellant: propellant.trim() }
  if (altitude_m != null) body.altitude_m = altitude_m
  if (expansion_ratio != null) body.expansion_ratio = expansion_ratio

  return _post('/api/aero/propulsion/cea-lite', body, token)
}

// ---------------------------------------------------------------------------
// Convenience: compute Δv budget for a multi-stage rocket
//
// stages: Array<{ isp_s, m0_kg, mf_kg, g0_m_s2? }>
// Returns: { ok, total_delta_v_m_s, stages: [...per-stage results] }
// ---------------------------------------------------------------------------

/**
 * Multi-stage Δv budget calculator.  Chains Tsiolkovsky calls sequentially.
 *
 * @param {Array<{isp_s: number, m0_kg: number, mf_kg: number, g0_m_s2?: number}>} stages
 * @param {string|null} [token]
 *
 * @returns {Promise<{
 *   ok: boolean,
 *   total_delta_v_m_s: number,
 *   total_delta_v_km_s: number,
 *   stages: Array<object>,
 * }>}
 */
export async function multiStageDeltaV(stages, token = null) {
  if (!Array.isArray(stages) || stages.length === 0) {
    throw new TypeError('aeroPropulsionBridge.multiStageDeltaV: stages must be a non-empty array')
  }

  const results = []
  let total = 0

  for (const stage of stages) {
    const res = await tsiolkovsky(stage, token)
    results.push(res)
    if (!res.ok) {
      return { ok: false, stages: results, reason: res.reason || 'Stage calculation failed' }
    }
    total += res.delta_v_m_s
  }

  return {
    ok: true,
    total_delta_v_m_s: total,
    total_delta_v_km_s: total / 1000,
    stages: results,
  }
}
