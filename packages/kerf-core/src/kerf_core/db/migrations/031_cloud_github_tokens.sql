CREATE TABLE IF NOT EXISTS cloud_github_tokens (
    user_id         uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token_encrypted bytea NOT NULL,
    scope           text NOT NULL DEFAULT '',
    github_user_id  bigint,
    github_login    text NOT NULL DEFAULT '',
    updated_at      timestamptz NOT NULL DEFAULT now()
);
