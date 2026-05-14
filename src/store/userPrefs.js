// Per-user UI preferences. Lives in a tiny zustand store backed by a
// JSONB column on `users` (server side). The frontend persists a copy in
// localStorage too so the next page load can apply prefs (compact mode,
// reduce-motion, default model) BEFORE the round-trip to /api/me/preferences
// completes — otherwise we'd flash a non-compact / motion-on render on
// every nav.
//
// Shape contract (mirrors backend/routes/api.py allowed_pref_keys):
//   default_model: string  (e.g. "claude-opus-4-7")
//   units:         "mm" | "cm" | "inches"
//   autosave_delay_ms: 250..2000
//   eval_debounce_ms:  100..1000
//   theme:         "system" | "dark"     ("system" is a placeholder/WIP)
//   reduce_motion: boolean
//   compact_mode:  boolean

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '../lib/api.js'

// Defaults consumed by the rest of the app when a key is not set. The
// backend never auto-fills these; the consumer falls back to DEFAULTS so a
// fresh user (and unauthenticated dev preview) sees sensible values.
export const PREF_DEFAULTS = Object.freeze({
  default_model: 'claude-opus-4-7',
  units: 'mm',
  autosave_delay_ms: 500,
  eval_debounce_ms: 250,
  theme: 'dark',
  reduce_motion: false,
  compact_mode: false,
})

export const useUserPrefs = create(
  persist(
    (set, get) => ({
      prefs: {},          // server-truth keys + values
      loaded: false,      // true after first successful loadPrefs()
      loading: false,
      saving: false,
      error: null,

      // get(key) returns the user-set value or PREF_DEFAULTS[key].
      get: (key) => {
        const v = get().prefs?.[key]
        if (v === undefined || v === null) return PREF_DEFAULTS[key]
        return v
      },

      // loadPrefs hydrates from the server. Idempotent.
      loadPrefs: async () => {
        if (get().loading) return
        set({ loading: true, error: null })
        try {
          const data = await api.getPreferences()
          set({ prefs: data || {}, loaded: true, loading: false })
          applyPrefsToDOM(data || {})
        } catch (err) {
          set({ loading: false, error: err?.message || 'failed to load preferences' })
        }
      },

      // setPref mutates a single key locally — the consumer must call save()
      // (or use the `setAndSave` convenience below) to persist. We also push
      // the change to the DOM immediately so toggles feel responsive.
      setPref: (key, value) => {
        const prev = get().prefs || {}
        const next = { ...prev }
        if (value === undefined || value === null) {
          delete next[key]
        } else {
          next[key] = value
        }
        set({ prefs: next })
        applyPrefsToDOM(next)
      },

      // save replaces the server-side object with the current local copy.
      save: async () => {
        if (get().saving) return
        set({ saving: true, error: null })
        try {
          const stored = await api.updatePreferences(get().prefs || {})
          set({ prefs: stored || {}, saving: false })
          applyPrefsToDOM(stored || {})
        } catch (err) {
          set({ saving: false, error: err?.message || 'failed to save preferences' })
          throw err
        }
      },

      // setAndSave is the most common path — used by toggles where the
      // intent is "store + persist immediately". It does NOT debounce; if
      // we ever add a slider that fires per-pixel we should add one.
      setAndSave: async (key, value) => {
        get().setPref(key, value)
        await get().save()
      },

      reset: () => set({ prefs: {}, loaded: false, error: null }),
    }),
    {
      name: 'kerf.userPrefs',
      // We persist `prefs` only — `loaded`/`loading`/`saving` should be
      // re-derived on each load. Persisting the cached prefs lets us
      // apply compact mode / reduced motion before the network round-trip.
      partialize: (s) => ({ prefs: s.prefs }),
    },
  ),
)

// Side-effect: paint compact-mode + reduce-motion onto the document so the
// rest of the app can react via plain CSS (or `matchMedia('(prefers-reduced-motion)')`-shaped checks).
//
// We attach kerf-compact / kerf-reduce-motion to <body> so any component
// can opt in with descendant selectors. Theme handling is a no-op today —
// the app is dark-only.
function applyPrefsToDOM(prefs) {
  if (typeof document === 'undefined') return
  const body = document.body
  if (!body) return
  const compact = !!prefs.compact_mode
  body.classList.toggle('kerf-compact', compact)
  const reduceMotion = !!prefs.reduce_motion
  body.classList.toggle('kerf-reduce-motion', reduceMotion)
}

// Apply on store-restore (persist middleware fires onRehydrateStorage but
// we hit the global state directly to keep the wiring trivial).
if (typeof window !== 'undefined') {
  // Defer one tick so document.body is reachable.
  queueMicrotask(() => {
    try {
      applyPrefsToDOM(useUserPrefs.getState().prefs || {})
    } catch { /* swallow */ }
  })
}
