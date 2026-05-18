import { create } from 'zustand'
import { api } from '../lib/api.js'

const CURRENT_KEY = 'kerf:currentWorkspaceSlug'

function loadStoredSlug() {
  try { return localStorage.getItem(CURRENT_KEY) || null } catch { return null }
}
function persistSlug(slug) {
  try {
    if (slug) localStorage.setItem(CURRENT_KEY, slug)
    else localStorage.removeItem(CURRENT_KEY)
  } catch {}
}

export const useWorkspaces = create((set, get) => ({
  workspaces: [],
  currentSlug: loadStoredSlug(),
  loading: false,
  loaded: false,
  error: null,

  loadAll: async () => {
    if (get().loading) return get().workspaces
    set({ loading: true, error: null })
    // The first workspace fetch happens right after the OAuth redirect,
    // where it can transiently fail: the autoscaled machine may be
    // cold-starting, or the access token isn't attached to the very
    // first request yet. Retry with backoff and ONLY mark `loaded` once
    // we actually have data — never latch `loaded:true` on a bare
    // failure (that previously stranded the session with no workspace,
    // surfacing as "workspace_id or workspace_slug required").
    const backoffMs = [400, 1000, 2500, 5000]
    let lastErr = null
    for (let attempt = 0; attempt <= backoffMs.length; attempt++) {
      try {
        const list = await api.listWorkspaces()
        const arr = Array.isArray(list) ? list : (list?.workspaces || [])
        set({ workspaces: arr, loading: false, loaded: true, error: null })
        const cur = get().currentSlug
        if (arr.length > 0 && (!cur || !arr.some((w) => w.slug === cur))) {
          get().setCurrent(arr[0].slug)
        }
        return arr
      } catch (err) {
        lastErr = err
        if (attempt < backoffMs.length) {
          await new Promise((r) => setTimeout(r, backoffMs[attempt]))
        }
      }
    }
    // Exhausted retries: surface the error but keep `loaded:false` so a
    // later trigger (route change / opening the New Project dialog) can
    // retry. The server also resolves the default workspace on create,
    // so the user is never hard-blocked even while this is failing.
    set({ loading: false, loaded: false, error: lastErr?.message || String(lastErr) })
    return []
  },

  setCurrent: (slug) => {
    persistSlug(slug)
    set({ currentSlug: slug })
  },

  create: async ({ name, slug }) => {
    const created = await api.createWorkspace({ name, slug })
    set((s) => ({ workspaces: [created, ...s.workspaces] }))
    get().setCurrent(created.slug)
    return created
  },
}))

export function currentWorkspace() {
  const { workspaces, currentSlug } = useWorkspaces.getState()
  return workspaces.find((w) => w.slug === currentSlug) || null
}
