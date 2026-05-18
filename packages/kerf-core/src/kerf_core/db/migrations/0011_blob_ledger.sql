-- 0011_blob_ledger.sql
-- Clean baseline DDL for the oid ref-count ledger (T-134).
--
-- blob_objects: one row per unique content-addressed blob (oid = hex SHA256 or
--   similar digest).  first_workspace_id records which workspace first uploaded
--   this oid (dedup billing: first uploader bears the size; forks pay 0).
--
-- blob_refs: one row per (oid, project, path) tuple that references a blob.
--   Dropping the last ref signals GC eligibility (T-136).  The primary key
--   (oid, project_id, path) ensures add_ref is idempotent via ON CONFLICT.

CREATE TABLE IF NOT EXISTS blob_objects (
    oid                 text        PRIMARY KEY,
    size_bytes          bigint      NOT NULL,
    first_workspace_id  uuid        REFERENCES workspaces(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS blob_objects_first_workspace_id_idx
    ON blob_objects (first_workspace_id);

CREATE TABLE IF NOT EXISTS blob_refs (
    oid         text        NOT NULL REFERENCES blob_objects(oid) ON DELETE CASCADE,
    project_id  uuid        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path        text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (oid, project_id, path)
);

CREATE INDEX IF NOT EXISTS blob_refs_project_id_idx ON blob_refs (project_id);
CREATE INDEX IF NOT EXISTS blob_refs_oid_idx        ON blob_refs (oid);
