-- 0010_github_app_render.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 063_github_installation.sql ════════════

-- Migrate GitHub repo-connect from OAuth user tokens to GitHub App installation tokens.
--
-- installation_id: numeric GitHub App installation ID selected by the user when
--   they install the Kerf GitHub App on their account/org. Persisted here so we
--   can mint short-lived installation tokens on demand without re-prompting the user.
--   The actual installation access tokens are NEVER persisted (cached in memory only).
--
-- This column is nullable: rows created before the GitHub App migration have no
-- installation_id. Callers should treat NULL as "not connected via App".
ALTER TABLE cloud_github_tokens
    ADD COLUMN IF NOT EXISTS github_installation_id bigint;

-- ════════════ folded: 064_cloud_github_tokens_repair.sql ════════════

-- Reconcile cloud_github_tokens for the GitHub App repo-connect flow on
-- legacy-built databases where the original 031 migration never applied
-- (its FK to users(id) made the whole statement roll back on the legacy
-- schema, so neither the table nor 063's column landed).
--
-- Self-contained and fully idempotent: no cross-table FK (user_id stays
-- the PRIMARY KEY, which is all the code's ON CONFLICT (user_id) needs).
-- Safe to run on fresh DBs and on partially-migrated ones alike.

CREATE TABLE IF NOT EXISTS cloud_github_tokens (
    user_id                 uuid PRIMARY KEY,
    access_token_encrypted  bytea NOT NULL DEFAULT ''::bytea,
    scope                   text NOT NULL DEFAULT '',
    github_user_id          bigint,
    github_login            text NOT NULL DEFAULT '',
    github_installation_id  bigint,
    updated_at              timestamptz NOT NULL DEFAULT now()
);

-- Backfill columns for DBs where a partial cloud_github_tokens already exists.
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS access_token_encrypted bytea;
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS scope text NOT NULL DEFAULT '';
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS github_user_id bigint;
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS github_login text NOT NULL DEFAULT '';
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS github_installation_id bigint;
ALTER TABLE cloud_github_tokens ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- ════════════ folded: 065_render_jobs.sql ════════════

-- Render job queue for the Blender Cycles worker (T-106b).
--
-- Self-contained and fully idempotent: CREATE IF NOT EXISTS throughout.
-- Safe to run on fresh databases and on already-migrated ones alike.

CREATE TABLE IF NOT EXISTS render_jobs (
    id              uuid PRIMARY KEY,
    user_id         uuid,
    scene_blob_hash text        NOT NULL DEFAULT '',
    preset          text        NOT NULL DEFAULT 'standard',
    status          text        NOT NULL DEFAULT 'queued',
    samples_done    int         NOT NULL DEFAULT 0,
    samples_total   int         NOT NULL DEFAULT 0,
    signed_url      text,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS render_jobs_user_id_idx ON render_jobs (user_id);
CREATE INDEX IF NOT EXISTS render_jobs_status_idx  ON render_jobs (status);
