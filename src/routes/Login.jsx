import { useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import Card from '../components/Card.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { useCloudConfig } from '../cloud/useCloudConfig.js'

const ERROR_LABELS = {
  missing_tokens: 'Sign-in did not return tokens. Please try again.',
  me_failed: 'Could not load your account. Please sign in again.',
  google_denied: 'Google sign-in was cancelled.',
  google_state: 'Google sign-in failed a security check. Please try again.',
  github_denied: 'GitHub sign-in was cancelled.',
  github_state: 'GitHub sign-in failed a security check. Please try again.',
}

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1c-.22-.66-.35-1.36-.35-2.1s.13-1.44.35-2.1V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l3.66-2.84z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"
      />
    </svg>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const setSession = useAuth((s) => s.setSession)
  const { googleEnabled, githubEnabled } = useCloudConfig()

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
              <div
                role="alert"
                aria-live="polite"
                className="mb-5 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
              >
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

            {(googleEnabled || githubEnabled) && (
              <>
                <div className="my-6 flex items-center gap-3">
                  <div className="h-px flex-1 bg-ink-800" />
                  <span className="text-[10px] uppercase tracking-widest text-ink-500 font-mono">
                    or
                  </span>
                  <div className="h-px flex-1 bg-ink-800" />
                </div>

                <div className="flex flex-col gap-3">
                  {googleEnabled && (
                    <a
                      href={api.googleAuthUrl()}
                      className="w-full inline-flex items-center justify-center gap-2 h-11 rounded-lg border border-ink-700 bg-ink-800/60 hover:bg-ink-800 transition-colors text-sm text-ink-100 font-medium"
                    >
                      <GoogleIcon />
                      Continue with Google
                    </a>
                  )}
                  {githubEnabled && (
                    <a
                      href={api.githubAuthUrl()}
                      className="w-full inline-flex items-center justify-center gap-2 h-11 rounded-lg border border-ink-700 bg-ink-800/60 hover:bg-ink-800 transition-colors text-sm text-ink-100 font-medium"
                    >
                      <GitHubIcon />
                      Continue with GitHub
                    </a>
                  )}
                </div>
              </>
            )}
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
