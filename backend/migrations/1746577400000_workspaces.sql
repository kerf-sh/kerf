-- Workspaces (orgs) — multi-member containers above projects.
--
-- Aggressive migration: this drops project_members and projects.owner_id,
-- replacing them with workspace_members + projects.workspace_id. The user has
-- explicitly waived data preservation; if you have local data and want to keep
-- it, run `migrate --reset` instead.

create table if not exists workspaces (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    avatar_storage_key text,
    created_by uuid not null references users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists workspaces_slug_idx on workspaces(slug);

create table if not exists workspace_members (
    workspace_id uuid not null references workspaces(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    role text not null check (role in ('owner','admin','member')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);
create index if not exists workspace_members_user_idx on workspace_members(user_id);

create table if not exists workspace_invites (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    email citext not null,
    role text not null check (role in ('owner','admin','member')),
    token text unique not null,
    created_by uuid not null references users(id) on delete cascade,
    created_at timestamptz not null default now()
);
create index if not exists workspace_invites_workspace_idx on workspace_invites(workspace_id);
create index if not exists workspace_invites_email_idx on workspace_invites(email);

-- Fold project ownership into workspaces. Drop project_members; add
-- projects.workspace_id (NOT NULL after backfill / wipe).
drop table if exists project_members;

alter table projects add column if not exists workspace_id uuid references workspaces(id) on delete cascade;
alter table projects drop column if exists owner_id;
-- Wipe any orphaned projects (no workspace_id yet) so we can NOT NULL it.
delete from projects where workspace_id is null;
alter table projects alter column workspace_id set not null;
create index if not exists projects_workspace_id_idx on projects(workspace_id);
