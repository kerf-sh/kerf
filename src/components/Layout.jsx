import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown, LogOut, User as UserIcon, Settings, CreditCard, UserCog, Users } from 'lucide-react'
import clsx from 'clsx'
import { LogoWordmark } from './Logo.jsx'
import WorkspaceSwitcher from './WorkspaceSwitcher.jsx'
import { useAuth } from '../store/auth.js'
import { useWorkspaces } from '../store/workspaces.js'
import { useCloudConfig } from '../cloud/useCloudConfig.js'
import { api } from '../lib/api.js'

function initials(name = '', email = '') {
  const src = (name || email || '?').trim()
  if (!src) return '?'
  const parts = src.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return src.slice(0, 2).toUpperCase()
}

function UserMenu({ user, onLogout, currentWorkspaceSlug, cloudEnabled }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const display = user?.name || user?.email || 'Account'

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          'flex items-center gap-2 rounded-lg pr-2 pl-1.5 h-9',
          'hover:bg-ink-800/80 transition-colors',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50',
        )}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="grid place-items-center w-7 h-7 rounded-md bg-kerf-300 text-ink-950 text-[11px] font-semibold tracking-tight">
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt=""
              className="w-7 h-7 rounded-md object-cover"
            />
          ) : (
            initials(user?.name, user?.email)
          )}
        </span>
        <span className="hidden sm:inline text-sm text-ink-200 max-w-[140px] truncate">
          {display}
        </span>
        <ChevronDown size={14} className="text-ink-300" />
      </button>

      {open && (
        <div
          role="menu"
          className={clsx(
            'absolute right-0 mt-2 w-56 rounded-xl border border-ink-800',
            'bg-ink-900/95 backdrop-blur shadow-xl shadow-black/40',
            'py-1.5 z-50',
          )}
        >
          <div className="px-3 py-2.5 border-b border-ink-800">
            <p className="text-sm text-ink-100 truncate">{user?.name || 'Signed in'}</p>
            <p className="text-xs text-ink-400 truncate font-mono">{user?.email}</p>
          </div>

          <div className="py-1">
            <Link
              to="/profile"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
            >
              <UserCog size={14} className="text-ink-300" />
              Profile
            </Link>
          </div>

          {currentWorkspaceSlug && (
            <div className="py-1 border-t border-ink-800">
              <p className="px-3 pt-1 pb-0.5 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-500">
                Workspace
              </p>
              <Link
                to={`/w/${currentWorkspaceSlug}/members`}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
              >
                <Users size={14} className="text-ink-300" />
                Members
              </Link>
              <Link
                to={`/w/${currentWorkspaceSlug}/settings`}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
              >
                <Settings size={14} className="text-ink-300" />
                Settings
              </Link>
              {cloudEnabled && (
                <>
                  <Link
                    to="/billing"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
                  >
                    <CreditCard size={14} className="text-ink-300" />
                    Billing
                  </Link>
                </>
              )}
            </div>
          )}

          <div className="py-1 border-t border-ink-800">
            <button
              type="button"
              role="menuitem"
              onClick={() => { setOpen(false); onLogout() }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
            >
              <LogOut size={14} className="text-ink-300" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout({ children, wide = false, padded = true }) {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const accessToken = useAuth((s) => s.accessToken)
  const setUser = useAuth((s) => s.setUser)
  const logout = useAuth((s) => s.logout)
  const currentWorkspaceSlug = useWorkspaces((s) => s.currentSlug)
  const { cloudEnabled } = useCloudConfig()
  const fetchedRef = useRef(false)

  // Hydrate user once if we have a token but no profile yet.
  useEffect(() => {
    if (!user && accessToken && !fetchedRef.current) {
      fetchedRef.current = true
      api
        .me()
        .then((u) => setUser(u))
        .catch(() => {
          // refresh middleware will have logged out on 401; nothing more to do
          fetchedRef.current = false
        })
    }
  }, [user, accessToken, setUser])

  const onLogout = async () => {
    try {
      await api.logout()
    } catch {
      // ignore network errors; we already cleared local state
    }
    logout()
    navigate('/login', { replace: true })
  }

  const fallbackUser = user || {
    name: '',
    email: '',
    avatar_url: null,
  }

  return (
    <div className="min-h-screen flex flex-col bg-ink-950 text-ink-100">
      <header className="sticky top-0 z-30 backdrop-blur-md bg-ink-950/70 border-b border-ink-900">
        <div
          className={clsx(
            'mx-auto px-6 h-16 flex items-center justify-between',
            wide ? 'max-w-none' : 'max-w-7xl',
          )}
        >
          <div className="flex items-center gap-3 min-w-0">
            <Link to="/" className="flex items-center flex-shrink-0" aria-label="Kerf home">
              <LogoWordmark />
            </Link>
            {accessToken && (
              <>
                <span className="text-ink-700 select-none flex-shrink-0">/</span>
                <WorkspaceSwitcher />
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* In-app top-nav: Docs only here — Workshop/Library are in
                the cloud nav below. Marketing pages (Compare/Roadmap/
                Domains) are intentionally NOT shown to signed-in users. */}
            <nav
              className="hidden md:flex items-center gap-1 mr-1"
              aria-label="Primary"
            >
              <Link
                to="/docs"
                className="text-xs text-ink-300 hover:text-ink-100 px-2 py-1 rounded-md hover:bg-ink-800/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
              >
                Docs
              </Link>
            </nav>
            {/* Cloud top-nav: Workshop hosts the project showcase, Library
                hosts the parts catalog. Both are cloud-only — gated on
                `cloudEnabled`. Hidden for signed-out and OSS callers. */}
            {accessToken && cloudEnabled && (
              <nav className="hidden sm:flex items-center gap-1 mr-1">
                <Link
                  to="/workshop"
                  className="text-xs text-ink-300 hover:text-ink-100 px-2 py-1 rounded-md hover:bg-ink-800/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
                >
                  Workshop
                </Link>
                <Link
                  to="/library"
                  className="text-xs text-ink-300 hover:text-ink-100 px-2 py-1 rounded-md hover:bg-ink-800/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
                >
                  Library
                </Link>
              </nav>
            )}
            {!user && accessToken && (
              <span className="text-xs text-ink-400 flex items-center gap-1.5">
                <UserIcon size={12} />
                loading…
              </span>
            )}
            <UserMenu
              user={fallbackUser}
              onLogout={onLogout}
              currentWorkspaceSlug={currentWorkspaceSlug}
              cloudEnabled={cloudEnabled}
            />
          </div>
        </div>
      </header>

      <main
        className={clsx(
          'flex-1',
          padded && (wide ? 'px-6 py-8' : 'mx-auto w-full max-w-7xl px-6 py-10'),
        )}
      >
        {children}
      </main>

    </div>
  )
}
