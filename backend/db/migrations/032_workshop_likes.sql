-- Workshop likes: lightweight toggle table for workshop project likes.
CREATE TABLE IF NOT EXISTS workshop_likes (
    user_id    UUID NOT NULL,
    project_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, project_id)
);

CREATE INDEX IF NOT EXISTS workshop_likes_project_id_idx ON workshop_likes (project_id);
