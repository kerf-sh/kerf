-- Phase 4: diff-based + compressed revisions.
--
-- Base rows store the full content; non-base rows store a diff (delta)
-- against their parent revision. Reads walk forward from the nearest
-- base. Both storage shapes are gzipped to bytea, so even base rows
-- shrink ~3-5x on typical text payloads.
--
-- The legacy `content` column stays in place. Old rows that pre-date
-- this migration still read from it (kind defaults to 'base', content_gz
-- is NULL → reader falls back to the plaintext column). New writes go
-- to content_gz. A one-shot backfill at backend/cmd/migrate-revisions
-- can populate content_gz for old rows; it is intentionally NOT run on
-- server boot.

alter table file_revisions
    add column if not exists kind text not null default 'base'
        check (kind in ('base', 'diff'));

alter table file_revisions
    add column if not exists content_gz bytea;

alter table file_revisions
    add column if not exists parent_revision_id uuid
        references file_revisions(id) on delete set null;

-- A short (≤200 chars) UTF-8 preview kept on every row regardless of
-- base/diff so ListRevisions stays O(1) per row without reconstructing.
alter table file_revisions
    add column if not exists content_preview text;

create index if not exists file_revisions_file_id_kind_idx
    on file_revisions(file_id, kind);
