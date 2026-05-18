/**
 * gdsLoader.js — Fetch wrapper for the backend GDS-II parse endpoint.
 *
 * Usage:
 *   import { parseGds } from './gdsLoader.js'
 *   const layout = await parseGds(file)   // file is a File/Blob
 *
 * On success returns the layout JSON:
 *   {
 *     cells: [{ name, shapes: [...] }],
 *     layers: [{ layer, datatype }, ...],
 *     topCell: string,
 *     db_unit: number,
 *     user_unit: number,
 *   }
 *
 * On failure throws an Error with a human-readable message.
 */

const API_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || ''

/**
 * POST a GDS file to the backend and return the parsed layout JSON.
 *
 * @param {File|Blob} fileOrBlob   The .gds file to upload.
 * @param {object}    [opts]       Optional overrides.
 * @param {string}    [opts.endpoint]   Backend endpoint (default: /api/silicon/gds/parse).
 * @param {string}    [opts.filename]   Filename to report in the multipart upload.
 * @returns {Promise<object>}  Layout JSON { cells, layers, topCell, db_unit, user_unit }.
 */
export async function parseGds(fileOrBlob, opts = {}) {
  const endpoint = opts.endpoint ?? `${API_URL}/api/silicon/gds/parse`
  const filename  = opts.filename ?? (fileOrBlob?.name ?? 'upload.gds')

  if (!fileOrBlob) {
    throw new Error('parseGds: no file provided')
  }

  const form = new FormData()
  form.append('file', fileOrBlob, filename)

  let res
  try {
    res = await fetch(endpoint, { method: 'POST', body: form })
  } catch (networkErr) {
    throw new Error(`GDS parse request failed (network): ${networkErr.message}`)
  }

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore JSON parse errors — keep statusText
    }
    throw new Error(`GDS parse failed (${res.status}): ${detail}`)
  }

  let data
  try {
    data = await res.json()
  } catch (parseErr) {
    throw new Error(`GDS parse response was not valid JSON: ${parseErr.message}`)
  }

  // Basic shape validation — surface early rather than crashing in the viewer
  if (!Array.isArray(data.cells)) {
    throw new Error('GDS parse response missing "cells" array')
  }

  return data
}
