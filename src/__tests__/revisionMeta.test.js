// revisionMeta.test.js — covers the per-source metadata helpers used by the
// History/Revision drawer to render source pills, avatars, and accent colors.

import { describe, it, expect } from 'vitest'
import { Sparkles, User, Wrench, RotateCcw } from 'lucide-react'
import { sourceMeta, sourceTag } from '../lib/revisionMeta.js'

describe('sourceMeta', () => {
  it('returns the user variant for source="user"', () => {
    const m = sourceMeta('user')
    expect(m.label).toBe('You')
    expect(m.icon).toBe(User)
    expect(m.accent).toBe('text-kerf-300')
  })

  it('returns the llm variant for source="llm"', () => {
    const m = sourceMeta('llm')
    expect(m.label).toBe('AI')
    expect(m.icon).toBe(Sparkles)
    expect(m.accent).toBe('text-purple-300')
  })

  it('returns the tool variant for source="tool"', () => {
    const m = sourceMeta('tool')
    expect(m.label).toBe('Tool')
    expect(m.icon).toBe(Wrench)
  })

  it('returns the restore variant for source="restore"', () => {
    const m = sourceMeta('restore')
    expect(m.label).toBe('Restore')
    expect(m.icon).toBe(RotateCcw)
    expect(m.accent).toBe('text-blue-300')
  })

  it('falls back to a generic Edit shape for unknown sources', () => {
    const m = sourceMeta('mystery')
    // Falls back, but stamps the unknown source name as the label.
    expect(m.label).toBe('mystery')
    expect(m.icon).toBe(User)
    expect(m.accent).toBe('text-ink-300')
  })

  it('falls back to label="Edit" when source is null/undefined/empty', () => {
    expect(sourceMeta(null).label).toBe('Edit')
    expect(sourceMeta(undefined).label).toBe('Edit')
    expect(sourceMeta('').label).toBe('Edit')
  })

  it('exposes both pill and avatar tailwind classes for every variant', () => {
    for (const source of ['user', 'llm', 'tool', 'restore']) {
      const m = sourceMeta(source)
      expect(m.pillBg).toMatch(/^bg-/)
      expect(m.avatarBg).toMatch(/^bg-/)
      expect(m.avatarFg).toMatch(/^text-/)
    }
  })
})

describe('sourceTag', () => {
  it('mirrors sourceMeta into the legacy {label, icon, className} shape', () => {
    const tag = sourceTag('llm')
    expect(tag).toEqual({
      label: 'AI',
      icon: Sparkles,
      className: 'text-purple-300',
    })
  })

  it('falls back consistently with sourceMeta for unknown sources', () => {
    const tag = sourceTag(null)
    expect(tag.label).toBe('Edit')
    expect(tag.className).toBe('text-ink-300')
  })

  it('preserves the unknown-source label in the tag form', () => {
    expect(sourceTag('agent').label).toBe('agent')
  })
})
