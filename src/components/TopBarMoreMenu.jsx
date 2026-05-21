// TopBarMoreMenu.jsx — T-L2 priority+ overflow menu for the Editor top-bar.
//
// Visible only at widths where the inline button row has had to elide
// lower-priority actions (i.e. < xl in the current breakpoint mapping). The
// caller passes `children` — those are the same action <button>s that
// appear inline, each with their own breakpoint-conditional visibility
// class (`inline-flex md:hidden` / `inline-flex lg:hidden` / etc.). When
// the popup mounts, only the ones not visible inline at the current width
// remain visible inside the popup, which is the priority+ pattern.
//
// Accessibility contract (T-L2):
//   - Trigger has aria-haspopup="menu" + aria-expanded (live) + aria-label
//   - Popup has role="menu" + aria-label
//   - ArrowDown/ArrowUp cycle focus through role="menuitem" children
//   - Home/End jump to first/last menuitem
//   - Escape closes + returns focus to trigger
//   - Click-outside closes
//   - Auto-closes when a menuitem is clicked (via bubbled click delegation)

import { useEffect, useRef, useState, useCallback } from 'react'
import { MoreHorizontal } from 'lucide-react'

// Exported so tests can import it without mounting the full Editor component.
export function TopBarMoreMenu({ children, hiddenFrom = 'xl' }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const buttonRef = useRef(null)
  const menuRef = useRef(null)

  // ── Keyboard: arrow navigation + Escape ──────────────────────────────────
  const handleMenuKeyDown = useCallback((e) => {
    if (!menuRef.current) return
    const items = Array.from(
      menuRef.current.querySelectorAll('[role="menuitem"]:not([disabled])')
    )
    if (!items.length) return

    const focused = document.activeElement
    const idx = items.indexOf(focused)

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = idx < items.length - 1 ? items[idx + 1] : items[0]
      next.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const prev = idx > 0 ? items[idx - 1] : items[items.length - 1]
      prev.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      items[0].focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      items[items.length - 1].focus()
    } else if (e.key === 'Tab') {
      // Tab moves to the next tabbable in the document — close the menu
      // so focus doesn't wander into invisible items.
      setOpen(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return

    function onDocMouseDown(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    function onDocKey(e) {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus?.()
      }
    }

    window.addEventListener('mousedown', onDocMouseDown)
    window.addEventListener('keydown', onDocKey)
    return () => {
      window.removeEventListener('mousedown', onDocMouseDown)
      window.removeEventListener('keydown', onDocKey)
    }
  }, [open])

  // Move focus to first menuitem when the menu opens.
  useEffect(() => {
    if (!open || !menuRef.current) return
    const first = menuRef.current.querySelector('[role="menuitem"]:not([disabled])')
    first?.focus?.()
  }, [open])

  const hiddenClass = `relative ${hiddenFrom}:hidden`

  return (
    <div ref={wrapRef} className={hiddenClass} data-testid="topbar-more-menu">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions"
        data-testid="topbar-more-trigger"
        className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
      >
        <MoreHorizontal size={14} aria-hidden="true" />
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="More actions"
          data-testid="topbar-more-popup"
          className="absolute right-0 top-full mt-1 z-40 min-w-[180px] bg-ink-900 border border-ink-700 rounded-md shadow-xl py-1"
          onKeyDown={handleMenuKeyDown}
          onClick={(e) => {
            // Auto-close after a menuitem click so the trigger doesn't have
            // to wire this explicitly.
            const t = e.target
            if (t && t.closest && t.closest('[role="menuitem"]')) setOpen(false)
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

export default TopBarMoreMenu
