import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { LogoWordmark } from './Logo.jsx'
import Button from './Button.jsx'

const NAV_LINKS = [
  { label: 'Domains', to: '/domains' },
  { label: 'Compare', to: '/compare' },
  { label: 'Docs', to: '/docs' },
]

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-30 backdrop-blur-md bg-ink-950/70 border-b border-ink-900">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <Link to="/" className="flex items-center shrink-0" aria-label="Kerf home">
          <LogoWordmark />
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1 flex-1 justify-center" aria-label="Primary">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.label}
              to={l.to}
              className="px-3 py-1.5 text-sm text-ink-300 hover:text-ink-100 transition-colors rounded-md"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        {/* Auth CTAs — always visible on desktop */}
        <nav className="hidden md:flex items-center gap-2 shrink-0" aria-label="Account">
          <Button as={Link} to="/login" variant="ghost" size="sm">
            Sign in
          </Button>
          <Button as={Link} to="/signup" variant="primary" size="sm">
            Sign up
          </Button>
        </nav>

        {/* Mobile: auth + hamburger */}
        <div className="flex md:hidden items-center gap-2">
          <Button as={Link} to="/signup" variant="primary" size="sm">
            Sign up
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
            {NAV_LINKS.map((l) => (
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
              to="/login"
              onClick={() => setMenuOpen(false)}
              className="py-2.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
            >
              Sign in
            </Link>
          </nav>
        </div>
      )}
    </header>
  )
}
