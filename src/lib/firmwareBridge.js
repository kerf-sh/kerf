/**
 * firmwareBridge.js — fetch wrapper around the firmware backend routes.
 *
 * Endpoints:
 *   POST /api/firmware/build   — compile a .fw.json project or .ino sketch
 *   POST /api/firmware/upload  — flash compiled artifact to a connected board
 *   POST /api/firmware/monitor — read a serial snapshot from the board
 *
 * All functions return a normalised result object:
 *   { ok: boolean, status: "success"|"error"|"pending", errors: string[], ...extra }
 *
 * They never throw — network / parse errors are caught and returned as
 *   { ok: false, status: "error", errors: ["<message>"] }.
 */

const API_URL = typeof import.meta !== 'undefined' && import.meta.env
  ? (import.meta.env.VITE_API_URL || '')
  : ''

/**
 * Normalise any response into the standard { ok, status, errors } shape.
 * Extra fields from the body are merged in.
 *
 * @param {Response|null} res  - fetch Response (or null on network error)
 * @param {object|null}   body - parsed JSON body (or null on parse error)
 * @param {string}        fallbackError - message used when body is absent
 * @returns {{ ok: boolean, status: string, errors: string[] }}
 */
export function normalise(res, body, fallbackError = 'Unknown error') {
  if (!body) {
    return {
      ok: false,
      status: 'error',
      errors: [fallbackError],
    }
  }

  // Body already has the canonical shape — just ensure required fields exist.
  // Spread body first so our normalised fields take precedence over raw body values.
  const normalisedErrors = Array.isArray(body.errors) ? body.errors : []
  return {
    ...body,
    ok: Boolean(body.ok),
    status: body.status || (body.ok ? 'success' : 'error'),
    errors: normalisedErrors,
  }
}

/**
 * Internal helper: POST to a firmware route and normalise the response.
 *
 * @param {string} path   - e.g. "/api/firmware/build"
 * @param {object} payload
 * @returns {Promise<{ ok: boolean, status: string, errors: string[] }>}
 */
async function firmwarePost(path, payload) {
  const url = `${API_URL}${path}`
  let res = null
  let body = null

  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    return normalise(null, null, `Network error: ${err.message || err}`)
  }

  try {
    body = await res.json()
  } catch {
    return normalise(res, null, `Failed to parse response from ${path}`)
  }

  return normalise(res, body)
}

/**
 * Build a firmware project.
 *
 * @param {string} sourcePath  - abs path to sketch dir or .ino file
 * @param {object} [fwConfig]  - parsed kerf.fw.json content (optional)
 * @returns {Promise<{
 *   ok: boolean,
 *   status: "success"|"error"|"pending",
 *   hex_path: string|null,
 *   errors: string[],
 *   warnings: string[],
 * }>}
 */
export async function buildFirmware(sourcePath, fwConfig = null) {
  return firmwarePost('/api/firmware/build', {
    source_path: sourcePath,
    fw_config: fwConfig,
  })
}

/**
 * Flash a compiled firmware artifact to a connected board.
 *
 * @param {string} hexPath    - abs path to the compiled .hex/.uf2 file
 * @param {object} [fwConfig] - parsed kerf.fw.json content (optional)
 * @param {string} [port]     - serial port override (e.g. "/dev/ttyUSB0")
 * @returns {Promise<{
 *   ok: boolean,
 *   status: "success"|"error"|"pending",
 *   port: string|null,
 *   errors: string[],
 * }>}
 */
export async function uploadFirmware(hexPath, fwConfig = null, port = null) {
  return firmwarePost('/api/firmware/upload', {
    hex_path: hexPath,
    fw_config: fwConfig,
    port,
  })
}

/**
 * Read a serial snapshot from the connected board.
 *
 * @param {object} [fwConfig] - parsed kerf.fw.json content (optional)
 * @param {string} [port]     - serial port override
 * @param {number} [baud]     - baud rate (default: 9600)
 * @returns {Promise<{
 *   ok: boolean,
 *   status: "success"|"error"|"pending",
 *   port: string|null,
 *   lines: string[],
 *   errors: string[],
 * }>}
 */
export async function monitorFirmware(fwConfig = null, port = null, baud = 9600) {
  return firmwarePost('/api/firmware/monitor', {
    fw_config: fwConfig,
    port,
    baud,
  })
}
