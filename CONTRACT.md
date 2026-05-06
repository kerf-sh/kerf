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
- **LLM**: Anthropic Claude (model `claude-opus-4-7`)

## Env loading

- Vite default mode → `.env` (local). `npm run dev:dev` → mode `dev`, also reads `.env.dev`. `npm run build` → mode `main`, reads `.env.main`.
- Backend: `--env=local|dev|main`. `local` loads `.env`. `dev` loads `.env` then overlays `.env.dev`. `main` loads `.env` then overlays `.env.main`. Files live at the **repo root**.

Required env keys: see `.env.example`.

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
      name text, kind text check in ('file','folder','assembly') default 'file',
      content text default '',
      created_at, updated_at)
-- assembly files store JSON describing referenced files + transforms in `content`.

chat_threads(id uuid pk, project_id uuid fk, file_id uuid null fk files,
             title text, is_starred bool default false,
             last_message_at timestamptz null,
             created_at, updated_at)

chat_messages(id uuid pk, thread_id uuid fk, role text check in ('user','assistant','system'),
              content text, part_refs jsonb default '[]',
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

### Chat
- `GET  /api/projects/:pid/threads?file_id=` → `Thread[]`
- `POST /api/projects/:pid/threads` `{title?, file_id?}` → `Thread`
- `PATCH /api/projects/:pid/threads/:tid` `{title?, is_starred?}` → `Thread`
- `DELETE /api/projects/:pid/threads/:tid` → 204
- `GET  /api/projects/:pid/threads/:tid/messages` → `Message[]`
- `POST /api/projects/:pid/threads/:tid/messages` `{content, part_refs?}` → `{user_message, assistant_message}`
  - Server calls Anthropic with: thread history + the JSCAD content of any referenced files + a system prompt explaining JSCAD authoring conventions.
  - Streams optional (v2). v1 returns full assistant message.

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
File    = {id, project_id, parent_id, name, kind, content?, created_at, updated_at}
Thread  = {id, project_id, file_id, title, is_starred, last_message_at, created_at}
Message = {id, thread_id, role, content, part_refs: PartRef[], created_at}
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

## File-ownership map (so agents don't collide)

- **Backend agent** owns: `backend/**`
- **CAD workspace agent** owns: `src/routes/Editor.jsx`, `src/components/{Renderer,CodeEditor,ChatPanel,FileTree,PartChip,ShareModal}.jsx`, `src/lib/{jscadRunner,geom3}.js`, `src/store/workspace.js`
- **Pages agent** owns: `src/routes/{Landing,Login,Signup,Projects}.jsx`, `src/components/{Layout,Header,Button,Input,Card}.jsx`
- **Branding agent** owns: `public/favicon.svg`, `src/components/Logo.jsx`, `src/styles/brand.css`

Shared (do not modify): `src/main.jsx`, `src/App.jsx`, `src/lib/api.js`, `src/store/auth.js`, `src/index.css`, `src/routes/{ProtectedRoute,AuthCallback}.jsx`, `vite.config.js`, `package.json`, `.env*`.
