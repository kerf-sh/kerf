import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, ArrowRight, MailCheck } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import Card from '../components/Card.jsx'
import { api, ApiError } from '../lib/api.js'

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

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      await api.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      // The endpoint never enumerates accounts; only surface real
      // transport/server failures.
      setError(
        err instanceof ApiError
          ? err.message || 'Could not send the reset link.'
          : 'Could not reach the server. Try again in a moment.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Shell>
      <Card className="p-7">
        {sent ? (
          <div className="text-center">
            <MailCheck size={28} className="mx-auto text-kerf-300" />
            <h1 className="mt-3 font-display text-xl font-semibold tracking-tight">
              Check your inbox
            </h1>
            <p className="mt-2 text-sm text-ink-400">
              If an account exists for <span className="text-ink-200">{email}</span>,
              a password-reset link is on its way. The link expires in 1 hour.
            </p>
          </div>
        ) : (
          <>
            <header className="mb-6">
              <h1 className="font-display text-2xl font-semibold tracking-tight">
                Reset your password
              </h1>
              <p className="mt-1 text-sm text-ink-400">
                Enter your email and we&apos;ll send a reset link.
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
                label="Email"
                type="email"
                name="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="mt-1 w-full"
                disabled={submitting}
              >
                {submitting ? 'Sending…' : 'Send reset link'}
                {!submitting && <ArrowRight size={16} />}
              </Button>
            </form>
          </>
        )}
      </Card>
      <p className="mt-6 text-center text-sm text-ink-400">
        Remembered it?{' '}
        <Link to="/login" className="text-kerf-300 hover:text-kerf-200 font-medium">
          Sign in
        </Link>
      </p>
    </Shell>
  )
}
