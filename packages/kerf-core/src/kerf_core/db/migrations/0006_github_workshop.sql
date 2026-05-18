-- 0006_github_workshop.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 031_cloud_github_tokens.sql ════════════

CREATE TABLE IF NOT EXISTS cloud_github_tokens (
    user_id         uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token_encrypted bytea NOT NULL,
    scope           text NOT NULL DEFAULT '',
    github_user_id  bigint,
    github_login    text NOT NULL DEFAULT '',
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ════════════ folded: 032_workshop_likes.sql ════════════

-- Workshop likes: lightweight toggle table for workshop project likes.
CREATE TABLE IF NOT EXISTS workshop_likes (
    user_id    UUID NOT NULL,
    project_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, project_id)
);

CREATE INDEX IF NOT EXISTS workshop_likes_project_id_idx ON workshop_likes (project_id);
