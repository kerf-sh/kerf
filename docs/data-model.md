# Data model

Kerf's Postgres schema is built by applying the SQL migrations in
`packages/kerf-core/src/kerf_core/db/migrations/` in order (`001_init.sql`
through `058_kind_quadmesh.sql` and counting). Each migration is purely
additive — no destructive drops or renames after the initial cut-over.

## Relationship overview

```
users
  └─► workspaces          (created_by)
        └─► workspace_members  (user_id, workspace_id, role)
        └─► workspace_invites
        └─► projects
              └─► files
                    └─► file_revisions
                    └─► chat_threads
                          └─► chat_messages
              └─► share_links
              └─► step_tessellation_jobs
              └─► fem_jobs
              └─► cam_jobs
              └─► upload_sessions
              └─► derived_artifacts

users ─► refresh_tokens
users ─► api_tokens        (workspace-scoped)
users ─► cloud_github_tokens
```

---

## Core tables

### `users`

Every person or service account. Created on first login (password, Google
OAuth, GitHub OAuth) or via `POST /api/auth/register`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | `gen_random_uuid()` |
| `email` | citext UNIQUE | Case-insensitive match |
| `password_hash` | text | bcrypt+pepper; NULL for OAuth-only accounts |
| `google_id` | text UNIQUE | Google OAuth subject |
| `name` | text | Display name |
| `avatar_url` | text | Legacy direct URL field |
| `account_role` | text | `user` / `admin` / `system` |
| `is_system` | boolean | Reserved for service accounts |
| `created_at` | timestamptz | |

Migration `016_user_avatar_storage.sql` adds `avatar_storage_key` so avatars
live in the same storage backend as blobs, not as bare URLs.

---

### `workspaces`

The org/team container. Every user gets a personal workspace on first login.
Slugs are lowercase alphanumeric with hyphens (`^[a-z0-9]([a-z0-9-]{1,30}[a-z0-9])?$`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `slug` | text UNIQUE | URL-safe identifier |
| `name` | text | Display name |
| `avatar_storage_key` | text | Optional; served via `/api/workspaces/avatar/{id}` |
| `created_by` | uuid → users | |
| `created_at` / `updated_at` | timestamptz | |

### `workspace_members`

Many-to-many join with role. Composite PK `(workspace_id, user_id)`.

`role`: `owner` | `admin` | `member`. The last owner of a workspace cannot be
demoted or removed.

### `workspace_invites`

Pending email invites. Consumed on `/api/workspaces/accept`.

---

### `projects`

A project is a named container of files inside a workspace.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `workspace_id` | uuid → workspaces | |
| `name` | text | |
| `description` | text | |
| `visibility` | text | `private` / `unlisted` / `public` |
| `tags` | text[] | Free-form; filterable via `@>` |
| `thumbnail_storage_key` | text | Optional; served via `/api/projects/{pid}/thumbnail` |
| `created_at` / `updated_at` | timestamptz | |

---

### `files`

The leaf nodes of the project tree. A file can be:

- A **text file** — content stored in the `content` column (JSON, JSCAD script, etc.)
- A **binary file** — content stored in the storage backend under `storage_key`
- A **folder** — `kind='folder'`, no content, children reference it via `parent_id`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `project_id` | uuid → projects | |
| `parent_id` | uuid → files | Self-referencing; NULL = root |
| `name` | text | Filename including extension |
| `kind` | text | See table below |
| `extension` | text | Override for binary files |
| `content` | text | Inline content for text files |
| `storage_key` | text | Storage backend key for binary files |
| `mime_type` | text | |
| `size` | bigint | |
| `mesh_storage_key` | text | glTF mesh from tessellation job |
| `deleted_at` | timestamptz | Soft delete — null = live |
| `created_at` / `updated_at` | timestamptz | |

**File kinds** (all values registered across migrations):

```
file  folder  assembly  step  step-ref  drawing  sketch  part  feature
circuit  equations  script  fem  cam  simulation  material  tolerance
graph  subd  mesh  draft  render  rf-study  topo  canvas  bim  family
schedule  view  sheet  assembly_lock  configurations  section  tool
plc_st  quadmesh  cam_layered  …
```

See [architecture.md § File kinds](./architecture.md) for which plugin owns
each kind.

---

### `file_revisions`

Append-only revision log. Every write (user edit, LLM tool call, restore) adds
a row. Revisions are the undo mechanism: `POST …/restore` appends a new
`source='restore'` row, making the restore itself undoable.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `file_id` | uuid → files | |
| `content` | text | Full content (legacy path, `codec='plain'`) |
| `content_gz` | bytea | Compressed content (`codec='gzip'`) |
| `content_sha256` | text | SHA-256 for dedup; indexed |
| `content_codec` | text | `plain` \| `gzip` |
| `content_preview` | text | 200-char preview for the History drawer |
| `kind` | text | `base` \| `diff` \| `ref` |
| `parent_revision_id` | uuid → file_revisions | Delta chain or cross-file dedup pointer |
| `delta_text` | text | Unified-diff string when `kind='diff'` |
| `source` | text | `user` \| `llm` \| `tool` \| `restore` |
| `user_id` | uuid → users | NULL for `llm` / `tool` sources |
| `created_at` | timestamptz | |

`[limits].file_revisions_max` (default 200) triggers a prune pass after each
write that trims the oldest non-base rows that are not anyone's
`parent_revision_id`.

**Revision evolution** (migrations 013 → 049):

- 013: adds `delta_kind`, `delta_text`, `parent_revision_id` — real-diff storage
- 018: adds `content_sha256` — SHA-dedup
- 048: adds `content_codec` (`gzip`) — compressed storage
- 049: adds `ref` as a valid `kind` — cross-file hash dedup pointer

---

### `chat_threads`

A conversation context associated with a project (and optionally a specific
file).

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `project_id` | uuid → projects | |
| `file_id` | uuid → files | Optional — pins the thread to a file |
| `title` | text | Auto-generated from first message |
| `is_starred` | boolean | |
| `last_message_at` | timestamptz | |
| `model` | text | Default model for this thread |
| `created_at` / `updated_at` | timestamptz | |

### `chat_messages`

Individual turns in a thread.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `thread_id` | uuid → chat_threads | |
| `role` | text | `user` \| `assistant` \| `system` \| `tool` |
| `content` | text | |
| `part_refs` | jsonb | File IDs the user explicitly attached |
| `tool_calls` | jsonb | Tool call list (assistant turns) |
| `tool_call_id` | text | Correlated tool result (tool turns) |
| `model` | text | Model used for assistant turn |
| `created_at` | timestamptz | |

---

### `api_tokens`

Long-lived workspace-scoped tokens for SDK / scripting use.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `workspace_id` | uuid → workspaces | |
| `user_id` | uuid → users | |
| `token_hash` | text UNIQUE | SHA-256 of the raw token |
| `name` | text | Human label |
| `scopes` | jsonb | Default `["workspace:member-role"]` |
| `last_used_at` | timestamptz | |
| `revoked_at` | timestamptz | |
| `created_at` | timestamptz | |

---

### `cloud_github_tokens`

One row per user who has connected their GitHub account (cloud only).

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | uuid PK → users | |
| `access_token_encrypted` | bytea | AES-GCM encrypted OAuth access token |
| `scope` | text | GitHub OAuth scopes granted |
| `github_user_id` | bigint | |
| `github_login` | text | GitHub username |
| `updated_at` | timestamptz | |

Used by `kerf-cloud` for cloud git operations. See
[cloud.md](./cloud.md) for the motivation.

---

## Other notable tables

| Table | Migration | Purpose |
|-------|-----------|---------|
| `share_links` | 001 | Project share tokens with optional expiry and max-use caps |
| `refresh_tokens` | 001 | HTTP-only refresh cookie storage |
| `step_tessellation_jobs` | 022 | STEP → glTF async job queue |
| `fem_jobs` | 027 | FEA job queue |
| `cam_jobs` | 030 | CAM job queue |
| `upload_sessions` | 008 | Chunked binary upload sessions |
| `derived_artifacts` | 024 | Cached computed outputs (thumbnails, exported files) |
| `usage_events` | 007 | Per-request usage tracking (LLM token counts, storage) |
| `library_parts` | 009 | Community parts catalog |
| `workshop_likes` | 032 | Likes for Workshop projects |
| `model_prices` | 050 | Per-model token pricing for billing |
| `billing_buckets` | 051 | `kerf_free` / `kerf_paid` / `byo` per-user billing classification |

---

## Storage backend relationship

`files.storage_key` (and `files.mesh_storage_key`,
`workspaces.avatar_storage_key`, etc.) are opaque keys into the configured
storage backend (`local`, `s3`, `git`, or `filesystem`). The key format is
backend-specific; the rest of the codebase only calls `storage.put(key, …)` /
`storage.get(key)`. Binary bytes never touch the database.

---

See also: [api-reference.md](./api-reference.md) · [architecture.md](./architecture.md)
