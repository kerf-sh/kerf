// AdminEmail — operator-only admin page for the transactional email
// subsystem (cloud-only).
//
// Mounted at /admin/email (admin role only). Lists every supported
// provider (Resend, SES, SMTP) with its enable toggle, last-used
// timestamp, and a "Configure" button that opens a credential modal.
// Below the providers, a recent-send log surfaces queued / sent /
// failed rows so the operator can debug deliverability without going
// to the database.
//
// Mirrors the structure of routes/AdminDistributors.jsx — every cloud
// admin page should look and feel the same so an operator can navigate
// without re-learning the UI.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Mail, Plus, Trash2, AlertTriangle, Check, X, Loader2,
  ExternalLink, Clock, Send, Star, ChevronDown,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import { ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { adminEmail } from './api.js'

// Provider form schemas. Drives the modal field set + validation. Stay
// in sync with backend/cloud/email/service.go validateCredentials.
const PROVIDER_FORMS = {
  resend: {
    label: 'Resend',
    blurb: 'Simplest provider — one API key, one verified domain. Get your key at resend.com → API Keys.',
    docsURL: 'https://resend.com/docs',
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: 're_…', type: 'password' },
      { key: 'from_email', label: 'From email', placeholder: 'kerf@yourdomain.com' },
      { key: 'from_name', label: 'From name (optional)', placeholder: 'kerf' },
    ],
  },
  ses: {
    label: 'AWS SES',
    blurb: 'Cheapest at scale. Verify either the from-domain or the from-address in SES first. Leave the access keys empty to use the default AWS credential chain (instance role, env, ~/.aws).',
    docsURL: 'https://docs.aws.amazon.com/ses/latest/dg/send-email.html',
    fields: [
      { key: 'from_email', label: 'From email', placeholder: 'kerf@yourdomain.com' },
      { key: 'from_name', label: 'From name (optional)', placeholder: 'kerf' },
      { key: 'region', label: 'Region', placeholder: 'us-east-1' },
      { key: 'api_key', label: 'AWS access key id (optional)', placeholder: 'AKIA…', type: 'password' },
      { key: 'smtp_password', label: 'AWS secret access key (optional)', placeholder: '••••••', type: 'password' },
    ],
  },
  smtp: {
    label: 'SMTP',
    blurb: 'For self-hosted MTAs or third-party relays (Postmark, Mailgun, SendGrid via SMTP). PLAIN auth over a TLS-wrapped connection.',
    docsURL: 'https://en.wikipedia.org/wiki/Simple_Mail_Transfer_Protocol',
    fields: [
      { key: 'from_email', label: 'From email', placeholder: 'kerf@yourdomain.com' },
      { key: 'from_name', label: 'From name (optional)', placeholder: 'kerf' },
      { key: 'smtp_host', label: 'SMTP host', placeholder: 'smtp.example.com' },
      { key: 'smtp_port', label: 'SMTP port', placeholder: '587', type: 'number' },
      { key: 'smtp_username', label: 'Username', placeholder: 'apikey' },
      { key: 'smtp_password', label: 'Password', placeholder: '••••••', type: 'password' },
    ],
  },
}

// Templates the test-send dropdown understands. Mirror of
// backend/cloud/email/templates.go:Templates.
const TEMPLATES = [
  'welcome',
  'password_reset',
  'password_reset_complete',
  'billing_receipt',
  'low_balance',
  'github_linked',
  'workshop_published',
]

export default function AdminEmail() {
  const user = useAuth((s) => s.user)
  const accessToken = useAuth((s) => s.accessToken)
  const navigate = useNavigate()

  const [rows, setRows] = useState([])
  const [activeName, setActiveName] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // provider name
  const [busy, setBusy] = useState(null)
  const [logEntries, setLogEntries] = useState([])
  const [logError, setLogError] = useState(null)
  const [logLoading, setLogLoading] = useState(false)
  const [showTest, setShowTest] = useState(false)

  // Admin role gate — backend enforces, this is just UX polish.
  useEffect(() => {
    if (!accessToken) return
    if (user && user.account_role !== 'admin' && user.account_role !== 'system') {
      navigate('/projects', { replace: true, state: { toast: 'Admin access required.' } })
    }
  }, [user, accessToken, navigate])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const out = await adminEmail.listProviders()
      setRows(Array.isArray(out?.providers) ? out.providers : [])
      setActiveName(out?.active || '')
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Admin access required.')
      } else {
        setError(err?.message || 'Failed to load providers')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadLog = async () => {
    setLogLoading(true)
    setLogError(null)
    try {
      const out = await adminEmail.log({ limit: 50 })
      setLogEntries(Array.isArray(out?.entries) ? out.entries : [])
    } catch (err) {
      setLogError(err?.message || 'Failed to load log')
    } finally {
      setLogLoading(false)
    }
  }

  useEffect(() => {
    if (accessToken) {
      load()
      loadLog()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken])

  const handleSave = async (name, payload) => {
    setBusy(name)
    setError(null)
    try {
      await adminEmail.upsertProvider(name, payload)
      setEditing(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  const handleDelete = async (name) => {
    if (!confirm(`Remove ${name} credentials? Outbound mail will fall back to the next configured provider.`)) return
    setBusy(name)
    setError(null)
    try {
      await adminEmail.deleteProvider(name)
      await load()
    } catch (err) {
      setError(err?.message || 'Delete failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Layout>
      <div className="max-w-3xl">
        <header className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <Mail size={18} className="text-kerf-300" />
            <h1 className="text-xl font-semibold text-ink-100">Transactional email</h1>
          </div>
          <p className="text-sm text-ink-400 max-w-2xl">
            Welcome, password reset, receipts, low-balance notices, and
            other system emails are dispatched through the active provider.
            Precedence is <span className="font-mono text-kerf-300">resend → ses → smtp</span> — the highest enabled provider wins.
            Credentials are encrypted at rest with a key derived from the JWT secret.
          </p>
        </header>

        {error && (
          <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 flex items-start gap-2">
            <AlertTriangle size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-amber-200">{error}</span>
          </div>
        )}

        <section className="mb-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs uppercase tracking-wider text-ink-500 font-medium">Providers</h2>
            <button
              type="button"
              onClick={() => setShowTest(true)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-ink-800 hover:border-kerf-300/40 hover:bg-ink-800/40 text-xs text-ink-300"
            >
              <Send size={11} />
              Send test
            </button>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-20 rounded-lg border border-ink-800 bg-ink-900 animate-pulse" />
              ))}
            </div>
          ) : (
            <ul className="space-y-3">
              {rows.map((row) => (
                <ProviderCard
                  key={row.provider}
                  row={row}
                  activeName={activeName}
                  busy={busy === row.provider}
                  onConfigure={() => setEditing(row.provider)}
                  onDelete={() => handleDelete(row.provider)}
                />
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs uppercase tracking-wider text-ink-500 font-medium">Recent log</h2>
            <button
              type="button"
              onClick={loadLog}
              disabled={logLoading}
              className="text-[11px] text-ink-400 hover:text-kerf-300 disabled:opacity-40"
            >
              Refresh
            </button>
          </div>
          {logError && (
            <div className="mb-2 text-xs text-amber-300">{logError}</div>
          )}
          {logLoading ? (
            <div className="h-16 rounded-md border border-ink-800 bg-ink-900 animate-pulse" />
          ) : logEntries.length === 0 ? (
            <p className="text-xs italic text-ink-500">No emails dispatched yet.</p>
          ) : (
            <div className="rounded-md border border-ink-800 overflow-hidden bg-ink-900/40">
              <table className="w-full text-xs">
                <thead className="bg-ink-900 text-[10px] uppercase tracking-wider text-ink-500">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">When</th>
                    <th className="text-left px-3 py-2 font-medium">Template</th>
                    <th className="text-left px-3 py-2 font-medium">To</th>
                    <th className="text-left px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-800/70">
                  {logEntries.map((e) => (
                    <LogRow key={e.id} entry={e} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {editing && (
          <CredentialModal
            name={editing}
            row={rows.find((r) => r.provider === editing)}
            onCancel={() => setEditing(null)}
            onSave={(payload) => handleSave(editing, payload)}
            saving={busy === editing}
          />
        )}

        {showTest && (
          <TestSendModal
            onCancel={() => setShowTest(false)}
            onSent={() => { setShowTest(false); loadLog() }}
          />
        )}
      </div>
    </Layout>
  )
}

function ProviderCard({ row, activeName, busy, onConfigure, onDelete }) {
  const form = PROVIDER_FORMS[row.provider] || { label: row.provider }
  const isActive = row.provider === activeName
  return (
    <li className="rounded-lg border border-ink-800 bg-ink-900/50 px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-ink-100">{form.label}</span>
            {isActive && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-kerf-300/15 text-kerf-300 border border-kerf-300/30">
                <Star size={9} />
                Active
              </span>
            )}
            {!isActive && row.has_secret && row.enabled && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-ink-800 text-ink-300 border border-ink-700">
                Standby
              </span>
            )}
            {!row.has_secret && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-amber-500/10 text-amber-300 border border-amber-500/30">
                Not configured
              </span>
            )}
            {row.has_secret && !row.enabled && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-ink-800 text-ink-400 border border-ink-700">
                Disabled
              </span>
            )}
          </div>
          <p className="text-xs text-ink-400 max-w-xl">
            {form.blurb || 'No description.'}
          </p>
          <div className="mt-1.5 flex items-center gap-3 text-[11px] text-ink-500">
            <span className="inline-flex items-center gap-1">
              <Clock size={10} />
              {row.last_used_at
                ? `Last used ${formatRelative(row.last_used_at)}`
                : 'Never used'}
            </span>
            {form.docsURL && (
              <a
                href={form.docsURL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-ink-400 hover:text-kerf-300"
              >
                <ExternalLink size={10} />
                Docs
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={onConfigure}
            disabled={busy}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-50"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
            {row.has_secret ? 'Update' : 'Configure'}
          </button>
          {row.has_secret && (
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              title="Remove credentials"
              className="p-1.5 rounded-md text-ink-400 hover:text-red-300 hover:bg-ink-800/60 disabled:opacity-50"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>
    </li>
  )
}

function LogRow({ entry }) {
  const status = entry.status
  const color =
    status === 'sent' ? 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10' :
    status === 'failed' ? 'text-red-300 border-red-500/30 bg-red-500/10' :
    'text-amber-300 border-amber-500/30 bg-amber-500/10'
  return (
    <tr className="hover:bg-ink-900/40">
      <td className="px-3 py-2 text-ink-400 whitespace-nowrap">{formatRelative(entry.created_at)}</td>
      <td className="px-3 py-2 font-mono text-ink-300">{entry.template}</td>
      <td className="px-3 py-2 text-ink-300 truncate max-w-[200px]" title={entry.to_email}>{entry.to_email}</td>
      <td className="px-3 py-2">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider border ${color}`}>
          {status}
        </span>
        {entry.error && (
          <div className="mt-1 text-[10px] text-ink-500 max-w-[280px] truncate" title={entry.error}>
            {entry.error}
          </div>
        )}
      </td>
    </tr>
  )
}

function CredentialModal({ name, row, onCancel, onSave, saving }) {
  const form = PROVIDER_FORMS[name]
  const [enabled, setEnabled] = useState(row?.enabled ?? true)
  const [rateLimit, setRateLimit] = useState(row?.rate_limit_per_minute || 60)
  const [secret, setSecret] = useState(() => {
    const o = {}
    for (const f of form?.fields || []) o[f.key] = ''
    return o
  })

  const requiredFields = (form?.fields || []).filter(
    (f) => !/optional/i.test(f.label),
  )
  const valid = requiredFields.every((f) => (secret[f.key] || '').toString().trim().length > 0)

  const submit = (e) => {
    e?.preventDefault()
    if (!valid) return
    // Convert numeric port to a number so JSON serializes correctly.
    const cleaned = { ...secret }
    if (cleaned.smtp_port) cleaned.smtp_port = Number(cleaned.smtp_port) || 0
    onSave({
      enabled,
      rate_limit_per_minute: Number(rateLimit) || 60,
      secret: cleaned,
    })
  }

  if (!form) return null

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-ink-950/80 backdrop-blur-sm p-6"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-xl border border-ink-800 bg-ink-900 shadow-2xl"
      >
        <div className="px-4 py-3 border-b border-ink-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-100">
            Configure {form.label}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded-md text-ink-400 hover:text-ink-100 hover:bg-ink-800"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>
        <div className="px-4 py-4 space-y-3">
          {form.blurb && (
            <p className="text-xs text-ink-400">{form.blurb}</p>
          )}
          {form.fields.map((f) => (
            <label key={f.key} className="block">
              <div className="text-[10px] uppercase tracking-wider text-ink-400 font-medium mb-1">
                {f.label}
              </div>
              <input
                type={f.type || 'text'}
                value={secret[f.key]}
                onChange={(e) => setSecret((s) => ({ ...s, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                autoComplete="off"
                className="w-full bg-ink-950 border border-ink-800 rounded px-2.5 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 font-mono"
              />
            </label>
          ))}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <div className="text-[10px] uppercase tracking-wider text-ink-400 font-medium mb-1">
                Rate limit (per minute)
              </div>
              <input
                type="number"
                min={1}
                value={rateLimit}
                onChange={(e) => setRateLimit(e.target.value)}
                className="w-full bg-ink-950 border border-ink-800 rounded px-2.5 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60"
              />
            </label>
            <label className="flex items-end gap-2 pb-1.5">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="accent-kerf-300"
              />
              <span className="text-xs text-ink-200">Enabled</span>
            </label>
          </div>
        </div>
        <div className="px-4 py-3 border-t border-ink-800 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1 rounded-md text-xs text-ink-400 hover:text-ink-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!valid || saving}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
            Save
          </button>
        </div>
      </form>
    </div>
  )
}

function TestSendModal({ onCancel, onSent }) {
  const [to, setTo] = useState('')
  const [template, setTemplate] = useState(TEMPLATES[0])
  const [vars, setVars] = useState('{}')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e?.preventDefault()
    setError(null)
    setBusy(true)
    try {
      let parsedVars = {}
      try {
        parsedVars = vars.trim() ? JSON.parse(vars) : {}
      } catch (err) {
        throw new Error('Vars must be valid JSON: ' + err.message)
      }
      await adminEmail.testSend({ to, template, vars: parsedVars })
      onSent?.()
    } catch (err) {
      setError(err?.message || 'Test send failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-ink-950/80 backdrop-blur-sm p-6"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-xl border border-ink-800 bg-ink-900 shadow-2xl"
      >
        <div className="px-4 py-3 border-b border-ink-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-100">Send test email</h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded-md text-ink-400 hover:text-ink-100 hover:bg-ink-800"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>
        <div className="px-4 py-4 space-y-3">
          <p className="text-xs text-ink-400">
            Renders the chosen template and queues it for the active provider.
            The send will appear in the log within a few seconds.
          </p>
          <label className="block">
            <div className="text-[10px] uppercase tracking-wider text-ink-400 font-medium mb-1">To</div>
            <input
              type="email"
              required
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="you@example.com"
              className="w-full bg-ink-950 border border-ink-800 rounded px-2.5 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600"
            />
          </label>
          <label className="block">
            <div className="text-[10px] uppercase tracking-wider text-ink-400 font-medium mb-1">Template</div>
            <div className="relative">
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                className="appearance-none w-full bg-ink-950 border border-ink-800 rounded px-2.5 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 font-mono pr-8"
              >
                {TEMPLATES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-500 pointer-events-none" />
            </div>
          </label>
          <label className="block">
            <div className="text-[10px] uppercase tracking-wider text-ink-400 font-medium mb-1">
              Vars (JSON)
            </div>
            <textarea
              value={vars}
              onChange={(e) => setVars(e.target.value)}
              rows={5}
              placeholder='{"Name": "Test", "AmountUSD": 10.00}'
              className="w-full bg-ink-950 border border-ink-800 rounded px-2.5 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 font-mono"
            />
          </label>
          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/5 px-2.5 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-ink-800 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1 rounded-md text-xs text-ink-400 hover:text-ink-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!to.trim() || busy}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
            Send
          </button>
        </div>
      </form>
    </div>
  )
}

function formatRelative(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Date.now() - then
  const sec = Math.round(diff / 1000)
  if (sec < 45) return 'just now'
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day}d ago`
  return `${Math.round(day / 30)}mo ago`
}
