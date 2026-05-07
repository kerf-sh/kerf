import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const API_URL = import.meta.env.VITE_API_URL || ''

// Single source of truth for tokens + current user. Persisted to localStorage so
// reload survives. Tokens are short-lived; refresh logic lives in lib/api.js.
export const useAuth = create(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      // bootstrapChecked is true once tryBootstrap has run (success OR
      // explicit "no state file"). Routes can wait on it before deciding
      // to redirect an unauthenticated user to /login.
      bootstrapChecked: false,
      bootstrapInflight: null,

      setSession: ({ accessToken, refreshToken, user }) =>
        set({ accessToken, refreshToken, user }),

      setAccessToken: (accessToken) => set({ accessToken }),

      setUser: (user) => set({ user }),

      logout: () => set({ accessToken: null, refreshToken: null, user: null }),

      isAuthed: () => !!get().accessToken,

      // tryBootstrap fetches /api/bootstrap and, if a state file exists on
      // the server (single-machine brew/curl-install path), seeds the
      // refresh token into the store. The first /api/me request after
      // this runs through the standard refresh flow in lib/api.js, which
      // turns the refresh token into a fresh access token + user row.
      //
      // Idempotent: safe to call from multiple places (App.jsx, Login.jsx)
      // — repeat invocations short-circuit on bootstrapChecked.
      tryBootstrap: () => {
        const s = get()
        if (s.bootstrapChecked) return Promise.resolve()
        if (s.bootstrapInflight) return s.bootstrapInflight
        // If the user is already authed (persisted refresh token from a
        // prior session), there's nothing to do.
        if (s.refreshToken) {
          set({ bootstrapChecked: true })
          return Promise.resolve()
        }
        const p = fetch(`${API_URL}/api/bootstrap`, { credentials: 'omit' })
          .then(async (r) => {
            if (!r.ok) throw new Error(`bootstrap ${r.status}`)
            return r.json()
          })
          .then((data) => {
            if (data && data.has_state && data.refresh_token) {
              set({
                refreshToken: data.refresh_token,
                user: data.user || null,
              })
            }
          })
          .catch((err) => {
            // Network errors are non-fatal — just fall through to the
            // normal login screen.
            console.warn('[auth] /api/bootstrap failed:', err)
          })
          .finally(() => {
            set({ bootstrapChecked: true, bootstrapInflight: null })
          })
        set({ bootstrapInflight: p })
        return p
      },
    }),
    {
      name: 'kerf.auth',
      // bootstrapChecked / bootstrapInflight are session-only — they
      // need to be re-derived on each page load.
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        user: s.user,
      }),
    },
  ),
)
