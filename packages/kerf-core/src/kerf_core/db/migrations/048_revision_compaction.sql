-- Phase 4: revision DB efficiency — compaction improvements.
--
-- 1. content_codec column: 'plain' | 'gzip'
--    When present, signals that content_gz stores raw bytea compressed
--    content rather than the legacy base64-encoded-string-in-text field.
--    Existing rows (NULL / 'plain') are treated as the old encoding path.
--
-- 2. content_sha256 gets a NOT NULL constraint eventually, but for now
--    we just ensure the index exists for dedup lookups.
--
-- All changes are purely additive — no destructive alterations.

alter table file_revisions
    add column if not exists content_codec text not null default 'plain'
        check (content_codec in ('plain', 'gzip'));

-- Index for fast dedup look-up: "does this file already have a revision
-- with this exact sha256?" Used by write_revision to skip identical saves.
create index if not exists file_revisions_file_sha256_idx
    on file_revisions(file_id, content_sha256)
    where content_sha256 is not null;

-- Index used by safe pruning: given a file, find the oldest revision whose
-- id does NOT appear as anyone's parent_revision_id.
create index if not exists file_revisions_parent_revision_id_idx
    on file_revisions(parent_revision_id)
    where parent_revision_id is not null;
