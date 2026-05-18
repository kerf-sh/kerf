/**
 * UncommittedBanner — T-185
 *
 * A gentle, dismissible banner that appears after 30 minutes of uncommitted
 * edits. It listens for the `uncommitted-too-long` event emitted by
 * `src/lib/dirtyTimer.js` and surfaces a one-click "Save a version" button
 * that opens the commit dialog (or calls an `onCommit` prop directly).
 *
 * TODO (marker pass): the ◯ vs ◌ dot distinction in the git graph (manual vs
 * autosave commits) is deferred to the parent GitGraph integration and requires
 * the `kind` column delivered by this ticket (T-185). Once GitGraph.jsx renders
 * commit rows it should read `commit.kind === 'autosave'` to swap the filled ◯
 * dot for a hollow ◌. No changes to GitGraph.jsx are made in this ticket.
 *
 * Props:
 *   workspaceId {string}          — current workspace; banner only shows for
 *                                   events matching this id.
 *   onCommit    {() => void}      — called when the user clicks "Save a version".
 *   className   {string}          — extra CSS classes for the root element.
 */

import { useEffect, useState, useCallback } from 'react'

export default function UncommittedBanner({ workspaceId, onCommit, className = '' }) {
  const [visible, setVisible] = useState(false)
  const [dirtyMs, setDirtyMs] = useState(0)

  useEffect(() => {
    function handleEvent(e) {
      if (!workspaceId || e.detail?.workspaceId !== workspaceId) return
      setDirtyMs(e.detail.dirtyMs ?? 0)
      setVisible(true)
    }

    window.addEventListener('uncommitted-too-long', handleEvent)
    return () => window.removeEventListener('uncommitted-too-long', handleEvent)
  }, [workspaceId])

  const handleCommit = useCallback(() => {
    setVisible(false)
    if (typeof onCommit === 'function') onCommit()
  }, [onCommit])

  const handleDismiss = useCallback(() => {
    setVisible(false)
  }, [])

  if (!visible) return null

  const dirtyMinutes = Math.round(dirtyMs / 60_000)

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        'uncommitted-banner',
        className,
      ].filter(Boolean).join(' ')}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 14px',
        background: 'var(--banner-bg, #1e2330)',
        borderLeft: '3px solid var(--banner-accent, #5BB0FF)',
        borderRadius: '4px',
        fontSize: '13px',
        color: 'var(--banner-text, #c9d1d9)',
        boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
      }}
    >
      <span style={{ flex: 1 }}>
        {dirtyMinutes >= 1
          ? `It's been ${dirtyMinutes} minute${dirtyMinutes === 1 ? '' : 's'} — save a version?`
          : "It's been a while — save a version?"}
      </span>

      <button
        onClick={handleCommit}
        style={{
          padding: '4px 12px',
          background: 'var(--banner-accent, #5BB0FF)',
          color: '#fff',
          border: 'none',
          borderRadius: '4px',
          cursor: 'pointer',
          fontWeight: 600,
          fontSize: '12px',
          whiteSpace: 'nowrap',
        }}
      >
        Save a version
      </button>

      <button
        onClick={handleDismiss}
        aria-label="Dismiss"
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--banner-text, #c9d1d9)',
          fontSize: '16px',
          lineHeight: 1,
          padding: '0 2px',
          opacity: 0.6,
        }}
      >
        ×
      </button>
    </div>
  )
}
