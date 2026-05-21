/**
 * ChatPanel.sendFailure.test.jsx
 *
 * Source-level assertions for T-B3 "Surface send failures in the chat panel".
 *
 * We inspect the JSX source directly (same pattern as other ChatPanel a11y
 * tests) to verify that:
 *  1. A send-failure banner with role="alert" aria-live="assertive" is
 *     rendered near the input when a send fails.
 *  2. The banner is driven by `sendError` state and clears on next send
 *     (handleSend calls setSendError(null) before onSend).
 *  3. The banner has the correct ARIA attributes.
 *  4. The banner is conditional — only renders when sendError is truthy.
 *  5. MessageBlock accepts an onRetry prop.
 *  6. The retry button only shows for non-user (assistant) errored messages.
 *  7. The retry button carries data-testid="chat-message-retry".
 *  8. The retry wiring in the render loop only supplies onRetry for errored
 *     assistant messages (retryContentByIndex map).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../ChatPanel.jsx'),
  'utf8',
)

describe('ChatPanel — T-B3 send-failure announcer', () => {
  // ----- banner structure -----

  it('banner has role="alert"', () => {
    // Should find the banner testid
    expect(SRC).toMatch(/data-testid="chat-send-error-banner"/)
    // role="alert" appears before the testid on the same element (within 200 chars)
    const bannerPos = SRC.indexOf('chat-send-error-banner')
    expect(bannerPos).toBeGreaterThan(-1)
    const nearby = SRC.slice(Math.max(0, bannerPos - 200), bannerPos + 50)
    expect(nearby).toMatch(/role="alert"/)
  })

  it('banner has aria-live="assertive"', () => {
    expect(SRC).toMatch(/aria-live="assertive"/)
  })

  it('banner element carries both role="alert" and aria-live="assertive" close together', () => {
    // They must be on the same JSX element (within ~120 chars of each other).
    const alertPos = SRC.indexOf('aria-live="assertive"')
    expect(alertPos).toBeGreaterThan(-1)
    const nearby = SRC.slice(Math.max(0, alertPos - 120), alertPos + 120)
    expect(nearby).toMatch(/role="alert"/)
    expect(nearby).toMatch(/chat-send-error-banner/)
  })

  it('banner is guarded by sendError state (only renders when truthy)', () => {
    // The JSX must include {sendError && (...banner...)}
    expect(SRC).toMatch(/\{sendError &&/)
  })

  it('banner contains the "Couldn\'t send" label', () => {
    expect(SRC).toMatch(/Couldn/)
  })

  it('banner has a dismiss button', () => {
    expect(SRC).toMatch(/chat-send-error-dismiss/)
    expect(SRC).toMatch(/setSendError\(null\)/)
  })

  // ----- state and clear-on-send -----

  it('sendError is declared as useState', () => {
    expect(SRC).toMatch(/const \[sendError, setSendError\] = useState\(null\)/)
  })

  it('handleSend clears sendError before calling onSend (transient)', () => {
    // setSendError(null) must appear inside handleSend before onSend call
    const handleSendBody = SRC.match(/const handleSend = useCallback\(\(content\)([\s\S]*?)\}, \[onSend/)
    expect(handleSendBody).toBeTruthy()
    const body = handleSendBody[0]
    const clearPos = body.indexOf('setSendError(null)')
    const sendPos = body.indexOf('onSend(content')
    expect(clearPos).toBeGreaterThan(-1)
    expect(sendPos).toBeGreaterThan(-1)
    expect(clearPos).toBeLessThan(sendPos)
  })

  it('sendError is derived from messages via useEffect', () => {
    expect(SRC).toMatch(/setSendError\(failed \?/)
  })

  // ----- per-message retry affordance -----

  it('MessageBlock signature accepts onRetry prop', () => {
    expect(SRC).toMatch(/function MessageBlock\s*\(\s*\{[^}]*onRetry/)
  })

  it('retry button has data-testid="chat-message-retry"', () => {
    expect(SRC).toMatch(/data-testid="chat-message-retry"/)
  })

  it('retry button only renders for non-user (assistant) errored messages', () => {
    // The retry button must be inside the !isUser guard
    const retryButtonArea = SRC.match(/!isUser && onRetry[\s\S]{0,300}?chat-message-retry/)
    expect(retryButtonArea).toBeTruthy()
  })

  it('retry button calls onRetry on click', () => {
    expect(SRC).toMatch(/onClick=\{onRetry\}/)
  })

  it('retryContentByIndex map is computed from renderItems to find preceding user content', () => {
    expect(SRC).toMatch(/retryContentByIndex/)
    expect(SRC).toMatch(/lastUserContent/)
  })

  it('onRetry is passed to MessageBlock only when retryContent is available', () => {
    // The render loop should include retryContentByIndex[i] lookup
    expect(SRC).toMatch(/retryContentByIndex\[i\]/)
    // And pass onRetry to MessageBlock
    expect(SRC).toMatch(/onRetry=\{onRetry\}/)
  })

  // ----- regression guards -----

  it('does not regress: existing chat-message-error testid is still present', () => {
    expect(SRC).toMatch(/data-testid="chat-message-error"/)
  })

  it('does not regress: role="alert" is still present on per-message error block', () => {
    // The per-message error block also has role="alert"
    const count = (SRC.match(/role="alert"/g) || []).length
    expect(count).toBeGreaterThanOrEqual(2)
  })
})
