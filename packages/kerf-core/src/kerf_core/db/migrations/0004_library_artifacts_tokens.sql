-- 0004_library_artifacts_tokens.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 020_library_submissions.sql ════════════

-- Library Phase 3 — manufacturer-PR submission queue.

create table if not exists library_part_submissions (
    id uuid primary key default gen_random_uuid(),
    submitter_user_id uuid not null references users(id) on delete cascade,
    target_workspace_id uuid not null references workspaces(id) on delete cascade,
    payload jsonb not null,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected')),
    review_note text not null default '',
    reviewer_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists library_part_submissions_status_idx
    on library_part_submissions(status);
create index if not exists library_part_submissions_submitter_idx
    on library_part_submissions(submitter_user_id);
create index if not exists library_part_submissions_target_idx
    on library_part_submissions(target_workspace_id);

-- ════════════ folded: 022_step_tessellation_jobs.sql ════════════

-- Performance Phase 3: server-side STEP pre-tessellation.

create table if not exists step_tessellation_jobs (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    status text not null default 'queued'
        check (status in ('queued','running','done','error')),
    error text,
    mesh_storage_key text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists step_tessellation_jobs_status_idx
    on step_tessellation_jobs(status, created_at)
    where status in ('queued','running');

create unique index if not exists step_tessellation_jobs_file_id_unique
    on step_tessellation_jobs(file_id);

alter table files add column if not exists mesh_storage_key text;

-- ════════════ folded: 024_derived_artifacts.sql ════════════

-- Cross-project derived-artifact cache.

create table if not exists derived_artifacts (
    id uuid primary key default gen_random_uuid(),
    source_file_id uuid not null references files(id) on delete cascade,
    content_sha256 text not null,
    derived_kind text not null
        check (derived_kind in ('jscad_mesh', 'sketch_geom2', 'circuit_board_3d')),
    payload bytea not null,
    payload_size_bytes int not null default 0,
    created_at timestamptz not null default now(),
    last_accessed_at timestamptz not null default now()
);

create unique index if not exists derived_artifacts_key_idx
    on derived_artifacts(source_file_id, content_sha256, derived_kind);
create index if not exists derived_artifacts_lru_idx
    on derived_artifacts(last_accessed_at);

-- ════════════ folded: 025_api_tokens.sql ════════════

-- API tokens for kerf-sdk auth (workspace-scoped).

create table if not exists api_tokens (
    id          uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    user_id     uuid not null references users(id) on delete cascade,
    token_hash  text unique not null,
    name        text not null,
    scopes      jsonb not null default '["workspace:member-role"]',
    last_used_at timestamptz,
    revoked_at  timestamptz,
    created_at  timestamptz not null default now()
);
create index if not exists api_tokens_workspace_idx on api_tokens(workspace_id);
create index if not exists api_tokens_user_idx on api_tokens(user_id);
create index if not exists api_tokens_token_hash_idx on api_tokens(token_hash);
