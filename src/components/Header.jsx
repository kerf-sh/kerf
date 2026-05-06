import { Link } from 'react-router-dom'
import { LogoWordmark } from './Logo.jsx'
import Button from './Button.jsx'

export default function Header() {
  return (
    <header className="sticky top-0 z-30 backdrop-blur-md bg-ink-950/70 border-b border-ink-900">
      <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center" aria-label="Kerf home">
          <LogoWordmark />
        </Link>

        <nav className="flex items-center gap-2">
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
