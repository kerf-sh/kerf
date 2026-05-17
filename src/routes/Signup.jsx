import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import Card from '../components/Card.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { useCloudConfig } from '../cloud/useCloudConfig.js'

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

export default function Signup() {
  const navigate = useNavigate()
  const setSession = useAuth((s) => s.setSession)
  const { googleEnabled, githubEnabled } = useCloudConfig()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [pwError, setPwError] = useState(null)

  const validatePw = (v) => {
    if (v.length > 0 && v.length < 8) {
      setPwError('Use at least 8 characters.')
    } else {
      setPwError(null)
    }
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    if (password.length < 8) {
      setPwError('Use at least 8 characters.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const data = await api.register(email.trim(), password, name.trim())
      setSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
      })
      navigate('/projects', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Could not create your account.')
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
                Create your account
              </h1>
              <p className="mt-1 text-sm text-ink-400">
                Free while in beta. No card required.
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
                label="Name"
                type="text"
                name="name"
                autoComplete="name"
                required
                placeholder="Ada Lovelace"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
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
                autoComplete="new-password"
                required
                minLength={8}
                placeholder="Minimum 8 characters"
                value={password}
                error={pwError}
                hint={!pwError ? '8 characters or more.' : undefined}
                onChange={(e) => {
                  setPassword(e.target.value)
                  validatePw(e.target.value)
                }}
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="mt-1 w-full"
                disabled={submitting}
              >
                {submitting ? 'Creating account…' : 'Create account'}
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
            Already have an account?{' '}
            <Link to="/login" className="text-kerf-300 hover:text-kerf-200 font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
