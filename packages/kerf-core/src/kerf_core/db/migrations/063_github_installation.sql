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
