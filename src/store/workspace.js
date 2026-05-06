// Zustand store for the editor workspace. One instance per browser tab — when
// the user opens a new project we just call loadProject(id) again.
//
// Owns:
//   - project metadata + file tree
//   - currently-open file's content + dirty flag
//   - chat threads + active thread + messages
//   - "picked part" state (renderer click) and pending part_refs queued for the
//     next chat message.
import { create } from 'zustand'
import { api } from '../lib/api.js'

const initial = {
  projectId: null,
  project: null,
  files: [],
  currentFileId: null,
  currentFile: null,
  currentFileContent: '',
  dirty: false,
  saving: false,
  loadingProject: false,
  loadError: null,

  threads: [],
  currentThreadId: null,
  messages: [],
  loadingMessages: false,
  sending: false,

  pickedPart: null,        // {file_id, part_id, label?} — last clicked
  pendingPartRefs: [],     // attached to next message
}

export const useWorkspace = create((set, get) => ({
  ...initial,

  // ---- Project + files ----
  loadProject: async (id) => {
    set({ projectId: id, loadingProject: true, loadError: null })
    try {
      const [project, files, threads] = await Promise.all([
        api.getProject(id),
        api.listFiles(id),
        api.listThreads(id).catch(() => []),
      ])

      // Pick a default file: first non-folder, prefer name === 'main.jscad'.
      const editable = files.filter((f) => f.kind !== 'folder')
      const main = editable.find((f) => f.name === 'main.jscad') || editable[0] || null

      set({
        project, files, threads,
        loadingProject: false,
        currentThreadId: threads[0]?.id ?? null,
      })

      if (main) await get().selectFile(main.id)
      if (threads[0]) await get().selectThread(threads[0].id)
    } catch (err) {
      set({ loadingProject: false, loadError: err?.message || String(err) })
    }
  },

  selectFile: async (fileId) => {
    if (!fileId) return
    set({ currentFileId: fileId, dirty: false })
    try {
      const file = await api.getFile(get().projectId, fileId)
      set({
        currentFile: file,
        currentFileContent: file.content ?? '',
        dirty: false,
      })
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  editContent: (text) => {
    set({ currentFileContent: text, dirty: true })
  },

  saveFile: async () => {
    const { projectId, currentFileId, currentFileContent, dirty } = get()
    if (!projectId || !currentFileId || !dirty) return
    set({ saving: true })
    try {
      const updated = await api.updateFile(projectId, currentFileId, { content: currentFileContent })
      set((s) => ({
        saving: false,
        dirty: false,
        currentFile: updated,
        files: s.files.map((f) => f.id === updated.id ? { ...f, ...updated, content: undefined } : f),
      }))
    } catch (err) {
      set({ saving: false, loadError: err?.message || String(err) })
    }
  },

  createFile: async (parentId, kind) => {
    const { projectId } = get()
    if (!projectId) return
    const defaults = {
      file: 'untitled.jscad',
      folder: 'New folder',
      assembly: 'assembly.json',
    }
    const seedContent = kind === 'assembly' ? '{"children":[]}' : ''
    try {
      const created = await api.createFile(projectId, {
        name: defaults[kind] || 'untitled',
        kind,
        parent_id: parentId,
        content: seedContent,
      })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      if (kind !== 'folder') await get().selectFile(created.id)
      return created
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  renameFile: async (id, name) => {
    const { projectId } = get()
    try {
      const updated = await api.updateFile(projectId, id, { name })
      set((s) => ({
        files: s.files.map((f) => f.id === id ? { ...f, name: updated.name } : f),
        currentFile: s.currentFile?.id === id ? { ...s.currentFile, name: updated.name } : s.currentFile,
      }))
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  deleteFile: async (id) => {
    const { projectId, currentFileId } = get()
    try {
      await api.deleteFile(projectId, id)
      set((s) => {
        const files = s.files.filter((f) => f.id !== id && f.parent_id !== id)
        const next = currentFileId === id
          ? (files.find((f) => f.kind !== 'folder') || null)
          : s.currentFile
        return {
          files,
          currentFileId: currentFileId === id ? (next?.id ?? null) : currentFileId,
          currentFile: currentFileId === id ? null : s.currentFile,
          currentFileContent: currentFileId === id ? '' : s.currentFileContent,
        }
      })
      if (currentFileId === id) {
        const f = get().files.find((f) => f.kind !== 'folder')
        if (f) await get().selectFile(f.id)
      }
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  updateProjectName: async (name) => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const updated = await api.updateProject(projectId, { name })
      set({ project: updated })
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  // ---- Picking ----
  pickPart: (partId) => {
    const { currentFileId, currentFile } = get()
    if (!partId) {
      set({ pickedPart: null })
      return
    }
    set({
      pickedPart: {
        part_id: partId,
        file_id: currentFileId,
        label: currentFile?.name,
      },
    })
  },

  attachPickedToChat: () => {
    const { pickedPart, pendingPartRefs } = get()
    if (!pickedPart) return
    // Avoid duplicates.
    const exists = pendingPartRefs.some((r) =>
      r.part_id === pickedPart.part_id && r.file_id === pickedPart.file_id,
    )
    if (exists) return
    set({ pendingPartRefs: [...pendingPartRefs, pickedPart] })
  },

  removePartRef: (idx) => {
    set((s) => ({ pendingPartRefs: s.pendingPartRefs.filter((_, i) => i !== idx) }))
  },

  clearPendingPartRefs: () => set({ pendingPartRefs: [] }),

  // ---- Threads + messages ----
  selectThread: async (threadId) => {
    const { projectId } = get()
    if (!threadId || !projectId) {
      set({ currentThreadId: null, messages: [] })
      return
    }
    set({ currentThreadId: threadId, loadingMessages: true, messages: [] })
    try {
      const messages = await api.listMessages(projectId, threadId)
      set({ messages: messages || [], loadingMessages: false })
    } catch (err) {
      set({ loadingMessages: false, loadError: err?.message || String(err) })
    }
  },

  createThread: async ({ title, file_id } = {}) => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const t = await api.createThread(projectId, { title, file_id })
      set((s) => ({ threads: [t, ...s.threads] }))
      await get().selectThread(t.id)
      return t
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  toggleStar: async (threadId) => {
    const { projectId, threads } = get()
    const t = threads.find((x) => x.id === threadId)
    if (!t) return
    const next = !t.is_starred
    // Optimistic.
    set({ threads: threads.map((x) => x.id === threadId ? { ...x, is_starred: next } : x) })
    try {
      await api.updateThread(projectId, threadId, { is_starred: next })
    } catch {
      set({ threads: get().threads.map((x) => x.id === threadId ? { ...x, is_starred: !next } : x) })
    }
  },

  deleteThread: async (threadId) => {
    const { projectId, currentThreadId, threads } = get()
    try {
      await api.deleteThread(projectId, threadId)
      const remaining = threads.filter((t) => t.id !== threadId)
      set({ threads: remaining })
      if (currentThreadId === threadId) {
        await get().selectThread(remaining[0]?.id ?? null)
      }
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  sendMessage: async (content) => {
    const { projectId, currentThreadId, pendingPartRefs, currentFileId } = get()
    if (!projectId || !content.trim()) return

    let threadId = currentThreadId
    if (!threadId) {
      const t = await get().createThread({ file_id: currentFileId })
      threadId = t?.id
      if (!threadId) return
    }

    // Optimistic user message.
    const optimistic = {
      id: `local-${Date.now()}`,
      thread_id: threadId,
      role: 'user',
      content,
      part_refs: pendingPartRefs,
      created_at: new Date().toISOString(),
      _pending: true,
    }
    set((s) => ({
      messages: [...s.messages, optimistic],
      sending: true,
      pendingPartRefs: [],
    }))
    try {
      const res = await api.sendMessage(projectId, threadId, {
        content,
        part_refs: optimistic.part_refs,
      })
      set((s) => {
        // Replace optimistic with server's user_message + assistant_message.
        const filtered = s.messages.filter((m) => m.id !== optimistic.id)
        const next = [...filtered]
        if (res?.user_message) next.push(res.user_message)
        if (res?.assistant_message) next.push(res.assistant_message)
        // Bump thread last_message_at locally.
        const threads = s.threads.map((t) => t.id === threadId
          ? { ...t, last_message_at: new Date().toISOString() }
          : t)
        return { messages: next, sending: false, threads }
      })
    } catch (err) {
      set((s) => ({
        sending: false,
        messages: s.messages.map((m) => m.id === optimistic.id
          ? { ...m, _error: err?.message || 'Failed to send' }
          : m),
      }))
    }
  },

  reset: () => set({ ...initial }),
}))
