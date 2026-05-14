# Workspaces and members

A **workspace** is the multi-member container above projects: every
project belongs to exactly one workspace, and every collaborator
joins through `workspace_members`. Workspaces also own the billing
attachment (cloud only — see `email.md` and the cloud billing
module). Created in migration
`1746577400000_workspaces.sql` which folded `project_members` into
`workspace_members` and replaced `projects.owner_id` with
`projects.workspace_id`.

If the user asks "who has access to this project" or "where do I
invite someone", the answer is always the **workspace**, never the
project — there's no per-project ACL anymore.

## `workspaces` table

```sql
workspaces (
  id          uuid pk,
  slug        text unique,           -- URL-safe; '/w/<slug>/...' routes
  name        text,                  -- display name
  avatar_storage_key text,           -- S3 / localfs key (POST /avatar)
  created_by  uuid → users(id),
  created_at  timestamptz,
  updated_at  timestamptz
)
```

The `slug` is the user-visible identifier. All workspace-scoped
routes are keyed off it: `/w/<slug>/projects`,
`/w/<slug>/settings`, `/w/<slug>/members`. The slug must be unique
across the install. Renaming the slug breaks bookmarks — the
Settings panel disables it after creation.

## `workspace_members` table

```sql
workspace_members (
  workspace_id  uuid → workspaces(id) on delete cascade,
  user_id       uuid → users(id) on delete cascade,
  role          text check (role in ('owner', 'admin', 'member')),
  created_at    timestamptz,
  primary key (workspace_id, user_id)
)
```

Three roles:

| Role     | Can do                                                                |
|----------|-----------------------------------------------------------------------|
| `owner`  | Everything `admin` can + delete the workspace + change billing        |
| `admin`  | Everything `member` can + invite/remove members + edit workspace meta |
| `member` | Read/write all projects in the workspace                              |

There's always at least one `owner` (the `created_by` user is
seeded as owner on workspace create). Demoting the last owner is
rejected by the API.

## `workspace_invites` table

Out-of-band invites for users who don't yet have an account. Each
row carries an email, a target role, and a one-shot token. When the
invitee accepts, a `workspace_members` row is created and the
invite is deleted. There's no doc tool for invites — it's a
backend-only flow driven by the Members panel.

## Routes

```
/w/:workspaceSlug/projects   — project list (Projects.jsx)
/w/:workspaceSlug/settings   — workspace meta + avatar (WorkspaceSettings.jsx)
/w/:workspaceSlug/members    — invite / remove / change role (WorkspaceMembers.jsx)
```

Inside a project the URL is
`/p/:projectId/...` — projects do **not** carry the workspace slug
in the URL because the project row holds the `workspace_id`
directly. The Layout component derives the active workspace from
the project on those routes.

## API summary

```
GET    /api/workspaces                            — list mine
POST   /api/workspaces                            — create   { name, slug }
GET    /api/workspaces/:slug                      — fetch one
PATCH  /api/workspaces/:slug                      — { name?, slug? }
DELETE /api/workspaces/:slug                      — owner-only
POST   /api/workspaces/:slug/avatar               — multipart upload
POST   /api/workspaces/:slug/members              — { email, role } → invite
DELETE /api/workspaces/:slug/members/:userId      — remove
PATCH  /api/workspaces/:slug/members/:userId      — { role } → promote/demote
```

The `lib/api.js` wrappers (`listWorkspaces`,
`inviteWorkspaceMember`, `changeWorkspaceMemberRole`, …) are the
canonical client surface.

## Stores — a confusing pair

There are **two** zustand stores with overlapping names. Don't
confuse them:

- `src/store/workspaces.js` — the **workspaces list** store
  (`useWorkspaces`). Holds the user's full workspace list and the
  active `currentSlug` (persisted to `localStorage` under
  `kerf:currentWorkspaceSlug`). Used by the WorkspaceSwitcher and
  the Projects route.

- `src/store/workspace.js` — the **editor-side workspace** store
  (`useWorkspace`). Holds the *currently open project's* in-editor
  state: the open file, dirty bytes, feature selection, viewport
  camera, history, etc. Has nothing to do with the workspaces
  table — it's named for "the user's open editor workspace" in the
  general sense.

When the LLM needs to "find which workspace a project belongs to",
the answer is on the project row (`workspace_id`), not in either
store. From the API, `GET /api/projects/:id` returns the project
JSON which includes the resolved workspace slug.

## Project ownership

Every `projects` row carries `workspace_id` (NOT NULL). When the
user asks "move this project to another workspace", that's a
backend mutation on `projects.workspace_id` — there's no LLM tool
for it today (the user does it via the Settings UI). The Layout
component looks up `workspace_id → slug` to render the breadcrumb.

## Billing attachment (cloud only)

In the cloud build, billing is attached **per workspace**, not per
user or per project: a single Stripe customer maps to one workspace
row, and storage charges (the `$0.20/GB-month` line) bill the
workspace. The OSS build leaves the cloud billing tables empty —
storage is whatever Postgres + your disk allow.

## Examples

### "Invite jane@example.com to my acme workspace as admin"

```
POST /api/workspaces/acme/members
{ "email": "jane@example.com", "role": "admin" }
```

Or via the JS wrapper:

```js
api.inviteWorkspaceMember('acme', 'jane@example.com', 'admin')
```

If Jane already has an account, she's added directly to
`workspace_members`. Otherwise a `workspace_invites` row is
created and an invite email is sent (cloud only).

### "Which workspace does project X belong to?"

```js
const proj = await api.getProject(projectId)
proj.workspace_slug   // → 'acme'
```

Or directly from the database side: the `projects.workspace_id`
column is the source of truth.

### "Demote a user from admin to member"

```
PATCH /api/workspaces/acme/members/<userId>
{ "role": "member" }
```

The API rejects demoting the last owner.

## Known limits

- **No transfer-project tool.** Moving a project between workspaces
  is UI-only today; the LLM can't do it via tools.
- **Slug is final after creation.** The Settings panel disables
  slug editing once the workspace exists; rename = create new +
  manual move.
- **OSS = single workspace recommended.** The OSS build supports
  multiple workspaces, but the install model assumes one shop /
  one team. Billing attachment is a no-op on OSS.
- **Invite emails are cloud-only.** OSS installs accept invites via
  copy-paste of the invite link from the Members panel.
