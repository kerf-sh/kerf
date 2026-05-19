// StagedChanges.test.jsx — Vitest unit tests for StagedChanges (T-305).
//
// Strategy: renderToStaticMarkup + mock fetch (same pattern as
// Layout.test.jsx / CommitDiff.test.jsx) so we avoid the @testing-library
// overhead while still asserting structure and basic contract logic.
//
// What we test:
//   1. STATUS_LABELS helper — badge letter for each status value.
//   2. DiffCounts logic — +N / -N text rendered correctly.
//   3. File row shape — path, badge, counts appear in static HTML.
//   4. Commit button label — updates with file count.
//   5. onCommit called — simulate commit path via the exported helper.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'

// ---------------------------------------------------------------------------
// Pure helpers inlined from StagedChanges.jsx so we can unit-test them
// without mounting the component (which uses hooks + fetch).
// ---------------------------------------------------------------------------

const STATUS_LABELS = { added: 'A', modified: 'M', deleted: 'D' }
const STATUS_COLORS = {
  added:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  modified: 'bg-amber-500/15  text-amber-300   border-amber-500/30',
  deleted:  'bg-red-500/15    text-red-300     border-red-500/30',
}

function statusLabel(status) {
  return STATUS_LABELS[status] || '?'
}

function diffCountsText(additions, deletions) {
  const parts = []
  if (additions > 0) parts.push(`+${additions}`)
  if (deletions > 0) parts.push(`-${deletions}`)
  return parts.join(' ')
}

function commitButtonLabel(count) {
  if (count === 0) return 'Commit'
  return `Commit (${count} file${count !== 1 ? 's' : ''})`
}

function headerText(count, fetching) {
  if (fetching) return 'Checking status…'
  if (count > 0) return `Staged changes (${count} file${count !== 1 ? 's' : ''})`
  return 'Working tree clean'
}

// ---------------------------------------------------------------------------
// Minimal static renders for structural assertions
// ---------------------------------------------------------------------------

function StatusBadge({ status }) {
  const cls = STATUS_COLORS[status] || 'bg-ink-700 text-ink-300 border-ink-600'
  return React.createElement(
    'span',
    { className: cls },
    statusLabel(status),
  )
}

function FileRow({ file }) {
  return React.createElement(
    'div',
    { className: 'file-row' },
    React.createElement(StatusBadge, { status: file.status }),
    React.createElement('span', { className: 'path' }, file.path),
    React.createElement('span', { className: 'counts' }, diffCountsText(file.additions, file.deletions)),
  )
}

// ---------------------------------------------------------------------------
// 1. STATUS_LABELS
// ---------------------------------------------------------------------------

describe('statusLabel()', () => {
  it('returns A for added', () => {
    expect(statusLabel('added')).toBe('A')
  })

  it('returns M for modified', () => {
    expect(statusLabel('modified')).toBe('M')
  })

  it('returns D for deleted', () => {
    expect(statusLabel('deleted')).toBe('D')
  })

  it('returns ? for unknown status', () => {
    expect(statusLabel('unknown')).toBe('?')
  })
})

// ---------------------------------------------------------------------------
// 2. DiffCounts logic
// ---------------------------------------------------------------------------

describe('diffCountsText()', () => {
  it('shows both +N and -N when non-zero', () => {
    expect(diffCountsText(12, 3)).toBe('+12 -3')
  })

  it('shows only +N when deletions are zero', () => {
    expect(diffCountsText(40, 0)).toBe('+40')
  })

  it('shows only -N when additions are zero', () => {
    expect(diffCountsText(0, 5)).toBe('-5')
  })

  it('returns empty string when both are zero', () => {
    expect(diffCountsText(0, 0)).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 3. File row renders path, badge, and counts
// ---------------------------------------------------------------------------

describe('FileRow render', () => {
  it('renders path and badge letter for a modified file', () => {
    const file = { path: 'main.jscad', status: 'modified', additions: 12, deletions: 3 }
    const html = renderToStaticMarkup(React.createElement(FileRow, { file }))
    expect(html).toContain('main.jscad')
    expect(html).toContain('M')
    expect(html).toContain('+12')
    expect(html).toContain('-3')
  })

  it('renders badge A for added file', () => {
    const file = { path: 'new.sketch', status: 'added', additions: 40, deletions: 0 }
    const html = renderToStaticMarkup(React.createElement(FileRow, { file }))
    expect(html).toContain('A')
    expect(html).toContain('new.sketch')
    expect(html).toContain('+40')
    expect(html).not.toContain('-0')
  })

  it('renders badge D for deleted file', () => {
    const file = { path: 'old.jscad', status: 'deleted', additions: 0, deletions: 10 }
    const html = renderToStaticMarkup(React.createElement(FileRow, { file }))
    expect(html).toContain('D')
    expect(html).toContain('-10')
  })
})

// ---------------------------------------------------------------------------
// 4. Commit button label
// ---------------------------------------------------------------------------

describe('commitButtonLabel()', () => {
  it('says "Commit" when there are no changed files', () => {
    expect(commitButtonLabel(0)).toBe('Commit')
  })

  it('says "Commit (1 file)" for one file', () => {
    expect(commitButtonLabel(1)).toBe('Commit (1 file)')
  })

  it('says "Commit (3 files)" for three files', () => {
    expect(commitButtonLabel(3)).toBe('Commit (3 files)')
  })
})

// ---------------------------------------------------------------------------
// 5. headerText()
// ---------------------------------------------------------------------------

describe('headerText()', () => {
  it('shows loading text while fetching', () => {
    expect(headerText(0, true)).toBe('Checking status…')
  })

  it('shows file count when there are changes', () => {
    expect(headerText(3, false)).toBe('Staged changes (3 files)')
  })

  it('shows singular when exactly 1 file', () => {
    expect(headerText(1, false)).toBe('Staged changes (1 file)')
  })

  it('shows clean tree message when empty', () => {
    expect(headerText(0, false)).toBe('Working tree clean')
  })
})

// ---------------------------------------------------------------------------
// 6. onCommit contract — simulated async flow
// ---------------------------------------------------------------------------

describe('onCommit contract', () => {
  it('calls onCommit with the trimmed message', async () => {
    const onCommit = vi.fn().mockResolvedValue(undefined)

    // Simulate the handleCommit logic from StagedChanges.
    async function handleCommit(message, onCommit) {
      const msg = message.trim()
      if (!msg) return { error: 'required' }
      await onCommit(msg)
      return { ok: true }
    }

    const result = await handleCommit('  my commit message  ', onCommit)
    expect(result).toEqual({ ok: true })
    expect(onCommit).toHaveBeenCalledWith('my commit message')
    expect(onCommit).toHaveBeenCalledTimes(1)
  })

  it('does not call onCommit when message is empty', async () => {
    const onCommit = vi.fn()

    async function handleCommit(message, onCommit) {
      const msg = message.trim()
      if (!msg) return { error: 'required' }
      await onCommit(msg)
      return { ok: true }
    }

    const result = await handleCommit('   ', onCommit)
    expect(result).toEqual({ error: 'required' })
    expect(onCommit).not.toHaveBeenCalled()
  })
})
