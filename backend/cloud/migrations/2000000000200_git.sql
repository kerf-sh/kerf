-- Cloud-only git integration. Real version control on top of the live
-- editor: a deliberate "save this version" feature, distinct from the
-- always-on file_revisions undo layer (which stays untouched).
--
-- The bare repo on disk (under cfg.Cloud.Git.Root) is the canonical
-- store for git objects. These tables are caches/metadata for the
-- graph view and a per-user GitHub OAuth token store.

-- One repo row per project that has git enabled. The bare repo lives
-- on disk at <root>/<project_id>.git. github_* fields are populated
-- only after a successful /import or /connect.
create table if not exists cloud_git_repos (
    project_id uuid primary key references projects(id) on delete cascade,
    default_branch text not null default 'main',
    github_owner text,
    github_repo text,
    github_remote_url text,
    last_pushed_at timestamptz,
    last_fetched_at timestamptz,
    created_at timestamptz not null default now()
);

-- Branch list, refreshed from the bare repo whenever a mutating op
-- (commit / branch / merge / pull) runs. The bare repo remains
-- canonical; this is purely an index for the graph view.
create table if not exists cloud_git_branches (
    project_id uuid not null references cloud_git_repos(project_id) on delete cascade,
    name text not null,
    head_sha text not null,
    is_default boolean not null default false,
    updated_at timestamptz not null default now(),
    primary key (project_id, name)
);

-- Commit cache. Same caveat as cloud_git_branches: refreshed best-effort
-- on every mutating op. The bare repo is the source of truth.
create table if not exists cloud_git_commits (
    project_id uuid not null references cloud_git_repos(project_id) on delete cascade,
    sha text not null,
    parent_shas text[] not null default '{}'::text[],
    message text not null,
    author_name text not null,
    author_email text not null,
    committed_at timestamptz not null,
    primary key (project_id, sha)
);
create index if not exists cloud_git_commits_committed_at_idx
    on cloud_git_commits(project_id, committed_at desc);

-- Per-user GitHub OAuth tokens. access_token_encrypted holds the AES-GCM
-- ciphertext (nonce prefix + ciphertext + GCM tag) of the user's bearer
-- token. The encryption key is derived from cfg.JWTSecret via SHA-256.
-- A real KMS-backed key store is out of scope for v1; rotating the JWT
-- secret will invalidate all stored tokens (users re-link).
create table if not exists cloud_github_tokens (
    user_id uuid primary key references users(id) on delete cascade,
    access_token_encrypted bytea not null,
    scope text,
    github_user_id bigint,
    github_login text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
