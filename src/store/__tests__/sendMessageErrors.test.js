/**
 * sendMessageErrors.test.js
 *
 * Regression: when the backend hangs or fails on POST /messages, the chat UI
 * must (1) clear the `sending` flag (so "Kerf is thinking…" goes away) and
 * (2) attach an `_error` string to the optimistic user-message so the
 * MessageBlock can render a "Message failed to send" alert.
 *
 * Strategy: mock `api.sendMessage` to reject, drive the workspace store, and
 * inspect the state. We bypass `createThread` by seeding `currentThreadId`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the API client so sendMessage can be made to reject deterministically.
vi.mock('../../lib/api.js', () => {
  const sendMessage = vi.fn()
  const listFiles = vi.fn(async () => [])
  return {
    api: {
      sendMessage,
      listFiles,
      // Other entries that workspace.js may pull off the import — stubbed
      // so importing the store doesn't blow up. Tests below only exercise
      // sendMessage.
      listMessages: vi.fn(async () => []),
      listThreads: vi.fn(async () => []),
      createThread: vi.fn(async () => ({ id: 't-new' })),
    },
    ApiError: class ApiError extends Error {
      constructor(status, message) { super(message); this.status = status }
    },
  }
})

// Avoid IndexedDB / file-revisions side effects from the real store.
vi.mock('../../lib/localStash.js', () => ({
  stash: vi.fn(),
  markFlushed: vi.fn(),
  _resetForTest: vi.fn(),
  _setIDBFactory: vi.fn(),
}))

import { api } from '../../lib/api.js'
import { useWorkspace } from '../workspace.js'

function reset() {
  useWorkspace.setState({
    projectId: 'p-1',
    currentThreadId: 't-1',
    currentFileId: null,
    pendingPartRefs: [],
    threads: [{ id: 't-1', title: 'x', last_message_at: null }],
    messages: [],
    sending: false,
  })
}

beforeEach(() => {
  api.sendMessage.mockReset()
  reset()
})

describe('sendMessage error handling', () => {
  it('clears `sending` when the backend rejects', async () => {
    api.sendMessage.mockRejectedValueOnce(
      Object.assign(new Error('Request timed out after 180s. Please try again.'), { status: 0 }),
    )
    await useWorkspace.getState().sendMessage('hello', {})
    const s = useWorkspace.getState()
    expect(s.sending).toBe(false)
  })

  it('attaches `_error` to the optimistic user message on failure', async () => {
    api.sendMessage.mockRejectedValueOnce(
      Object.assign(new Error('Request timed out after 180s. Please try again.'), { status: 0 }),
    )
    await useWorkspace.getState().sendMessage('hello there', {})
    const { messages } = useWorkspace.getState()
    // The optimistic message stays in the list so the user sees what they typed.
    expect(messages).toHaveLength(1)
    expect(messages[0].role).toBe('user')
    expect(messages[0].content).toBe('hello there')
    expect(messages[0]._error).toMatch(/timed out/i)
  })

  it('keeps the optimistic message visible (does not silently drop it)', async () => {
    api.sendMessage.mockRejectedValueOnce(new Error('network down'))
    await useWorkspace.getState().sendMessage('please render', {})
    const { messages, sending } = useWorkspace.getState()
    expect(sending).toBe(false)
    expect(messages.find((m) => m.content === 'please render')).toBeTruthy()
    expect(messages.find((m) => m.content === 'please render')._error).toBe('network down')
  })

  it('falls back to a generic message when the error has none', async () => {
    api.sendMessage.mockRejectedValueOnce({})  // no .message
    await useWorkspace.getState().sendMessage('hi', {})
    const m = useWorkspace.getState().messages[0]
    expect(m._error).toBe('Failed to send')
  })
})
