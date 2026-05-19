/**
 * sseClient.test.js
 *
 * Unit tests for src/lib/sseClient.js
 *
 * Tests:
 *  - Parse multi-line SSE frames from a mock ReadableStream
 *  - Handle the `event:` field + `data:` field
 *  - Handle `:` heartbeat comments (don't emit them)
 *  - AbortSignal cancellation
 *  - Multiple frames in one chunk
 *  - Frames split across chunks
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { streamSse } from '../sseClient.js'

// ---------------------------------------------------------------------------
// Helpers to build mock fetch responses with a ReadableStream body
// ---------------------------------------------------------------------------

function makeStream(chunks) {
  const encoder = new TextEncoder()
  let i = 0
  return new ReadableStream({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i++]))
      } else {
        controller.close()
      }
    },
  })
}

function mockFetch(chunks, status = 200) {
  const stream = makeStream(chunks)
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: async () => ({ detail: 'mock error' }),
    body: stream,
  })
}

async function collect(gen) {
  const results = []
  for await (const item of gen) {
    results.push(item)
  }
  return results
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('streamSse', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', undefined)
  })

  it('parses a single frame with event + data', async () => {
    vi.stubGlobal('fetch', mockFetch([
      'event: assistant_text_delta\ndata: {"text":" hello"}\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].event).toBe('assistant_text_delta')
    expect(results[0].data).toEqual({ text: ' hello' })
  })

  it('parses multiple frames in one chunk', async () => {
    vi.stubGlobal('fetch', mockFetch([
      'event: tool_use_start\ndata: {"tool_use_id":"tu_1","name":"read_file"}\n\n' +
      'event: tool_executing\ndata: {"tool_use_id":"tu_1","name":"read_file"}\n\n' +
      'event: assistant_done\ndata: {"stop_reason":"end_turn","input_tokens":10,"output_tokens":5,"model":"m"}\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(3)
    expect(results[0].event).toBe('tool_use_start')
    expect(results[1].event).toBe('tool_executing')
    expect(results[2].event).toBe('assistant_done')
  })

  it('handles frames split across chunks', async () => {
    // First chunk ends in the middle of a data line
    vi.stubGlobal('fetch', mockFetch([
      'event: assistant_text_delta\ndat',
      'a: {"text":"split"}\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].data.text).toBe('split')
  })

  it('skips heartbeat comment lines', async () => {
    vi.stubGlobal('fetch', mockFetch([
      ': keepalive\n\n' +
      'event: assistant_text_delta\ndata: {"text":"after heartbeat"}\n\n' +
      ': keepalive\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].event).toBe('assistant_text_delta')
    expect(results[0].data.text).toBe('after heartbeat')
  })

  it('skips empty frames', async () => {
    vi.stubGlobal('fetch', mockFetch([
      '\n\n' +
      'event: assistant_done\ndata: {"stop_reason":"end_turn","input_tokens":0,"output_tokens":0,"model":"m"}\n\n' +
      '\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].event).toBe('assistant_done')
  })

  it('uses default event name "message" when event: line is absent', async () => {
    vi.stubGlobal('fetch', mockFetch([
      'data: {"foo":"bar"}\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].event).toBe('message')
    expect(results[0].data).toEqual({ foo: 'bar' })
  })

  it('throws on non-ok response', async () => {
    vi.stubGlobal('fetch', mockFetch([], 401))

    await expect(collect(streamSse('/api/test', {}))).rejects.toThrow(/401/)
  })

  it('stops iteration when AbortSignal is aborted', async () => {
    const ctrl = new AbortController()

    // Provide many chunks so the stream would keep going
    const encoder = new TextEncoder()
    let chunkCount = 0
    const stream = new ReadableStream({
      pull(controller) {
        chunkCount++
        if (ctrl.signal.aborted) {
          controller.close()
          return
        }
        if (chunkCount <= 5) {
          controller.enqueue(encoder.encode(
            `event: assistant_text_delta\ndata: {"text":"chunk${chunkCount}"}\n\n`
          ))
        } else {
          controller.close()
        }
      },
    })

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: stream,
    }))

    const results = []
    const gen = streamSse('/api/test', {}, { signal: ctrl.signal })

    for await (const item of gen) {
      results.push(item)
      // Abort after first item
      if (results.length === 1) {
        ctrl.abort()
        break
      }
    }

    // We should have stopped after 1 item
    expect(results).toHaveLength(1)
  })

  it('passes custom headers to fetch', async () => {
    const mockF = mockFetch([
      'event: assistant_done\ndata: {"stop_reason":"end_turn","input_tokens":0,"output_tokens":0,"model":"m"}\n\n',
    ])
    vi.stubGlobal('fetch', mockF)

    await collect(streamSse('/api/test', { foo: 'bar' }, {
      headers: { authorization: 'Bearer tok' },
    }))

    const [, init] = mockF.mock.calls[0]
    expect(init.headers.authorization).toBe('Bearer tok')
  })

  it('sends the body as JSON', async () => {
    const mockF = mockFetch([
      'event: assistant_done\ndata: {"stop_reason":"end_turn","input_tokens":0,"output_tokens":0,"model":"m"}\n\n',
    ])
    vi.stubGlobal('fetch', mockF)

    await collect(streamSse('/api/test', { content: 'hello', model: 'claude' }))

    const [, init] = mockF.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ content: 'hello', model: 'claude' })
  })

  it('handles non-JSON data gracefully (passes raw string)', async () => {
    vi.stubGlobal('fetch', mockFetch([
      'event: raw\ndata: not json at all\n\n',
    ]))

    const results = await collect(streamSse('/api/test', {}))
    expect(results).toHaveLength(1)
    expect(results[0].data).toBe('not json at all')
  })
})
