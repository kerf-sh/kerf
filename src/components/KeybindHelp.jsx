// KeybindHelp.jsx — Overlay panel listing active viewport keybindings.
//
// Usage:
//   <KeybindHelp bindings={DEFAULT_BINDINGS} onClose={() => setOpen(false)} />
//
// Props:
//   bindings  — array of binding objects (same shape as DEFAULT_BINDINGS)
//   onClose   — optional callback, called when the user presses Escape or
//               clicks the close button / backdrop
//   title     — optional heading override (defaults to "Viewport Shortcuts")

import { useEffect } from 'react'
import { ACTIONS } from '../lib/viewportKeybinds.js'

// Human-readable labels for each action constant.
const ACTION_LABELS = {
  [ACTIONS.VIEW_FRONT]:       'Front view',
  [ACTIONS.VIEW_RIGHT]:       'Right view',
  [ACTIONS.VIEW_TOP]:         'Top view',
  [ACTIONS.VIEW_CAMERA]:      'Camera view',
  [ACTIONS.TOGGLE_ORTHO]:     'Toggle orthographic / perspective',
  [ACTIONS.TRANSLATE]:        'Translate (Grab)',
  [ACTIONS.ROTATE]:           'Rotate',
  [ACTIONS.SCALE]:            'Scale',
  [ACTIONS.WIREFRAME]:        'Wireframe shading',
  [ACTIONS.RENDERED_SHADING]: 'Rendered / material preview',
  [ACTIONS.TOGGLE_GIZMO]:     'Toggle gizmo panel',
  [ACTIONS.PIE_MENU]:         'Shading pie menu',
  [ACTIONS.EDIT_MODE]:        'Toggle edit mode',
  [ACTIONS.CANCEL]:           'Cancel / exit',
}

// Groups for visual organisation.
const GROUPS = [
  {
    label: 'Views',
    actions: [
      ACTIONS.VIEW_FRONT,
      ACTIONS.VIEW_RIGHT,
      ACTIONS.VIEW_TOP,
      ACTIONS.VIEW_CAMERA,
      ACTIONS.TOGGLE_ORTHO,
    ],
  },
  {
    label: 'Transform',
    actions: [ACTIONS.TRANSLATE, ACTIONS.ROTATE, ACTIONS.SCALE],
  },
  {
    label: 'Shading',
    actions: [ACTIONS.WIREFRAME, ACTIONS.RENDERED_SHADING, ACTIONS.PIE_MENU],
  },
  {
    label: 'Modes',
    actions: [ACTIONS.TOGGLE_GIZMO, ACTIONS.EDIT_MODE, ACTIONS.CANCEL],
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Format a binding object into a human-readable key chord string.
 * e.g. { key: 'z', shift: true } → 'Shift+Z'
 */
export function formatBinding(binding) {
  if (!binding) return ''
  const parts = []
  if (binding.ctrl)  parts.push('Ctrl')
  if (binding.alt)   parts.push('Alt')
  if (binding.shift) parts.push('Shift')

  const k = binding.key
  // Capitalise single letters; leave special keys (Escape, Tab, …) as-is.
  if (k.length === 1) {
    parts.push(k.toUpperCase())
  } else {
    parts.push(k)
  }

  return parts.join('+')
}

/**
 * Given a bindings array, return the first binding entry for a given action.
 */
export function bindingForAction(bindings, action) {
  return bindings.find((b) => b.action === action) ?? null
}

/**
 * Return all binding entries for a given action (an action may have multiple).
 */
export function bindingsForAction(bindings, action) {
  return bindings.filter((b) => b.action === action)
}

// ── KeyChip ───────────────────────────────────────────────────────────────────

function KeyChip({ label }) {
  if (!label) return null
  return (
    <kbd className="inline-flex items-center justify-center min-w-[2rem] h-6 px-1.5 rounded bg-ink-800 border border-ink-600 text-ink-100 text-[11px] font-mono leading-none shadow-[0_1px_0_rgba(0,0,0,0.5)]">
      {label}
    </kbd>
  )
}

// ── BindingRow ────────────────────────────────────────────────────────────────

function BindingRow({ action, bindings }) {
  const entries = bindingsForAction(bindings, action)
  const label   = ACTION_LABELS[action] ?? action

  return (
    <div className="flex items-center justify-between gap-4 py-1.5 border-b border-ink-800/60 last:border-0">
      <span className="text-ink-300 text-xs">{label}</span>
      <div className="flex items-center gap-1 shrink-0">
        {entries.length === 0 ? (
          <span className="text-ink-500 text-[11px] italic">unbound</span>
        ) : (
          entries.map((b, i) => (
            <span key={i} className="flex items-center gap-0.5">
              {i > 0 && <span className="text-ink-600 text-[10px] mx-0.5">/</span>}
              <KeyChip label={formatBinding(b)} />
            </span>
          ))
        )}
      </div>
    </div>
  )
}

// ── GroupBlock ────────────────────────────────────────────────────────────────

function GroupBlock({ group, bindings }) {
  return (
    <div>
      <h3 className="text-[10px] uppercase tracking-widest text-ink-500 font-semibold mb-1 mt-3 first:mt-0">
        {group.label}
      </h3>
      {group.actions.map((action) => (
        <BindingRow key={action} action={action} bindings={bindings} />
      ))}
    </div>
  )
}

// ── KeybindHelp ───────────────────────────────────────────────────────────────

/**
 * Floating overlay panel displaying the active viewport keybindings.
 *
 * @param {{ bindings: Array, onClose?: () => void, title?: string }} props
 */
export default function KeybindHelp({ bindings = [], onClose, title = 'Viewport Shortcuts' }) {
  // Close on Escape key.
  useEffect(() => {
    if (!onClose) return
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {/* Panel — stop backdrop click propagation */}
      <div
        className="relative w-80 max-h-[80vh] overflow-y-auto rounded-xl bg-ink-900 border border-ink-700 shadow-2xl p-4 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
          {onClose && (
            <button
              onClick={onClose}
              className="text-ink-400 hover:text-ink-100 transition-colors rounded p-0.5"
              aria-label="Close shortcuts panel"
              type="button"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path
                  d="M1 1l12 12M13 1L1 13"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          )}
        </div>

        {/* Binding groups */}
        {GROUPS.map((group) => (
          <GroupBlock key={group.label} group={group} bindings={bindings} />
        ))}
      </div>
    </div>
  )
}
