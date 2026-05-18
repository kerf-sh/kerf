/**
 * atopileCompileBridge.js
 *
 * Fetch wrapper around the backend POST /atopile/compile route.
 *
 * Returns a normalised result object so callers never have to interpret
 * raw HTTP error shapes:
 *
 *   { ok: true,  circuit: [...], warnings: [] }
 *   { ok: false, errors: [{ message, line?, col? }], circuit: null }
 *
 * Usage:
 *   import { compileAtopile } from '../lib/atopileCompileBridge.js'
 *
 *   const result = await compileAtopile(source, { module: 'LedDriver' })
 *   if (result.ok) {
 *     // result.circuit is the Circuit JSON array
 *   } else {
 *     // result.errors is [{ message, line?, col? }]
 *   }
 *
 * The bridge never throws — it always returns the normalised object even
 * when the network is down or the server returns a non-JSON body.
 */

const API_URL = import.meta.env?.VITE_API_URL ?? ''

/**
 * @typedef {Object} AtopileCompileError
 * @property {string} message
 * @property {number|null} [line]
 * @property {number|null} [col]
 */

/**
 * @typedef {Object} AtopileCompileResult
 * @property {boolean} ok
 * @property {Array<object>|null} circuit   - Circuit JSON elements (ok=true only)
 * @property {string[]} warnings            - Non-fatal warnings
 * @property {AtopileCompileError[]|null} errors  - Compile errors (ok=false only)
 */

/**
 * Compile atopile source text via the backend.
 *
 * @param {string} source - Raw .ato source text
 * @param {{ module?: string, signal?: AbortSignal }} [opts]
 * @returns {Promise<AtopileCompileResult>}
 */
export async function compileAtopile(source, opts = {}) {
  const { module: topModule, signal } = opts

  const body = { source }
  if (topModule) body.module = topModule

  let res
  try {
    res = await fetch(`${API_URL}/atopile/compile`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') {
      return _aborted()
    }
    return _networkError(err.message)
  }

  let json
  try {
    json = await res.json()
  } catch {
    return _networkError(`server returned non-JSON (status ${res.status})`)
  }

  if (res.status === 400) {
    const detail = json?.detail ?? 'invalid request'
    return { ok: false, circuit: null, warnings: [], errors: [{ message: detail }] }
  }

  if (res.status === 422) {
    // FastAPI validation error
    const msg = _extractValidationMessage(json)
    return { ok: false, circuit: null, warnings: [], errors: [{ message: msg }] }
  }

  if (!res.ok) {
    const detail = json?.detail ?? `server error (${res.status})`
    return { ok: false, circuit: null, warnings: [], errors: [{ message: detail }] }
  }

  if (json.ok === false) {
    return {
      ok: false,
      circuit: null,
      warnings: json.warnings ?? [],
      errors: json.errors ?? [{ message: 'compile failed (unknown error)' }],
    }
  }

  return {
    ok: true,
    circuit: json.circuit ?? [],
    warnings: json.warnings ?? [],
    errors: null,
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _aborted() {
  return { ok: false, circuit: null, warnings: [], errors: [{ message: 'aborted' }] }
}

function _networkError(message) {
  return {
    ok: false,
    circuit: null,
    warnings: [],
    errors: [{ message: `Network error: ${message}` }],
  }
}

function _extractValidationMessage(json) {
  try {
    const detail = json?.detail
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((e) => e.msg ?? String(e)).join('; ')
    }
    return String(detail ?? 'validation error')
  } catch {
    return 'validation error'
  }
}
