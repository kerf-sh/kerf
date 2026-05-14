import { Link } from 'react-router-dom'
import { LogoWordmark } from './Logo.jsx'
import Button from './Button.jsx'

export default function Header() {
  return (
    <header className="sticky top-0 z-30 backdrop-blur-md bg-ink-950/70 border-b border-ink-900">
      <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between gap-6">
        <Link to="/" className="flex items-center" aria-label="Kerf home">
          <LogoWordmark />
        </Link>

        {/* Secondary nav — hidden on small screens; auth CTAs always visible. */}
        <nav
          className="hidden md:flex items-center gap-1"
          aria-label="Primary"
        >
          <Link
            to="/docs"
            className="px-3 py-1.5 text-sm text-ink-300 hover:text-ink-100 transition-colors rounded-md"
          >
            Docs
          </Link>
          <Link
            to="/roadmap"
            className="px-3 py-1.5 text-sm text-ink-300 hover:text-ink-100 transition-colors rounded-md"
          >
            Roadmap
          </Link>
        </nav>

        <nav className="flex items-center gap-2" aria-label="Account">
          <Button as={Link} to="/login" variant="ghost" size="sm">
            Sign in
          </Button>
          <Button as={Link} to="/signup" variant="primary" size="sm">
            Sign up
          </Button>
        </nav>
      </div>
    </header>
  )
}
