// AdminDistributors — operator-only admin page for distributor APIs.
//
// Mounted at /admin/distributors (admin role only). Lists every known
// distributor (DigiKey, Mouser, LCSC) with its enable toggle, last-used
// timestamp, and a "Configure" button that opens a credential modal.
// Non-admins are bounced to /projects with a toast.
//
// Security note: the backend re-checks admin role on every endpoint;
// this route is purely a UX gate. If a non-admin somehow hits this URL,
// they'd get 403s from /api/admin/distributors and see an error state.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck, Plus, Trash2, RefreshCw, AlertTriangle,
  Check, X, Loader2, ExternalLink, Clock,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'

// Per-distributor credential form schemas. Drives the modal field set
// and the validation gate. Keep in sync with the backend's
// validateCredentials in backend/internal/distributors/service.go.
const DISTRIBUTOR_FORMS = {
  digikey: {
    label: 'DigiKey',
    fields: [
      { key: 'client_id', label: 'Client ID', placeholder: 'AbCdEf…' },
      { key: 'client_secret', label: 'Client Secret', placeholder: '••••••', type: 'password' },
    ],
    docsURL: 'https://developer.digikey.com',
    blurb: 'OAuth2 client credentials. Create an app at developer.digikey.com → Production APIs → Search v3.',
  },
  mouser: {
    label: 'Mouser',
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password' },
    ],
    docsURL: 'https://www.mouser.com/api-hub',
    blurb: 'Set your account locale to United States / USD before generating an API key — pricing is locale-bound.',
  },
  lcsc: {
    label: 'LCSC',
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password' },
    ],
    docsURL: 'https://www.lcsc.com/api-portal',
    blurb: 'Pricing is returned in CNY; conversion to USD requires the cloud FX cache to be running.',
  },
}

export default function AdminDistributors() {
  const user = useAuth((s) => s.user)
  const accessToken = useAuth((s) => s.accessToken)
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // distributor name
  const [busy, setBusy] = useState(null)        // distributor name being mutated

  // Gate: admin role only. We let the backend be the source of truth
  // (it'll 403 us regardless), but we render a redirect-with-toast for
  // non-admins to avoid a flash of error UI.
  useEffect(() => {
    // Wait for the user row to hydrate. Layout fetches /api/me lazily
    // when the store has a token but no user.
    if (!accessToken) return
    if (user && user.account_role !== 'admin' && user.account_role !== 'system') {
      navigate('/projects', { replace: true, state: { toast: 'Admin access required.' } })
    }
  }, [user, accessToken, navigate])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const out = await api.admin.listDistributors()
      setRows(Array.isArray(out?.distributors) ? out.distributors : [])
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Admin access required.')
      } else {
        setError(err?.message || 'Failed to load distributors')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (accessToken) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken])

  const handleSave = async (name, payload) => {
    setBusy(name)
    setError(null)
    try {
      await api.admin.updateDistributor(name, payload)
      setEditing(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  const handleToggle = async (name, current) => {
    // Toggling enabled requires re-supplying the secret because the PUT
    // route always replaces credentials. The button is disabled when
    // there's no secret on file; toggling-only is "configure" instead.
    if (!current.has_secret) {
      setEditing(name)
      return
    }
    // No way to flip enabled without re-uploading the secret today —
    // this is a UX limitation; for now, opening the editor is the
    // path. (We could add a dedicated PATCH /enabled endpoint later.)
    setEditing(name)
  }

  const handleDelete = async (name) => {
    if (!confirm(`Remove ${name} credentials? Any pending refreshes will fail until re-configured.`)) return
    setBusy(name)
    setError(null)
    try {
      await api.admin.deleteDistributor(name)
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
            <ShieldCheck size={18} className="text-kerf-300" />
            <h1 className="text-xl font-semibold text-ink-100">Distributor APIs</h1>
          </div>
          <p className="text-sm text-ink-400 max-w-2xl">
            Live pricing and stock for Library parts come from these
            distributors. Credentials are encrypted at rest with a key
            derived from the JWT secret — rotating that secret will
            invalidate every entry below and require re-configuration.
          </p>
        </header>

        {error && (
          <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 flex items-start gap-2">
            <AlertTriangle size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-amber-200">{error}</span>
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 rounded-lg border border-ink-800 bg-ink-900 animate-pulse" />
            ))}
          </div>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => (
              <DistributorCard
                key={row.name}
                row={row}
                busy={busy === row.name}
                onConfigure={() => setEditing(row.name)}
                onDelete={() => handleDelete(row.name)}
                onToggle={() => handleToggle(row.name, row)}
              />
            ))}
            {rows.length === 0 && (
              <li className="text-sm text-ink-500 italic">
                No distributors known to the registry.
              </li>
            )}
          </ul>
        )}

        {editing && (
          <CredentialModal
            name={editing}
            row={rows.find((r) => r.name === editing)}
            onCancel={() => setEditing(null)}
            onSave={(payload) => handleSave(editing, payload)}
            saving={busy === editing}
          />
        )}
      </div>
    </Layout>
  )
}

function DistributorCard({ row, busy, onConfigure, onDelete, onToggle }) {
  const form = DISTRIBUTOR_FORMS[row.name] || { label: row.name }
  return (
    <li className="rounded-lg border border-ink-800 bg-ink-900/50 px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-ink-100">{form.label}</span>
            {row.has_secret ? (
              row.enabled ? (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-kerf-300/15 text-kerf-300 border border-kerf-300/30">
                  <Check size={9} />
                  Enabled
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-ink-800 text-ink-400 border border-ink-700">
                  Disabled
                </span>
              )
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-amber-500/10 text-amber-300 border border-amber-500/30">
                Not configured
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
            <span className="font-mono">
              {row.rate_limit_per_minute || 60} rpm
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

function CredentialModal({ name, row, onCancel, onSave, saving }) {
  const form = DISTRIBUTOR_FORMS[name]
  const [enabled, setEnabled] = useState(row?.enabled ?? true)
  const [rateLimit, setRateLimit] = useState(row?.rate_limit_per_minute || 60)
  const [secret, setSecret] = useState(() => {
    const o = {}
    for (const f of form?.fields || []) o[f.key] = ''
    return o
  })

  const valid = (form?.fields || []).every((f) => (secret[f.key] || '').trim().length > 0)

  const submit = (e) => {
    e?.preventDefault()
    if (!valid) return
    onSave({
      enabled,
      rate_limit_per_minute: Number(rateLimit) || 60,
      secret,
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
