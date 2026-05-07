// Lightweight bootstrap config hook. Hits /api/config exactly once per page
// load and caches the result in a tiny zustand store. Safe to call from
// either the OSS frontend (will just see cloudEnabled=false defaults) or
// the cloud bundle.
//
// Shape returned by /api/config (per CONTRACT.md):
//   {
//     cloud_enabled: bool,
//     google_client_id?: string,
//     paystack_public_key?: string,
//   }

import { useEffect } from 'react'
import { create } from 'zustand'

const API_URL = import.meta.env.VITE_API_URL || ''

const DEFAULTS = {
  ready: false,
  cloudEnabled: false,
  googleClientId: '',
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
        set({
          ready: true,
          cloudEnabled: !!data.cloud_enabled,
          googleClientId: data.google_client_id || '',
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
    googleClientId: state.googleClientId,
    paystackPublicKey: state.paystackPublicKey,
  }
}

// Imperative accessor for code that can't use hooks (e.g. router loaders).
export function getCloudConfig() {
  return useStore.getState()
}
