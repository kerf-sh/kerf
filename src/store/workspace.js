// Zustand store for the editor workspace. One instance per browser tab — when
// the user opens a new project we just call loadProject(id) again.
//
// Owns:
//   - project metadata + file tree
//   - currently-open file's content + dirty flag
//   - chat threads + active thread + messages (incl. tool messages)
//   - "picked part" state (renderer click) and pending part_refs queued for the
//     next chat message.
//   - per-file part visibility (hiddenPartIds), session-only.
//   - the live `parts` array for the currently-open file (JSCAD or STEP).
import { create } from 'zustand'
import { api } from '../lib/api.js'
import { runJscad } from '../lib/jscadRunner.js'
import { loadStep } from '../lib/stepLoader.js'

// Tool names whose effects mutate files; sendMessage() refetches the tree
// and the open file's content when one of these shows up in the response.
const FILE_MUTATING_TOOLS = new Set([
  'write_file', 'edit_file', 'create_file', 'delete_file', 'import_step',
])

function fileKindFor(file) {
  // Map a File row → {kind: 'jscad' | 'step' | 'assembly' | 'folder'} for the
  // editor pipeline. We sniff by extension since the DB `kind` is the broader
  // ('file', 'folder', 'assembly') taxonomy.
  if (!file) return 'jscad'
  if (file.kind === 'folder') return 'folder'
  if (file.kind === 'assembly') return 'assembly'
  const name = (file.name || '').toLowerCase()
  if (name.endsWith('.step') || name.endsWith('.stp')) return 'step'
  return 'jscad'
}

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

  // Live parts for the currently-open file, regardless of source.
  parts: [],
  partsError: null,
  loadingParts: false,

  threads: [],
  currentThreadId: null,
  messages: [],
  loadingMessages: false,
  sending: false,

  pickedPart: null,        // {file_id, part_id, label?} — last clicked
  pendingPartRefs: [],     // attached to next message

  // Per-file visibility map: Map<file_id, Set<part_id>>. Session-only.
  hiddenPartIds: new Map(),
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
    await get().loadFileForEditor(fileId)
  },

  // Routes a file load to the JSCAD or STEP pipeline depending on extension.
  // Sets currentFile, currentFileContent, parts, partsError as appropriate.
  loadFileForEditor: async (fileId) => {
    const { projectId } = get()
    if (!projectId || !fileId) return
    set({ loadingParts: true, partsError: null })
    try {
      const file = await api.getFile(projectId, fileId)
      const kind = fileKindFor(file)
      if (kind === 'step') {
        // Binary asset; download via authed fetch + run through occt.
        set({
          currentFile: file,
          currentFileContent: '',
          dirty: false,
          parts: [],
        })
        try {
          const buf = await api.downloadFileURL(projectId, fileId)
          const { parts } = await loadStep(buf)
          // Only commit if this is still the open file.
          if (get().currentFileId === fileId) {
            set({ parts, loadingParts: false, partsError: null })
          }
        } catch (err) {
          if (get().currentFileId === fileId) {
            set({
              loadingParts: false,
              partsError: err?.message || 'Failed to load STEP',
              parts: [],
            })
          }
        }
        return
      }
      // JSCAD / text path.
      set({
        currentFile: file,
        currentFileContent: file.content ?? '',
        dirty: false,
      })
      // Run JSCAD immediately so parts populate even before any keystroke.
      try {
        const res = await runJscad(file.content ?? '')
        if (get().currentFileId === fileId) {
          if (res.error) {
            set({ partsError: res.error, loadingParts: false })
          } else {
            set({ parts: res.parts || [], partsError: null, loadingParts: false })
          }
        }
      } catch (err) {
        if (get().currentFileId === fileId) {
          set({ partsError: err?.message || String(err), loadingParts: false })
        }
      }
    } catch (err) {
      set({ loadingParts: false, loadError: err?.message || String(err) })
    }
  },

  // Setter used by the editor's debounced re-run — keeps parts in sync with
  // the user's typing without re-fetching the file.
  setLiveParts: (parts) => set({ parts: parts || [] }),
  setPartsError: (msg) => set({ partsError: msg }),

  editContent: (text) => {
    set({ currentFileContent: text, dirty: true })
  },

  saveFile: async () => {
    const { projectId, currentFileId, currentFileContent, dirty, currentFile } = get()
    if (!projectId || !currentFileId || !dirty) return
    // Don't try to save STEP files — they're binary.
    if (fileKindFor(currentFile) === 'step') {
      set({ dirty: false })
      return
    }
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

  // Upload a binary asset (currently STEP) to the project, add the resulting
  // File row to the tree, and switch to it.
  uploadAsset: async (browserFile, { kind = 'step', parent_id = null } = {}) => {
    const { projectId } = get()
    if (!projectId || !browserFile) return null
    try {
      const created = await api.uploadAsset(projectId, browserFile, { kind, parent_id })
      set((s) => ({ files: [...s.files, { ...created, content: undefined }] }))
      await get().selectFile(created.id)
      return created
    } catch (err) {
      set({ loadError: err?.message || String(err) })
      return null
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

  // ---- Visibility ----
  togglePartVisibility: (fileId, partId) => {
    if (!fileId || !partId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      const current = new Set(next.get(fileId) || [])
      if (current.has(partId)) current.delete(partId)
      else current.add(partId)
      next.set(fileId, current)
      return { hiddenPartIds: next }
    })
  },

  isolatePart: (fileId, partId) => {
    if (!fileId || !partId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      const all = new Set(s.parts.map((p) => p.id).filter((id) => id !== partId))
      next.set(fileId, all)
      return { hiddenPartIds: next }
    })
  },

  showAllParts: (fileId) => {
    if (!fileId) return
    set((s) => {
      const next = new Map(s.hiddenPartIds)
      next.set(fileId, new Set())
      return { hiddenPartIds: next }
    })
  },

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

  createThread: async ({ title, file_id, model } = {}) => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const t = await api.createThread(projectId, { title, file_id, model })
      set((s) => ({ threads: [t, ...s.threads] }))
      await get().selectThread(t.id)
      return t
    } catch (err) {
      set({ loadError: err?.message || String(err) })
    }
  },

  setThreadModel: async (threadId, model) => {
    const { projectId, threads } = get()
    if (!projectId || !threadId) return
    set({ threads: threads.map((t) => t.id === threadId ? { ...t, model } : t) })
    try {
      await api.updateThread(projectId, threadId, { model })
    } catch {
      // Server is the source of truth on next load; UI keeps optimistic value.
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

  sendMessage: async (content, { model } = {}) => {
    const { projectId, currentThreadId, pendingPartRefs, currentFileId } = get()
    if (!projectId || !content.trim()) return

    let threadId = currentThreadId
    if (!threadId) {
      const title = content.trim().slice(0, 60)
      const t = await get().createThread({ title, file_id: currentFileId, model })
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
        model,
      })
      set((s) => {
        // Replace optimistic with server's user_message + tool_messages + assistant_message.
        const filtered = s.messages.filter((m) => m.id !== optimistic.id)
        const next = [...filtered]
        if (res?.user_message) next.push(res.user_message)
        if (Array.isArray(res?.tool_messages)) {
          for (const m of res.tool_messages) next.push(m)
        }
        if (res?.assistant_message) next.push(res.assistant_message)
        // Bump thread last_message_at locally.
        const threads = s.threads.map((t) => t.id === threadId
          ? { ...t, last_message_at: new Date().toISOString() }
          : t)
        return { messages: next, sending: false, threads }
      })

      // If any tool message used a file-mutating tool, refresh the tree and
      // (if it's the open file) reload its content. Backend denormalizes
      // tool_name onto each tool_messages row so we don't have to cross-walk
      // back to the (unreturned) intermediate assistant messages.
      const toolMsgs = res?.tool_messages || []
      const mutated =
        toolMsgs.some((m) => m?.tool_name && FILE_MUTATING_TOOLS.has(m.tool_name)) ||
        (Array.isArray(res?.assistant_message?.tool_calls)
          && res.assistant_message.tool_calls.some((c) => FILE_MUTATING_TOOLS.has(c.name))) ||
        // Defensive fallback: if the backend forgets tool_name, refresh
        // anytime we got tool messages back. Cheap (file list is small).
        (toolMsgs.length > 0 && toolMsgs.every((m) => !m?.tool_name))

      if (mutated) {
        try {
          const fresh = await api.listFiles(projectId)
          set({ files: fresh })
        } catch { /* tolerate */ }
        const { currentFileId: openId } = get()
        if (openId) {
          await get().loadFileForEditor(openId)
        }
      }
    } catch (err) {
      set((s) => ({
        sending: false,
        messages: s.messages.map((m) => m.id === optimistic.id
          ? { ...m, _error: err?.message || 'Failed to send' }
          : m),
      }))
    }
  },

  reset: () => set({ ...initial, hiddenPartIds: new Map() }),
}))
