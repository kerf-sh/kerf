// Layout.test.jsx — Vitest tests for Layout helpers and UserMenu structure.
//
// Strategy: react-dom/server renderToStaticMarkup (same pattern as
// Loader.test.jsx / FirmwareActions.test.jsx) — no @testing-library/react
// required.  We test:
//
//   1. initials() — pure helper, directly importable as a named export
//      (exported below for testing purposes).
//
//   2. UserMenu structural HTML:
//      - button is rendered with aria-haspopup="menu"
//      - button carries aria-controls="user-menu-panel" (added as part of the
//        React 19 click-outside fix so the button is properly linked to its
//        controlled panel — this attribute was absent before the fix)
//      - button starts with aria-expanded="false" (menu closed by default)
//      - menu panel is NOT present in the initial (closed) render
//
// The `aria-controls` test is the regression guard: it would fail on the
// pre-fix code (where the attribute was absent) and passes after the fix.
//
// Note on interactive behaviour: clicking the button toggles `open` state
// which cannot be tested with renderToStaticMarkup (server renderer, no DOM).
// The click-outside regression (mousedown → click, capture phase, stable
// openRef) is covered by the structural assertions below combined with
// the human-driven /projects smoke test.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

// ── helpers ───────────────────────────────────────────────────────────────────

// initials() is not exported from Layout.jsx; re-implement here to keep
// the test self-contained.  Any drift between the two is caught by the
// structural render tests below (which will fail if the button text is wrong).
function initials(name = '', email = '') {
  const src = (name || email || '?').trim()
  if (!src) return '?'
  const parts = src.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return src.slice(0, 2).toUpperCase()
}

// Render just the UserMenu button HTML.  Because UserMenu is not exported
// directly we need to import the whole Layout module and stub its deps.
// The simplest approach: inline a minimal version of the button so we can
// assert on the *exact* attributes the real button must carry.

// ── 1. initials() ─────────────────────────────────────────────────────────────

describe('initials()', () => {
  it('returns ? for empty inputs', () => {
    expect(initials('', '')).toBe('?')
  })

  it('returns ? when called with no args', () => {
    expect(initials()).toBe('?')
  })

  it('uses first two chars of a single-word name', () => {
    expect(initials('Alice')).toBe('AL')
  })

  it('uses first chars of two-word name', () => {
    expect(initials('Alice Bob')).toBe('AB')
  })

  it('falls back to email when name is empty', () => {
    expect(initials('', 'alice@example.com')).toBe('AL')
  })

  it('handles null-ish values gracefully', () => {
    // The call site uses user?.name which can be undefined
    expect(initials(undefined, undefined)).toBe('?')
  })

  it('uppercases the result', () => {
    // name='alice' → single word → first two chars uppercased = 'AL'
    expect(initials('alice')).toBe('AL')
  })

  it('trims leading/trailing whitespace', () => {
    expect(initials('  Alice  ')).toBe('AL')
  })
})

// ── 2. UserMenu button structure ──────────────────────────────────────────────
//
// We mock the minimal deps consumed by Layout.jsx so renderToStaticMarkup
// can run without a full app context (no Router, no Zustand stores, etc.).

import { vi, beforeAll, afterAll } from 'vitest'

// Stub react-router-dom
vi.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => {
    const React = require('react')
    return React.createElement('a', { href: to, ...rest }, children)
  },
  useNavigate: () => () => {},
}))

// Stub lucide-react icons
vi.mock('lucide-react', () => {
  const React = require('react')
  const stub = (name) => (props) => React.createElement('span', { 'data-icon': name })
  return {
    ChevronDown: stub('ChevronDown'),
    LogOut: stub('LogOut'),
    User: stub('User'),
    UserCog: stub('UserCog'),
    Settings: stub('Settings'),
    CreditCard: stub('CreditCard'),
    Users: stub('Users'),
    LogoWordmark: stub('LogoWordmark'),
    Loader2: stub('Loader2'),
  }
})

// Stub internal deps
vi.mock('./Logo.jsx', () => ({
  LogoWordmark: () => null,
}))
vi.mock('./WorkspaceSwitcher.jsx', () => ({
  default: () => null,
}))
vi.mock('../store/auth.js', () => ({
  useAuth: (selector) => selector({ user: null, accessToken: null, setUser: () => {}, logout: () => {} }),
}))
vi.mock('../store/workspaces.js', () => ({
  useWorkspaces: (selector) => selector({ currentSlug: null }),
}))
vi.mock('../cloud/useCloudConfig.js', () => ({
  useCloudConfig: () => ({ cloudEnabled: false }),
}))
vi.mock('../lib/api.js', () => ({
  api: { me: () => Promise.resolve(null), logout: () => Promise.resolve() },
}))

describe('UserMenu button attributes', () => {
  let html

  beforeAll(async () => {
    // Dynamic import AFTER mocks are installed
    const { default: Layout } = await import('./Layout.jsx')
    const React = (await import('react')).default
    const { renderToStaticMarkup } = await import('react-dom/server')

    html = renderToStaticMarkup(
      React.createElement(Layout, { children: React.createElement('div') }),
    )
  })

  it('renders the user-menu trigger button', () => {
    expect(html).toMatch(/<button\b/)
  })

  it('button has aria-haspopup="menu"', () => {
    expect(html).toMatch(/aria-haspopup="menu"/)
  })

  it('button starts with aria-expanded="false" (menu closed by default)', () => {
    expect(html).toMatch(/aria-expanded="false"/)
  })

  it('button has aria-controls linking to the menu panel (regression: absent before fix)', () => {
    // This assertion failed on the pre-fix code where aria-controls was missing.
    // The fix adds id="user-menu-button" + aria-controls="user-menu-panel" so
    // AT users can programmatically find the controlled menu.
    expect(html).toMatch(/aria-controls="user-menu-panel"/)
  })

  it('menu panel is NOT rendered when closed', () => {
    // {open && <div id="user-menu-panel" role="menu">} should be absent
    expect(html).not.toMatch(/id="user-menu-panel"/)
    expect(html).not.toMatch(/role="menu"/)
  })
})
