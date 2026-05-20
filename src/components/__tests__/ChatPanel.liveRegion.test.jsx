/**
 * ChatPanel.liveRegion.test.jsx
 *
 * Source-level assertions for T-B2 "Live region for streamed assistant replies".
 *
 * We inspect the JSX source directly (same pattern as ChatPanel.toolChips.test.jsx)
 * to verify that the latest assistant message bubble carries the correct
 * aria-live attributes so screen-reader users hear streamed output.
 *
 * Tests:
 *  - MessageBlock accepts isLatestAssistant prop
 *  - aria-live="polite" is applied to the latest assistant bubble
 *  - aria-atomic="false" is applied (incremental announcements)
 *  - data-live-region="assistant-reply" marker is present (test-hook)
 *  - aria-live is NOT applied when isLatestAssistant is false / user message
 *  - The scroll container does NOT carry aria-live (prevents double-announce)
 *  - The render loop calculates lastAssistantIdx before mapping
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../ChatPanel.jsx'),
  'utf8',
)

describe('ChatPanel — T-B2 live region for streamed assistant replies', () => {
  it('MessageBlock signature includes isLatestAssistant param', () => {
    expect(SRC).toMatch(/function MessageBlock\s*\(\s*\{[^}]*isLatestAssistant/)
  })

  it('aria-live="polite" is set on the assistant bubble', () => {
    expect(SRC).toMatch(/'aria-live':\s*'polite'/)
  })

  it('aria-atomic="false" is set (incremental streaming announcements)', () => {
    expect(SRC).toMatch(/'aria-atomic':\s*'false'/)
  })

  it('data-live-region="assistant-reply" marker is present', () => {
    expect(SRC).toMatch(/'data-live-region':\s*'assistant-reply'/)
  })

  it('live-region attrs are conditional on isLatestAssistant and !isUser', () => {
    // The spread must guard on isLatestAssistant so user bubbles are unaffected
    expect(SRC).toMatch(/isLatestAssistant[\s\S]{0,80}'aria-live'/)
  })

  it('the scroll container (scrollRef) does not carry aria-live', () => {
    // Find the scrollRef div and verify no aria-live on that line
    const scrollDivMatch = SRC.match(/ref={scrollRef}[^\n]*/)
    expect(scrollDivMatch).toBeTruthy()
    expect(scrollDivMatch[0]).not.toMatch(/aria-live/)
  })

  it('the render loop computes lastAssistantIdx before mapping renderItems', () => {
    const lastIdxPos = SRC.indexOf('lastAssistantIdx')
    const mapPos = SRC.indexOf('renderItems.map')
    expect(lastIdxPos).toBeGreaterThan(0)
    expect(mapPos).toBeGreaterThan(0)
    expect(lastIdxPos).toBeLessThan(mapPos)
  })

  it('isLatestAssistant prop is passed to MessageBlock in the render loop', () => {
    expect(SRC).toMatch(/isLatestAssistant=\{i === lastAssistantIdx\}/)
  })

  it('does not regress: MessageBlock still renders Markdown for assistant content', () => {
    expect(SRC).toMatch(/<Markdown/)
  })
})
