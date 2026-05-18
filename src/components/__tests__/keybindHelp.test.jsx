// keybindHelp.test.jsx — Pure helper tests for KeybindHelp utilities.
//
// Tests the exported pure functions (formatBinding, bindingForAction,
// bindingsForAction) without any React DOM rendering overhead, following the
// established mepView / railingView test convention.

import { describe, it, expect } from 'vitest'
import {
  formatBinding,
  bindingForAction,
  bindingsForAction,
} from '../KeybindHelp.jsx'
import { DEFAULT_BINDINGS, ACTIONS } from '../../lib/viewportKeybinds.js'

// ── 1. formatBinding ──────────────────────────────────────────────────────────

describe('formatBinding', () => {
  it('formats a plain letter key', () => {
    expect(formatBinding({ key: 'g' })).toBe('G')
  })

  it('formats Shift+letter as "Shift+X"', () => {
    expect(formatBinding({ key: 'z', shift: true })).toBe('Shift+Z')
  })

  it('formats Ctrl+key', () => {
    expect(formatBinding({ key: 'z', ctrl: true })).toBe('Ctrl+Z')
  })

  it('formats Ctrl+Shift+key with correct order', () => {
    expect(formatBinding({ key: 's', ctrl: true, shift: true })).toBe('Ctrl+Shift+S')
  })

  it('formats special keys (Escape, Tab) without uppercasing', () => {
    expect(formatBinding({ key: 'Escape' })).toBe('Escape')
    expect(formatBinding({ key: 'Tab' })).toBe('Tab')
  })

  it('formats numeric key', () => {
    expect(formatBinding({ key: '1' })).toBe('1')
  })

  it('formats backtick key', () => {
    expect(formatBinding({ key: '`' })).toBe('`')
  })

  it('returns empty string for null', () => {
    expect(formatBinding(null)).toBe('')
  })

  it('formats Alt+key', () => {
    expect(formatBinding({ key: 'r', alt: true })).toBe('Alt+R')
  })
})

// ── 2. bindingForAction ───────────────────────────────────────────────────────

describe('bindingForAction', () => {
  it('returns the first binding for view_front (key 1)', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.VIEW_FRONT)
    expect(b).not.toBeNull()
    expect(b.key).toBe('1')
  })

  it('returns first binding for translate (key g)', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.TRANSLATE)
    expect(b).not.toBeNull()
    expect(b.key).toBe('g')
  })

  it('returns null for an action not in the list', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, 'nonexistent_action')
    expect(b).toBeNull()
  })

  it('returns null for empty bindings list', () => {
    expect(bindingForAction([], ACTIONS.CANCEL)).toBeNull()
  })
})

// ── 3. bindingsForAction ──────────────────────────────────────────────────────

describe('bindingsForAction', () => {
  it('returns all entries for pie_menu (` and ~)', () => {
    const entries = bindingsForAction(DEFAULT_BINDINGS, ACTIONS.PIE_MENU)
    expect(entries.length).toBeGreaterThanOrEqual(2)
    const keys = entries.map((b) => b.key)
    expect(keys).toContain('`')
    expect(keys).toContain('~')
  })

  it('returns both wireframe and rendered_shading entries for Z key family', () => {
    const wireframe = bindingsForAction(DEFAULT_BINDINGS, ACTIONS.WIREFRAME)
    const rendered  = bindingsForAction(DEFAULT_BINDINGS, ACTIONS.RENDERED_SHADING)
    expect(wireframe.length).toBeGreaterThanOrEqual(1)
    expect(rendered.length).toBeGreaterThanOrEqual(1)
    // They share the same physical key but different shift state
    expect(wireframe[0].key).toBe('z')
    expect(rendered[0].key).toBe('z')
    expect(rendered[0].shift).toBe(true)
    expect(wireframe[0].shift).toBeFalsy()
  })

  it('returns empty array for unknown action', () => {
    expect(bindingsForAction(DEFAULT_BINDINGS, 'unknown')).toHaveLength(0)
  })

  it('returns single entry for toggle_ortho', () => {
    const entries = bindingsForAction(DEFAULT_BINDINGS, ACTIONS.TOGGLE_ORTHO)
    expect(entries).toHaveLength(1)
    expect(entries[0].key).toBe('5')
  })

  it('returns single entry for cancel (Escape)', () => {
    const entries = bindingsForAction(DEFAULT_BINDINGS, ACTIONS.CANCEL)
    expect(entries).toHaveLength(1)
    expect(entries[0].key).toBe('Escape')
  })
})

// ── 4. Cross-check: formatBinding on real DEFAULT_BINDINGS entries ────────────

describe('formatBinding applied to DEFAULT_BINDINGS entries', () => {
  it('G entry formats as "G"', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.TRANSLATE)
    expect(formatBinding(b)).toBe('G')
  })

  it('Shift+Z entry formats as "Shift+Z"', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.RENDERED_SHADING)
    expect(formatBinding(b)).toBe('Shift+Z')
  })

  it('Escape entry formats as "Escape"', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.CANCEL)
    expect(formatBinding(b)).toBe('Escape')
  })

  it('Tab entry formats as "Tab"', () => {
    const b = bindingForAction(DEFAULT_BINDINGS, ACTIONS.EDIT_MODE)
    expect(formatBinding(b)).toBe('Tab')
  })
})
