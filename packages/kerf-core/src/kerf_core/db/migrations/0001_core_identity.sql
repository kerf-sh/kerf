-- 0001_core_identity.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 001_init.sql ════════════

-- Kerf initial schema.
-- Generated for backend bootstrap.

create extension if not exists "pgcrypto";
create extension if not exists "citext";

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email citext unique not null,
    password_hash text,
    google_id text unique,
    name text not null default '',
    avatar_url text not null default '',
    account_role text not null default 'user' check (account_role in ('user','admin','system')),
    is_system boolean not null default false,
    email_verified boolean not null default false,
    created_at timestamptz not null default now()
);
create index if not exists users_account_role_idx on users(account_role);

create table if not exists refresh_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token_hash text unique not null,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists refresh_tokens_user_id_idx on refresh_tokens(user_id);

-- Single-use, expiring tokens for email verification and password
-- reset. token_hash stores sha256(token); the raw token only ever
-- lives in the emailed link. used_at marks consumption (single use).
create table if not exists email_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    kind text not null check (kind in ('verify','reset')),
    token_hash text unique not null,
    expires_at timestamptz not null,
    used_at timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists email_tokens_user_id_idx on email_tokens(user_id);
create index if not exists email_tokens_token_hash_idx on email_tokens(token_hash);

create table if not exists projects (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    name text not null,
    description text not null default '',
    visibility text not null default 'private' check (visibility in ('private','unlisted','public')),
    -- Workshop fork lineage: which public project this was forked from
    -- (null = original). on delete set null so deleting the source
    -- never cascade-deletes its forks.
    forked_from_project_id uuid references projects(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists projects_workspace_id_idx on projects(workspace_id);
create index if not exists projects_forked_from_idx on projects(forked_from_project_id);

create table if not exists share_links (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    token text unique not null,
    role text not null check (role in ('editor','viewer')),
    expires_at timestamptz,
    revoked_at timestamptz,
    max_uses int,
    uses int not null default 0,
    created_by uuid not null references users(id) on delete cascade,
    created_at timestamptz not null default now()
);
create index if not exists share_links_project_id_idx on share_links(project_id);

create table if not exists files (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    parent_id uuid references files(id) on delete cascade,
    name text not null,
    kind text not null default 'file' check (kind in ('file','folder','assembly','step','drawing','sketch')),
    content text not null default '',
    storage_key text,
    mime_type text,
    size bigint,
    deleted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists files_project_id_idx on files(project_id);
create index if not exists files_parent_id_idx on files(parent_id);
create index if not exists files_storage_key_idx on files(storage_key);
create index if not exists files_deleted_at_idx on files(deleted_at);

create table if not exists file_revisions (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    content text not null,
    source text not null check (source in ('user','llm','tool','restore')),
    user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);
create index if not exists file_revisions_file_id_created_at_idx on file_revisions(file_id, created_at desc);

create table if not exists chat_threads (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    file_id uuid references files(id) on delete set null,
    title text not null default '',
    is_starred boolean not null default false,
    last_message_at timestamptz,
    model text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists chat_threads_project_id_idx on chat_threads(project_id);
create index if not exists chat_threads_file_id_idx on chat_threads(file_id);

create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    thread_id uuid not null references chat_threads(id) on delete cascade,
    role text not null check (role in ('user','assistant','system','tool')),
    content text not null default '',
    part_refs jsonb not null default '[]'::jsonb,
    tool_calls jsonb not null default '[]'::jsonb,
    tool_call_id text,
    model text,
    created_at timestamptz not null default now()
);
create index if not exists chat_messages_thread_id_idx on chat_messages(thread_id);

-- ════════════ folded: files_kind_check (29 kind migrations collapsed) ════════════

-- ── files.kind: final enumeration ──
-- Collapsed from 29 incremental kind migrations (010,011,012,019,021,023,
-- 026,033-046,053,054,056-061_kind_wiring). The authoritative set is the
-- last one that shipped (061_kind_wiring). The abandoned interim kinds
-- (family,stair,railing,curtain_wall,graph,draft) were already removed from
-- the lineage before the final constraint and are intentionally absent.
alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','duct','pipe','conduit','subd','mesh','render','section','cam_layered','tool','plc_st','plc_ld','quadmesh','print','gem','wiring','firmware','mold','pid','optics','layup','dental')
);

-- ════════════ folded: 002_files_soft_delete_and_revisions.sql ════════════

-- Backfills the soft-delete column and revision history table for DBs that
-- ran the original init migration before either was added. Idempotent:
-- "if not exists" everywhere so re-running on an up-to-date DB is a no-op.

alter table files
    add column if not exists deleted_at timestamptz;
create index if not exists files_deleted_at_idx on files(deleted_at);

create table if not exists file_revisions (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    content text not null,
    source text not null check (source in ('user','llm','tool','restore')),
    user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);
create index if not exists file_revisions_file_id_created_at_idx
    on file_revisions(file_id, created_at desc);

-- ════════════ folded: 003_workspaces.sql ════════════

-- Workspaces (orgs) — multi-member containers above projects.

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

alter table projects add column if not exists workspace_id uuid references workspaces(id) on delete cascade;
alter table projects drop column if exists owner_id;
delete from projects where workspace_id is null;
alter table projects alter column workspace_id set not null;
create index if not exists projects_workspace_id_idx on projects(workspace_id);

-- ════════════ folded: dental_cases (T-171) ════════════
-- The kerf-dental package needs a per-case anatomy / treatment record
-- attached to a project. Folded into the kerf-core baseline per the
-- clean-baseline rule (no package-local migrations on the shared DB).
create table if not exists dental_cases (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects(id) on delete cascade,
    patient_ref text not null default '',
    tooth_ids   text[] not null default '{}',
    treatment   text not null default 'crown'
        check (treatment in ('crown', 'aligner', 'guide', 'bridge', 'veneer', 'inlay')),
    notes       text not null default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists dental_cases_project_id_idx
    on dental_cases(project_id);
create index if not exists dental_cases_treatment_idx
    on dental_cases(treatment);
