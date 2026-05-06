import { useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import Card from '../components/Card.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'

const ERROR_LABELS = {
  missing_tokens: 'Google sign-in did not return tokens. Please try again.',
  me_failed: 'Could not load your account. Please sign in again.',
  google_denied: 'Google sign-in was cancelled.',
  google_state: 'Google sign-in failed a security check. Please try again.',
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#EA4335"
        d="M12 10.2v3.9h5.5c-.24 1.4-1.7 4.1-5.5 4.1-3.3 0-6-2.7-6-6.2s2.7-6.2 6-6.2c1.9 0 3.2.8 3.9 1.5l2.7-2.6C16.9 3.1 14.7 2 12 2 6.9 2 2.7 6.1 2.7 12S6.9 22 12 22c6.9 0 9.5-4.8 9.5-7.3 0-.5 0-.9-.1-1.3z"
      />
      <path
        fill="#34A853"
        d="M3.9 7.5l3.2 2.4C8 8 10 6.6 12 6.6c1.9 0 3.2.8 3.9 1.5l2.7-2.6C16.9 4 14.7 3 12 3 8.5 3 5.5 5 3.9 7.5z"
      />
      <path
        fill="#FBBC05"
        d="M12 21c2.7 0 4.9-.9 6.5-2.4l-3.1-2.5c-.8.6-2 1-3.4 1-2.6 0-4.8-1.7-5.6-4.1l-3.2 2.5C4.9 18.9 8.2 21 12 21z"
      />
      <path
        fill="#4285F4"
        d="M21.5 12.7c0-.5 0-.9-.1-1.3H12v3.9h5.5c-.2 1.2-1 2.3-2.1 3l3.1 2.5c1.8-1.6 3-4.1 3-8.1z"
      />
    </svg>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const setSession = useAuth((s) => s.setSession)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // Initialize error directly from query string so we don't write state in an effect.
  const initialError = (() => {
    const e = params.get('error')
    if (!e) return null
    return ERROR_LABELS[e] || decodeURIComponent(e)
  })()
  const [error, setError] = useState(initialError)

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const data = await api.login(email.trim(), password)
      setSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
      })
      const dest = location.state?.from || '/projects'
      navigate(dest, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Could not sign in.')
      } else {
        setError('Could not reach the server. Try again in a moment.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-ink-950 text-ink-100">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
          WebkitMaskImage:
            'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        }}
      />

      <div className="relative flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <Link to="/" className="flex justify-center mb-8" aria-label="Kerf home">
            <LogoWordmark className="text-2xl" />
          </Link>

          <Card className="p-7">
            <header className="mb-6">
              <h1 className="font-display text-2xl font-semibold tracking-tight">
                Welcome back
              </h1>
              <p className="mt-1 text-sm text-ink-400">
                Sign in to continue to your projects.
              </p>
            </header>

            {error && (
              <div className="mb-5 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <Input
                label="Email"
                type="email"
                name="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Input
                label="Password"
                type="password"
                name="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="mt-1 w-full"
                disabled={submitting}
              >
                {submitting ? 'Signing in…' : 'Sign in'}
                {!submitting && <ArrowRight size={16} />}
              </Button>
            </form>

            <div className="my-6 flex items-center gap-3">
              <div className="h-px flex-1 bg-ink-800" />
              <span className="text-[10px] uppercase tracking-widest text-ink-500 font-mono">
                or
              </span>
              <div className="h-px flex-1 bg-ink-800" />
            </div>

            <a
              href={api.googleAuthUrl()}
              className="w-full inline-flex items-center justify-center gap-2 h-11 rounded-lg border border-ink-700 bg-ink-800/60 hover:bg-ink-800 transition-colors text-sm text-ink-100 font-medium"
            >
              <GoogleIcon />
              Continue with Google
            </a>
          </Card>

          <p className="mt-6 text-center text-sm text-ink-400">
            Don&apos;t have an account?{' '}
            <Link
              to="/signup"
              className="text-kerf-300 hover:text-kerf-200 font-medium"
            >
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
