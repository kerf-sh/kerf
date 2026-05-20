import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Loader2, Save, Upload, UserCog, X } from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { useAuth } from '../store/auth.js'
import { api, ApiError } from '../lib/api.js'

export default function Profile() {
  const user = useAuth((s) => s.user)
  const setUser = useAuth((s) => s.setUser)

  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => { setName(user?.name || '') }, [user?.id])

  const onPickAvatar = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) { setErr('Pick an image file.'); return }
    setAvatarBusy(true); setErr(null); setMsg(null)
    try {
      const updated = await api.uploadAvatar(file)
      if (updated) setUser({ ...user, ...updated })
      setMsg('Avatar updated.')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : (e?.message || 'Upload failed.'))
    } finally {
      setAvatarBusy(false)
    }
  }

  const onClearAvatar = async () => {
    setAvatarBusy(true); setErr(null); setMsg(null)
    try {
      const updated = await api.deleteAvatar()
      if (updated) setUser({ ...user, ...updated })
      else setUser({ ...user, avatar_url: '' })
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not clear avatar.')
    } finally {
      setAvatarBusy(false)
    }
  }

  const save = async (e) => {
    e?.preventDefault?.()
    if (saving) return
    setSaving(true); setMsg(null); setErr(null)
    try {
      const updated = await api.updateMe({ name: name.trim() })
      if (updated) setUser({ ...user, ...updated })
      setMsg('Saved.')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : (e?.message || 'Could not save profile.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Layout>
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <span className="grid place-items-center w-10 h-10 rounded-xl bg-kerf-300/15 border border-kerf-300/30 text-kerf-300">
            <UserCog size={18} />
          </span>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">Account</p>
            <h1 className="font-display text-2xl font-semibold tracking-tight">Profile</h1>
          </div>
        </div>

        <Card className="p-6">
          <div className="flex items-start gap-4 mb-5 pb-5 border-b border-ink-800">
            <div className="relative">
              {user?.avatar_url ? (
                <img src={user.avatar_url} alt="" className="w-20 h-20 rounded-full object-cover bg-ink-800" />
              ) : (
                <div className="grid place-items-center w-20 h-20 rounded-full bg-kerf-300/15 border border-kerf-300/30 text-kerf-300 font-semibold text-2xl">
                  {(user?.name || user?.email || '?').slice(0, 2).toUpperCase()}
                </div>
              )}
              {avatarBusy && (
                <div className="absolute inset-0 grid place-items-center bg-ink-950/70 rounded-full">
                  <Loader2 size={18} className="animate-spin text-kerf-300" />
                </div>
              )}
            </div>
            <div className="flex-1 flex flex-col gap-2">
              <div>
                <p className="text-[11px] font-medium text-ink-300 uppercase tracking-wider">Avatar</p>
                <p className="text-[12px] text-ink-500 leading-snug">PNG, JPEG or WebP. We'll resize and re-host on our CDN.</p>
              </div>
              <div className="flex items-center gap-2">
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onPickAvatar} />
                <Button type="button" variant="ghost" size="sm" onClick={() => fileRef.current?.click()} disabled={avatarBusy}>
                  <Upload size={12} />
                  {user?.avatar_url ? 'Replace' : 'Upload'}
                </Button>
                {user?.avatar_url && (
                  <Button type="button" variant="ghost" size="sm" onClick={onClearAvatar} disabled={avatarBusy}>
                    <X size={12} />
                    Remove
                  </Button>
                )}
              </div>
            </div>
          </div>

          <form className="flex flex-col gap-4" onSubmit={save}>
            {err && (
              <div
                role="alert"
                aria-live="assertive"
                className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
              >
                <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden />
                <span>{err}</span>
              </div>
            )}
            {msg && (
              <div role="status" aria-live="polite" className="text-xs text-kerf-300">{msg}</div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-medium text-ink-300 uppercase tracking-wider">Email</label>
              <div className="px-3 py-2 rounded-lg border border-ink-800 bg-ink-950 text-sm text-ink-200 font-mono">
                {user?.email || '—'}
              </div>
              <p className="text-[11px] text-ink-500">Email is bound to your sign-in method and can't be changed here.</p>
            </div>

            <Input
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />

            <div className="flex justify-end">
              <Button type="submit" variant="primary" size="md" disabled={saving}>
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </Layout>
  )
}
