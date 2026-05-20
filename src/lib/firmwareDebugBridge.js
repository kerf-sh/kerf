/**
 * firmwareDebugBridge.js — fetch wrapper around the /firmware/debug/* routes.
 *
 * Endpoints:
 *   POST /api/firmware/debug/attach   — attach to target, return RTOS snapshot
 *   GET  /api/firmware/debug/snapshot — return last cached snapshot
 *
 * Cloud path: the server always returns the JTAG sentinel:
 *   { ok: false, error: "JTAG_LOCAL_ONLY",
 *     message: "JTAG requires the local Kerf CLI", ... }
 *
 * All functions return a normalised result object and never throw.
 */

const API_URL = typeof import.meta !== 'undefined' && import.meta.env
  ? (import.meta.env.VITE_API_URL || '')
  : ''

/** Sentinel message returned by the cloud API for JTAG operations. */
export const JTAG_CLOUD_SENTINEL = 'JTAG requires the local Kerf CLI'

/**
 * Normalise a raw API response into the standard debug result shape.
 *
 * @param {Response|null} res
 * @param {object|null}   body
 * @param {string}        fallbackError
 * @returns {{ ok: boolean, error: string|null, message: string, tasks: Array,
 *             sync_objects: Array, edges: Array, warnings: string[] }}
 */
export function normaliseDebug(res, body, fallbackError = 'Unknown error') {
  if (!body) {
    return {
      ok: false,
      error: 'NETWORK_ERROR',
      message: fallbackError,
      tasks: [],
      sync_objects: [],
      edges: [],
      warnings: [fallbackError],
    }
  }
  return {
    ok: Boolean(body.ok),
    error: body.error || null,
    message: body.message || (body.ok ? 'ok' : (body.error || 'error')),
    tasks: Array.isArray(body.tasks) ? body.tasks : [],
    sync_objects: Array.isArray(body.sync_objects) ? body.sync_objects : [],
    edges: Array.isArray(body.edges) ? body.edges : [],
    warnings: Array.isArray(body.warnings) ? body.warnings : [],
  }
}

/**
 * Attach to a target and return a live RTOS debug snapshot.
 *
 * On the cloud path the server returns the JTAG sentinel; the result will
 * have ok:false and error:"JTAG_LOCAL_ONLY".
 *
 * @param {object} [opts]
 * @param {string} [opts.elfPath]   - abs path to ELF file
 * @param {string} [opts.target]    - OpenOCD target (default "stm32f4")
 * @param {string} [opts.rtos]      - "kerfrtos" or "freertos"
 * @returns {Promise<{
 *   ok: boolean,
 *   error: string|null,
 *   message: string,
 *   tasks: Array<{name:string, state:string, priority:number,
 *                 stack_high_water:number, stack_size:number,
 *                 stack_pct_free:number, stack_warning:boolean}>,
 *   sync_objects: Array<{name:string, kind:string, held_by:string|null,
 *                         waiters:string[]}>,
 *   edges: Array<{from:string, to:string, label:string}>,
 *   warnings: string[],
 * }>}
 */
export async function attachDebugSession({ elfPath = '', target = 'stm32f4', rtos = 'kerfrtos' } = {}) {
  const url = `${API_URL}/api/firmware/debug/attach`
  let res = null
  let body = null
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ elf_path: elfPath, target, rtos }),
    })
  } catch (err) {
    return normaliseDebug(null, null, `Network error: ${err.message || err}`)
  }
  try {
    body = await res.json()
  } catch {
    return normaliseDebug(res, null, 'Failed to parse response from /firmware/debug/attach')
  }
  return normaliseDebug(res, body)
}

/**
 * Fetch the last cached RTOS debug snapshot.
 *
 * @returns {Promise<ReturnType<typeof normaliseDebug>>}
 */
export async function fetchDebugSnapshot() {
  const url = `${API_URL}/api/firmware/debug/snapshot`
  let res = null
  let body = null
  try {
    res = await fetch(url, { method: 'GET' })
  } catch (err) {
    return normaliseDebug(null, null, `Network error: ${err.message || err}`)
  }
  try {
    body = await res.json()
  } catch {
    return normaliseDebug(res, null, 'Failed to parse response from /firmware/debug/snapshot')
  }
  return normaliseDebug(res, body)
}

/**
 * Returns true when the result carries the JTAG cloud sentinel.
 *
 * @param {object} result - result from attachDebugSession / fetchDebugSnapshot
 * @returns {boolean}
 */
export function isJtagSentinel(result) {
  return result.error === 'JTAG_LOCAL_ONLY' ||
    (typeof result.message === 'string' && result.message.includes(JTAG_CLOUD_SENTINEL))
}
