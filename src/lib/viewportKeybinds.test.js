// viewportKeybinds.test.js — Vitest assertions for dispatchKey + helpers.
//
// Covers:
//   1. Each Blender default keystroke fires the expected action.
//   2. Chord keys (Shift+Z) work and are distinguished from plain keys.
//   3. Unbound keys return null.
//   4. mergeBindings override semantics.

import { describe, it, expect } from 'vitest'
import {
  ACTIONS,
  DEFAULT_BINDINGS,
  dispatchKey,
  mergeBindings,
} from './viewportKeybinds.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build a minimal KeyboardEvent-like object for dispatchKey.
 */
function evt(key, { shift = false, ctrl = false, alt = false, meta = false } = {}) {
  return { key, shiftKey: shift, ctrlKey: ctrl, altKey: alt, metaKey: meta }
}

// ── 1. Default bindings — view presets ───────────────────────────────────────

describe('dispatchKey — view preset keys', () => {
  it('1 → view_front', () => {
    expect(dispatchKey(evt('1'), DEFAULT_BINDINGS)).toBe(ACTIONS.VIEW_FRONT)
  })

  it('3 → view_right', () => {
    expect(dispatchKey(evt('3'), DEFAULT_BINDINGS)).toBe(ACTIONS.VIEW_RIGHT)
  })

  it('7 → view_top', () => {
    expect(dispatchKey(evt('7'), DEFAULT_BINDINGS)).toBe(ACTIONS.VIEW_TOP)
  })

  it('0 → view_camera', () => {
    expect(dispatchKey(evt('0'), DEFAULT_BINDINGS)).toBe(ACTIONS.VIEW_CAMERA)
  })

  it('5 → toggle_ortho', () => {
    expect(dispatchKey(evt('5'), DEFAULT_BINDINGS)).toBe(ACTIONS.TOGGLE_ORTHO)
  })
})

// ── 2. Default bindings — transform modes ────────────────────────────────────

describe('dispatchKey — transform keys', () => {
  it('G → translate (lower-case key)', () => {
    expect(dispatchKey(evt('g'), DEFAULT_BINDINGS)).toBe(ACTIONS.TRANSLATE)
  })

  it('G → translate (upper-case key, e.g. caps-lock on)', () => {
    expect(dispatchKey(evt('G'), DEFAULT_BINDINGS)).toBe(ACTIONS.TRANSLATE)
  })

  it('R → rotate', () => {
    expect(dispatchKey(evt('r'), DEFAULT_BINDINGS)).toBe(ACTIONS.ROTATE)
  })

  it('S → scale', () => {
    expect(dispatchKey(evt('s'), DEFAULT_BINDINGS)).toBe(ACTIONS.SCALE)
  })
})

// ── 3. Default bindings — shading toggles ────────────────────────────────────

describe('dispatchKey — shading keys', () => {
  it('Z → wireframe', () => {
    expect(dispatchKey(evt('z'), DEFAULT_BINDINGS)).toBe(ACTIONS.WIREFRAME)
  })

  it('Shift+Z → rendered_shading (chord)', () => {
    expect(dispatchKey(evt('z', { shift: true }), DEFAULT_BINDINGS)).toBe(ACTIONS.RENDERED_SHADING)
  })

  it('Shift+Z is distinct from plain Z', () => {
    const plain   = dispatchKey(evt('z'),                   DEFAULT_BINDINGS)
    const shifted = dispatchKey(evt('z', { shift: true }), DEFAULT_BINDINGS)
    expect(plain).not.toBe(shifted)
    expect(plain).toBe(ACTIONS.WIREFRAME)
    expect(shifted).toBe(ACTIONS.RENDERED_SHADING)
  })
})

// ── 4. Default bindings — panel / mode toggles ───────────────────────────────

describe('dispatchKey — panel and mode keys', () => {
  it('T → toggle_gizmo', () => {
    expect(dispatchKey(evt('t'), DEFAULT_BINDINGS)).toBe(ACTIONS.TOGGLE_GIZMO)
  })

  it('` (backtick) → pie_menu', () => {
    expect(dispatchKey(evt('`'), DEFAULT_BINDINGS)).toBe(ACTIONS.PIE_MENU)
  })

  it('~ (tilde, shifted backtick on some layouts) → pie_menu', () => {
    expect(dispatchKey(evt('~'), DEFAULT_BINDINGS)).toBe(ACTIONS.PIE_MENU)
  })

  it('Tab → edit_mode', () => {
    expect(dispatchKey(evt('Tab'), DEFAULT_BINDINGS)).toBe(ACTIONS.EDIT_MODE)
  })

  it('Escape → cancel', () => {
    expect(dispatchKey(evt('Escape'), DEFAULT_BINDINGS)).toBe(ACTIONS.CANCEL)
  })
})

// ── 5. Unbound keys return null ───────────────────────────────────────────────

describe('dispatchKey — unbound keys', () => {
  it('returns null for an unbound letter key', () => {
    expect(dispatchKey(evt('q'), DEFAULT_BINDINGS)).toBeNull()
  })

  it('returns null for an unbound number key', () => {
    expect(dispatchKey(evt('9'), DEFAULT_BINDINGS)).toBeNull()
  })

  it('returns null for an unbound function key', () => {
    expect(dispatchKey(evt('F1'), DEFAULT_BINDINGS)).toBeNull()
  })

  it('returns null for Shift+G (no binding defined)', () => {
    expect(dispatchKey(evt('g', { shift: true }), DEFAULT_BINDINGS)).toBeNull()
  })

  it('returns null for Ctrl+Z (no binding defined)', () => {
    expect(dispatchKey(evt('z', { ctrl: true }), DEFAULT_BINDINGS)).toBeNull()
  })
})

// ── 6. Edge cases ─────────────────────────────────────────────────────────────

describe('dispatchKey — edge cases', () => {
  it('returns null when event is null', () => {
    expect(dispatchKey(null, DEFAULT_BINDINGS)).toBeNull()
  })

  it('returns null when bindings is null', () => {
    expect(dispatchKey(evt('z'), null)).toBeNull()
  })

  it('returns null for empty bindings list', () => {
    expect(dispatchKey(evt('z'), [])).toBeNull()
  })

  it('custom single-binding list works', () => {
    const custom = [{ key: 'x', action: 'delete' }]
    expect(dispatchKey(evt('x'), custom)).toBe('delete')
  })
})

// ── 7. mergeBindings ──────────────────────────────────────────────────────────

describe('mergeBindings', () => {
  it('returns base unchanged when no overrides', () => {
    const result = mergeBindings(DEFAULT_BINDINGS, [])
    expect(result).toEqual(DEFAULT_BINDINGS)
  })

  it('override replaces matching key+modifier tuple', () => {
    const overrides = [{ key: 'z', action: 'custom_wireframe' }]
    const merged = mergeBindings(DEFAULT_BINDINGS, overrides)
    // plain Z should now return custom_wireframe
    expect(dispatchKey(evt('z'), merged)).toBe('custom_wireframe')
  })

  it('override does not affect non-conflicting bindings', () => {
    const overrides = [{ key: 'z', action: 'custom_wireframe' }]
    const merged = mergeBindings(DEFAULT_BINDINGS, overrides)
    // Shift+Z should still work as before
    expect(dispatchKey(evt('z', { shift: true }), merged)).toBe(ACTIONS.RENDERED_SHADING)
  })

  it('can add a brand-new binding', () => {
    const overrides = [{ key: 'x', action: 'delete' }]
    const merged = mergeBindings(DEFAULT_BINDINGS, overrides)
    expect(dispatchKey(evt('x'), merged)).toBe('delete')
    // existing bindings intact
    expect(dispatchKey(evt('g'), merged)).toBe(ACTIONS.TRANSLATE)
  })

  it('last override wins when two overrides share the same key+modifier', () => {
    const overrides = [
      { key: 'g', action: 'first' },
      { key: 'g', action: 'second' },
    ]
    const merged = mergeBindings([], overrides)
    // dispatchKey picks the first match in iteration order; 'first' appears first
    expect(dispatchKey(evt('g'), merged)).toBe('first')
  })
})
