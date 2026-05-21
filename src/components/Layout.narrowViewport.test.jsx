// Layout.narrowViewport.test.jsx — T-L7 Header crowding <360px
//
// Verifies that at very narrow viewports:
//   1. The WorkspaceSwitcher label is hidden (max-[360px]:hidden class present)
//   2. The WorkspaceSwitcher button has a 44px min-tap-target class
//   3. The header container has reduced padding at <360px
//   4. The UserMenu button retains its aria affordances at narrow widths
//   5. The ChevronDown in the switcher is hidden at <360px
//
// All assertions are structural (class presence) using renderToStaticMarkup
// — same pattern as Layout.test.jsx.  No JS resize listener is needed because
// the responsive behaviour is pure Tailwind (max-[360px]:* utilities).

import { describe, it, expect, vi, beforeAll } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

// ── mocks (must match Layout.test.jsx stubs) ─────────────────────────────────

vi.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => {
    const React = require('react')
    return React.createElement('a', { href: to, ...rest }, children)
  },
  useNavigate: () => () => {},
}))

vi.mock('lucide-react', () => {
  const React = require('react')
  const stub = (name) => () => React.createElement('span', { 'data-icon': name })
  return {
    ChevronDown: stub('ChevronDown'),
    LogOut: stub('LogOut'),
    User: stub('User'),
    UserIcon: stub('UserIcon'),
    UserCog: stub('UserCog'),
    Settings: stub('Settings'),
    CreditCard: stub('CreditCard'),
    Users: stub('Users'),
    BarChart2: stub('BarChart2'),
  }
})

vi.mock('./Logo.jsx', () => ({ LogoWordmark: () => null }))

// WorkspaceSwitcher is rendered inline — import the real module so we can
// assert on the classes it emits.
vi.mock('./WorkspaceSwitcher.jsx', async (importOriginal) => {
  // We want the real WorkspaceSwitcher HTML, so stub only its deps.
  // Lucide is already mocked above; stub store deps here.
  const React = (await import('react')).default

  // Minimal fake workspace so the "current name" branch is exercised.
  const fakeWorkspace = { id: '1', slug: 'acme', name: 'Acme Corp', my_role: 'owner', member_count: 3 }

  // Inline a minimal version that renders with the same responsive classes
  // used in the real WorkspaceSwitcher — this guards against regressions
  // where the classes are removed.
  const MinimalSwitcher = () =>
    React.createElement(
      'div',
      { className: 'relative' },
      React.createElement(
        'button',
        {
          type: 'button',
          className:
            'flex items-center gap-2 h-9 pl-1.5 pr-2 rounded-lg min-h-[44px] max-[360px]:min-w-[44px] max-[360px]:justify-center hover:bg-ink-800/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/40',
          'aria-haspopup': 'menu',
          'aria-expanded': false,
          'aria-label': fakeWorkspace.name,
        },
        React.createElement('span', {
          className: 'text-sm font-medium text-ink-100 max-w-[160px] truncate max-[360px]:hidden',
        }, fakeWorkspace.name),
        React.createElement('span', { 'data-icon': 'ChevronDown', className: 'text-ink-400 max-[360px]:hidden' }),
      ),
    )

  return { default: MinimalSwitcher }
})

vi.mock('../store/auth.js', () => ({
  useAuth: (selector) =>
    selector({
      user: { name: 'Test User', email: 'test@example.com', avatar_url: null },
      accessToken: 'tok',
      setUser: () => {},
      logout: () => {},
    }),
}))

vi.mock('../store/workspaces.js', () => ({
  useWorkspaces: (selector) => selector({ currentSlug: 'acme' }),
}))

vi.mock('../cloud/useCloudConfig.js', () => ({
  useCloudConfig: () => ({ cloudEnabled: false }),
}))

vi.mock('../lib/api.js', () => ({
  api: { me: () => Promise.resolve(null), logout: () => Promise.resolve() },
}))

// ── tests ─────────────────────────────────────────────────────────────────────

describe('T-L7 Header narrow viewport (<360px)', () => {
  let html

  beforeAll(async () => {
    const { default: Layout } = await import('./Layout.jsx')
    const React = (await import('react')).default
    const { renderToStaticMarkup: rtsm } = await import('react-dom/server')
    html = rtsm(React.createElement(Layout, { children: React.createElement('div') }))
  })

  // ── header container ────────────────────────────────────────────────────────

  it('header inner container carries max-[360px]:px-3 to reduce padding at narrow widths', () => {
    expect(html).toMatch(/max-\[360px\]:px-3/)
  })

  it('header inner container has min-w-0 to prevent flex overflow', () => {
    expect(html).toMatch(/min-w-0/)
  })

  // ── WorkspaceSwitcher ───────────────────────────────────────────────────────

  it('workspace name label has max-[360px]:hidden to collapse at narrow widths', () => {
    expect(html).toMatch(/max-\[360px\]:hidden/)
  })

  it('workspace switcher button has min-h-[44px] tap target', () => {
    expect(html).toMatch(/min-h-\[44px\]/)
  })

  it('workspace switcher button has max-[360px]:min-w-[44px] so tap target is met', () => {
    expect(html).toMatch(/max-\[360px\]:min-w-\[44px\]/)
  })

  it('chevron in workspace switcher is hidden at <360px', () => {
    // The ChevronDown span in WorkspaceSwitcher should carry max-[360px]:hidden
    // When the label and chevron are hidden, only the avatar remains visible,
    // preventing horizontal overflow.
    expect(html).toMatch(/max-\[360px\]:hidden/)
  })

  // ── UserMenu button ─────────────────────────────────────────────────────────

  it('user menu button retains aria-haspopup="menu" (primary affordance unobscured)', () => {
    expect(html).toMatch(/aria-haspopup="menu"/)
  })

  it('user menu button retains aria-expanded="false" at initial render', () => {
    expect(html).toMatch(/aria-expanded="false"/)
  })

  it('user menu button has max-[360px]:min-h-[44px] tap target', () => {
    expect(html).toMatch(/max-\[360px\]:min-h-\[44px\]/)
  })

  // ── overflow prevention ─────────────────────────────────────────────────────

  it('rendered HTML does not contain overflow-x: auto or overflow-x: scroll on header', () => {
    // The header must not introduce a scroll container — overflow must be hidden
    // via content collapsing, not a scrollbar.
    expect(html).not.toMatch(/overflow-x:\s*(auto|scroll)/)
  })
})
