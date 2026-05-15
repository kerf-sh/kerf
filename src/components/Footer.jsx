import { Link } from 'react-router-dom'
import { Github, ExternalLink } from 'lucide-react'
import { LogoMark } from './Logo.jsx'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

function Col({ title, children }) {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-400">
        {title}
      </h3>
      <ul className="flex flex-col gap-2">{children}</ul>
    </div>
  )
}

function Item({ to, href, external, children }) {
  const cls =
    'inline-flex items-center gap-1.5 text-sm text-ink-300 hover:text-ink-100 transition-colors'
  if (href) {
    return (
      <li>
        <a
          href={href}
          target={external ? '_blank' : undefined}
          rel={external ? 'noreferrer' : undefined}
          className={cls}
        >
          {children}
          {external && <ExternalLink size={11} className="opacity-60" />}
        </a>
      </li>
    )
  }
  return (
    <li>
      <Link to={to} className={cls}>
        {children}
      </Link>
    </li>
  )
}

export default function Footer() {
  return (
    <footer className="relative border-t border-ink-900 bg-ink-950">
      <div className="mx-auto max-w-7xl px-6 py-14">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-8">
          {/* brand column */}
          <div className="flex flex-col gap-4 lg:pr-6">
            <Link to="/" className="inline-flex items-center gap-2" aria-label="Kerf home">
              <LogoMark size={26} className="text-kerf-300" />
              <span className="font-display font-semibold text-lg tracking-tight text-ink-100">
                kerf
              </span>
            </Link>
            <p className="text-sm text-ink-400 leading-relaxed max-w-xs">
              Chat-native CAD. Mechanical, electronics, drawings — one
              workspace, fully open source.
            </p>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 self-start rounded-md border border-ink-800 bg-ink-900/60 px-2.5 py-1.5 text-xs text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors"
            >
              <Github size={13} />
              {/* open-source pitch: invite contributors */}
              <span className="font-mono">Open source — contributors welcome</span>
            </a>
          </div>

          <Col title="Product">
            <Item to="/projects">Editor</Item>
            <Item to="/library">Library</Item>
            <Item to="/workshop">Workshop</Item>
            <Item to="/pricing">Pricing</Item>
            <Item to="/roadmap">Roadmap</Item>
          </Col>

          <Col title="Resources">
            <Item to="/docs">Docs</Item>
            <Item href={GITHUB_URL} external>
              <Github size={12} className="opacity-70" />
              GitHub
            </Item>
            <Item href={`${GITHUB_URL}/releases`} external>
              Changelog
            </Item>
          </Col>

          <Col title="Legal">
            <Item to="/docs/terms">Terms</Item>
            <Item to="/docs/privacy">Privacy</Item>
            <Item to="/docs/license">License</Item>
          </Col>
        </div>

        {/* bottom strip */}
        <div className="mt-12 pt-6 border-t border-ink-900 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <span className="text-xs text-ink-500 font-mono">
              © {new Date().getFullYear()} Kerf
            </span>
            <span className="hidden sm:inline text-ink-700">·</span>
            <span className="text-xs text-ink-500 font-mono">MIT licensed</span>
          </div>

          <div className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-500">
              <span className="text-base leading-none" aria-hidden>🇿🇦</span>
              <span>Built in South Africa</span>
            </span>

            <span className="hidden sm:inline text-ink-700">·</span>

            <span className="font-mono text-[11px] text-ink-600" title="Kerf version">
              v{__APP_VERSION__}
            </span>
          </div>
        </div>
      </div>
    </footer>
  )
}
