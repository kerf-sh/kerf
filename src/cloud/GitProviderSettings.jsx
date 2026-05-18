// GitProviderSettings — inline Git Settings panel rendered inside GitPanel.
//
// Surface: list the external mirror providers that the backend reports as
// configured (GET /git/providers), connect or disconnect the project's
// optional external mirror (POST/DELETE /projects/:pid/git/provider/...),
// and display sync status.
//
// The central framing — Kerf's hosted git is always the source of truth;
// the external mirror is *optional* and additive — is surfaced prominently
// from the API `note` field on every response.
//
// Empty/none-configured state (providers list is empty) is handled
// gracefully: a short explanation is shown and no connect UI is rendered.
//
// This component is intentionally self-contained so it can be slotted
// inside GitPanel without touching Editor.jsx or any Settings route.

import { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle, Check, ChevronDown, ExternalLink, GitBranch,
  Globe, Loader2, PlugZap, Settings, Unplug, X,
} from 'lucide-react'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'
import Button from '../components/Button.jsx'

// ---------------------------------------------------------------------------
// Pure helpers (tested in gitProviderSettings.test.js)
// ---------------------------------------------------------------------------

/** Returns the icon character / emoji for a known provider id. */
export function providerIcon(providerId) {
  if (!providerId) return null
  const id = String(providerId).toLowerCase()
  if (id === 'github') return 'gh'
  if (id === 'gitlab') return 'gl'
  return id.slice(0, 2).toUpperCase()
}

/** Given a raw remote URL, strips the scheme+host to show just the path. */
export function shortRemoteUrl(url) {
  if (!url) return ''
  try {
    const u = new URL(url)
    return (u.hostname + u.pathname).replace(/\.git$/, '')
  } catch {
    return url.replace(/\.git$/, '')
  }
}

/** Derive the human-readable sync state label from a status response. */
export function syncStateLabel(status) {
  if (!status) return 'Unknown'
  if (!status.connected) return 'Not connected'
  if (status.last_sync_at) {
    return `Synced`
  }
  return 'Connected'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProviderBadge({ provider }) {
  const abbr = providerIcon(provider.id)
  return (
    <span className="inline-flex items-center gap-1.5 h-6 px-2 rounded bg-ink-800 border border-ink-700 text-ink-200 text-[11px] font-mono">
      {abbr}
    </span>
  )
}

function ConnectForm({ providers, projectId, onConnected, onCancel }) {
  const [selectedProvider, setSelectedProvider] = useState(providers[0]?.id || '')
  const [remoteUrl, setRemoteUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const selectedProviderObj = providers.find((p) => p.id === selectedProvider)

  const handleConnect = useCallback(async () => {
    if (!selectedProvider || !remoteUrl.trim()) {
      setError('Choose a provider and enter the remote URL.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await git.providerConnect(projectId, selectedProvider, remoteUrl.trim())
      onConnected(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connection failed.')
    } finally {
      setBusy(false)
    }
  }, [projectId, selectedProvider, remoteUrl, onConnected])

  return (
    <div className="space-y-2.5 pt-1">
      {/* Provider selector */}
      {providers.length > 1 && (
        <div className="relative">
          <button
            type="button"
            onClick={() => setDropdownOpen((v) => !v)}
            className="w-full flex items-center justify-between h-7 px-2 rounded-md bg-ink-800 border border-ink-700 hover:border-ink-600 text-xs text-ink-100"
          >
            <span className="flex items-center gap-1.5">
              {selectedProviderObj && <ProviderBadge provider={selectedProviderObj} />}
              <span>{selectedProviderObj?.label || selectedProviderObj?.name || selectedProvider}</span>
            </span>
            <ChevronDown size={11} className="text-ink-400 shrink-0" />
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-8 z-30 w-full rounded-md bg-ink-900 border border-ink-700 shadow-xl py-1">
              {providers.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { setSelectedProvider(p.id); setDropdownOpen(false) }}
                  className="w-full flex items-center gap-2 px-3 h-7 text-left text-xs text-ink-100 hover:bg-ink-800"
                >
                  <Check size={11} className={p.id === selectedProvider ? 'text-kerf-300' : 'text-transparent'} />
                  <ProviderBadge provider={p} />
                  <span>{p.label || p.name || p.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Remote URL input */}
      <div className="flex flex-col gap-1">
        <label className="text-[10px] text-ink-400 uppercase tracking-wider">
          Remote URL
        </label>
        <input
          type="url"
          value={remoteUrl}
          onChange={(e) => setRemoteUrl(e.target.value)}
          placeholder={
            selectedProvider === 'github'
              ? 'https://github.com/owner/repo.git'
              : selectedProvider === 'gitlab'
              ? 'https://gitlab.com/group/repo.git'
              : 'https://…'
          }
          className="h-7 w-full rounded-md bg-ink-800 border border-ink-700 px-2 text-xs text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-400"
        />
      </div>

      {error && (
        <div className="flex items-start gap-1.5 text-[11px] text-red-300">
          <AlertCircle size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center gap-2 pt-0.5">
        <Button size="sm" variant="primary" onClick={handleConnect} disabled={busy} className="flex-1">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <PlugZap size={12} />}
          {busy ? 'Connecting…' : 'Connect mirror'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main exported component
// ---------------------------------------------------------------------------

export function GitProviderSettings({ projectId, onClose }) {
  const [providers, setProviders] = useState(null)    // null = loading
  const [status, setStatus] = useState(null)          // null = loading
  const [loadError, setLoadError] = useState(null)
  const [showConnectForm, setShowConnectForm] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Load providers list + current status in parallel.
  useEffect(() => {
    let cancelled = false
    setProviders(null)
    setStatus(null)
    setLoadError(null)

    Promise.all([
      git.listProviders().catch((e) => ({ _error: e })),
      git.providerStatus(projectId).catch((e) => ({ _error: e })),
    ]).then(([provRes, statusRes]) => {
      if (cancelled) return
      if (provRes._error) {
        setLoadError(
          provRes._error instanceof ApiError
            ? provRes._error.message
            : 'Could not load providers.',
        )
        setProviders([])
      } else {
        setProviders(Array.isArray(provRes?.providers) ? provRes.providers : [])
      }
      if (statusRes && !statusRes._error) {
        setStatus(statusRes)
      } else {
        setStatus({ connected: false })
      }
    })

    return () => { cancelled = true }
  }, [projectId])

  const handleConnected = useCallback((res) => {
    setStatus(res)
    setShowConnectForm(false)
  }, [])

  const handleDisconnect = useCallback(async () => {
    if (!window.confirm('Remove the external mirror link? Kerf\'s hosted git is unaffected.')) return
    setDisconnecting(true)
    setActionError(null)
    try {
      const res = await git.providerDisconnect(projectId)
      setStatus(res)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Disconnect failed.')
    } finally {
      setDisconnecting(false)
    }
  }, [projectId])

  const loading = providers === null || status === null
  const noProviders = !loading && providers.length === 0
  const isConnected = status?.connected === true
  // The API `note` from the most recent response — always surface this.
  const note = status?.note || null

  return (
    <div className="flex flex-col h-full bg-ink-900">
      {/* Header */}
      <div className="flex items-center justify-between h-10 px-3 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-ink-200 uppercase tracking-wider">
          <Settings size={12} className="text-kerf-300" />
          Git Settings
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
          title="Back to Git panel"
        >
          <X size={14} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-4">

        {/* Kerf git retention framing — always rendered once we have any data. */}
        {!loading && (
          <div className="rounded-md border border-kerf-400/25 bg-kerf-300/5 px-3 py-2.5 text-[11px] text-kerf-200/90 leading-relaxed">
            <div className="flex items-start gap-2">
              <GitBranch size={12} className="mt-0.5 shrink-0 text-kerf-300" />
              <span>
                {note ||
                  "Kerf's hosted git is always retained as your source of truth. " +
                  'External mirrors (GitHub, GitLab, …) are optional — adding one ' +
                  "lets you push to a second remote, but it doesn't replace " +
                  "Kerf's own copy."}
              </span>
            </div>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-ink-400 py-2">
            <Loader2 size={13} className="animate-spin" />
            Loading…
          </div>
        )}

        {/* Error state */}
        {loadError && (
          <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-2 text-[11px] text-red-200">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span>{loadError}</span>
          </div>
        )}

        {/* No configured providers */}
        {noProviders && !loadError && (
          <div className="rounded-md border border-ink-800 bg-ink-850/40 px-3 py-3 text-[11px] text-ink-400 leading-relaxed space-y-1">
            <div className="flex items-center gap-1.5 text-ink-300">
              <Globe size={12} className="shrink-0" />
              <span className="font-medium">No external providers configured</span>
            </div>
            <p>
              The server has no Git mirror providers set up. Ask your Kerf
              administrator to configure a GitHub or GitLab integration in the
              server environment.
            </p>
          </div>
        )}

        {/* Provider list + connect/disconnect */}
        {!loading && providers.length > 0 && (
          <div className="space-y-3">
            <div>
              <h4 className="text-[10px] uppercase tracking-wider text-ink-400 mb-1.5">
                Available Mirrors
              </h4>
              <ul className="space-y-1.5">
                {providers.map((p) => {
                  const isActive = isConnected && status.provider_id === p.id
                  return (
                    <li
                      key={p.id}
                      className={
                        'flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs ' +
                        (isActive
                          ? 'border-kerf-400/40 bg-kerf-300/5'
                          : 'border-ink-800 bg-ink-850/30')
                      }
                    >
                      <ProviderBadge provider={p} />
                      <span className={isActive ? 'text-ink-100 font-medium' : 'text-ink-300'}>
                        {p.label || p.name || p.id}
                      </span>
                      {isActive && (
                        <span className="ml-auto flex items-center gap-1 text-[10px] text-emerald-300">
                          <Check size={10} /> Connected
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>

            {/* Current connection status */}
            {isConnected && (
              <div className="rounded-md border border-ink-800 bg-ink-850/40 px-3 py-2.5 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-400">
                  <PlugZap size={11} />
                  External Mirror
                </div>
                {status.remote_url && (
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-100 font-mono break-all">
                    <ExternalLink size={10} className="shrink-0 text-ink-400" />
                    {shortRemoteUrl(status.remote_url)}
                  </div>
                )}
                <div className="text-[10px] text-ink-400">
                  {syncStateLabel(status)}
                  {status.last_sync_at && (
                    <span className="ml-1 text-ink-500">
                      · {new Date(status.last_sync_at).toLocaleString()}
                    </span>
                  )}
                </div>

                {actionError && (
                  <div className="flex items-start gap-1.5 text-[11px] text-red-300 pt-1">
                    <AlertCircle size={11} className="mt-0.5 shrink-0" />
                    <span>{actionError}</span>
                  </div>
                )}

                <div className="pt-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleDisconnect}
                    disabled={disconnecting}
                    className="text-red-300 hover:bg-red-500/10"
                  >
                    {disconnecting
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Unplug size={12} />}
                    Remove mirror
                  </Button>
                </div>
              </div>
            )}

            {/* Connect form or trigger */}
            {!isConnected && !showConnectForm && (
              <div>
                {actionError && (
                  <div className="flex items-start gap-1.5 text-[11px] text-red-300 mb-2">
                    <AlertCircle size={11} className="mt-0.5 shrink-0" />
                    <span>{actionError}</span>
                  </div>
                )}
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => { setShowConnectForm(true); setActionError(null) }}
                  className="w-full"
                >
                  <PlugZap size={12} />
                  Add external mirror…
                </Button>
              </div>
            )}

            {!isConnected && showConnectForm && (
              <ConnectForm
                providers={providers}
                projectId={projectId}
                onConnected={handleConnected}
                onCancel={() => setShowConnectForm(false)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default GitProviderSettings
