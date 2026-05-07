# Kerf — build contract (shared spec for all subagents)

Kerf is a chat-driven CAD tool. JSCAD (`@jscad/modeling`) is the file format.
Users edit code, see a 3D rendering, click parts to reference them, and chat
with an LLM to refine the model. Projects can have multiple files and assemblies.

This file is the source of truth for the API surface and data model so frontend
and backend agents stay in sync. **Do not change without updating both sides.**

---

## Stack

- **Frontend**: Vite 8 + React 19 + React Router 7 + Tailwind CSS v4 + Zustand
- **3D**: Three.js (r160) + `@jscad/modeling` 2.x
- **Editor**: `@monaco-editor/react`
- **Backend**: Go (chi router, pgx, JWT, bcrypt, `golang.org/x/oauth2/google`, `joho/godotenv`)
- **DB**: Postgres (Supabase-compatible)
- **LLM**: Multi-provider — Anthropic, OpenAI, Moonshot, Gemini. Default model is `claude-opus-4-7`. Per-thread/per-message override via `model`.

## Configuration

The backend reads a single TOML file (`kerf.toml`). The frontend continues
to use Vite's `.env` for the small set of build-time vars listed below.

### Backend — `kerf.toml`

See `kerf.example.toml` for the full schema. Search order:

1. `--config <path>` CLI flag
2. `KERF_CONFIG` environment variable
3. `./kerf.toml` (cwd)
4. `${XDG_CONFIG_HOME:-~/.config}/kerf/config.toml`
5. `/etc/kerf/config.toml`

Sections: `[server]`, `[database]`, `[auth]`, `[storage]` (`backend =
"local" | "s3" | "filesystem"`), `[llm.anthropic|openai|moonshot|gemini]`,
`[usage]`, `[limits]`, `[system_user]`, and `[cloud.*]` (only honored
when the binary is built with `-tags=cloud`). `[limits].file_revisions_max`
(default 200) caps per-file revision history.

Auth is always on. To get the brew/curl-install "open browser, you're
already logged in" UX, set `[system_user].email` and `[system_user].password`
— the server (a) ensures the user row exists, (b) mints a long-lived
refresh token, (c) writes it to `~/.config/kerf/state.json`. The
frontend reads `GET /api/bootstrap` on first load and silently signs the
user in. Multi-user deploys leave `[system_user].password` blank.

The legacy `[auth].optional` flag is removed; an old kerf.toml with
`optional = true` triggers a one-line deprecation warning at boot and is
otherwise ignored.

LLM provider activation: a non-empty `api_key` under `[llm.<provider>]`
enables that provider. `[llm].default_model` is the fallback model ID when
neither the request nor the thread specifies one (default `claude-opus-4-7`).

### Frontend — `.env`

Only `VITE_*` keys are needed. The backend serves `/api/config` at runtime
for everything else (Google client ID, cloud-mode flag, etc.).

- `VITE_API_URL` — backend URL the dev proxy targets.
- `VITE_GOOGLE_CLIENT_ID` — must match `auth.google.client_id` in `kerf.toml`.

---

## Data model (Postgres)

```
users(id uuid pk, email citext unique, password_hash text null, google_id text null unique,
      name text, avatar_url text,
      account_role text default 'user' check in ('user','admin','system'),
      is_system boolean default false,
      created_at timestamptz default now())

refresh_tokens(id uuid pk, user_id uuid fk, token_hash text unique,
               expires_at timestamptz, revoked_at timestamptz null,
               created_at timestamptz default now())

projects(id uuid pk, owner_id uuid fk users, name text, description text,
         visibility text check in ('private','unlisted','public') default 'private',
         project_type text check in ('mechanical','electronics','architecture') default 'mechanical',
         created_at, updated_at)
-- project_type gates which renderer loads, which LLM-prompt addendum is
-- emitted, and which file kinds the FileTree's "+ New" dropdown surfaces.
-- See "Project types" below for the per-type table; v1 is permissive on the
-- API surface (any kind may be created in any project — the menu just
-- hides non-default kinds), so cross-domain edge cases (a quick mechanical
-- bracket inside an electronics project) don't 400.

project_members(project_id uuid fk, user_id uuid fk,
                role text check in ('owner','editor','viewer'),
                created_at, primary key(project_id, user_id))

share_links(id uuid pk, project_id uuid fk, token text unique,
            role text check in ('editor','viewer'),
            expires_at timestamptz null, revoked_at timestamptz null,
            max_uses int null, uses int default 0,
            created_by uuid fk users, created_at)

files(id uuid pk, project_id uuid fk, parent_id uuid null fk files,
      name text, kind text check in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit') default 'file',
      content text default '',
      storage_key text null,    -- set for blob-backed kinds (currently 'step')
      mime_type text null,
      size bigint null,
      deleted_at timestamptz null,  -- soft-delete (see Revisions section)
      created_at, updated_at)
-- assembly files store JSON describing referenced files + transforms in `content`.
-- step files have an empty content; the binary lives in Storage (see Storage section).
-- feature files (.feature) store an OCCT B-rep feature-tree JSON; edited only via feature_* tools (READONLY_FEATURE for write/edit/delete_file).
-- circuit files (.circuit.tsx) store tscircuit JSX source; editable via add_component/connect/set_component_prop or directly with write_file/edit_file.
-- part files (.part) store library Part metadata JSON; edited only via part tools (READONLY_PART for write/edit/delete_file). See "Library / Parts" below.
-- DELETE on a file is implemented as a soft-delete: deleted_at is set and the
-- row is excluded from list/get queries. Revisions remain readable so the
-- file can be restored from the History drawer.

file_revisions(id uuid pk, file_id uuid fk files on delete cascade,
               content text not null,
               source text check in ('user','llm','tool','restore'),
               user_id uuid null fk users on delete set null,
               created_at timestamptz default now())
-- Per-file edit history. Every PATCH /files/:fid (with content), every write
-- tool, and every restore appends a row. The application prunes anything
-- beyond `limits.file_revisions_max` (default 200) per file on each write.

chat_threads(id uuid pk, project_id uuid fk, file_id uuid null fk files,
             title text, is_starred bool default false,
             last_message_at timestamptz null,
             model text null,
             created_at, updated_at)

chat_messages(id uuid pk, thread_id uuid fk,
              role text check in ('user','assistant','system','tool'),
              content text, part_refs jsonb default '[]',
              tool_calls jsonb default '[]',  -- assistant rows that requested tools
              tool_call_id text null,         -- set on role='tool' rows linking back to assistant
              model text null,
              created_at)

upload_sessions(id uuid pk, project_id uuid fk projects, user_id uuid fk users,
                filename text, size bigint, mime text, sha256 text,
                storage_key text,            -- temp storage prefix for this upload
                chunk_size int default 5242880, total_chunks int,
                received_chunks int[] default '{}',
                bytes_received bigint default 0,
                complete bool default false,
                created_at, expires_at timestamptz default now() + interval '24 hours')
-- One row per in-flight chunked upload (Phase 2). Wiped by the finalize
-- handler on success, by an explicit DELETE, or by a 30-min janitor when
-- expires_at lapses on an incomplete row.

schema_migrations(version text pk, applied_at timestamptz default now())
```

**Thread eviction:** after each thread insert, if `count(threads where project_id = ? and is_starred = false) > MAX_THREADS_PER_PROJECT` (default 50), delete oldest non-starred threads (cascade to messages).

---

## REST API (all JSON; auth via `Authorization: Bearer <access_token>`)

### Auth (no auth required)
- `POST /auth/register` `{email,password,name}` → `{access_token, refresh_token, user}`
- `POST /auth/login`    `{email,password}`      → same
- `POST /auth/refresh`  `{refresh_token}`        → same (rotates refresh token)
- `POST /auth/logout`   `{refresh_token}`        → 204
- `GET  /auth/google/start?redirect=`            → 302 to Google with state cookie
- `GET  /auth/google/callback?code&state`        → 302 to `${FRONTEND_URL}/auth/callback?access_token=…&refresh_token=…`

### Me
- `GET /api/me` → `User`

### Projects
- `GET    /api/projects` → `Project[]` (anything I own or am a member of)
- `POST   /api/projects` `{name, description?, project_type?}` → `Project`
  - `project_type` defaults to `'mechanical'` if omitted (forward-compat for
    older clients). Validated against the small enum
    (`mechanical`/`electronics`/`architecture`).
  - The starter file is type-aware: `mechanical`/`architecture` →
    seed `main.jscad`; `electronics` → seed `main.circuit.tsx`.
- `GET    /api/projects/:id` → `Project` (includes `my_role`, `project_type`)
- `PATCH  /api/projects/:id` `{name?, description?, visibility?, project_type?}` → `Project`
  - `project_type` is patchable so a misclassified project can be fixed
    after creation (rare; mostly create-time).
- `DELETE /api/projects/:id` → 204 (owner only)

### Files
- `GET    /api/projects/:pid/files` → `File[]` (full tree, no content; content omitted)
- `POST   /api/projects/:pid/files` `{name, kind, parent_id?, content?}` → `File`
- `GET    /api/projects/:pid/files/:fid` → `File` (with content)
- `PATCH  /api/projects/:pid/files/:fid` `{name?, content?, parent_id?}` → `File`
- `DELETE /api/projects/:pid/files/:fid` → 204
- `GET    /api/projects/:pid/files/:fid/download` → 200 streamed binary, or 302 to a presigned URL when storage supports it. Auth required (project membership). Used for kinds with a `storage_key` (e.g. `step`).

### File revisions
- `GET  /api/projects/:pid/files/:fid/revisions?limit=50` → `Revision[]` with `content_preview` (first 200 chars) per row, newest first. Editor+ on the project; readable for soft-deleted files too.
- `GET  /api/projects/:pid/files/:fid/revisions/:rid` → `Revision` with full `content`.
- `POST /api/projects/:pid/files/:fid/restore/:rid` → applies the revision's content to the file (clearing `deleted_at` if set) and inserts a new `source='restore'` revision row so the restore itself is undoable. Returns the updated `File`. Editor+.

```ts
Revision = {
  id, file_id, source: 'user'|'llm'|'tool'|'restore',
  user_id: string|null, user_name?: string,
  created_at,
  content_preview?: string,   // list endpoint only
  content?: string,           // single-revision endpoint only
}
```

### Assets (binary uploads)
- `POST   /api/projects/:pid/assets` (multipart, editor+) → `File`
  - `file` — the binary
  - `kind` — must be `step` in v1
  - `parent_id?` — optional parent folder UUID
  - 413 if larger than 50MB; 400 for any kind other than `step`.
  - This endpoint remains for **small** assets. STEP files of any meaningful
    size should use the chunked upload path below.

### Chunked, resumable uploads (Phase 2)

For large STEP files we upload in 5 MB chunks via a session-scoped protocol.
All four endpoints require editor+ on the project. Max single upload size is
configured via `[limits].step_max_bytes` (default 200 MB).

- `POST   /api/projects/:pid/uploads` `{filename, size, mime, sha256}`
   → `{upload_id, chunk_size, received_chunks: [n], total_chunks, complete}`
  - `sha256` is the lowercase hex SHA-256 of the file the client intends to
    send; the server stores it on the session row and re-verifies on
    finalize.
  - **Idempotency / resume**: if the project already has a session with the
    same SHA-256 that hasn't expired, the server returns its `upload_id`
    along with the `received_chunks` already on disk, so the client only
    PUTs the missing ones. If the prior session is *complete*, `complete:
    true` is returned and the client can call `finalize` directly without
    re-sending bytes.

- `PUT    /api/projects/:pid/uploads/:uid/chunks/:n`
   body: `application/octet-stream`, raw bytes; → 204
  - `n` is 0-indexed. Chunk size must equal the value returned by `init`
    (the last chunk may be smaller).

- `GET    /api/projects/:pid/uploads/:uid`
   → `{upload_id, received_chunks, total_chunks, bytes_received, complete}`

- `POST   /api/projects/:pid/uploads/:uid/finalize` `{kind: 'step', parent_id?}`
   → `File`
  - Concatenates the chunks into permanent storage, streams them through
    SHA-256 and verifies against the claim. Mismatch → `422` with
    `{error, code: 'CHECKSUM_MISMATCH'}` and the upload is wiped.
  - On success the session row + temp chunks are deleted.

- `DELETE /api/projects/:pid/uploads/:uid` → 204
  - Cancels and wipes an in-flight upload.

Incomplete sessions auto-expire after `[limits].upload_session_ttl_hours`
(default 24h); a janitor goroutine sweeps them every 30 minutes.

### Blobs (local storage backend only)
- `GET    /api/blobs/{key}` (auth required) — serves the binary backing a file row.
  Authorization: the caller must be a member of the project that owns the file
  whose `storage_key == {key}`. Used by the local storage backend; S3 backends
  return presigned URLs from `download` instead.

### Chat
- `GET  /api/projects/:pid/threads?file_id=` → `Thread[]`
- `POST /api/projects/:pid/threads` `{title?, file_id?, model?}` → `Thread`
- `PATCH /api/projects/:pid/threads/:tid` `{title?, is_starred?, model?}` → `Thread`
- `DELETE /api/projects/:pid/threads/:tid` → 204
- `GET  /api/projects/:pid/threads/:tid/messages` → `Message[]`
- `POST /api/projects/:pid/threads/:tid/messages` `{content, part_refs?, model?}` → `{user_message, assistant_message, tool_messages: Message[]}`
  - Server calls the resolved provider with: thread history + the JSCAD content of any referenced files + a system prompt explaining JSCAD authoring conventions.
  - Server runs the **agent loop** (see "Agent loop" below) — the model may issue tool calls, the server executes them, and feeds the results back until the model emits a non-tool turn or the iteration cap is hit.
  - `assistant_message` is the **last** assistant turn. `tool_messages` is every `role='tool'` row created during the loop (in order).
  - Model precedence per message: `body.model` → `thread.model` → `DEFAULT_MODEL`.
  - Streams optional (v2). v1 returns full assistant message.

### Models
- `GET /api/models` → `ModelInfo[]` (only models whose provider has an API key configured). Each item: `{id, provider, label, context_window?, is_default}`.

### Sharing
- `POST   /api/projects/:pid/share/links` `{role, expires_at?, max_uses?}` → `ShareLink` (token only returned on create)
- `GET    /api/projects/:pid/share/links` → `ShareLink[]` (token redacted)
- `DELETE /api/projects/:pid/share/links/:lid` → 204
- `GET    /api/share/:token` (no auth required) → `{project, role, requires_login}`
- `POST   /api/share/:token/accept` (auth required) → `{project_id}`

### Members
- `GET    /api/projects/:pid/members` → `Member[]`
- `POST   /api/projects/:pid/members` `{email, role}` → `Member` (404 if user not found)
- `PATCH  /api/projects/:pid/members/:uid` `{role}` → `Member`
- `DELETE /api/projects/:pid/members/:uid` → 204

---

## Object shapes (JSON)

```ts
User    = {id, email, name, avatar_url, account_role, is_system, created_at}
// account_role is the global role on the platform: 'user' | 'admin' | 'system'.
// is_system is true only for the seeded system account.
Project = {id, owner_id, name, description, visibility,
           project_type: 'mechanical'|'electronics'|'architecture',
           my_role: 'owner'|'editor'|'viewer', created_at, updated_at}
File    = {id, project_id, parent_id, name, kind: 'file'|'folder'|'assembly'|'step'|'drawing'|'sketch'|'part'|'feature'|'circuit',
           content?, storage_key?, mime_type?, size?, download_url?,
           created_at, updated_at}
// storage_key/mime_type/size/download_url are only set for blob-backed kinds (e.g. 'step').
// download_url is the relative path of the auth-protected download route.
// 'part' files store JSON metadata for a Library entry — see "Library / Parts" below.
// 'feature' files store an OCCT B-rep feature-tree JSON; managed exclusively via feature_* tools (see ROADMAP.md for the OCCT phase).
// 'circuit' files (.circuit.tsx) store tscircuit JSX source for electronics designs (see ROADMAP.md for the electronics phase).
Thread  = {id, project_id, file_id, title, is_starred, last_message_at, model: string|null, created_at}
Message = {id, thread_id, role: 'user'|'assistant'|'system'|'tool',
           content, part_refs: PartRef[],
           tool_calls: ToolCall[],     // assistant rows that requested tools
           tool_call_id: string|null,  // set on role='tool' rows
           model: string|null, created_at}
ToolCall = {id, name, arguments: string /* raw JSON */}
// Message.model is populated for assistant messages only (string), null for user/system messages.
ModelInfo = {id, provider: 'anthropic'|'openai'|'moonshot'|'gemini', label, context_window?: number, is_default: boolean}
PartRef = {file_id, part_id, label?}   // part_id here is the JSCAD `id` field of an Object — see "JSCAD file convention" below for the Part/Object distinction. The wire field name is unchanged for back-compat.
Member  = {user_id, project_id, role, user: User, created_at}
ShareLink = {id, project_id, token?, role, expires_at, revoked_at, max_uses, uses, created_at}
```

## Project types

A `project_type` enum on the project row is the seam for taking Kerf
beyond mechanical CAD (electronics via tscircuit, architecture).
The chat / files / revisions plumbing stays shared; the type gates
which renderer loads, which LLM-prompt addendum is emitted, and which
file kinds the FileTree's "+ New" menu surfaces.

| Type | Native file kinds (UI menu) | Default starter file | Renderer |
|---|---|---|---|
| **mechanical** *(default)* | `file`, `folder`, `sketch`, `assembly`, `drawing`, `feature`, `part` | `main.jscad` | Three.js 3D + 2D drawing canvas |
| **electronics** | `folder`, `circuit`, `part`, `drawing` | `main.circuit.tsx` | tscircuit schematic + PCB + 3D-board |
| **architecture** *(WIP stub)* | `file`, `folder`, `sketch`, `drawing` | `main.jscad` | Mechanical surface for now |

**Permissive vs strict file-kind enforcement.** v1 ships **permissive**:
the backend's `CreateFile` accepts any kind in any project, and the only
type-aware gate is the FileTree's create-dropdown filter. Rationale:
strict gates would surprise users dropping a quick mechanical bracket
into an electronics project (or vice versa) — the cross-domain case is
rare but real, especially for the upcoming "PCB-as-part in mechanical
assembly" feature. The single source of truth on the backend lives in
`backend/internal/handlers/projecttype.go` (`ProjectTypeKinds` map +
`KindAllowedFor` helper, currently unused by handlers but ready when we
flip strict mode on); on the frontend it lives in
`src/lib/projectTypes.js` (mirrored constant). Adding a fifth type later
is a CHECK-constraint update + map entry on each side — no data
migration.

**LLM addendum.** The agent loop in
`backend/internal/handlers/messages.go` reads the project's
`project_type` once per request and prepends a single line to the system
prompt:

> Project type: `<type>`. Native file kinds: `<comma-list>`. Default starter file: `<name>`.

Tiny on the wire (~30-40 tokens) so we re-emit it on every call rather
than caching at thread level — keeps thread switches and project-type
patches trivially correct.

**Workshop multi-type.** The cloud Workshop carries `project_type`
through on listings and accepts a `?type=` filter (`mechanical`,
`electronics`, `architecture`, or omitted for "all"). Forks
preserve the source project's type. See `### Workshop` below.

## JSCAD file convention

Vocabulary (locked — used everywhere in code, prompts, and UI):

- **Part** — a whole `.jscad` file. Each Part exports a default function that
  returns an array of **Objects**.
- **Object** — one entry in a Part's exported array: `{id, geom}` where
  `geom` is a `@jscad/modeling` Geom3 and `id` is what gets clicked /
  referenced from chat. A Part contains one or many Objects.
- **Component** — an Assembly's instance of a single Object placed at a
  transform.

Example Part:

```js
import { primitives, transforms } from '@jscad/modeling'
export default function () {
  const a = primitives.cuboid({ size: [10, 10, 10] })
  const b = transforms.translate([15, 0, 0], primitives.sphere({ radius: 5 }))
  return [
    { id: 'base',   geom: a },
    { id: 'sphere', geom: b },
  ]
}
```

JSCAD files in Kerf are "part studios" (à la OnShape) — a single Part can
expose multiple Objects. Assemblies reference individual Objects via
`(file_id, object_id)`.

Assembly files (`kind='assembly'`): `content` is JSON describing Components
(referenced Objects + transforms):

```ts
type Assembly = {
  components: Array<{
    id: string                  // unique within the assembly, user-editable
    file_id: string             // references another file in the same project (the Part)
    object_id: string           // an Object id from that Part's exported array.
                                // Required. The legacy "*" wildcard is no longer
                                // accepted on writes — to place every Object,
                                // the UI / LLM creates one Component per Object.
                                // Reads still tolerate "*" and the legacy
                                // `part_id` field name; AssemblyEditor expands
                                // wildcards on first display so the next save
                                // migrates the file.
    transform: number[16]       // row-major 4x4 matrix (Three convention)
    params?: Record<string, any>  // optional parameters passed to the JSCAD function
    visible?: boolean           // defaults to true
    color?: [number, number, number]  // optional rgb override (0-1)
  }>
}
```

Default extension is `.assembly` (created via FileTree → "New assembly").
A Component contributes a single transformed Object id'd as `${componentId}`.
Legacy components with `object_id: "*"` are auto-expanded by the renderer
into `${componentId}/${origObjectId}` entries until the next save migrates them.

Insert UX: AssemblyEditor's "Add component" opens a Part picker. If the
picked Part has a single Object, it is added directly. If 2+ Objects, a
modal lists them with checkboxes (all checked by default) and a "Place as
rigid group" toggle (assigns the same starting transform to every checked
Component, so they read as a unit). Confirm creates N Components.

ObjectsPanel UX: each Object row carries Duplicate (Copy icon) and Delete
buttons that mutate the source Part's code via a bracket-matching helper
(see `src/lib/jscadObjectOps.js`). Both go through the standard PATCH
path so a `file_revisions` row is written and Cmd+Z undoes the change.
The matcher bails (toast) when the file isn't a clean
`return [{id, geom}, ...]`.

Drawing files (`kind='drawing'`): `content` is JSON describing one or more
sheets. Each sheet owns its frame, projected views, dimensions, annotations,
centerlines, breaks and engineering symbols.

```ts
type Drawing = {
  // Canonical multi-sheet shape. Old single-sheet drawings (with top-level
  // frame/views/dimensions/annotations and no `sheets` array) load via a
  // back-compat shim that wraps them in `sheets: [legacy]`. The serializer
  // always writes BOTH `sheets[]` AND a top-level mirror of sheets[0].
  sheets: Sheet[]
}

type Sheet = {
  id: string
  frame: {
    size: 'A4'|'A3'|'A2'|'A1'|'A0'|'ANSI_A'|'ANSI_B'|'ANSI_C'|'ANSI_D'
    orientation: 'landscape'|'portrait'
    template?: 'default'|'iso'|'ansi'|'kerf'   // title-block layout
    title?: string, author?: string, date?: string
    scale_label?: string                       // e.g. "1:2"
    sheet_number?: string, notes?: string
    extra?: Record<string, string>             // template-specific fields
  }
  views:       View[]
  dimensions:  Dimension[]
  annotations: Annotation[]
  centerlines: Centerline[]
  breaks:      Break[]
  symbols:     Symbol[]
}

type View = {
  id: string, source_file_id: string, part_id?: string  // '*' = all parts
  projection: 'front'|'top'|'right'|'left'|'back'|'bottom'|'iso'
  scale: number                          // model units per page mm
  position: [number, number]             // page-mm top-left of bbox
  show_hidden?: boolean, show_silhouette?: boolean, label?: string
  is_section?: boolean                   // hatched section view
  hatch_spacing?: number, hatch_angle?: number
}

type Dimension =
  | { id, kind: 'linear'|'aligned',     view_id, a, b, offset, value?: string }
  | { id, kind: 'radius'|'diameter',    view_id, a, b, offset?, value?: string }
  | { id, kind: 'angular',              view_id, vertex, a, b, radius, value?: string }
  | { id, kind: 'baseline'|'chain',     view_id, picks: Pt[], offset, value?: string }
  | { id, kind: 'ordinate',             view_id, picks: Pt[], origin?: Pt, value?: string }

// `value` is an optional manual override; null/missing → auto-measured. The
// UI renders a small "M" flag next to manually-overridden dimensions.

type Annotation =
  | { id, kind: 'text',     view_id?, x, y, text, fontSize?, color? }
  | { id, kind: 'note',     view_id?, x, y, text, fontSize?, color? }    // boxed
  | { id, kind: 'leader',   view_id?, from: Pt, to: Pt, text, side? }
  | { id, kind: 'balloon',  view_id?, cx, cy, number, leader?: Pt }
  | { id, kind: 'polyline', view_id?, points: Pt[], stroke?, dashed?, width? }
  | { id, kind: 'rect',     view_id?, x, y, width, height, stroke?, fill? }
  | { id, kind: 'circle',   view_id?, cx, cy, r, stroke?, fill? }

type Symbol =
  | { id, kind: 'surface_finish', view_id?, position: Pt, params: { ra?: string, machined?: boolean } }
  | { id, kind: 'weld',           view_id?, position: Pt, params: { text?, side?: 'arrow'|'other' } }
  | { id, kind: 'gdt',            view_id?, position: Pt, params: { characteristic, tolerance, datums } }

type Centerline =
  | { id, view_id?, style: 'center_dashed', refs: string[] }
  | { id, view_id?, style: 'center_dashed', custom: { p1: Pt, p2: Pt } }

type Break = { id, view_id?, orientation: 'horizontal'|'vertical', p1: Pt, p2: Pt, style: 'zigzag' }

type Pt = { x: number, y: number }
```

All coordinates are PAGE MILLIMETRES. `view_id` is optional on annotations —
when present the entry logically belongs to that view; when absent it
free-floats on the sheet. Length values multiply by the bound view's `scale`
to display model-mm. Section views render with a 45° SVG `<pattern>` fill
clipped to the projected bbox.

Drawing tools (LLM):

| Tool | Purpose |
|---|---|
| `add_dimension` | One tool, polymorphic by `kind` (linear/aligned/radius/diameter/angular/baseline/chain/ordinate). |
| `add_annotation` | One tool, polymorphic by `kind` (text/note/leader/balloon/polyline/rect/circle/surface_finish/weld/gdt). |
| `add_centerline` | Add a centerline; pass `refs` for auto-detect or `custom: {p1, p2}` for manual. |
| `add_break` | Add a break-line between two points. |
| `add_sheet` | Append a sheet with its own size/template. |
| `set_drawing_scale` | Set sheet's scale label and propagate to view scales. |
| `set_title_field` | Set a title-block field; canonical or template-specific. |
| `add_view_to_drawing`, `add_standard_views`, `drawing_remove_view`, `drawing_remove_dimension`, `remove_annotation` | Existing — unchanged. |

---

## Library / Parts

A **Part** is a `kind='part'` file holding KiCad-style catalog metadata
(manufacturer / MPN / value / datasheet + an array of distributor links) and
optionally a `model_storage_key` pointing at a 3D model blob (STEP or GLB).
A **Library** is just a project (or folder within a project) full of Parts —
there's no extra schema for "library", it's a UX convention.

Assemblies reference Parts the same way they reference any other file: a
`Component` has `file_id` pointing at the Part. The renderer pulls geometry
from the Part's `model_storage_key`; the BOM rollup harvests metadata.

The canonical JSON shape lives in `src/lib/part.js` (frontend) and
`backend/internal/tools/part_tools.go` (backend `partDoc` type). Summary:

```ts
type Part = {
  version: 1
  name: string
  description?: string
  category?: string                // 'resistor' | 'bolt' | 'bearing' | …
  manufacturer?: string
  mpn?: string
  value?: string                   // '10kΩ', 'M3x20', etc.
  datasheet_url?: string
  distributors: Array<{
    name: string                   // 'digikey' | 'mouser' | 'lcsc' | 'mcmaster' | …
    sku?: string
    url: string
    price_usd?: number             // populated by Phase-2 sync; manual in v1
    stock?: number
    fetched_at?: string            // ISO timestamp; Phase 2 only
  }>
  model_storage_key?: string       // points at a blob in Storage (STEP or GLB)
  model_mime_type?: string         // 'model/step' | 'model/gltf-binary'
  symbol_file_id?: string          // electronics — Phase 2 (kind='symbol')
  footprint_file_id?: string       // electronics — Phase 2 (kind='footprint')
  metadata?: Record<string, any>   // free-form per-category extras
}
```

### BOM endpoint

`GET /api/projects/:pid/bom` (member+):

```ts
type BOMResponse = {
  rows: Array<{
    part: Part                       // full Part metadata projection
    file_id: string
    path: string                     // absolute POSIX path
    count: number
    unit_price_usd?: number          // from first distributor with a price_usd
    total_price_usd?: number         // count * unit_price_usd
    primary_distributor?: { name: string, url: string, sku?: string }
  }>
  total_price_usd?: number
  warnings: string[]                 // missing MPNs, MPN collisions, cycles
}
```

Algorithm: walk every `kind='assembly'` file in the project, recurse through
nested assemblies (cycle protection: per-walk visited set, removed on stack
unwind so disjoint branches still aggregate), and aggregate leaf Part
references. Aggregation key is MPN when present, otherwise file id. The BOM
is also exposed to the LLM as the `generate_bom` tool.

### Library tools

| Tool | Args | Returns |
|---|---|---|
| `create_part` * | `{path, metadata}` | `{path, id, name}` — path auto-suffixes `.part`; `metadata.name` required. |
| `set_part_metadata` * | `{path, patch}` | `{path, name}` — partial merge; refuses `version` ≠ 1. Distributors-array patches fully replace; use `add_distributor_link` to append. |
| `add_distributor_link` * | `{path, name, sku?, url}` | `{path, distributor, sku, action: 'added'\|'updated'}` — idempotent on `(name, sku)`. |
| `generate_bom` | `{}` | `{rows, total_price_usd, warnings}` — same shape as the BOM endpoint. Read-only. |

---

## Agent loop

`POST .../messages` is **not** a single LLM call. The server runs an agent loop:

1. Insert the user message, build the LLM history (mapping assistant rows with
   their `tool_calls` and `role='tool'` rows with their `tool_call_id`).
2. Resolve the provider + model.
3. Call the provider with the configured tools (filtered by the caller's role
   — viewers cannot call write tools).
4. Persist the assistant turn (with `tool_calls` populated if any).
5. If `len(tool_calls) == 0` or `stop_reason == "stop"`: break.
6. Otherwise execute every tool call **synchronously inside the request
   handler** and persist a `role='tool'` row per result.
7. Append the assistant + tool-result messages to the request and loop.
8. Cap: **10 iterations** (`MaxAgentIterations`). On exhaustion, append a
   final assistant message: `"(stopped: max tool iterations reached)"`.
9. Update `chat_threads.last_message_at` once at the end of the request.

Response: `{user_message, assistant_message, tool_messages}` where
`assistant_message` is the final assistant turn and `tool_messages` is every
tool result row created during the loop, in order.

---

## Tools

Every tool returns a JSON string. Errors are returned as
`{"error":"...","code":"NOT_FOUND|AMBIGUOUS|FORBIDDEN|...}` — the handler
never 500s on a tool-level failure.

Roles: **read** tools (no `*` below) require viewer+; **write** tools (marked
`*`) require editor+ — viewers receive `FORBIDDEN`.

| Tool | Args | Returns |
|---|---|---|
| `list_files` | `{}` | `{files:[{path, kind, size?}, …]}` |
| `read_file` | `{path}` | `{path, content}` (errors on binary kinds like `step`) |
| `write_file` * | `{path, content}` | `{path, bytes}` (auto-creates intermediate folders) |
| `edit_file` * | `{path, old_string, new_string}` | `{path, replaced:1}` (error if old_string is missing or matches >1 time) |
| `create_file` * | `{path, content?, kind?}` (`kind` ∈ file/folder/assembly) | `{path, id}` |
| `delete_file` * | `{path}` | `{path}` |
| `search_code` | `{query, max?}` | `{matches:[{path, line, preview}, …]}` |
| `import_step` * | `{name, url, parent_path?}` | `{path, id, size}` (HTTPS only; 30s timeout; 50MB cap) |
| `validate_jscad` | `{path}` | `{path, ok:true, checked:false, note:"client-side validation"}` |
| `assembly_add` * | `{assembly_path, component_id, source_path, object_id, position?, rotation?, scale?}` | `{path, component_id}` (rotation in degrees XYZ; default identity; `object_id` is required and references a single Object — `"*"` is rejected) |
| `assembly_set_transform` * | `{assembly_path, component_id, position?, rotation?, scale?}` | `{path, component_id}` (each axis optional; omitted axes preserve previous decomposed value) |
| `assembly_set_object` * | `{assembly_path, component_id, object_id}` | `{path, component_id, object_id}` (change which Object of the source Part the Component references; `"*"` is rejected) |
| `duplicate_object` * | `{path, object_id, new_id?}` | `{path, object_id}` (clones the matching Object entry in a Part; bracket-match-based; bails with `PARSE_FAILED` on non-conventional layouts) |
| `delete_object` * | `{path, object_id}` | `{path, object_id}` (removes the matching Object entry in a Part; same matcher / failure mode as `duplicate_object`) |
| `add_annotation` * | `{drawing_path, kind, view_id?, ...kind-specific args}` | `{path, id, annotations}` — kind ∈ text/leader/polyline/rect/circle; coordinates in PAGE MILLIMETRES |
| `remove_annotation` * | `{drawing_path, annotation_id}` | `{path, removed: 0\|1}` |
| `list_revisions` | `{file_path, limit?}` | `{revisions:[{id, source, user_id, user_name?, created_at, content_preview}, …]}` — newest first; resolves soft-deleted files by name as a fallback |
| `restore_revision` * | `{file_path, revision_id}` | `{path, restored_revision_id, new_revision_id}` — also clears `deleted_at` if the file was soft-deleted, so this is the LLM-side "undelete" path |

Path conventions: POSIX-like, leading `/`, no trailing `/`. Root is `/`.

---

## Storage

Binary assets (currently STEP files) live behind a Storage abstraction with
two backends:

- **local** — writes to `LOCAL_STORAGE_PATH` (default `./.kerf-storage`).
  `download` streams from disk; the auth-protected `/api/blobs/{key}` route
  serves objects when a frontend needs a stable URL.
- **s3** — uses AWS SDK v2 against S3 or an S3-compatible endpoint.
  `download` returns a 302 to a presigned URL when the file is large.

Selection rule: `STORAGE_BACKEND=s3` (or unset + `S3_BUCKET` populated) → S3.
Otherwise → local.

Env keys:

```
STORAGE_BACKEND       # "" | "local" | "s3" (auto-detect when blank)
LOCAL_STORAGE_PATH    # default ./.kerf-storage
S3_BUCKET
S3_REGION
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_ENDPOINT           # for S3-compatible providers (R2, MinIO, etc.)
S3_PUBLIC_URL_BASE    # e.g. https://cdn.kerf.app
```

Object keys are namespaced: `projects/<project_id>/assets/<uuid>-<filename>`.

---

## File-ownership map (so agents don't collide)

- **Backend agent** owns: `backend/**`
- **CAD workspace agent** owns: `src/routes/Editor.jsx`, `src/components/{Renderer,CodeEditor,ChatPanel,FileTree,PartChip,ShareModal}.jsx`, `src/lib/{jscadRunner,geom3}.js`, `src/store/workspace.js`
- **Pages agent** owns: `src/routes/{Landing,Login,Signup,Projects}.jsx`, `src/components/{Layout,Header,Button,Input,Card}.jsx`
- **Branding agent** owns: `public/favicon.svg`, `src/components/Logo.jsx`, `src/styles/brand.css`

Shared (do not modify): `src/main.jsx`, `src/App.jsx`, `src/lib/api.js`, `src/store/auth.js`, `src/index.css`, `src/routes/{ProtectedRoute,AuthCallback}.jsx`, `vite.config.js`, `package.json`, `.env*`.
