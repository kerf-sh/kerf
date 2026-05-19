/**
 * sseClient.js
 *
 * Minimal SSE client for POST-based server-sent events.
 *
 * The browser's built-in EventSource only supports GET. We use fetch() +
 * ReadableStream to support POST bodies, custom headers, and AbortSignal.
 *
 * Usage:
 *   for await (const { event, data } of streamSse(url, body, { signal, headers })) {
 *     // event: string (e.g. "assistant_text_delta")
 *     // data: parsed JSON object
 *   }
 *
 * Heartbeat comments (lines starting with ":") are silently skipped.
 * Multi-line data fields are concatenated with "\n" before JSON.parse.
 */

/**
 * Parse a single SSE frame (one block between double-newlines) into
 * { event, data } or null if the frame has no data.
 *
 * @param {string} block - raw text between blank lines
 * @returns {{ event: string, data: any } | null}
 */
function parseFrame(block) {
  let event = 'message'
  const dataLines = []

  for (const line of block.split('\n')) {
    if (line.startsWith(':')) {
      // Comment / heartbeat — skip
      continue
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (dataLines.length === 0) return null

  const raw = dataLines.join('\n')
  let data
  try {
    data = JSON.parse(raw)
  } catch {
    data = raw
  }

  return { event, data }
}

/**
 * Async generator that opens a POST SSE connection and yields parsed events.
 *
 * @param {string} url
 * @param {any} body - will be JSON.stringify'd
 * @param {{ signal?: AbortSignal, headers?: Record<string,string> }} [options]
 * @yields {{ event: string, data: any }}
 */
export async function* streamSse(url, body, options = {}) {
  const { signal, headers = {} } = options

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'text/event-stream',
      ...headers,
    },
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j?.detail || j?.message || detail
    } catch { /* ignore */ }
    throw new Error(`SSE request failed: ${res.status} ${detail}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      if (signal?.aborted) break

      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by blank lines (\n\n).
      // We may receive a partial frame; keep the tail in buffer.
      const parts = buffer.split('\n\n')
      // The last part may be incomplete — keep it in buffer.
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const trimmed = part.trim()
        if (!trimmed) continue

        const frame = parseFrame(trimmed)
        if (frame) {
          yield frame
        }
      }
    }

    // Flush any remaining buffer content (stream ended without trailing \n\n)
    if (buffer.trim()) {
      const frame = parseFrame(buffer.trim())
      if (frame) yield frame
    }
  } finally {
    reader.releaseLock()
  }
}
