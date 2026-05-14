-- Backfills the soft-delete column and revision history table for DBs that
-- ran the original init migration before either was added. Idempotent:
-- "if not exists" everywhere so re-running on an up-to-date DB is a no-op.

alter table files
    add column if not exists deleted_at timestamptz;
create index if not exists files_deleted_at_idx on files(deleted_at);

create table if not exists file_revisions (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    content text not null,
    source text not null check (source in ('user','llm','tool','restore')),
    user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);
create index if not exists file_revisions_file_id_created_at_idx
    on file_revisions(file_id, created_at desc);
