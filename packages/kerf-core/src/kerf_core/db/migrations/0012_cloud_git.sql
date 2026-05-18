-- 0012_cloud_git.sql
-- Clean baseline DDL for the cloud-git substrate (T-125).
--
-- The live cloud-git commit handler (POST /projects/{pid}/git/commit) and
-- the fork endpoint in kerf-cloud read/write these tables, but they had no
-- migration in-tree — the prior handler wrote a synthetic sha and never
-- built a tree, so the gap was invisible until T-125 wired the real
-- materialize_and_commit path. Folded in here as clean baseline DDL.
--
-- cloud_git_repos:    one row per project — the bare repo's default branch,
--                     current head sha, and optional GitHub mirror config.
-- cloud_git_branches: per-project branch heads (PK project_id+name).
-- cloud_git_commits:  append-only log of deliberate commits (the sha always
--                     resolves to a real commit in the project's bare repo;
--                     written AFTER the git commit + blob ledger succeed).

CREATE TABLE IF NOT EXISTS cloud_git_repos (
    project_id        uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    default_branch    text NOT NULL DEFAULT 'main',
    head_sha          text NOT NULL DEFAULT '',
    github_remote_url text,
    github_owner      text,
    github_repo       text,
    last_pushed_at    timestamptz,
    last_fetched_at   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    gitlab_host       text,
    gitlab_namespace  text,
    gitlab_project    text
);

CREATE TABLE IF NOT EXISTS cloud_git_branches (
    project_id uuid    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       text    NOT NULL,
    head_sha   text    NOT NULL DEFAULT '',
    is_default boolean NOT NULL DEFAULT false,
    PRIMARY KEY (project_id, name)
);

CREATE TABLE IF NOT EXISTS cloud_git_commits (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sha          text NOT NULL,
    message      text NOT NULL,
    author_name  text NOT NULL DEFAULT '',
    author_email text NOT NULL DEFAULT '',
    branch       text NOT NULL DEFAULT 'main',
    parent_shas  text[] NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cloud_git_commits_project_created_idx
    ON cloud_git_commits (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS cloud_git_commits_project_sha_idx
    ON cloud_git_commits (project_id, sha);
