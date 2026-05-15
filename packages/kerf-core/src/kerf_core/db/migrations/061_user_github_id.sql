-- Add github_id to users for GitHub Sign-In (login/signup).
-- Distinct from cloud_github_tokens (repo-connect OAuth tokens).
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id text;
CREATE UNIQUE INDEX IF NOT EXISTS users_github_id_unique ON users (github_id) WHERE github_id IS NOT NULL;
