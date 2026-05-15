// Lightweight bootstrap config hook. Hits /api/config exactly once per page
// load and caches the result in a tiny zustand store. Safe to call from
// either the OSS frontend (will just see cloudEnabled=false defaults) or
// the cloud bundle.
//
// Shape returned by /api/config (per CONTRACT.md):
//   {
//     cloud_enabled: bool,
//     google_client_id?: string,
//     google_enabled?: bool,
//     github_enabled?: bool,
//     github_client_id?: string,
//     paystack_public_key?: string,
//   }
//
// OAuth availability (googleEnabled / githubEnabled) is derived at runtime
// from the server's kerf.toml so the same Docker image works across
// environments without a rebuild. VITE_GOOGLE_CLIENT_ID is kept as a
// build-time fallback for local dev that skips the /api/config fetch.

import { useEffect } from 'react'
import { create } from 'zustand'

const API_URL = import.meta.env.VITE_API_URL || ''

// Build-time fallback: if VITE_GOOGLE_CLIENT_ID was baked in (local dev
// workflow), treat Google as enabled without needing the runtime flag.
const BUILD_GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

const DEFAULTS = {
  ready: false,
  cloudEnabled: false,
  // localMode default is true so an OSS build that fails to fetch
  // /api/config (e.g. CORS misconfigured) still skips /login, matching
  // server-side defaults. The cloud build always overrides via the
  // /api/config response.
  localMode: true,
  googleClientId: BUILD_GOOGLE_CLIENT_ID,
  googleEnabled: !!BUILD_GOOGLE_CLIENT_ID,
  githubEnabled: false,
  githubClientId: '',
  paystackPublicKey: '',
}

const useStore = create((set, get) => ({
  ...DEFAULTS,
  _inflight: null,

  fetch: () => {
    const s = get()
    if (s.ready || s._inflight) return s._inflight
    const p = fetch(`${API_URL}/api/config`, { credentials: 'omit' })
      .then(async (r) => {
        if (!r.ok) throw new Error(`config ${r.status}`)
        return r.json()
      })
      .then((data) => {
        // Runtime client ID takes precedence over build-time env.
        const googleClientId = data.google_client_id || BUILD_GOOGLE_CLIENT_ID
        // google_enabled from server takes precedence; fall back to whether
        // any client ID is present (handles older server binaries).
        const googleEnabled = data.google_enabled != null
          ? !!data.google_enabled
          : !!googleClientId
        const githubEnabled = !!data.github_enabled
        const githubClientId = data.github_client_id || ''
        set({
          ready: true,
          cloudEnabled: !!data.cloud_enabled,
          // local_mode is the single source of truth for "skip the
          // login screen". Fall back to !cloud_enabled when the
          // backend hasn't surfaced the flag yet (older binary).
          localMode: data.local_mode != null ? !!data.local_mode : !data.cloud_enabled,
          googleClientId,
          googleEnabled,
          githubEnabled,
          githubClientId,
          paystackPublicKey: data.paystack_public_key || '',
          _inflight: null,
        })
      })
      .catch((err) => {
        // Treat network/unreachable as "OSS defaults". Surface in console
        // so devs notice misconfigured proxies.
        console.warn('[useCloudConfig] /api/config failed:', err)
        set({ ...DEFAULTS, ready: true, _inflight: null })
      })
    set({ _inflight: p })
    return p
  },
}))

export function useCloudConfig() {
  const state = useStore()
  useEffect(() => {
    if (!state.ready && !state._inflight) state.fetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return {
    ready: state.ready,
    cloudEnabled: state.cloudEnabled,
    localMode: state.localMode,
    googleClientId: state.googleClientId,
    googleEnabled: state.googleEnabled,
    githubEnabled: state.githubEnabled,
    githubClientId: state.githubClientId,
    paystackPublicKey: state.paystackPublicKey,
  }
}

// Imperative accessor for code that can't use hooks (e.g. router loaders).
export function getCloudConfig() {
  return useStore.getState()
}
