/**
 * ToastBus.jsx — Global toast notification system.
 *
 * Architecture
 * ────────────
 * A single event bus (module-level Map of listeners) decouples the toast
 * trigger from the UI layer. Any module can call `toast(...)` or import
 * `useToast` without needing access to a React context. The <ToastBus>
 * component subscribes to the bus, owns the toast list in local state, and
 * renders the overlay.
 *
 * This keeps toast calls simple:
 *   import { toast } from '@/components/ToastBus'
 *   toast.success('Saved!')
 *   toast.error('Upload failed', { duration: 0 })  // 0 = persist until dismissed
 *
 * Public API
 * ──────────
 *   <ToastBus />       — Mount once at the app root (outside any scroll containers).
 *
 *   toast(message, options?)        — show an 'info' toast
 *   toast.success(message, options?) — show a 'success' toast
 *   toast.error(message, options?)   — show an 'error' toast
 *   toast.warning(message, options?) — show a 'warning' toast
 *
 *   options:
 *     - duration: number  ms until auto-dismiss. Default 4000. 0 = never.
 *     - id: string        Deduplicate by ID (2nd call with same ID replaces 1st).
 *
 *   useToast() → { toasts, dismiss, add, pause, resume }
 *     React hook for components that need direct access to the toast list.
 *     - toasts:  ToastEntry[]  Current live toasts
 *     - dismiss: (id) => void  Remove a toast by ID
 *     - add:     (msg, opts) => string  Add a toast; returns its ID
 *     - pause:   (id) => void  Pause auto-dismiss timer (e.g. on hover/focus)
 *     - resume:  (id) => void  Resume auto-dismiss with remaining time
 *
 *   dismissToast(id) — programmatic dismiss without the hook
 *
 * Toast entry shape
 * ─────────────────
 *   { id, message, variant, duration, createdAt }
 *   variant: 'info' | 'success' | 'error' | 'warning'
 *
 * Accessibility
 * ─────────────
 *   - Toasts use role="status" for info/success and role="alert" for
 *     error/warning so AT announces them at the appropriate urgency.
 *   - aria-live="polite" (info/success) / aria-live="assertive" (error/warning).
 *   - Dismiss button has aria-label="Dismiss notification".
 *   - Esc key dismisses the toast when focus is anywhere inside it.
 *   - Auto-dismiss is paused on mouse hover or keyboard focus, and resumes
 *     (with the remaining time) when the pointer or focus leaves.
 *   - The container is positioned fixed in the viewport corner and does not
 *     trap focus; users can dismiss with the close button, Esc, or wait for
 *     auto-dismiss.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import clsx from 'clsx'
import { X, CheckCircle, AlertTriangle, Info, XCircle } from 'lucide-react'

// ── Bus ───────────────────────────────────────────────────────────────────────

let _listeners = new Set()
let _toastIdCounter = 0

function nextToastId() {
  _toastIdCounter += 1
  return `toast-${_toastIdCounter}`
}

/**
 * Internal: broadcast a toast to all mounted ToastBus instances.
 *
 * @param {string} message
 * @param {{ variant?: string, duration?: number, id?: string }} options
 * @returns {string} the toast's ID
 */
function _emit(message, options = {}) {
  const entry = {
    id: options.id ?? nextToastId(),
    message,
    variant: options.variant ?? 'info',
    duration: options.duration !== undefined ? options.duration : 4000,
    createdAt: Date.now(),
  }
  for (const fn of _listeners) fn({ type: 'add', entry })
  return entry.id
}

function _emitDismiss(id) {
  for (const fn of _listeners) fn({ type: 'dismiss', id })
}

// ── Public imperative API ─────────────────────────────────────────────────────

export function toast(message, options) {
  return _emit(message, { ...options, variant: 'info' })
}
toast.success = (message, options) => _emit(message, { ...options, variant: 'success' })
toast.error   = (message, options) => _emit(message, { ...options, variant: 'error' })
toast.warning = (message, options) => _emit(message, { ...options, variant: 'warning' })

export function dismissToast(id) {
  _emitDismiss(id)
}

/**
 * Reset the bus (clears listeners and resets counter).
 * FOR TESTS ONLY.
 */
export function _resetBus() {
  _listeners = new Set()
  _toastIdCounter = 0
}

// ── useToast hook ─────────────────────────────────────────────────────────────

/**
 * React hook that provides access to the toast list and imperative controls.
 *
 * @returns {{ toasts: ToastEntry[], dismiss: (id: string) => void, add: (msg: string, opts?: object) => string, pause: (id: string) => void, resume: (id: string) => void }}
 */
export function useToast() {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef({})
  // Track remaining time when a toast is paused { id: remainingMs }
  const pausedRef = useRef({})
  // Track when each timer started { id: startTimestamp }
  const timerStartRef = useRef({})
  // Track the full duration for each active timer { id: durationMs }
  const timerDurationRef = useRef({})

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    clearTimeout(timersRef.current[id])
    delete timersRef.current[id]
    delete pausedRef.current[id]
    delete timerStartRef.current[id]
    delete timerDurationRef.current[id]
  }, [])

  const scheduleAutoDismiss = useCallback(
    (id, duration) => {
      if (duration <= 0) return
      clearTimeout(timersRef.current[id])
      timerStartRef.current[id] = Date.now()
      timerDurationRef.current[id] = duration
      timersRef.current[id] = setTimeout(() => dismiss(id), duration)
    },
    [dismiss],
  )

  /**
   * Pause the auto-dismiss timer for a toast (e.g. on hover/focus).
   * Stores remaining time so resume() can restore it accurately.
   */
  const pause = useCallback((id) => {
    if (!timersRef.current[id]) return
    clearTimeout(timersRef.current[id])
    delete timersRef.current[id]
    const elapsed = Date.now() - (timerStartRef.current[id] ?? Date.now())
    const remaining = Math.max(0, (timerDurationRef.current[id] ?? 0) - elapsed)
    pausedRef.current[id] = remaining
  }, [])

  /**
   * Resume the auto-dismiss timer with the remaining time.
   */
  const resume = useCallback(
    (id) => {
      const remaining = pausedRef.current[id]
      if (remaining == null) return
      delete pausedRef.current[id]
      scheduleAutoDismiss(id, remaining)
    },
    [scheduleAutoDismiss],
  )

  const add = useCallback(
    (message, options = {}) => {
      const id = options.id ?? nextToastId()
      const entry = {
        id,
        message,
        variant: options.variant ?? 'info',
        duration: options.duration !== undefined ? options.duration : 4000,
        createdAt: Date.now(),
      }
      setToasts((prev) => {
        // Replace if same ID; otherwise append
        const exists = prev.some((t) => t.id === id)
        return exists ? prev.map((t) => (t.id === id ? entry : t)) : [...prev, entry]
      })
      if (entry.duration > 0) {
        clearTimeout(timersRef.current[id])
        scheduleAutoDismiss(id, entry.duration)
      }
      return id
    },
    [scheduleAutoDismiss],
  )

  // Subscribe to bus events
  useEffect(() => {
    function handler(event) {
      if (event.type === 'add') {
        const { entry } = event
        setToasts((prev) => {
          const exists = prev.some((t) => t.id === entry.id)
          return exists
            ? prev.map((t) => (t.id === entry.id ? entry : t))
            : [...prev, entry]
        })
        if (entry.duration > 0) {
          clearTimeout(timersRef.current[entry.id])
          scheduleAutoDismiss(entry.id, entry.duration)
        }
      } else if (event.type === 'dismiss') {
        dismiss(event.id)
      }
    }

    _listeners.add(handler)
    return () => {
      _listeners.delete(handler)
      // Clear all pending timers on unmount
      for (const timer of Object.values(timersRef.current)) {
        clearTimeout(timer)
      }
    }
  }, [dismiss, scheduleAutoDismiss])

  return { toasts, dismiss, add, pause, resume }
}

// ── Toast UI primitives ───────────────────────────────────────────────────────

export const VARIANT_CONFIG = {
  info: {
    icon: Info,
    role: 'status',
    live: 'polite',
    iconClass: 'text-kerf-300',
    borderClass: 'border-kerf-700/60',
  },
  success: {
    icon: CheckCircle,
    role: 'status',
    live: 'polite',
    iconClass: 'text-green-400',
    borderClass: 'border-green-700/60',
  },
  error: {
    icon: XCircle,
    role: 'alert',
    live: 'assertive',
    iconClass: 'text-red-400',
    borderClass: 'border-red-700/60',
  },
  warning: {
    icon: AlertTriangle,
    role: 'alert',
    live: 'assertive',
    iconClass: 'text-amber-400',
    borderClass: 'border-amber-700/60',
  },
}

function ToastItem({ entry, onDismiss, onPause, onResume }) {
  const config = VARIANT_CONFIG[entry.variant] ?? VARIANT_CONFIG.info
  const Icon = config.icon

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onDismiss(entry.id)
    }
  }

  return (
    <div
      role={config.role}
      aria-live={config.live}
      // Keyboard: Esc dismisses when any element inside the toast is focused
      onKeyDown={handleKeyDown}
      // Hover/focus: pause auto-dismiss so users with slower reading speeds
      // can read without the toast disappearing under them.
      onMouseEnter={() => onPause?.(entry.id)}
      onMouseLeave={() => onResume?.(entry.id)}
      onFocusCapture={() => onPause?.(entry.id)}
      onBlurCapture={() => onResume?.(entry.id)}
      className={clsx(
        'flex items-start gap-3 w-full max-w-sm',
        'bg-ink-800 border rounded-xl px-4 py-3',
        'shadow-[0_4px_24px_rgba(0,0,0,0.5)]',
        config.borderClass,
      )}
    >
      <Icon
        size={18}
        aria-hidden="true"
        className={clsx('shrink-0 mt-0.5', config.iconClass)}
      />
      <p className="flex-1 text-sm text-ink-100 leading-snug">{entry.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(entry.id)}
        aria-label="Dismiss notification"
        className={clsx(
          'shrink-0 -mr-1 -mt-0.5 rounded-md p-1',
          'text-ink-400 hover:text-ink-100 hover:bg-ink-700',
          'transition-colors duration-100',
          'focus:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300/50',
        )}
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  )
}

// ── ToastBus component (mounts once at app root) ─────────────────────────────

export default function ToastBus() {
  const { toasts, dismiss, pause, resume } = useToast()

  if (toasts.length === 0) return null

  return (
    <div
      aria-label="Notifications"
      className={clsx(
        'fixed bottom-6 right-6 z-[10000]',
        'flex flex-col items-end gap-2',
        'pointer-events-none',
      )}
    >
      {toasts.map((entry) => (
        <div key={entry.id} className="pointer-events-auto">
          <ToastItem entry={entry} onDismiss={dismiss} onPause={pause} onResume={resume} />
        </div>
      ))}
    </div>
  )
}
