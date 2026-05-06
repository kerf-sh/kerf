import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// Single source of truth for tokens + current user. Persisted to localStorage so
// reload survives. Tokens are short-lived; refresh logic lives in lib/api.js.
export const useAuth = create(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setSession: ({ accessToken, refreshToken, user }) =>
        set({ accessToken, refreshToken, user }),

      setAccessToken: (accessToken) => set({ accessToken }),

      setUser: (user) => set({ user }),

      logout: () => set({ accessToken: null, refreshToken: null, user: null }),

      isAuthed: () => !!get().accessToken,
    }),
    { name: 'kerf.auth' },
  ),
)
