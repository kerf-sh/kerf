import { useEffect, useState } from 'react'
import { X, Copy, Trash2, Link as LinkIcon, UserPlus, Check, Loader2 } from 'lucide-react'
import { api } from '../lib/api.js'

const ROLES = ['viewer', 'editor', 'owner']
const LINK_ROLES = ['viewer', 'editor']

function Tab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? 'border-kerf-300 text-kerf-200'
          : 'border-transparent text-ink-300 hover:text-ink-100'
      }`}
    >
      {children}
    </button>
  )
}

function MembersTab({ projectId }) {
  const [members, setMembers] = useState(null)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('editor')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    api.listMembers(projectId)
      .then((m) => { if (!cancelled) setMembers(m || []) })
      .catch((e) => { if (!cancelled) setErr(e?.message || String(e)) })
    return () => { cancelled = true }
  }, [projectId, reloadKey])

  const reload = () => setReloadKey((k) => k + 1)

  async function invite(e) {
    e.preventDefault()
    if (!email.trim()) return
    setBusy(true); setErr('')
    try {
      await api.inviteMember(projectId, { email: email.trim(), role })
      setEmail('')
      reload()
    } catch (ex) {
      setErr(ex?.message || 'Failed to invite')
    } finally {
      setBusy(false)
    }
  }

  async function changeRole(uid, r) {
    try {
      await api.updateMember(projectId, uid, { role: r })
      reload()
    } catch (e) {
      setErr(e?.message || String(e))
    }
  }

  async function remove(uid) {
    if (!confirm('Remove this member?')) return
    try {
      await api.removeMember(projectId, uid)
      reload()
    } catch (e) {
      setErr(e?.message || String(e))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={invite} className="flex gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@example.com"
          className="flex-1 bg-ink-850 border border-ink-700 rounded-md px-3 py-1.5 text-sm text-ink-100 placeholder:text-ink-400 outline-none focus:border-kerf-300/60"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="bg-ink-850 border border-ink-700 rounded-md px-2 py-1.5 text-sm text-ink-100 outline-none focus:border-kerf-300/60"
        >
          {LINK_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <button
          type="submit"
          disabled={busy || !email.trim()}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-sm font-medium hover:bg-kerf-200 disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <UserPlus size={13} />}
          Invite
        </button>
      </form>
      {err && <div className="text-xs text-red-400">{err}</div>}
      <div className="flex flex-col gap-1">
        {members === null ? (
          <div className="text-xs text-ink-400 py-4 text-center">Loading members…</div>
        ) : members.length === 0 ? (
          <div className="text-xs text-ink-400 py-4 text-center">No members yet.</div>
        ) : members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-3 py-2 px-2 rounded hover:bg-ink-800">
            <div className="w-7 h-7 rounded-full bg-ink-700 flex items-center justify-center text-[11px] text-ink-200 font-semibold flex-shrink-0">
              {(m.user?.name || m.user?.email || '?').slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-ink-100 truncate">{m.user?.name || m.user?.email}</div>
              {m.user?.name && (
                <div className="text-[11px] text-ink-400 truncate">{m.user?.email}</div>
              )}
            </div>
            <select
              value={m.role}
              onChange={(e) => changeRole(m.user_id, e.target.value)}
              disabled={m.role === 'owner'}
              className="bg-ink-850 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 outline-none disabled:opacity-50"
            >
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            {m.role !== 'owner' && (
              <button
                type="button"
                onClick={() => remove(m.user_id)}
                className="p-1 rounded text-ink-400 hover:text-red-400 hover:bg-ink-700"
                title="Remove"
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function LinksTab({ projectId }) {
  const [links, setLinks] = useState(null)
  const [role, setRole] = useState('viewer')
  const [expiresIn, setExpiresIn] = useState('never')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [copiedId, setCopiedId] = useState(null)
  const [freshTokens, setFreshTokens] = useState({}) // tokens only available at creation time
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    api.listShareLinks(projectId)
      .then((ls) => { if (!cancelled) setLinks(ls || []) })
      .catch((e) => { if (!cancelled) setErr(e?.message || String(e)) })
    return () => { cancelled = true }
  }, [projectId, reloadKey])

  const reload = () => setReloadKey((k) => k + 1)

  async function create() {
    setBusy(true); setErr('')
    try {
      let expires_at = null
      if (expiresIn !== 'never') {
        const days = parseInt(expiresIn, 10)
        expires_at = new Date(Date.now() + days * 86400_000).toISOString()
      }
      const link = await api.createShareLink(projectId, { role, expires_at })
      if (link?.token) setFreshTokens((t) => ({ ...t, [link.id]: link.token }))
      reload()
    } catch (ex) {
      setErr(ex?.message || 'Failed to create link')
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id) {
    if (!confirm('Revoke this link?')) return
    try {
      await api.revokeShareLink(projectId, id)
      reload()
    } catch (e) {
      setErr(e?.message || String(e))
    }
  }

  function copy(id, token) {
    if (!token) return
    const url = `${window.location.origin}/share/${token}`
    navigator.clipboard.writeText(url).then(() => {
      setCopiedId(id)
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500)
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] uppercase tracking-wider text-ink-400">Role</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="bg-ink-850 border border-ink-700 rounded-md px-2 py-1.5 text-sm text-ink-100 outline-none focus:border-kerf-300/60"
          >
            {LINK_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] uppercase tracking-wider text-ink-400">Expires</label>
          <select
            value={expiresIn}
            onChange={(e) => setExpiresIn(e.target.value)}
            className="bg-ink-850 border border-ink-700 rounded-md px-2 py-1.5 text-sm text-ink-100 outline-none focus:border-kerf-300/60"
          >
            <option value="never">Never</option>
            <option value="1">1 day</option>
            <option value="7">7 days</option>
            <option value="30">30 days</option>
          </select>
        </div>
        <button
          type="button"
          onClick={create}
          disabled={busy}
          className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-sm font-medium hover:bg-kerf-200 disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <LinkIcon size={13} />}
          Create link
        </button>
      </div>
      {err && <div className="text-xs text-red-400">{err}</div>}
      <div className="flex flex-col gap-1">
        {links === null ? (
          <div className="text-xs text-ink-400 py-4 text-center">Loading links…</div>
        ) : links.length === 0 ? (
          <div className="text-xs text-ink-400 py-4 text-center">No share links yet.</div>
        ) : links.map((l) => {
          const token = l.token || freshTokens[l.id]
          const url = token ? `${window.location.origin}/share/${token}` : '(token hidden — copy at creation)'
          return (
            <div key={l.id} className="flex items-center gap-2 py-2 px-2 rounded hover:bg-ink-800">
              <LinkIcon size={13} className="text-ink-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-mono text-ink-100 truncate">{url}</div>
                <div className="text-[10px] text-ink-400 mt-0.5">
                  {l.role} · {l.uses ?? 0} uses
                  {l.expires_at && ` · expires ${new Date(l.expires_at).toLocaleDateString()}`}
                  {l.revoked_at && ' · revoked'}
                </div>
              </div>
              {token && (
                <button
                  type="button"
                  onClick={() => copy(l.id, token)}
                  className="p-1 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-700"
                  title="Copy link"
                >
                  {copiedId === l.id ? <Check size={13} className="text-kerf-300" /> : <Copy size={13} />}
                </button>
              )}
              {!l.revoked_at && (
                <button
                  type="button"
                  onClick={() => revoke(l.id)}
                  className="p-1 rounded text-ink-400 hover:text-red-400 hover:bg-ink-700"
                  title="Revoke"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ShareModal({ projectId, onClose }) {
  const [tab, setTab] = useState('members')

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-950/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-ink-900 border border-ink-700 rounded-xl shadow-2xl flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <h2 className="text-base font-semibold text-ink-100">Share project</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-ink-800 text-ink-300 hover:text-ink-100"
          >
            <X size={16} />
          </button>
        </div>
        <div className="px-4 border-b border-ink-800 flex gap-1">
          <Tab active={tab === 'members'} onClick={() => setTab('members')}>Members</Tab>
          <Tab active={tab === 'links'} onClick={() => setTab('links')}>Links</Tab>
        </div>
        <div className="p-4 overflow-auto">
          {tab === 'members' ? <MembersTab projectId={projectId} /> : <LinksTab projectId={projectId} />}
        </div>
      </div>
    </div>
  )
}
