/**
 * MobileNavSheet — a slide-up drawer for mobile navigation.
 *
 * The drawer slides up from the bottom of the screen when `open` is true and
 * slides back down when it is false.  It is fully accessible:
 *   - aria-hidden reflects the open/closed state so screen readers skip
 *     the drawer when it is not visible.
 *   - role="dialog" + aria-modal="true" trap focus semantically.
 *   - A labelled close button is always rendered inside the sheet.
 *   - An optional translucent backdrop closes the sheet on click.
 *
 * Props
 * -----
 *   open          {boolean}  — controls visibility (required)
 *   onClose       {function} — called when the close button or backdrop is
 *                              clicked.  Also called on Escape key.
 *   title         {string}   — accessible name for the dialog (default: 'Navigation')
 *   className     {string}   — extra classes on the sheet panel
 *   children      {node}     — nav links / any content
 *
 * Usage
 * -----
 *   const [navOpen, setNavOpen] = useState(false)
 *
 *   <MobileNavSheet open={navOpen} onClose={() => setNavOpen(false)} title="Menu">
 *     <nav>…</nav>
 *   </MobileNavSheet>
 */

import { useEffect, useRef } from 'react'
import clsx from 'clsx'

export default function MobileNavSheet({
  open,
  onClose,
  title = 'Navigation',
  className,
  children,
}) {
  const panelRef = useRef(null)

  // Close on Escape key.
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Trap focus inside the sheet when open.
  useEffect(() => {
    if (!open || !panelRef.current) return
    const focusable = panelRef.current.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )
    if (focusable.length) focusable[0].focus()
  }, [open])

  // Lock body scroll while the sheet is open.
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  const labelId = 'mobile-nav-sheet-title'

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className={clsx(
          'fixed inset-0 z-40 bg-ink-950/60 backdrop-blur-sm',
          'transition-opacity duration-300',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        )}
      />

      {/* Sheet panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        aria-hidden={!open}
        className={clsx(
          'fixed inset-x-0 bottom-0 z-50',
          'flex flex-col',
          'bg-ink-900 border-t border-ink-700',
          'rounded-t-2xl shadow-2xl',
          'max-h-[85dvh] overflow-y-auto',
          // Slide-up / slide-down animation via translate.
          'transition-transform duration-300 ease-out',
          open ? 'translate-y-0' : 'translate-y-full',
          className,
        )}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1 shrink-0" aria-hidden="true">
          <span className="w-10 h-1 rounded-full bg-ink-600" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800 shrink-0">
          <h2
            id={labelId}
            className="text-sm font-semibold text-ink-100 tracking-tight"
          >
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close navigation"
            onClick={onClose}
            className={clsx(
              'grid place-items-center w-8 h-8 rounded-lg',
              'text-ink-400 hover:text-ink-100 hover:bg-ink-800',
              'transition-colors duration-150',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50',
            )}
          >
            {/* ✕ icon rendered as SVG so no icon-lib dependency is added */}
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M1 1l12 12M13 1L1 13"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {children}
        </div>
      </div>
    </>
  )
}
