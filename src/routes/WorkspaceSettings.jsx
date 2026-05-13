import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AlertCircle, Copy, Loader2, Save, Settings, Trash2, Upload, X } from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { api, ApiError } from '../lib/api.js'
import { useWorkspaces } from '../store/workspaces.js'

export default function WorkspaceSettings() {
  const navigate = useNavigate()
  const { workspaceSlug } = useParams()
  const loadAll = useWorkspaces((s) => s.loadAll)

  const [ws, setWs] = useState(null)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [tokens, setTokens] = useState([])
  const [tokensLoading, setTokensLoading] = useState(true)
  const [newTokenName, setNewTokenName] = useState('')
  const [tokenCreating, setTokenCreating] = useState(false)
  const [newCreatedToken, setNewCreatedToken] = useState(null)
  const fileRef = useRef(null)

  const onPickAvatar = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) { setErr('Pick an image file.'); return }
    setAvatarBusy(true); setErr(null); setMsg(null)
    try {
      const updated = await api.uploadWorkspaceAvatar(workspaceSlug, file)
      setWs(updated)
      await loadAll()
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
      const updated = await api.deleteWorkspaceAvatar(workspaceSlug)
      setWs(updated || { ...ws, avatar_url: '' })
      await loadAll()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not clear avatar.')
    } finally {
      setAvatarBusy(false)
    }
  }

  const loadTokens = () => {
    setTokensLoading(true)
    api.listAPITokens()
      .then(setTokens)
      .catch(() => {})
      .finally(() => setTokensLoading(false))
  }

  const createToken = async (e) => {
    e?.preventDefault()
    if (!newTokenName.trim() || tokenCreating) return
    setTokenCreating(true)
    try {
      const created = await api.createAPIToken(newTokenName.trim())
      setNewCreatedToken(created.token)
      setNewTokenName('')
      loadTokens()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not create token.')
    } finally {
      setTokenCreating(false)
    }
  }

  const revokeToken = async (tokenID) => {
    try {
      await api.revokeAPIToken(tokenID)
      loadTokens()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not revoke token.')
    }
  }

  useEffect(() => {
    let cancelled = false
    api.getWorkspace(workspaceSlug)
      .then((data) => {
        if (cancelled) return
        setWs(data); setName(data.name || ''); setSlug(data.slug || '')
      })
      .catch((e) => { if (!cancelled) setErr(e instanceof ApiError ? e.message : 'Could not load workspace.') })
    return () => { cancelled = true }
  }, [workspaceSlug])

  useEffect(() => {
    let cancelled = false
    api.listAPITokens()
      .then((data) => { if (!cancelled) setTokens(data) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setTokensLoading(false) })
    return () => { cancelled = true }
  }, [])

  const save = async (e) => {
    e?.preventDefault?.()
    if (saving) return
    setSaving(true); setMsg(null); setErr(null)
    try {
      const updated = await api.updateWorkspace(workspaceSlug, { name: name.trim(), slug: slug.trim() })
      setWs(updated)
      await loadAll()
      setMsg('Saved.')
      if (updated.slug && updated.slug !== workspaceSlug) {
        navigate(`/w/${updated.slug}/settings`, { replace: true })
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : (e?.message || 'Could not save workspace.'))
    } finally {
      setSaving(false)
    }
  }

  const onDelete = async () => {
    const sure = window.prompt(`Type the workspace slug "${workspaceSlug}" to confirm deletion. This is permanent.`)
    if (sure !== workspaceSlug) return
    setDeleting(true)
    try {
      await api.deleteWorkspace(workspaceSlug)
      await loadAll()
      navigate('/projects', { replace: true })
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not delete workspace.')
      setDeleting(false)
    }
  }

  if (!ws && !err) {
    return (
      <Layout>
        <div className="max-w-2xl mx-auto py-12 text-center text-ink-400">
          <Loader2 size={16} className="animate-spin inline-block mr-2" /> Loading…
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <span className="grid place-items-center w-10 h-10 rounded-xl bg-kerf-300/15 border border-kerf-300/30 text-kerf-300">
            <Settings size={18} />
          </span>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">Workspace</p>
            <h1 className="font-display text-2xl font-semibold tracking-tight">{ws?.name || workspaceSlug}</h1>
          </div>
        </div>

        <Card className="p-6 mb-6">
          <div className="flex items-start gap-4 mb-5 pb-5 border-b border-ink-800">
            <div className="relative">
              {ws?.avatar_url ? (
                <img
                  src={ws.avatar_url}
                  alt=""
                  className="w-20 h-20 rounded-2xl object-cover bg-ink-800"
                />
              ) : (
                <div className="grid place-items-center w-20 h-20 rounded-2xl bg-kerf-300/15 border border-kerf-300/30 text-kerf-300 font-semibold text-2xl tracking-tight">
                  {(ws?.name || workspaceSlug || '?').slice(0, 2).toUpperCase()}
                </div>
              )}
              {avatarBusy && (
                <div className="absolute inset-0 grid place-items-center bg-ink-950/70 rounded-2xl">
                  <Loader2 size={18} className="animate-spin text-kerf-300" />
                </div>
              )}
            </div>
            <div className="flex-1 flex flex-col gap-2">
              <div>
                <p className="text-[11px] font-medium text-ink-300 uppercase tracking-wider">Avatar</p>
                <p className="text-[12px] text-ink-500 leading-snug">
                  Shown next to projects you publish, in Workshop listings, and on Library parts.
                  PNG or JPEG, square preferred.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={onPickAvatar}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => fileRef.current?.click()}
                  disabled={avatarBusy}
                >
                  <Upload size={12} />
                  {ws?.avatar_url ? 'Replace' : 'Upload'}
                </Button>
                {ws?.avatar_url && (
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
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{err}</span>
              </div>
            )}
            {msg && <div className="text-xs text-kerf-300">{msg}</div>}

            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-medium text-ink-300 uppercase tracking-wider">URL slug</label>
              <div className="flex items-stretch rounded-lg border border-ink-700 bg-ink-950 overflow-hidden focus-within:border-kerf-300/60 transition-colors">
                <span className="grid place-items-center px-3 text-[12px] font-mono text-ink-500 bg-ink-900 border-r border-ink-800">/w/</span>
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, '-'))}
                  className="flex-1 bg-transparent px-2 py-2 text-sm font-mono text-ink-100 outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button type="submit" variant="primary" size="md" disabled={saving}>
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        </Card>

        <Card className="p-6 mb-6">
          <h3 className="font-display text-base font-semibold tracking-tight mb-1">API Tokens</h3>
          <p className="text-xs text-ink-400 mb-4">
            Tokens are shown only once at creation. Store them securely.
          </p>

          {newCreatedToken && (
            <div className="mb-4 p-3 rounded-lg border border-kerf-300/30 bg-kerf-300/10">
              <p className="text-xs text-kerf-300 mb-2 font-medium">Token created — copy it now, it won&apos;t be shown again.</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono text-ink-100 bg-ink-950 px-2 py-1.5 rounded overflow-x-auto">{newCreatedToken}</code>
                <Button variant="ghost" size="sm" onClick={() => navigator.clipboard.writeText(newCreatedToken)}>
                  <Copy size={12} />
                </Button>
              </div>
              <button
                type="button"
                className="mt-2 text-xs text-ink-500 hover:text-ink-300 transition-colors"
                onClick={() => setNewCreatedToken(null)}
              >
                Done
              </button>
            </div>
          )}

          <form className="flex items-center gap-2 mb-6" onSubmit={createToken}>
            <Input
              placeholder="Token name"
              value={newTokenName}
              onChange={(e) => setNewTokenName(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" variant="primary" size="md" disabled={tokenCreating || !newTokenName.trim()}>
              {tokenCreating ? <Loader2 size={13} className="animate-spin" /> : null}
              Generate
            </Button>
          </form>

          {tokensLoading ? (
            <div className="text-center text-xs text-ink-500 py-4">
              <Loader2 size={14} className="animate-spin inline-block mr-2" /> Loading…
            </div>
          ) : tokens.length === 0 ? (
            <p className="text-xs text-ink-500 text-center py-4">No API tokens yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-ink-800">
                    <th className="text-left pb-2 text-[11px] font-medium text-ink-400 uppercase tracking-wider">Name</th>
                    <th className="text-left pb-2 text-[11px] font-medium text-ink-400 uppercase tracking-wider">Created</th>
                    <th className="text-left pb-2 text-[11px] font-medium text-ink-400 uppercase tracking-wider">Last used</th>
                    <th className="pb-2 w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map((token) => (
                    <tr key={token.id} className="border-b border-ink-800/50 last:border-0">
                      <td className="py-2.5 font-mono text-ink-100">{token.name}</td>
                      <td className="py-2.5 text-ink-400">{token.created_at ? new Date(token.created_at).toLocaleDateString() : '—'}</td>
                      <td className="py-2.5 text-ink-400">{token.last_used_at ? new Date(token.last_used_at).toLocaleDateString() : 'Never'}</td>
                      <td className="py-2.5 text-right">
                        <Button variant="ghost" size="sm" onClick={() => revokeToken(token.id)}>
                          <Trash2 size={12} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card className="p-6 border-red-500/20">
          <h3 className="font-display text-base font-semibold tracking-tight text-red-200 mb-1">Danger zone</h3>
          <p className="text-xs text-ink-400 mb-4">
            Deleting a workspace removes all of its projects, files, and chat history. This is permanent.
          </p>
          <Button variant="ghost" size="md" onClick={onDelete} disabled={deleting}>
            <Trash2 size={13} />
            {deleting ? 'Deleting…' : 'Delete workspace'}
          </Button>
        </Card>
      </div>
    </Layout>
  )
}
