/**
 * revisionPreview.test.js — vitest unit tests for the lazy-preview helpers.
 *
 * Covers:
 *   - formatPreview: whitespace collapse, truncation, ellipsis, empty/null.
 *   - truncateContent: no-op on short content, truncation on long content.
 *   - revisionDisplayPreview: priority order, fallback paths.
 */

import { describe, it, expect } from 'vitest'
import {
  formatPreview,
  truncateContent,
  revisionDisplayPreview,
  PREVIEW_MAX,
} from './revisionPreview.js'

// ─────────────────────────────────────────────────────────────────────────────
// formatPreview
// ─────────────────────────────────────────────────────────────────────────────

describe('formatPreview', () => {
  it('returns empty string for null input', () => {
    expect(formatPreview(null)).toBe('')
  })

  it('returns empty string for undefined input', () => {
    expect(formatPreview(undefined)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(formatPreview('')).toBe('')
  })

  it('collapses multiple spaces to one', () => {
    expect(formatPreview('hello   world')).toBe('hello world')
  })

  it('collapses newlines and tabs', () => {
    expect(formatPreview('{\n  "key": "value"\n}')).toBe('{ "key": "value" }')
  })

  it('trims leading and trailing whitespace', () => {
    expect(formatPreview('  hello  ')).toBe('hello')
  })

  it('returns short content unchanged (no truncation)', () => {
    const short = 'a'.repeat(PREVIEW_MAX - 1)
    expect(formatPreview(short)).toBe(short)
  })

  it('returns content at exact PREVIEW_MAX unchanged', () => {
    const exact = 'a'.repeat(PREVIEW_MAX)
    expect(formatPreview(exact)).toBe(exact)
  })

  it('truncates content longer than PREVIEW_MAX with ellipsis', () => {
    const long = 'a'.repeat(PREVIEW_MAX + 10)
    const result = formatPreview(long)
    expect(result).toHaveLength(PREVIEW_MAX + 1) // +1 for the '…' char
    expect(result.endsWith('…')).toBe(true)
    expect(result.slice(0, PREVIEW_MAX)).toBe('a'.repeat(PREVIEW_MAX))
  })

  it('accepts a custom maxLen', () => {
    const result = formatPreview('hello world foo bar baz', 10)
    expect(result).toBe('hello worl…')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// truncateContent
// ─────────────────────────────────────────────────────────────────────────────

describe('truncateContent', () => {
  it('returns empty string for null', () => {
    expect(truncateContent(null)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(truncateContent('')).toBe('')
  })

  it('returns short content unchanged', () => {
    const short = 'line\n'.repeat(50)
    expect(truncateContent(short)).toBe(short)
  })

  it('does NOT collapse whitespace (preserves formatting)', () => {
    const indented = '{\n  "key": "value"\n}'
    expect(truncateContent(indented)).toBe(indented)
  })

  it('truncates at maxLen and appends ellipsis', () => {
    const long = 'x'.repeat(5000)
    const result = truncateContent(long)
    expect(result.endsWith('…')).toBe(true)
    expect(result.slice(0, 4096)).toBe('x'.repeat(4096))
  })

  it('accepts a custom maxLen', () => {
    const result = truncateContent('abcdef', 3)
    expect(result).toBe('abc…')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// revisionDisplayPreview
// ─────────────────────────────────────────────────────────────────────────────

describe('revisionDisplayPreview', () => {
  it('returns empty string for null rev', () => {
    expect(revisionDisplayPreview(null)).toBe('')
  })

  it('uses content_preview when present', () => {
    const rev = { id: '1', content_preview: 'hello world', content: 'ignored' }
    expect(revisionDisplayPreview(rev)).toBe('hello world')
  })

  it('falls back to first 200 chars of content when content_preview is absent', () => {
    const rev = { id: '1', content_preview: null, content: 'fallback content here' }
    expect(revisionDisplayPreview(rev)).toBe('fallback content here')
  })

  it('returns empty string when both content_preview and content are absent', () => {
    const rev = { id: '1' }
    expect(revisionDisplayPreview(rev)).toBe('')
  })

  it('truncates a long content_preview', () => {
    const long = 'z'.repeat(PREVIEW_MAX + 50)
    const rev = { id: '1', content_preview: long }
    const result = revisionDisplayPreview(rev)
    expect(result.endsWith('…')).toBe(true)
    expect(result.slice(0, PREVIEW_MAX)).toBe('z'.repeat(PREVIEW_MAX))
  })

  it('collapses whitespace from content_preview', () => {
    const rev = { id: '1', content_preview: 'line one\nline two\n' }
    expect(revisionDisplayPreview(rev)).toBe('line one line two')
  })
})
