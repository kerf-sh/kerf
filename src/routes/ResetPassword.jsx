import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import Card from '../components/Card.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'

function Shell({ children }) {
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
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        }}
      />
      <div className="relative flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <Link to="/" className="flex justify-center mb-8" aria-label="Kerf home">
            <LogoWordmark className="text-2xl" />
          </Link>
          {children}
        </div>
      </div>
    </div>
  )
}

export default function ResetPassword() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const setSession = useAuth((s) => s.setSession)

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      const data = await api.resetPassword(token, password)
      setSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
      })
      navigate('/projects', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message || 'Could not reset your password.'
          : 'Could not reach the server. Try again in a moment.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <Shell>
        <Card className="p-7 text-center">
          <AlertCircle size={28} className="mx-auto text-red-300" />
          <h1 className="mt-3 font-display text-xl font-semibold tracking-tight">
            Invalid reset link
          </h1>
          <p className="mt-2 text-sm text-ink-400">
            This link is missing its token. Request a new one.
          </p>
          <Link
            to="/forgot-password"
            className="mt-4 inline-block text-kerf-300 hover:text-kerf-200 font-medium text-sm"
          >
            Send a new reset link
          </Link>
        </Card>
      </Shell>
    )
  }

  return (
    <Shell>
      <Card className="p-7">
        <header className="mb-6">
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Choose a new password
          </h1>
          <p className="mt-1 text-sm text-ink-400">
            For security, this signs you out of other devices.
          </p>
        </header>
        {error && (
          <div
            role="alert"
            className="mb-5 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <Input
            label="New password"
            type="password"
            name="new-password"
            autoComplete="new-password"
            required
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Input
            label="Confirm password"
            type="password"
            name="confirm-password"
            autoComplete="new-password"
            required
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="mt-1 w-full"
            disabled={submitting}
          >
            {submitting ? 'Updating…' : 'Set new password'}
            {!submitting && <ArrowRight size={16} />}
          </Button>
        </form>
      </Card>
      <p className="mt-6 text-center text-sm text-ink-400">
        <Link to="/login" className="text-kerf-300 hover:text-kerf-200 font-medium">
          Back to sign in
        </Link>
      </p>
    </Shell>
  )
}
