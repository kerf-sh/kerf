# API reference

All routes are mounted under `/api` by `kerf-core`. The router is defined in
`packages/kerf-api/src/kerf_api/routes.py`; auth routes live in
`packages/kerf-auth/src/kerf_auth/routes.py`.

## Authentication

Kerf uses two token types carried in standard HTTP cookies:

| Cookie | Type | TTL |
|--------|------|-----|
| `access_token` | HS256 JWT (`sub` = user UUID) | `jwt_access_ttl_minutes` (default 15 min) |
| `refresh_token` | opaque `secrets.token_urlsafe(64)` | `jwt_refresh_ttl_days` (default 30 days) |

For SDK / headless access, long-lived opaque **API tokens** are issued per
workspace and carried in the `Authorization: Bearer <token>` header.

Every endpoint that requires auth is guarded by `require_auth` from
`kerf_core.dependencies`. Endpoints that accept anonymous access for public
projects use `optional_auth`. Role enforcement (`owner` / `admin` / `member` /
`viewer`) happens inside each handler via `get_user_workspace_role`.

---

## Auth endpoints (`/api/auth/…`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | none | Email+password signup. Returns `access_token` + `refresh_token` cookies and the created user + workspace. |
| POST | `/api/auth/login` | none | Email+password login. Same cookie response. |
| POST | `/api/auth/refresh` | refresh cookie | Issue new access token from a valid refresh token. |
| POST | `/api/auth/logout` | any | Revoke the current refresh token. |
| GET | `/api/auth/github/login/start` | none | Begin GitHub OAuth. Redirects to GitHub. |
| GET | `/api/auth/github/login/callback` | none | Handle GitHub OAuth callback. Sets cookies, redirects to app. |
| GET | `/api/auth/google/start` | none | Begin Google OAuth. Redirects to Google. |
| GET | `/api/auth/google/callback` | none | Handle Google OAuth callback. |
| POST | `/api/auth/bootstrap-local` | none | Local-mode auto-login (only when `local_mode=true`). |

---

## Bootstrap / config

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/config` | none | Public feature flags: `cloud_enabled`, `local_mode`, OAuth availability. No secrets returned. |
| GET | `/api/bootstrap` | none | Local-mode only. Returns persisted `refresh_token` from `~/.config/kerf/state.json`. |
| GET | `/api/models` | none | Available LLM models (`claude-sonnet-4`, `claude-opus-4`, …). |

---

## Current user

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/me` | required | Authenticated user profile + default workspace. |
| PATCH | `/api/me` | required | Update `name`. |
| POST | `/api/me/avatar` | required | Upload avatar image. |
| DELETE | `/api/me/avatar` | required | Remove avatar. |

**GET /api/me response**

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "Jane Smith",
  "avatar_url": "",
  "account_role": "user",
  "is_system": false,
  "created_at": "2025-01-01T00:00:00Z",
  "default_workspace": { "id": "uuid", "slug": "my-ws", "name": "My Workspace" }
}
```

---

## Workspaces

Workspaces are the multi-member containers that own projects. Every user gets
a personal workspace on first login.

Roles: `owner` > `admin` > `member`.

| Method | Path | Auth | Min role |
|--------|------|------|----------|
| GET | `/api/workspaces` | required | self |
| POST | `/api/workspaces` | required | — (creates) |
| GET | `/api/workspaces/{slug}` | required | member |
| PATCH | `/api/workspaces/{slug}` | required | admin |
| DELETE | `/api/workspaces/{slug}` | required | owner |
| POST | `/api/workspaces/accept` | required | — (invite token) |
| GET | `/api/workspaces/avatar/{id}` | none | — |
| POST | `/api/workspaces/{slug}/avatar` | required | admin |
| DELETE | `/api/workspaces/{slug}/avatar` | required | admin |
| POST | `/api/workspaces/{slug}/members` | required | admin |
| PATCH | `/api/workspaces/{slug}/members/{member_id}` | required | admin |
| DELETE | `/api/workspaces/{slug}/members/{member_id}` | required | admin |

**Workspace object**

```json
{
  "id": "uuid",
  "slug": "my-org",
  "name": "My Org",
  "avatar_url": "/api/workspaces/avatar/uuid",
  "my_role": "owner",
  "member_count": 3,
  "project_count": 12,
  "created_at": "…"
}
```

---

## Projects

Projects belong to a workspace. Visibility: `private` | `unlisted` | `public`.

| Method | Path | Auth | Min role |
|--------|------|------|----------|
| GET | `/api/projects` | required | member |
| POST | `/api/projects` | required | member |
| GET | `/api/projects/{pid}` | required | member |
| PATCH | `/api/projects/{pid}` | required | member |
| DELETE | `/api/projects/{pid}` | required | owner |
| GET | `/api/projects/{pid}/bom` | required | member |
| GET | `/api/projects/{pid}/export` | required | member |
| POST | `/api/projects/{pid}/thumbnail` | required | member |
| GET | `/api/projects/{pid}/cover` | required | member |

**POST /api/projects body**

```json
{
  "workspace_id": "uuid",
  "name": "My Part",
  "description": "",
  "tags": ["mech", "prototype"],
  "starter": "jscad"
}
```

`starter` accepts `"jscad"` (seeds a default `.jscad` script), `"circuit"`, or
`"blank"`.

**GET /api/projects — query params**

- `workspace_id` or `workspace_slug` — filter to one workspace
- `tag` — filter by tag (array-contains)

**GET /api/projects/{pid}/bom response**

```json
{
  "rows": [
    {
      "part": { "name": "M3×10 cap screw", "mpn": "…", "distributors": [] },
      "file_id": "uuid",
      "path": "/hardware/m3_cap_screw.part",
      "count": 12,
      "unit_price_usd": 0.08,
      "total_price_usd": 0.96
    }
  ],
  "total_price_usd": 4.20,
  "warnings": []
}
```

---

## Files

Files are the leaf nodes of the project tree. A `folder` is a file with
`kind='folder'` and no content. Files are soft-deleted (`deleted_at`); bytes
are retained until a purge pass.

| Method | Path | Auth | Min role |
|--------|------|------|----------|
| GET | `/api/projects/{pid}/files` | required | member |
| POST | `/api/projects/{pid}/files` | required | member |
| GET | `/api/projects/{pid}/files/{fid}` | required | member |
| PATCH | `/api/projects/{pid}/files/{fid}` | required | member |
| DELETE | `/api/projects/{pid}/files/{fid}` | required | member |
| GET | `/api/projects/{pid}/files/{fid}/download` | required | member |

Valid kinds for POST: `file`, `folder`, `assembly`, `drawing`, `sketch`,
`part`, `feature`, `circuit`, `equations`, `script`, `fem`, `cam`.

**File object (list response)**

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "parent_id": null,
  "name": "bracket.feature",
  "kind": "feature",
  "extension": null,
  "storage_key": null,
  "download_url": null,
  "tessellation_status": null,
  "created_at": "…",
  "updated_at": "…"
}
```

---

## Async jobs (FEM, CAM, simulation, tessellation)

All heavy compute runs as an async job. Submit → poll for status.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/projects/{pid}/files/{fid}/tessellate` | Queue STEP → glTF tessellation |
| DELETE | `/api/projects/{pid}/files/{fid}/tessellate` | Re-queue (purge cached mesh) |
| POST | `/api/projects/{pid}/files/{fid}/fem` | Submit FEA job |
| GET | `/api/projects/{pid}/files/{fid}/fem/status` | Poll FEA: `queued` / `running` / `done` / `error` |
| POST | `/api/projects/{pid}/files/{fid}/cam` | Submit CAM job |
| GET | `/api/projects/{pid}/files/{fid}/cam/status` | Poll CAM |
| POST | `/api/projects/{pid}/files/{fid}/sim` | Submit dynamics simulation |
| GET | `/api/projects/{pid}/files/{fid}/sim/status` | Poll simulation |

**Status response**

```json
{ "job_id": "uuid", "status": "done", "result": { … }, "error": null }
```

---

## Assembly, tolerance, derived artifacts

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/projects/{pid}/files/{fid}/solve-mates` | Solve assembly mate constraints. Body: `{ "fixed_component_id": "uuid" }` |
| POST | `/api/projects/{pid}/files/{fid}/tolerance/run` | Run tolerance stack-up. Body: `{ "method": "monte_carlo", "samples": 10000, "rss_k": 3.0 }` |
| POST | `/api/projects/{pid}/files/{fid}/derived` | Compute or fetch a derived artifact (thumbnail, glTF, PDF) |
| POST | `/api/projects/{pid}/files/{fid}/derived/store` | Store a derived artifact key |
| DELETE | `/api/projects/{pid}/files/{fid}/derived` | Purge derived artifact |
| GET | `/api/projects/{pid}/files/{fid}/diff` | Diff two revisions of a file |

---

## Uploads (chunked)

Large binary files (STEP, renders) use a chunked upload protocol.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/projects/{pid}/uploads` | Initiate; returns `upload_id` |
| PUT | `/api/projects/{pid}/uploads/{uid}/chunks/{n}` | Upload chunk `n` |
| GET | `/api/projects/{pid}/uploads/{uid}` | Check upload status |
| POST | `/api/projects/{pid}/uploads/{uid}/finalize` | Finalize and create file record |
| DELETE | `/api/projects/{pid}/uploads/{uid}` | Abort upload |

---

## Chat threads and messages

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/projects/{pid}/threads` | required | List threads for project |
| POST | `/api/projects/{pid}/threads` | required | Create thread |
| PATCH | `/api/projects/{pid}/threads/{tid}` | required | Update title / model |
| DELETE | `/api/projects/{pid}/threads/{tid}` | required | Delete thread |
| GET | `/api/projects/{pid}/threads/{tid}/messages` | required | List messages |
| POST | `/api/projects/{pid}/threads/{tid}/messages` | member+ | Send message and run agent loop |

**POST message body**

```json
{
  "content": "Make the boss 6 mm tall",
  "model": "claude-sonnet-4-20250514",
  "part_refs": []
}
```

**POST message response**

```json
{
  "user_message": { "id": "uuid", "role": "user", "content": "…" },
  "assistant_message": { "id": "uuid", "role": "assistant", "content": "Done — I updated the pad depth to 6 mm." },
  "tool_messages": [
    { "id": "uuid", "role": "tool", "content": "{\"ok\":true}" }
  ]
}
```

The agent loop runs up to 10 tool-call iterations inside the single HTTP
request. Viewer role cannot post messages.

---

## Revisions (undo history)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/projects/{pid}/files/{fid}/revisions` | List revisions. Query: `limit` (max 200) |
| GET | `/api/projects/{pid}/files/{fid}/revisions/{rid}` | Get one revision metadata |
| GET | `/api/projects/{pid}/files/{fid}/revisions/{rid}/content` | Get revision full content |
| POST | `/api/projects/{pid}/files/{fid}/revisions/{rid}/restore` | Restore file to this revision |

**Revision object**

```json
{
  "id": "uuid",
  "file_id": "uuid",
  "source": "llm",
  "user_id": "uuid",
  "user_name": "Jane",
  "content_preview": "{ \"version\": 3, \"features\": [ …",
  "created_at": "…"
}
```

`source` is `user` | `llm` | `tool` | `restore`.

---

## Sharing and members

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/projects/{pid}/share/links` | Create share link |
| GET | `/api/projects/{pid}/share/links` | List share links |
| DELETE | `/api/projects/{pid}/share/links/{lid}` | Revoke share link |
| GET | `/api/share/{token}` | Look up share link metadata (no auth) |
| POST | `/api/share/{token}/accept` | Accept share link (auth required) |
| GET | `/api/projects/{pid}/members` | List members |
| POST | `/api/projects/{pid}/members` | Add member by email |
| PATCH | `/api/projects/{pid}/members/{uid}` | Change member role |
| DELETE | `/api/projects/{pid}/members/{uid}` | Remove member |

---

## Imports

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/projects/{pid}/imports/kicad` | Import a KiCad `.kicad_pcb` file. Multipart form. |
| POST | `/api/projects/{pid}/files/{fid}/distributors/refresh` | Re-fetch distributor pricing for a `.part` file |

---

## Workshop (cloud)

Public project gallery. Requires `cloud_enabled`.

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/workshop/` | optional |
| GET | `/api/workshop/parts` | optional |
| GET | `/api/workshop/{slug}` | optional |
| POST | `/api/workshop/publish` | required |
| POST | `/api/workshop/regenerate-readme` | required |
| DELETE | `/api/workshop/{slug}` | required |
| POST | `/api/workshop/{slug}/like` | required |
| POST | `/api/workshop/{slug}/fork` | required |

---

## Library (parts catalog)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/library/parts` | Search community parts. Query: `q`, `page`, `per_page` |
| GET | `/api/library/parts/{slug}` | Get one part |
| POST | `/api/library/submissions` | Submit a new part |
| GET | `/api/admin/library/submissions` | Admin: list pending submissions |
| PUT | `/api/admin/library/submissions/{id}` | Admin: approve / reject |

---

## Blobs

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/blobs/{path}` | Fetch a storage blob by key. Returns bytes (local backend) or 302 to presigned URL (S3). Requires auth on the project that owns the blob. |

---

## Admin (distributor + publisher management)

| Method | Path | Min role |
|--------|------|----------|
| GET | `/api/admin/distributors` | system |
| PUT | `/api/admin/distributors/{name}` | system |
| DELETE | `/api/admin/distributors/{name}` | system |
| GET | `/api/admin/publishers` | system |
| PUT | `/api/admin/publishers/{user_id}` | system |

---

## Health and capabilities

Mounted by `kerf-core`, not `kerf-api`.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/health/capabilities` | Union of all loaded plugin `provides` lists + per-plugin metadata |

---

## Status codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created |
| 204 | No content (DELETE success) |
| 400 | Bad request — malformed input, validation failure |
| 401 | Unauthenticated — missing or expired token |
| 403 | Forbidden — authenticated but insufficient role |
| 404 | Not found (also returned instead of 403 on resource isolation) |
| 409 | Conflict — slug collision, duplicate entry |
| 410 | Gone — share link exhausted |
| 500 | Unexpected server error |

Tool-call errors inside the agent loop never return 500 — they return
`{"error": "…", "code": "…"}` JSON that the LLM can inspect.

---

See also: [data-model.md](./data-model.md) · [v1-rpc.md](./v1-rpc.md) · [architecture.md](./architecture.md)
