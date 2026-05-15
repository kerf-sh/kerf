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
