-- Phase 4: diff-based + compressed revisions.

alter table file_revisions
    add column if not exists kind text not null default 'base'
        check (kind in ('base', 'diff'));

alter table file_revisions
    add column if not exists content_gz bytea;

alter table file_revisions
    add column if not exists parent_revision_id uuid
        references file_revisions(id) on delete set null;

alter table file_revisions
    add column if not exists content_preview text;

create index if not exists file_revisions_file_id_kind_idx
    on file_revisions(file_id, kind);
