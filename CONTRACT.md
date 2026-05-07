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

## Env loading

- Vite default mode → `.env` (local). `npm run dev:dev` → mode `dev`, also reads `.env.dev`. `npm run build` → mode `main`, reads `.env.main`.
- Backend: `--env=local|dev|main`. `local` loads `.env`. `dev` loads `.env` then overlays `.env.dev`. `main` loads `.env` then overlays `.env.main`. Files live at the **repo root**.

Required env keys: see `.env.example`.

LLM-related env keys:
- `ANTHROPIC_API_KEY` — enables the Anthropic provider.
- `OPENAI_API_KEY` — enables the OpenAI provider.
- `MOONSHOT_API_KEY` — enables the Moonshot provider.
- `GEMINI_API_KEY` — enables the Gemini provider.
- `DEFAULT_MODEL` — fallback model ID when neither the request nor the thread specifies one (default `claude-opus-4-7`).
- `ANTHROPIC_MODEL` — **deprecated**. Replaced by per-thread/per-message `model` plus `DEFAULT_MODEL`. Still read for backward compatibility but unused at runtime.

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
         created_at, updated_at)

project_members(project_id uuid fk, user_id uuid fk,
                role text check in ('owner','editor','viewer'),
                created_at, primary key(project_id, user_id))

share_links(id uuid pk, project_id uuid fk, token text unique,
            role text check in ('editor','viewer'),
            expires_at timestamptz null, revoked_at timestamptz null,
            max_uses int null, uses int default 0,
            created_by uuid fk users, created_at)

files(id uuid pk, project_id uuid fk, parent_id uuid null fk files,
      name text, kind text check in ('file','folder','assembly','step') default 'file',
      content text default '',
      storage_key text null,    -- set for blob-backed kinds (currently 'step')
      mime_type text null,
      size bigint null,
      created_at, updated_at)
-- assembly files store JSON describing referenced files + transforms in `content`.
-- step files have an empty content; the binary lives in Storage (see Storage section).

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
- `POST   /api/projects` `{name, description?}` → `Project` (also creates a default `main.jscad` file)
- `GET    /api/projects/:id` → `Project` (includes `my_role`)
- `PATCH  /api/projects/:id` `{name?, description?, visibility?}` → `Project`
- `DELETE /api/projects/:id` → 204 (owner only)

### Files
- `GET    /api/projects/:pid/files` → `File[]` (full tree, no content; content omitted)
- `POST   /api/projects/:pid/files` `{name, kind, parent_id?, content?}` → `File`
- `GET    /api/projects/:pid/files/:fid` → `File` (with content)
- `PATCH  /api/projects/:pid/files/:fid` `{name?, content?, parent_id?}` → `File`
- `DELETE /api/projects/:pid/files/:fid` → 204
- `GET    /api/projects/:pid/files/:fid/download` → 200 streamed binary, or 302 to a presigned URL when storage supports it. Auth required (project membership). Used for kinds with a `storage_key` (e.g. `step`).

### Assets (binary uploads)
- `POST   /api/projects/:pid/assets` (multipart, editor+) → `File`
  - `file` — the binary
  - `kind` — must be `step` in v1
  - `parent_id?` — optional parent folder UUID
  - 413 if larger than 50MB; 400 for any kind other than `step`.

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
Project = {id, owner_id, name, description, visibility, my_role: 'owner'|'editor'|'viewer', created_at, updated_at}
File    = {id, project_id, parent_id, name, kind: 'file'|'folder'|'assembly'|'step',
           content?, storage_key?, mime_type?, size?, download_url?,
           created_at, updated_at}
// storage_key/mime_type/size/download_url are only set for blob-backed kinds (e.g. 'step').
// download_url is the relative path of the auth-protected download route.
Thread  = {id, project_id, file_id, title, is_starred, last_message_at, model: string|null, created_at}
Message = {id, thread_id, role: 'user'|'assistant'|'system'|'tool',
           content, part_refs: PartRef[],
           tool_calls: ToolCall[],     // assistant rows that requested tools
           tool_call_id: string|null,  // set on role='tool' rows
           model: string|null, created_at}
ToolCall = {id, name, arguments: string /* raw JSON */}
// Message.model is populated for assistant messages only (string), null for user/system messages.
ModelInfo = {id, provider: 'anthropic'|'openai'|'moonshot'|'gemini', label, context_window?: number, is_default: boolean}
PartRef = {file_id, part_id, label?}   // part_id is the JSCAD `id` field on a part
Member  = {user_id, project_id, role, user: User, created_at}
ShareLink = {id, project_id, token?, role, expires_at, revoked_at, max_uses, uses, created_at}
```

## JSCAD file convention

Each `.jscad` file's `default export` is a function returning `[{id, geom}]`
where `geom` is a `@jscad/modeling` Geom3. The `id` is what gets clicked /
referenced from chat. Example:

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

Assembly files (`kind='assembly'`): `content` is JSON: `{children:[{file_id, transform:[16-numbers]}]}`.

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
