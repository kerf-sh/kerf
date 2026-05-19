/**
 * chatPanelError.test.js
 *
 * Source-level oracle for the chat-error UI affordance.
 *
 * Regression context: chat used to hang on "Kerf is thinking…" forever when
 * the backend stalled. With the timeout fix in src/lib/api.js, sendMessage
 * rejects after CHAT_TIMEOUT_MS and the store attaches `_error` to the
 * optimistic message. This test pins the *rendered* error structure so a
 * refactor cannot silently regress to the old too-small "10px text-red-400"
 * single-line treatment.
 *
 * We assert on source rather than via @testing-library because ChatPanel
 * pulls in CodeMirror / Markdown / lucide-react eagerly, which would force
 * a heavy DOM-mode test for what is fundamentally a JSX-shape contract.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../ChatPanel.jsx'),
  'utf8',
)

describe('ChatPanel — message error affordance', () => {
  it('renders a role="alert" container when message._error is set', () => {
    // Must be screen-reader announced — silent failures are the original bug.
    expect(SRC).toMatch(/message\._error[\s\S]{0,400}role="alert"/)
  })

  it('uses a stable data-testid for the error block', () => {
    expect(SRC).toMatch(/data-testid="chat-message-error"/)
  })

  it('shows a "Message failed to send" heading inside the error', () => {
    expect(SRC).toMatch(/Message failed to send/)
  })

  it('prompts the user to retry', () => {
    expect(SRC).toMatch(/Try sending it again/)
  })

  it('renders the raw error text from message._error', () => {
    expect(SRC).toMatch(/\{message\._error\}/)
  })

  it('uses a TriangleAlert icon (visual cue, not just colour)', () => {
    // Colour-only error indicators are inaccessible. The icon must be present.
    expect(SRC).toMatch(/<TriangleAlert\b/)
    expect(SRC).toMatch(/TriangleAlert,?\s*\n?\s*\}\s*from\s*'lucide-react'/m)
  })

  it('does NOT regress to the tiny one-line text-red-400 treatment', () => {
    // The old code rendered <div className="text-[10px] text-red-400">{message._error}</div>
    // with no border, no heading, no aria role. Block that exact line shape.
    expect(SRC).not.toMatch(/<div className="text-\[10px\] text-red-400">\{message\._error\}<\/div>/)
  })
})
