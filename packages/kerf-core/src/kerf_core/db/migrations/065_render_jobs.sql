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
