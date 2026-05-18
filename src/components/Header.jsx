import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { LogoWordmark } from './Logo.jsx'
import Button from './Button.jsx'
import { useAuth } from '../store/auth.js'

// Signed-out: marketing nav. Signed-in: just the app sections — no
// Domains/Compare/Roadmap and no Sign in/Sign up; a single button goes
// straight into the app.
const MARKETING_LINKS = [
  { label: 'Domains', to: '/domains' },
  { label: 'Compare', to: '/compare' },
  { label: 'Roadmap', to: '/roadmap' },
  { label: 'Docs', to: '/docs' },
]
const APP_LINKS = [
  { label: 'Docs', to: '/docs' },
  { label: 'Workshop', to: '/workshop' },
  { label: 'Library', to: '/library' },
]

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const authed = useAuth((s) => !!s.accessToken)
  const navLinks = authed ? APP_LINKS : MARKETING_LINKS

  return (
    <header className="sticky top-0 z-30 backdrop-blur-md bg-ink-950/70 border-b border-ink-900">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <Link
          to={authed ? '/projects' : '/'}
          className="flex items-center shrink-0"
          aria-label={authed ? 'Open Kerf' : 'Kerf home'}
        >
          <LogoWordmark />
        </Link>

        {/* Desktop nav */}
        <nav
          className="hidden md:flex items-center gap-1 flex-1 justify-center"
          aria-label="Primary"
        >
          {navLinks.map((l) => (
            <Link
              key={l.label}
              to={l.to}
              className="px-3 py-1.5 text-sm text-ink-300 hover:text-ink-100 transition-colors rounded-md"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        {/* Desktop right side */}
        <nav className="hidden md:flex items-center gap-2 shrink-0" aria-label="Account">
          {authed ? (
            <Button as={Link} to="/projects" variant="primary" size="sm">
              Open Kerf
            </Button>
          ) : (
            <>
              <Button as={Link} to="/login" variant="ghost" size="sm">
                Sign in
              </Button>
              <Button as={Link} to="/signup" variant="primary" size="sm">
                Sign up
              </Button>
            </>
          )}
        </nav>

        {/* Mobile right side */}
        <div className="flex md:hidden items-center gap-2">
          <Button as={Link} to={authed ? '/projects' : '/signup'} variant="primary" size="sm">
            {authed ? 'Open Kerf' : 'Sign up'}
          </Button>
          <button
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="grid place-items-center w-9 h-9 rounded-md text-ink-300 hover:text-ink-100 hover:bg-ink-800/80 transition-colors"
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden border-t border-ink-900 bg-ink-950/95 backdrop-blur-md">
          <nav className="flex flex-col py-2 px-4" aria-label="Mobile primary">
            {navLinks.map((l) => (
              <Link
                key={l.label}
                to={l.to}
                onClick={() => setMenuOpen(false)}
                className="py-2.5 text-sm text-ink-200 hover:text-ink-100 transition-colors border-b border-ink-900 last:border-0"
              >
                {l.label}
              </Link>
            ))}
            <Link
              to={authed ? '/projects' : '/login'}
              onClick={() => setMenuOpen(false)}
              className="py-2.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
            >
              {authed ? 'Open Kerf' : 'Sign in'}
            </Link>
          </nav>
        </div>
      )}
    </header>
  )
}
