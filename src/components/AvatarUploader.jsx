import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Trash2, X, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_BYTES = 1 * 1024 * 1024

// AvatarUploader is a self-contained dialog: a file picker, a live preview
// of the chosen image, an "Upload" CTA, and (when an avatar exists) a
// "Remove" affordance. The backend does the canonical resize — we just
// preview the raw selection so the user knows what they picked.
export default function AvatarUploader({ user, onClose, onUpdated }) {
  const setUser = useAuth((s) => s.setUser)
  const fileInputRef = useRef(null)

  const [picked, setPicked] = useState(null) // { file, url }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Revoke any pending preview URL when the dialog unmounts or picked
  // is reset. The URL is created synchronously inside the picker
  // handler so render doesn't have to coordinate with an effect.
  useEffect(() => {
    const url = picked?.url
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [picked])

  // Esc to close, focus-trap-lite: focus the picker on mount.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const handlePick = (f) => {
    setError(null)
    if (!f) return
    if (!ACCEPTED_TYPES.includes(f.type)) {
      setError('Unsupported format. Use JPEG, PNG, or WebP.')
      return
    }
    if (f.size > MAX_BYTES) {
      setError('Image is over 1 MB. Pick something smaller.')
      return
    }
    setPicked({ file: f, url: URL.createObjectURL(f) })
  }

  const handleUpload = async () => {
    if (!picked?.file) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api.uploadAvatar(picked.file)
      setUser(updated)
      onUpdated?.(updated)
      onClose?.()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e?.message || 'Upload failed')
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async () => {
    setBusy(true)
    setError(null)
    try {
      const updated = await api.deleteAvatar()
      setUser(updated)
      onUpdated?.(updated)
      onClose?.()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e?.message || 'Remove failed')
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  const hasExisting = !!user?.avatar_url
  // Prefer the picked-file preview; otherwise show the existing avatar so
  // the user has a baseline to compare against.
  const previewSrc = picked?.url || user?.avatar_url || null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-ink-950/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="avatar-uploader-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose?.()
      }}
    >
      <div className="w-[420px] max-w-[92vw] rounded-2xl border border-ink-800 bg-ink-900 shadow-2xl shadow-black/50">
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <h2 id="avatar-uploader-title" className="text-base font-semibold text-ink-100">
            Edit avatar
          </h2>
          <button
            type="button"
            onClick={() => !busy && onClose?.()}
            className="rounded-md p-1 text-ink-400 hover:text-ink-100 hover:bg-ink-800/80 disabled:opacity-50"
            disabled={busy}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 pb-5 space-y-4">
          <div className="flex items-center gap-4">
            <div className="grid place-items-center w-20 h-20 rounded-full bg-ink-800 border border-ink-700 overflow-hidden">
              {previewSrc ? (
                <img src={previewSrc} alt="" className="w-20 h-20 object-cover" />
              ) : (
                <span className="text-ink-400 text-sm">none</span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-ink-200 truncate">{user?.name || user?.email || 'Account'}</p>
              <p className="text-xs text-ink-400 mt-0.5">JPEG, PNG, or WebP. Up to 1 MB.</p>
              <p className="text-xs text-ink-400">Resized to 256x256 server-side.</p>
            </div>
          </div>

          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              className="hidden"
              onChange={(e) => handlePick(e.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              className={clsx(
                'w-full flex items-center justify-center gap-2 rounded-lg',
                'border border-dashed border-ink-700 bg-ink-950/40',
                'px-3 py-3 text-sm text-ink-200',
                'hover:border-kerf-300/60 hover:bg-ink-900 hover:text-ink-100',
                'transition-colors disabled:opacity-50',
              )}
            >
              <ImagePlus size={16} className="text-kerf-300" />
              {picked ? `Replace · ${picked.file.name}` : 'Choose image'}
            </button>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            <div>
              {hasExisting && (
                <button
                  type="button"
                  onClick={handleRemove}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 text-xs text-ink-400 hover:text-red-300 disabled:opacity-50"
                >
                  <Trash2 size={13} />
                  Remove
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => !busy && onClose?.()}
                disabled={busy}
                className="px-3 h-8 rounded-md text-sm text-ink-300 hover:bg-ink-800/80 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUpload}
                disabled={busy || !picked}
                className={clsx(
                  'inline-flex items-center gap-1.5 px-3 h-8 rounded-md text-sm font-medium',
                  'bg-kerf-300 text-ink-950 hover:bg-kerf-200',
                  'disabled:bg-ink-700 disabled:text-ink-400 disabled:cursor-not-allowed',
                )}
              >
                {busy && <Loader2 size={13} className="animate-spin" />}
                Upload
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
