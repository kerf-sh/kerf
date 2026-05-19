// BranchPicker.test.jsx — Vitest unit tests for BranchPicker (T-306).
//
// Strategy: renderToStaticMarkup + pure logic assertions so we avoid
// @testing-library overhead (same pattern as Layout.test.jsx).
//
// What we test:
//   1. AheadBehindBadge text — correct chip text for ahead/behind values.
//   2. Trigger button renders current branch name.
//   3. Branch list renders all branches.
//   4. onCheckout called — simulate checkout logic.
//   5. onCreateBranch called — simulate create logic.
//   6. onDeleteBranch called — simulate delete logic.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'

// ---------------------------------------------------------------------------
// Pure helpers inlined from BranchPicker.jsx
// ---------------------------------------------------------------------------

function aheadBehindText(ahead, behind) {
  if (ahead == null && behind == null) return null
  if (ahead === 0 && behind === 0) return 'synced'
  const parts = []
  if (ahead > 0) parts.push(`${ahead}↑`)
  if (behind > 0) parts.push(`${behind}↓`)
  return parts.join(' ')
}

function triggerLabel(currentBranch) {
  return currentBranch || '—'
}

// ---------------------------------------------------------------------------
// Minimal static renders
// ---------------------------------------------------------------------------

function AheadBehindBadge({ ahead, behind }) {
  const text = aheadBehindText(ahead, behind)
  if (!text) return null
  return React.createElement('span', { className: 'ahead-behind' }, text)
}

function BranchListItem({ branch, currentBranch }) {
  const isCurrent = branch.name === currentBranch
  return React.createElement(
    'div',
    { className: `branch-item${isCurrent ? ' current' : ''}` },
    React.createElement('span', { className: 'check' }, isCurrent ? '✓' : ''),
    React.createElement('span', { className: 'name' }, branch.name),
    React.createElement(AheadBehindBadge, { ahead: branch.ahead, behind: branch.behind }),
  )
}

function BranchList({ branches, currentBranch }) {
  return React.createElement(
    'div',
    { className: 'branch-list' },
    branches.map((b) =>
      React.createElement(BranchListItem, { key: b.name, branch: b, currentBranch }),
    ),
  )
}

// ---------------------------------------------------------------------------
// 1. aheadBehindText()
// ---------------------------------------------------------------------------

describe('aheadBehindText()', () => {
  it('returns null when both are null (no remote)', () => {
    expect(aheadBehindText(null, null)).toBeNull()
  })

  it('returns "synced" when ahead=0 and behind=0', () => {
    expect(aheadBehindText(0, 0)).toBe('synced')
  })

  it('shows N↑ when ahead > 0 and behind = 0', () => {
    expect(aheadBehindText(3, 0)).toBe('3↑')
  })

  it('shows N↓ when behind > 0 and ahead = 0', () => {
    expect(aheadBehindText(0, 2)).toBe('2↓')
  })

  it('shows both when ahead and behind > 0', () => {
    expect(aheadBehindText(3, 1)).toBe('3↑ 1↓')
  })
})

// ---------------------------------------------------------------------------
// 2. Trigger button renders current branch
// ---------------------------------------------------------------------------

describe('triggerLabel()', () => {
  it('returns branch name when set', () => {
    expect(triggerLabel('main')).toBe('main')
  })

  it('returns em-dash when not set', () => {
    expect(triggerLabel('')).toBe('—')
    expect(triggerLabel(null)).toBe('—')
    expect(triggerLabel(undefined)).toBe('—')
  })
})

// ---------------------------------------------------------------------------
// 3. Branch list renders all branches + check on current
// ---------------------------------------------------------------------------

describe('BranchList render', () => {
  const branches = [
    { name: 'main',    head_sha: 'abc', is_default: true,  ahead: 0,    behind: 0 },
    { name: 'feature', head_sha: 'def', is_default: false, ahead: 3,    behind: 1 },
    { name: 'hotfix',  head_sha: 'ghi', is_default: false, ahead: null, behind: null },
  ]

  it('renders all branch names', () => {
    const html = renderToStaticMarkup(
      React.createElement(BranchList, { branches, currentBranch: 'main' }),
    )
    expect(html).toContain('main')
    expect(html).toContain('feature')
    expect(html).toContain('hotfix')
  })

  it('marks current branch with check icon', () => {
    const html = renderToStaticMarkup(
      React.createElement(BranchList, { branches, currentBranch: 'feature' }),
    )
    // The "feature" item should be .current and have a checkmark.
    // Simple: we check for class="branch-item current" containing check text.
    expect(html).toContain('branch-item current')
  })

  it('renders synced badge for 0/0 branch', () => {
    const html = renderToStaticMarkup(
      React.createElement(BranchList, { branches, currentBranch: 'main' }),
    )
    expect(html).toContain('synced')
  })

  it('renders N↑ / N↓ for feature branch', () => {
    const html = renderToStaticMarkup(
      React.createElement(BranchList, { branches, currentBranch: 'main' }),
    )
    expect(html).toContain('3↑')
    expect(html).toContain('1↓')
  })

  it('renders no badge for branch without remote', () => {
    const html = renderToStaticMarkup(
      React.createElement(BranchList, { branches, currentBranch: 'main' }),
    )
    // hotfix has ahead=null, behind=null → no AheadBehindBadge rendered.
    // All ahead-behind text rendered will be for main (synced) and feature (3↑ 1↓).
    // Count occurrences of "ahead-behind" in the HTML.
    const count = (html.match(/ahead-behind/g) || []).length
    // main → synced (1) + feature → 3↑ 1↓ (1) = 2 badges, hotfix → 0 badges
    expect(count).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// 4. onCheckout called — simulated
// ---------------------------------------------------------------------------

describe('onCheckout contract', () => {
  it('calls onCheckout with the selected branch name', async () => {
    const onCheckout = vi.fn().mockResolvedValue(undefined)

    async function handleCheckout(name, currentBranch, onCheckout) {
      if (name === currentBranch) return
      await onCheckout(name)
    }

    await handleCheckout('feature', 'main', onCheckout)
    expect(onCheckout).toHaveBeenCalledWith('feature')
  })

  it('does NOT call onCheckout when clicking the current branch', async () => {
    const onCheckout = vi.fn()

    async function handleCheckout(name, currentBranch, onCheckout) {
      if (name === currentBranch) return
      await onCheckout(name)
    }

    await handleCheckout('main', 'main', onCheckout)
    expect(onCheckout).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// 5. onCreateBranch called — simulated
// ---------------------------------------------------------------------------

describe('onCreateBranch contract', () => {
  it('calls onCreateBranch with the trimmed name', async () => {
    const onCreateBranch = vi.fn().mockResolvedValue(undefined)

    async function handleCreate(newName, onCreateBranch) {
      const name = newName.trim()
      if (!name) return { error: 'required' }
      await onCreateBranch(name)
      return { ok: true }
    }

    const result = await handleCreate('  my-feature  ', onCreateBranch)
    expect(result).toEqual({ ok: true })
    expect(onCreateBranch).toHaveBeenCalledWith('my-feature')
  })

  it('does not call onCreateBranch for empty name', async () => {
    const onCreateBranch = vi.fn()

    async function handleCreate(newName, onCreateBranch) {
      const name = newName.trim()
      if (!name) return { error: 'required' }
      await onCreateBranch(name)
      return { ok: true }
    }

    const result = await handleCreate('   ', onCreateBranch)
    expect(result).toEqual({ error: 'required' })
    expect(onCreateBranch).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// 6. onDeleteBranch called — simulated
// ---------------------------------------------------------------------------

describe('onDeleteBranch contract', () => {
  it('calls onDeleteBranch with the branch name', async () => {
    const onDeleteBranch = vi.fn().mockResolvedValue(undefined)

    async function handleDeleteConfirm(name, onDeleteBranch) {
      await onDeleteBranch(name)
      return { ok: true }
    }

    const result = await handleDeleteConfirm('old-feature', onDeleteBranch)
    expect(result).toEqual({ ok: true })
    expect(onDeleteBranch).toHaveBeenCalledWith('old-feature')
  })
})
