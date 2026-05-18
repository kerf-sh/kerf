// Account settings page. Three sections plus a danger zone.
//   - Profile: name + email (avatar lives in the existing Layout uploader).
//   - Password: change-password form (current + new + confirm).
//   - Account: read-only created_at + role + verified-publisher badge.
//   - Danger zone: delete account with typed-confirmation.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Loader2, Save, Lock, AlertTriangle, BadgeCheck,
} from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import { useAuth } from '../store/auth.js'
import { api, ApiError } from '../lib/api.js'
import { appVersion } from '../lib/appVersion.js'

function fmtDate(s) {
  if (!s) return ''
  try { return new Intl.DateTimeFormat(undefined, { dateStyle: 'long' }).format(new Date(s)) }
  catch { return s }
}

export default function Settings() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const setUser = useAuth((s) => s.setUser)
  const logout = useAuth((s) => s.logout)

  // ----- Profile -----
  const [name, setName] = useState(user?.name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileMsg, setProfileMsg] = useState(null)
  useEffect(() => {
    setName(user?.name || '')
    setEmail(user?.email || '')
  }, [user?.id])

  const saveProfile = async (e) => {
    e?.preventDefault?.()
    if (profileSaving) return
    const patch = {}
    if (name !== (user?.name || '')) patch.name = name.trim()
    if (email !== (user?.email || '')) patch.email = email.trim()
    if (Object.keys(patch).length === 0) {
      setProfileMsg({ kind: 'info', text: 'Nothing to save.' })
      return
    }
    setProfileSaving(true)
    setProfileMsg(null)
    try {
      const updated = await api.updateMe(patch)
      setUser(updated)
      setProfileMsg({ kind: 'ok', text: 'Saved.' })
    } catch (err) {
      setProfileMsg({ kind: 'err', text: err instanceof ApiError ? err.message : 'Save failed.' })
    } finally {
      setProfileSaving(false)
    }
  }

  // ----- Password -----
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdSaving, setPwdSaving] = useState(false)
  const [pwdMsg, setPwdMsg] = useState(null)

  const savePassword = async (e) => {
    e?.preventDefault?.()
    if (pwdSaving) return
    if (newPwd !== confirmPwd) { setPwdMsg({ kind: 'err', text: 'New passwords do not match.' }); return }
    if (newPwd.length < 8) { setPwdMsg({ kind: 'err', text: 'New password must be at least 8 characters.' }); return }
    setPwdSaving(true); setPwdMsg(null)
    try {
      await api.changePassword(currentPwd, newPwd)
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('')
      setPwdMsg({ kind: 'ok', text: 'Password updated.' })
    } catch (err) {
      setPwdMsg({ kind: 'err', text: err instanceof ApiError ? err.message : 'Could not change password.' })
    } finally {
      setPwdSaving(false)
    }
  }

  // ----- Delete account -----
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteMsg, setDeleteMsg] = useState(null)

  const deleteAccount = async () => {
    if (deleteConfirm !== 'DELETE') {
      setDeleteMsg({ kind: 'err', text: 'Type DELETE in the confirmation box first.' })
      return
    }
    setDeleting(true); setDeleteMsg(null)
    try {
      await api.deleteMe()
      logout()
      navigate('/', { replace: true })
    } catch (err) {
      setDeleting(false)
      setDeleteMsg({ kind: 'err', text: err instanceof ApiError ? err.message : 'Delete failed.' })
    }
  }

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <header className="flex items-center gap-3 px-6 py-4 border-b border-ink-800">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-ink-400 hover:text-kerf-300"
          title="Back"
        >
          <ArrowLeft size={16} />
        </button>
        <LogoWordmark />
        <span className="text-ink-500">/</span>
        <span className="text-sm text-ink-200">Settings</span>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-10">
        {/* Profile */}
        <section>
          <h2 className="text-sm font-semibold text-ink-100 mb-1">Profile</h2>
          <p className="text-xs text-ink-400 mb-4">Your name and email. Avatar is set from the user menu in the header.</p>
          <form onSubmit={saveProfile} className="space-y-3 max-w-md">
            <Field label="Name">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm focus:outline-none focus:border-kerf-300/60"
              />
            </Field>
            <Field label="Email">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm font-mono focus:outline-none focus:border-kerf-300/60"
              />
            </Field>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={profileSaving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-50"
              >
                {profileSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                Save
              </button>
              {profileMsg && <Inline msg={profileMsg} />}
            </div>
          </form>
        </section>

        {/* Password */}
        <section>
          <h2 className="text-sm font-semibold text-ink-100 mb-1">Password</h2>
          <p className="text-xs text-ink-400 mb-4">At least 8 characters. Active sessions stay signed in until they refresh.</p>
          <form onSubmit={savePassword} className="space-y-3 max-w-md">
            <Field label="Current password">
              <input
                type="password"
                value={currentPwd}
                onChange={(e) => setCurrentPwd(e.target.value)}
                autoComplete="current-password"
                className="w-full px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm font-mono focus:outline-none focus:border-kerf-300/60"
              />
            </Field>
            <Field label="New password">
              <input
                type="password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                autoComplete="new-password"
                className="w-full px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm font-mono focus:outline-none focus:border-kerf-300/60"
              />
            </Field>
            <Field label="Confirm new password">
              <input
                type="password"
                value={confirmPwd}
                onChange={(e) => setConfirmPwd(e.target.value)}
                autoComplete="new-password"
                className="w-full px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm font-mono focus:outline-none focus:border-kerf-300/60"
              />
            </Field>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={pwdSaving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-50"
              >
                {pwdSaving ? <Loader2 size={12} className="animate-spin" /> : <Lock size={12} />}
                Update password
              </button>
              {pwdMsg && <Inline msg={pwdMsg} />}
            </div>
          </form>
        </section>

        {/* Account */}
        <section>
          <h2 className="text-sm font-semibold text-ink-100 mb-1">Account</h2>
          <div className="text-xs text-ink-400 space-y-1 max-w-md">
            <Row k="Member since" v={fmtDate(user?.created_at)} />
            <Row k="Role" v={user?.account_role || 'user'} />
            {user?.is_verified_publisher && (
              <div className="inline-flex items-center gap-1.5 mt-1 px-2 py-1 rounded-md bg-amber-300/10 text-amber-300 border border-amber-300/30">
                <BadgeCheck size={12} />
                Verified publisher
              </div>
            )}
          </div>
        </section>

        {/* About */}
        <section>
          <h2 className="text-sm font-semibold text-ink-100 mb-1">About</h2>
          <div className="text-xs text-ink-400 space-y-1 max-w-md">
            <Row k="Kerf version" v={`v${appVersion()}`} />
          </div>
        </section>

        {/* Danger zone */}
        <section className="border border-red-400/30 rounded-md p-4 bg-red-400/5">
          <h2 className="text-sm font-semibold text-red-300 mb-1 flex items-center gap-2">
            <AlertTriangle size={14} />
            Danger zone
          </h2>
          <p className="text-xs text-ink-400 mb-3">
            Delete your account permanently. Your projects and files are removed via the database
            cascade. This cannot be undone.
          </p>
          <div className="flex items-center gap-2 max-w-md">
            <input
              type="text"
              placeholder='Type DELETE to confirm'
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-ink-900 border border-ink-700 rounded text-sm font-mono focus:outline-none focus:border-red-400/60"
            />
            <button
              type="button"
              onClick={deleteAccount}
              disabled={deleting || deleteConfirm !== 'DELETE'}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-500 text-white text-xs font-medium hover:bg-red-400 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {deleting ? <Loader2 size={12} className="animate-spin" /> : null}
              Delete account
            </button>
          </div>
          {deleteMsg && <div className="mt-2"><Inline msg={deleteMsg} /></div>}
        </section>
      </main>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[11px] uppercase tracking-wide text-ink-500 mb-1">{label}</span>
      {children}
    </label>
  )
}

function Row({ k, v }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-ink-500 w-32">{k}</span>
      <span className="text-ink-200 font-mono">{v || '—'}</span>
    </div>
  )
}

function Inline({ msg }) {
  if (!msg) return null
  const cls = msg.kind === 'err' ? 'text-red-400'
    : msg.kind === 'ok' ? 'text-emerald-400'
    : 'text-ink-400'
  return <span className={`text-[11px] ${cls}`}>{msg.text}</span>
}
