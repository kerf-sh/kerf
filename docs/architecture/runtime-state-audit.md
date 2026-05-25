# Runtime State Audit

_Anchored at commit `ccb91c8` — 2026-05-19_

---

## Executive Summary

- **Multi-instance safety: YES (today).** All persistent state lives in Postgres
  (asyncpg pool) and Tigris S3; auth is stateless JWT. The one fire-and-forget
  `asyncio.create_task` (`_auto_title_thread`) writes to Postgres, so it is safe.
  No `lru_cache`, no module-level mutable dicts used as caches, no persistent
  WebSocket or SSE fan-out. **However**, the in-process `PresenceChannel` class in
  `kerf_cloud/collab/presence.py` is a single-machine pub/sub stub — it is not
  wired to any HTTP endpoint yet, but it **will break** the moment a second instance
  is added or presence is exposed.

  > This audit was written against the Koyeb deployment (`koyeb.yaml`).
  > The multi-instance safety analysis below applies to any horizontally-scaled
  > container deployment.

- **IndexedDB save status: IMPLEMENTED but not wired to editors.** `localStash`,
  `autosaveScheduler`, and `dirtyStore` are fully coded and tested. `reconcile()` is
  called at app load (`main.jsx`) and `beforeunload` is guarded. But no editor
  component imports `markDirty` from `autosaveScheduler` — the scheduler is an
  island. Additionally, `autosaveScheduler.flush()` calls
  `stash(workspaceId, filePath)` (2-arg form) expecting bytes back, but
  `localStash.stash()` is a write-only function that returns `undefined`.

- **Every project is a git repo: NO — only after explicit init.** `POST /projects`
  (`create_project`) creates a workspace + starter file only; it does not call
  `POST /projects/{pid}/git/init` and does not insert a `cloud_git_repos` row. Git
  is an opt-in feature; `cloud_git_repos` has a nullable FK to `projects` (not a
  required 1:1). The Git LFS substrate ("Phase 2: every project a real hosted
  repo") described in project memory is not yet implemented.

- **Tests:** `localStash.test.js` and `dirtyStore.test.js` are comprehensive and
  pass cleanly. The autosave-scheduler stash-call bug is latent only — the
  scheduler is never imported by real code paths today.

- **No immediate production incidents** from the above — but three follow-up items
  are listed at the bottom.

---

## 1 — Multi-instance Safety

### Koyeb service config (current hosted tier)

Kerf runs on Koyeb with a single `web` service instance by default.
Koyeb scales horizontally by adding replicas; the same multi-instance
safety properties described below apply regardless of the number of
replicas.

Key Koyeb knobs to review when scaling:
- **Replicas**: set via the Koyeb dashboard or `koyeb service update --replicas N`.
- **Health check path**: `/healthz` — Koyeb routes traffic only to healthy instances.
- **No sticky-session config by default**: requests are round-robined across
  replicas. Do not rely on in-process state surviving across requests.

### koyeb.yaml audit

```yaml
# koyeb.yaml (relevant scaling fields)
# replicas: 1          # single replica by default
# min_scale: 1
# max_scale: 3         # autoscale up to 3 on concurrency
```

- `min_scale: 1` → one replica kept running at all times; Koyeb autoscales
  up under concurrency pressure up to `max_scale`.
- **No sticky-session config by default**: Koyeb round-robins requests across
  replicas. Do not rely on in-process state surviving across requests.
- **Health check**: `/healthz` — Koyeb routes traffic only to healthy replicas.

**Today** only one replica is realistic for the current traffic level, but
Koyeb _can_ add a replica on concurrency spikes and the config does not prevent it.

### In-memory state audit

#### kerf-api (`packages/kerf-api/src/kerf_api/`)

| Location | What | Multi-machine safe? |
|---|---|---|
| `routes.py:968` `STARTER_SEEDS` | Immutable dict constant | ✅ read-only |
| `routes.py:1947` `DERIVED_KIND_ALLOWED` | Immutable frozenset constant | ✅ read-only |
| `routes.py:2514` `_auto_title_thread` + `asyncio.create_task` (line 2846) | Fire-and-forget; writes `chat_threads.title` via asyncpg pool acquired from the request-scoped pool reference | ✅ state in Postgres |
| All `StreamingResponse` usages (lines 3938, 4079, 4119, 4162, 4232) | File/image download streams | ✅ stateless byte streams |

**No `@functools.lru_cache` or `@cache` decorators found anywhere in either package.**

**No module-level mutable dicts/lists/sets used as caches.**

#### kerf-cloud (`packages/kerf-cloud/src/kerf_cloud/`)

| Location | What | Multi-machine safe? |
|---|---|---|
| `collab/presence.py` `PresenceChannel` | In-process pub/sub stub; `_slots` and `_subscribers` are instance dicts | ⚠️ NOT safe across machines — but **not wired to any HTTP endpoint today** |
| `collab/crdt.py` `YMap` / `YArray` | CRDT primitives, instantiated per-request or in tests | ✅ no module-level singleton |
| `scheduler/auto_commit.py` `start_auto_commit_loop` | Background asyncio task; all state via asyncpg pool + S3 storage | ✅ safe (would duplicate work on N machines, not corrupt state) |
| `distributors/sync.py` `_sweep_loop` | Background asyncio task; reads/writes distributor cache via DB | ✅ safe (idempotent polling) |
| `email/mailer.py` drain task | Background asyncio drain; writes email send log to DB | ✅ safe |

**Key finding for presence/collab:** `PresenceChannel` is defined in
`kerf_cloud/collab/presence.py` and exported from `kerf_cloud/collab/__init__.py`,
but grepping all route files shows it is **never instantiated at module level** —
it exists only in tests and the collab package itself. It is explicitly documented
as a stub: _"In production it would be backed by Redis pub/sub or a WebSocket fan-out layer."_

### Conclusion

**Today: multi-instance safe.** All persistent state is in Postgres + Tigris S3.
JWT tokens are stateless. There are no in-memory caches that differ between
instances, no WebSocket fan-out, no SSE persistent connections.

**Risk window:** If the Koyeb autoscaler adds a second replica, requests will be
round-robined without affinity. This is safe for current features, but the
`auto_commit_loop` and `_sweep_loop` tasks will each run on every instance —
wasted work, not corruption, because Postgres constraints make both idempotent.

### What would need to change for presence/cursor-sharing

- `PresenceChannel` must be backed by **Redis pub/sub** (e.g. Upstash Redis, or
  a managed Redis on Koyeb) rather than an in-process dict.
- Presence events must be pushed to clients via a persistent transport. The
  current `StreamingResponse` usages are one-shot downloads, not SSE streams.
  Real-time delivery would require a new SSE or WebSocket endpoint on the server
  plus a frontend EventSource/WebSocket connection.
- Until that transport exists, a second instance means cursor events are silently
  dropped (they'd reach subscribers on the same instance only).
- Sticky sessions (Koyeb session-affinity header) could be a short-term
  workaround if presence is collocated with a long-lived SSE connection per
  user, but that breaks horizontal scale.

---

## 2 — IndexedDB Save Status

### Architecture

```
editor change
    │
    ▼
[workspace store: dirty = true]
    │
    ▼  (currently missing: markDirty call)
[autosaveScheduler._keys Map]  ←── module-level timer state (JS-process only)
    │
    ├── idle debounce (2 s)
    └── hard cap (30 s)
         │
         ▼
    localStash.stash(wsId, path, bytes)  → IndexedDB  flushedToL2=false
         │
         ▼
    POST /workspaces/{id}/files/{path}/revisions
         │
    2xx → localStash.markFlushed(wsId, path)  → IDB flushedToL2=true
    err → keep dirty, exponential backoff (2→4→8→…→30 s)
```

### What is done

| Component | Status |
|---|---|
| `src/lib/localStash.js` | Complete. `stash`, `markFlushed`, `listDirty`, `reconcile` all implemented and tested. |
| `src/lib/localStash.test.js` | 7 test cases covering round-trip, overwrite, multi-file, partial flush, cross-workspace isolation, idempotency. All pass. |
| `src/stores/dirtyStore.js` | Complete. Zustand store that listens on `_addListener` hook from localStash. `useDirtyL1Count()` updates reactively. |
| `src/stores/dirtyStore.test.js` | 5 test cases covering reactive count updates. All pass. |
| `src/lib/autosaveScheduler.js` | Complete. Debounce + hard-cap timers, in-flight guard, exponential backoff. `markDirty(wsId, path)` is the API. |
| `src/main.jsx` | Load-time `reconcile()` call — flushes dirty IDB entries on app boot if auth already resolved, and on login event. `beforeunload` guard fires native browser prompt when IDB has dirty entries. |

### Gaps found

- **gap: `autosaveScheduler` is never called from any editor.** No component
  or store file imports `markDirty` from `autosaveScheduler`. The scheduler is
  fully coded but is an unconnected island. Editors call
  `workspace.saveFile()` → `api.updateFile()` directly, bypassing the IDB
  L1 layer entirely. **Offline edits are NOT persisted to IDB.**

- **gap: `autosaveScheduler.flush()` line 90 — wrong stash call signature.**
  ```js
  // autosaveScheduler.js:90
  bytes = await stash(workspaceId, filePath)   // ← 2-arg call, returns undefined
  ```
  `localStash.stash(workspaceId, filePath, bytes)` is a write function; it
  takes `bytes` as the third argument and returns `undefined`. There is no
  corresponding read/get function exported from `localStash`. The scheduler
  needs a `getBytes(workspaceId, filePath)` (or `readEntry`) exported from
  `localStash`, and the flush path must call that to retrieve the bytes before
  POSTing. This bug is latent — it won't fire until `markDirty` is wired.

- **gap: `reconcile` in `main.jsx` POSTs to a workspace-files endpoint
  (`/api/workspaces/${workspaceId}/files/…`) but `autosaveScheduler.flush()`
  POSTs to `/workspaces/${workspaceId}/files/${filePath}/revisions`.** These are
  different URL shapes; the reconcile path may not exist in the current API
  surface. Needs a consistency check when wiring.

- **gap: Cmd+Z restores from `file_revisions` (server-side), not from IDB.**
  `workspace.js:2650` loads `listRevisions` → restores the second-newest server
  revision. There is no IDB-restore path for undo. This is correct design
  (server is L2 source of truth), but it means undo only works when the file has
  been flushed to the server at least once. An edit typed but not yet autosaved
  would be lost on Cmd+Z if the user edits then immediately undoes before the
  2-second debounce fires.

- **gap: no autosaveScheduler tests for the multi-file-path case.** The
  `autosaveScheduler.test.js` exists (referenced in comments) but was not
  verified to cover the case where `stash` returns bytes.

### Current behaviour summary

Edits in the editor today go directly to the server via `api.updateFile()` (PATCH)
with no IDB intermediate step. The L1 IDB stash infrastructure is built and
tested in isolation but is not connected to any editor. The `beforeunload` guard
will never fire in practice (IDB is never written by editor code), and the
load-time `reconcile` is a no-op.

---

## 3 — Every Project is a Git Repo

### What the intent is

From project memory (`git_lfs_substrate.md`), Phase 2 of the roadmap is:
> _"every cloud project = a hosted git repo … `git clone` + `git lfs pull` works → no Kerf client/lock-in."_

The design calls for Git LFS (`*.step`, `*.stl`, `*.glb`, etc.) routed to bunny.net,
with a Batch API for presigned URLs and an `lfs_objects` ref-count table.

### Current schema

`0012_cloud_git.sql` — clean baseline DDL:

- `cloud_git_repos` — PK `project_id uuid REFERENCES projects(id)` — one row per
  project **when git is enabled**. Notably the FK is `PRIMARY KEY`, so there can
  be at most one git repo per project, but the row is **not created automatically**.
- `cloud_git_branches` — per-project branch heads.
- `cloud_git_commits` — append-only deliberate/autosave commit log.

### Code paths

**`POST /projects` (`kerf_api/routes.py:978`)** — `create_project`:

```python
async with conn.transaction():
    project = await projects_queries.create_project(...)
    if starter_name and starter_content:
        await files_queries.create_file(...)
# ← no cloud_git_repos insert; no call to git_init
return {...project, "my_role": role}
```

No git repo is initialised on project create.

**`POST /projects/{pid}/git/init` (`kerf_cloud/routes.py:172`)** — explicit opt-in:

```python
existing = await conn.fetchrow(
    "SELECT * FROM cloud_git_repos WHERE project_id = $1", pid)
if existing:
    return {...}   # idempotent
await conn.execute(
    "INSERT INTO cloud_git_repos (project_id, default_branch, head_sha) VALUES ($1, 'main', '')", pid)
```

This endpoint is idempotent and safe, but it must be called explicitly by the
user (via the git panel) or by a migration/backfill script.

### Conclusion

**Every project is NOT a git repo today.** Git is an opt-in feature:

1. User creates a project → no `cloud_git_repos` row.
2. User opens the git panel and clicks "Enable git" → `POST /projects/{pid}/git/init`
   → row created, `head_sha = ''`.
3. User makes a deliberate commit → commit stored in `cloud_git_commits` + bare
   repo blob in storage.

**Phase 2 (auto-init + LFS Batch API) is not started.** The `cloud_git_repos`
schema is ready (correct FK, nullable GitHub/GitLab columns), but the auto-init
hook and the LFS Batch API (`lfs_objects` table, presigned-URL handler) are
absent.

---

## Followups (prioritised code work)

1. **Wire `markDirty` into editors** — import `markDirty` from
   `autosaveScheduler` in `workspace.js` (or the relevant editor component) and
   call it on every content change (currently the `dirty: true` zustand state is
   set but the scheduler is never notified). This is the load-bearing step to
   make L1 IDB actually work.

2. **Add `getBytes(workspaceId, filePath)` to `localStash.js`** — export a read
   function that the `autosaveScheduler.flush()` path can call instead of the
   2-arg `stash()` misuse. Fix line 90 of `autosaveScheduler.js` to call
   `getBytes` not `stash`.

3. **Reconcile the flush URL** — `autosaveScheduler` posts to
   `/workspaces/{id}/files/{path}/revisions`; `main.jsx` reconcile posts to
   `/api/workspaces/{id}/files/{path}`. Confirm both exist in the API router (or
   unify to one path) before wiring editors.

4. **Auto-init cloud git on project create** — add an `INSERT INTO cloud_git_repos`
   (or a call to the `git_init` helper) inside the `create_project` transaction
   in `routes.py`. This is a one-liner; the endpoint is already idempotent.

5. **Redis-back `PresenceChannel` before enabling presence** — when cursor-sharing
   is added, replace the in-process `_slots`/`_subscribers` dicts with a Redis
   pub/sub channel keyed by `project_id`. Do this before enabling auto-scale
   beyond 1 replica on Koyeb.

6. **Duplicate auto_commit/sweep_loop work on multi-instance** — if/when replica
   count is raised above 1 on Koyeb, consider a Postgres advisory lock to avoid N
   instances each polling all workspaces every 60 s. Not a correctness issue
   today, but will become noisy at scale.
