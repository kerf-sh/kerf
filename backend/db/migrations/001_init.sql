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

create table if not exists projects (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    name text not null,
    description text not null default '',
    visibility text not null default 'private' check (visibility in ('private','unlisted','public')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists projects_workspace_id_idx on projects(workspace_id);

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
