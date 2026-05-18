// viewportKeybinds.js — Blender-style viewport keyboard shortcut dispatcher.
//
// Usage:
//   import { DEFAULT_BINDINGS, dispatchKey } from './viewportKeybinds.js'
//
//   // In a keydown handler:
//   const action = dispatchKey(event, DEFAULT_BINDINGS)
//   if (action) handleViewportAction(action)
//
// A binding entry describes a single keystroke or chord:
//   { key, shift?, ctrl?, alt?, meta? } → actionName
//
// `key` is matched against event.key (case-insensitive for single letters,
// exact match for special keys like 'Escape', 'Tab', etc.).
//
// Bindings are plain JSON-serialisable objects so they can be persisted and
// overridden by users at runtime.

// ── Action constants ──────────────────────────────────────────────────────────

export const ACTIONS = {
  // Numpad view presets (match Blender numpad layout)
  VIEW_FRONT:    'view_front',    // Numpad 1
  VIEW_RIGHT:    'view_right',    // Numpad 3
  VIEW_TOP:      'view_top',      // Numpad 7
  VIEW_CAMERA:   'view_camera',   // Numpad 0

  // Projection toggle
  TOGGLE_ORTHO:  'toggle_ortho',  // Numpad 5

  // Transform modes
  TRANSLATE:     'translate',     // G
  ROTATE:        'rotate',        // R
  SCALE:         'scale',         // S

  // Viewport shading
  WIREFRAME:        'wireframe',        // Z
  RENDERED_SHADING: 'rendered_shading', // Shift+Z

  // Panel / mode toggles
  TOGGLE_GIZMO: 'toggle_gizmo', // T
  PIE_MENU:     'pie_menu',      // ~  (key: '`' in most layouts, also '~')
  EDIT_MODE:    'edit_mode',     // Tab

  // Escape / cancel
  CANCEL:       'cancel',        // Escape
}

// ── Default Blender-style bindings ────────────────────────────────────────────
//
// Each entry: { key, shift?, ctrl?, alt?, meta?, action }
// Modifier fields default to false when absent (treated as false).

export const DEFAULT_BINDINGS = [
  // --- Numpad view presets ---
  { key: '1',      action: ACTIONS.VIEW_FRONT   },
  { key: '3',      action: ACTIONS.VIEW_RIGHT   },
  { key: '7',      action: ACTIONS.VIEW_TOP     },
  { key: '0',      action: ACTIONS.VIEW_CAMERA  },

  // Toggle orthographic / perspective
  { key: '5',      action: ACTIONS.TOGGLE_ORTHO },

  // Transform modes (letter keys, no modifiers)
  { key: 'g',      action: ACTIONS.TRANSLATE    },
  { key: 'r',      action: ACTIONS.ROTATE       },
  { key: 's',      action: ACTIONS.SCALE        },

  // Shading toggles
  { key: 'z',                      action: ACTIONS.WIREFRAME        },
  { key: 'z', shift: true,         action: ACTIONS.RENDERED_SHADING },

  // Panel / mode toggles
  { key: 't',      action: ACTIONS.TOGGLE_GIZMO },
  { key: '`',      action: ACTIONS.PIE_MENU     }, // unshifted tilde/backtick
  { key: '~',      action: ACTIONS.PIE_MENU     }, // shifted form on some layouts
  { key: 'Tab',    action: ACTIONS.EDIT_MODE    },

  // Cancel
  { key: 'Escape', action: ACTIONS.CANCEL       },
]

// ── dispatchKey ───────────────────────────────────────────────────────────────

/**
 * Match a KeyboardEvent against a bindings list and return the action name.
 *
 * @param {KeyboardEvent|{key:string,shiftKey?:boolean,ctrlKey?:boolean,altKey?:boolean,metaKey?:boolean}} event
 * @param {Array<{key:string,shift?:boolean,ctrl?:boolean,alt?:boolean,meta?:boolean,action:string}>} bindings
 * @returns {string|null} action name, or null if no binding matched
 */
export function dispatchKey(event, bindings) {
  if (!event || !bindings) return null

  // Normalise the event key for comparison.
  // Single-character keys (letters) are lowercased so bindings can be written
  // in lower-case and still match regardless of caps-lock state.
  const rawKey = event.key ?? ''
  const normalised = rawKey.length === 1 ? rawKey.toLowerCase() : rawKey

  const evShift = Boolean(event.shiftKey)
  const evCtrl  = Boolean(event.ctrlKey)
  const evAlt   = Boolean(event.altKey)
  const evMeta  = Boolean(event.metaKey)

  // Iterate from back → front so later (more-specific) entries win, but in
  // practice the list is ordered most-specific-first for readability and we
  // break on first match regardless.
  for (let i = 0; i < bindings.length; i++) {
    const b = bindings[i]

    const bKey   = b.key.length === 1 ? b.key.toLowerCase() : b.key
    const bShift = Boolean(b.shift)
    const bCtrl  = Boolean(b.ctrl)
    const bAlt   = Boolean(b.alt)
    const bMeta  = Boolean(b.meta)

    if (
      normalised === bKey &&
      evShift   === bShift &&
      evCtrl    === bCtrl  &&
      evAlt     === bAlt   &&
      evMeta    === bMeta
    ) {
      return b.action
    }
  }

  return null
}

// ── mergeBindings ─────────────────────────────────────────────────────────────

/**
 * Merge a user-supplied override list on top of a base list.
 * Overrides are appended; dispatchKey iterates from index 0, so for a clean
 * override we deduplicate: any base entry whose (key+modifiers) tuple matches
 * an override entry is removed.
 *
 * @param {Array} base
 * @param {Array} overrides
 * @returns {Array}
 */
export function mergeBindings(base, overrides) {
  if (!overrides || overrides.length === 0) return base

  const key = (b) =>
    [
      (b.key.length === 1 ? b.key.toLowerCase() : b.key),
      Boolean(b.shift),
      Boolean(b.ctrl),
      Boolean(b.alt),
      Boolean(b.meta),
    ].join('|')

  const overrideKeys = new Set(overrides.map(key))
  const filtered = base.filter((b) => !overrideKeys.has(key(b)))
  return [...filtered, ...overrides]
}
